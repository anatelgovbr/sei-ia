"""Tests for jobs/api_rest/services/embedding_service.py.

embedding_service builds a module-level EmbeddingGenerator() on import — this
is safe (no network I/O at construction, see test_embedding_generator.py) so
the module import itself is not mocked. Individual functions are exercised
with the module-level `embedding_generator` and `get_embeddings_db_connector`
patched per test.
"""

import json
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pandas as pd
import pytest

import jobs.api_rest.services.embedding_service as embedding_service
from jobs.services.embedder.providers.litellm import LiteLLMEmbeddingProvider


def _patch_tiktoken_model_name():
    # tiktoken_model_name is a @property — patch.object on an instance would
    # first read the "original" value via the real getter (triggering a real
    # HTTP call), so it must be patched at the class level with PropertyMock.
    return patch.object(
        LiteLLMEmbeddingProvider,
        "tiktoken_model_name",
        new_callable=PropertyMock,
        return_value="text-embedding-3-small",
    )


class TestSplitChunks:
    def test_splits_text_into_chunks_tiktoken(self):
        with patch.object(
            embedding_service.embedding_generator.provider,
            "tokenizer_type",
            "tiktoken",
        ), _patch_tiktoken_model_name():
            chunks, positions = embedding_service.split_chunks(
                "frase um. frase dois. frase tres.",
                chunk_size=10,
                chunk_overlap=0,
            )

        assert len(chunks) > 0
        assert positions == []

    def test_returns_positions_when_requested(self):
        text = "abc def ghi"
        with patch.object(
            embedding_service.embedding_generator.provider,
            "tokenizer_type",
            "tiktoken",
        ), _patch_tiktoken_model_name():
            chunks, positions = embedding_service.split_chunks(
                text, chunk_size=3, chunk_overlap=0, return_positions=True
            )

        assert len(positions) == len(chunks)
        for chunk, (start, end) in zip(chunks, positions, strict=False):
            assert text[start:end] == chunk


class TestCheckEmbeddingsExist:
    pytestmark = pytest.mark.asyncio

    async def test_maps_existing_and_missing_ids(self):
        fake_connector = MagicMock()
        fake_df = pd.DataFrame({"id_documento": [1, 2]})
        fake_connector.select_async = AsyncMock(return_value=fake_df)

        with patch.object(
            embedding_service,
            "get_embeddings_db_connector",
            return_value=fake_connector,
        ):
            result = await embedding_service.check_embeddings_exist(["1", "2", "3"])

        assert result == {"1": True, "2": True, "3": False}


class TestProcessDocumentForEmbedding:
    def test_appends_chunks_to_pool_file(self, tmp_path):
        req_filepath = tmp_path / "pool_req.jsonl"

        with patch.object(
            embedding_service, "split_chunks", return_value=(["chunk1"], [(0, 6)])
        ), patch.object(
            embedding_service.embedding_generator, "append_pool_file"
        ) as mock_append:
            embedding_service.process_document_for_embedding(
                "doc1", "conteudo", req_filepath
            )

        mock_append.assert_called_once()
        pool_input = mock_append.call_args[0][0]
        assert pool_input.doc_id == "doc1"
        assert pool_input.input_texts == ["chunk1"]


class TestSaveEmbeddingsToDb:
    def test_no_rows_is_noop(self):
        embedding_service.save_embeddings_to_db([])

    def test_inserts_deduplicated_rows(self):
        result_file = [
            {
                "request": {
                    "doc_ids": ["1"],
                    "chunk_ids": [0],
                    "positions": [(0, 5)],
                },
                "response": [[0.1, 0.2]],
            }
        ]

        fake_session = MagicMock()
        fake_connector = MagicMock()
        fake_connector.get_session.return_value = fake_session

        with patch.object(
            embedding_service,
            "get_embeddings_db_connector",
            return_value=fake_connector,
        ):
            embedding_service.save_embeddings_to_db(result_file)

        fake_session.execute.assert_called_once()
        fake_session.commit.assert_called_once()
        fake_session.close.assert_called_once()

    def test_rolls_back_on_sqlalchemy_error(self):
        from sqlalchemy.exc import SQLAlchemyError

        result_file = [
            {
                "request": {
                    "doc_ids": ["1"],
                    "chunk_ids": [0],
                    "positions": [(0, 5)],
                },
                "response": [[0.1]],
            }
        ]

        fake_session = MagicMock()
        fake_session.execute.side_effect = SQLAlchemyError("boom")
        fake_connector = MagicMock()
        fake_connector.get_session.return_value = fake_session

        with patch.object(
            embedding_service,
            "get_embeddings_db_connector",
            return_value=fake_connector,
        ), pytest.raises(RuntimeError):
            embedding_service.save_embeddings_to_db(result_file)

        fake_session.rollback.assert_called_once()
        fake_session.close.assert_called_once()


class TestGenerateEmbeddingsFromPool:
    def test_reads_pool_and_writes_results(self, tmp_path):
        req_filepath = tmp_path / "req.jsonl"
        save_filepath = tmp_path / "save.jsonl"
        req_filepath.write_text(
            json.dumps({"input_texts": ["a", "b"], "doc_ids": ["1", "1"]}) + "\n"
        )

        with patch.object(
            embedding_service.embedding_generator,
            "generate",
            return_value=[[0.1], [0.2]],
        ):
            result = embedding_service.generate_embeddings_from_pool(
                req_filepath, save_filepath
            )

        assert len(result) == 1
        assert result[0]["response"] == [[0.1], [0.2]]
        assert save_filepath.exists()


class TestGenerateEmbeddingsForDocuments:
    pytestmark = pytest.mark.asyncio

    async def test_returns_already_exists_when_all_present(self):
        with patch.object(
            embedding_service,
            "check_embeddings_exist",
            new=AsyncMock(return_value={"1": True}),
        ):
            result = await embedding_service.generate_embeddings_for_documents(["1"])

        assert result["status"] == "already_exists"
        assert result["skipped_ids"] == ["1"]

    async def test_processes_new_documents_end_to_end(self, tmp_path):
        req_filepath = tmp_path / "req.jsonl"
        save_filepath = tmp_path / "save.jsonl"
        req_filepath.touch()
        save_filepath.touch()

        with patch.object(
            embedding_service,
            "check_embeddings_exist",
            new=AsyncMock(return_value={"1": False}),
        ), patch.object(
            embedding_service.embedding_generator,
            "create_temp_files",
            return_value=(req_filepath, save_filepath),
        ), patch(
            "jobs.document_extraction.document_reader.get_document_content",
            new=AsyncMock(return_value="conteudo do documento"),
        ), patch.object(
            embedding_service, "process_document_for_embedding"
        ) as mock_process, patch.object(
            embedding_service,
            "generate_embeddings_from_pool",
            return_value=[
                {"request": {"doc_ids": ["1"]}, "response": [[0.1]]}
            ],
        ), patch.object(
            embedding_service, "save_embeddings_to_db"
        ) as mock_save:
            result = await embedding_service.generate_embeddings_for_documents(["1"])

        assert result["status"] == "processed"
        assert result["processed_count"] == 1
        mock_process.assert_called_once()
        mock_save.assert_called_once()

    async def test_marks_documents_without_content(self, tmp_path):
        req_filepath = tmp_path / "req.jsonl"
        save_filepath = tmp_path / "save.jsonl"
        req_filepath.touch()
        save_filepath.touch()

        with patch.object(
            embedding_service,
            "check_embeddings_exist",
            new=AsyncMock(return_value={"1": False}),
        ), patch.object(
            embedding_service.embedding_generator,
            "create_temp_files",
            return_value=(req_filepath, save_filepath),
        ), patch(
            "jobs.document_extraction.document_reader.get_document_content",
            new=AsyncMock(return_value=""),
        ), patch.object(
            embedding_service, "generate_embeddings_from_pool", return_value=[]
        ), patch.object(embedding_service, "save_embeddings_to_db"):
            result = await embedding_service.generate_embeddings_for_documents(["1"])

        assert result["no_content_ids"] == ["1"]
        assert result["processed_count"] == 0


class TestDeleteEmbeddingsByDocumentIds:
    pytestmark = pytest.mark.asyncio

    async def test_returns_zero_for_empty_input(self):
        assert await embedding_service.delete_embeddings_by_document_ids([]) == 0

    async def test_connects_when_pool_missing_and_deletes(self):
        fake_conn = AsyncMock()
        fake_conn.execute = AsyncMock(return_value="DELETE 3")

        fake_pool = MagicMock()
        fake_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=fake_conn)
        fake_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        fake_connector = MagicMock()
        fake_connector.pool = None
        fake_connector.connect = AsyncMock(
            side_effect=lambda: setattr(fake_connector, "pool", fake_pool)
        )

        with patch.object(
            embedding_service,
            "get_embeddings_db_connector",
            return_value=fake_connector,
        ):
            result = await embedding_service.delete_embeddings_by_document_ids([1, 2])

        assert result == 3
        fake_connector.connect.assert_awaited_once()

    async def test_raises_runtime_error_on_failure(self):
        fake_connector = MagicMock()
        fake_connector.pool = MagicMock()
        fake_connector.pool.acquire.side_effect = RuntimeError("boom")

        with patch.object(
            embedding_service,
            "get_embeddings_db_connector",
            return_value=fake_connector,
        ), pytest.raises(RuntimeError):
            await embedding_service.delete_embeddings_by_document_ids([1])
