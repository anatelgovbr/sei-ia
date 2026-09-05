"""Regressões para entradas vazias no pipeline de embeddings."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from sei_ia.agents import pergunta
from sei_ia.agents.pergunta import auto_indexing
from sei_ia.data.pydantic_models import ItemDocumentRequest
from sei_ia.services.async_llm_requests.api_requests_from_file import (
    APIRequest as LegacyAPIRequest,
)
from sei_ia.services.async_llm_requests.async_requests import (
    APIRequest,
    StatusTracker,
    calculate_token_usage,
)
from sei_ia.services.embedder import pipeline
from sei_ia.services.embedder.embedding_generator import (
    EmbeddingGenerator,
    InputPoolEmbd,
)
from sei_ia.services.embedder.input_validation import (
    ensure_embedding_input,
    first_document_id,
)
from sei_ia.services.embedder.providers.azure import AzureOpenAIEmbeddingProvider
from sei_ia.services.exceptions.embedding_exceptions import (
    AutoIndexingException,
    DocumentContentNotExtractableException,
    EmbeddingInputException,
    EmptyEmbeddingInputException,
)
from sei_ia.services.exceptions.http_exceptions import HTTPException400


def test_embedding_generator_uses_fixed_public_alias(monkeypatch):
    """O roteamento no proxy não pode depender da identidade física da tabela."""
    from sei_ia.configs.settings_config import settings

    monkeypatch.setattr(
        settings, "LITELLM_EMBEDDING_MODEL", "provider/embedding-physical"
    )
    monkeypatch.setattr(settings, "EMBEDDING_ENCODING_NAME", "cl100k_base")

    generator = EmbeddingGenerator()

    assert generator.provider.model == "embedding"
    assert generator.provider.encoding_name == "cl100k_base"
    assert settings.LITELLM_EMBEDDING_MODEL == "provider/embedding-physical"


def test_empty_document_does_not_write_embedding_pool(tmp_path, monkeypatch):
    pool_path = tmp_path / "pool.jsonl"
    pool_path.touch()
    append_pool = MagicMock()
    monkeypatch.setattr(pipeline.embedding_generator, "append_pool_file", append_pool)
    monkeypatch.setattr(pipeline, "split_chunks", lambda *args, **kwargs: ([], []))
    document = ItemDocumentRequest(id_documento="doc-123", content="")

    with pytest.raises(HTTPException) as exc_info:
        pipeline.process_document(document, pool_path)

    assert type(exc_info.value).__name__ == "DocumentContentNotExtractableException"
    assert exc_info.value.document_id == "doc-123"
    assert "conteúdo extraível" in exc_info.value.detail
    append_pool.assert_not_called()
    assert pool_path.read_text() == ""


def test_valid_chunk_keeps_pool_fields_aligned(tmp_path):
    pool_path = tmp_path / "pool.jsonl"
    pool_path.touch()
    tokenizer = MagicMock()
    tokenizer.encode.side_effect = lambda text: list(text)
    generator = EmbeddingGenerator.__new__(EmbeddingGenerator)
    generator.provider = SimpleNamespace(
        get_tokenizer=lambda: tokenizer,
        max_context_size=100,
    )
    pool_input = InputPoolEmbd(
        input_texts=["chunk válido"],
        doc_id="doc-456",
        chunk_ids=[7],
        positions=[(10, 22)],
    )

    generator.append_pool_file(pool_input, pool_path)

    request = json.loads(pool_path.read_text())
    assert request["input_texts"] == ["chunk válido"]
    assert request["doc_ids"] == ["doc-456"]
    assert request["chunk_ids"] == [7]
    assert request["positions"] == [[10, 22]]
    assert (
        len(
            {
                len(request["input_texts"]),
                len(request["doc_ids"]),
                len(request["chunk_ids"]),
                len(request["positions"]),
            }
        )
        == 1
    )


def test_pool_writer_rejects_empty_and_misaligned_inputs(tmp_path):
    pool_path = tmp_path / "pool.jsonl"
    pool_path.touch()
    generator = EmbeddingGenerator.__new__(EmbeddingGenerator)

    with pytest.raises(HTTPException) as empty_error:
        generator.append_pool_file(
            InputPoolEmbd(
                input_texts=[],
                doc_id="doc-empty",
                chunk_ids=[],
                positions=[],
            ),
            pool_path,
        )

    assert type(empty_error.value).__name__ == (
        "DocumentContentNotExtractableException"
    )
    assert pool_path.read_text() == ""

    with pytest.raises(HTTPException) as alignment_error:
        generator.append_pool_file(
            InputPoolEmbd(
                input_texts=["chunk"],
                doc_id="doc-misaligned",
                chunk_ids=[],
                positions=[(0, 5)],
            ),
            pool_path,
        )

    assert type(alignment_error.value).__name__ == "EmbeddingInputException"
    assert "desalinhados" in alignment_error.value.detail
    assert pool_path.read_text() == ""


def test_nonempty_document_without_chunks_is_explicit_error(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "split_chunks", lambda *args, **kwargs: ([], []))
    document = ItemDocumentRequest(id_documento="doc-no-chunks", content="conteúdo")

    with pytest.raises(HTTPException) as exc_info:
        pipeline.process_document(document, tmp_path / "pool.jsonl")

    assert type(exc_info.value).__name__ == "DocumentContentNotExtractableException"


def test_shared_input_validation_covers_valid_and_malformed_shapes():
    ensure_embedding_input("texto")
    ensure_embedding_input(["texto"])
    assert first_document_id({"doc_ids": ["doc-first", "doc-second"]}) == "doc-first"
    assert first_document_id({"doc_ids": []}) is None
    assert first_document_id({"doc_ids": "not-a-list"}) is None

    for invalid_input in ("", ["texto", ""], None):
        with pytest.raises(HTTPException) as exc_info:
            ensure_embedding_input(invalid_input)
        assert type(exc_info.value).__name__ == "EmptyEmbeddingInputException"


def test_generator_and_token_counter_reject_empty_input_before_dependencies():
    generator = EmbeddingGenerator.__new__(EmbeddingGenerator)
    generator.provider = MagicMock()

    with pytest.raises(HTTPException):
        generator.generate([])
    generator.provider.generate_embeddings.assert_not_called()

    with pytest.raises(HTTPException):
        calculate_token_usage(
            {"input_texts": [], "doc_ids": ["doc-token-counter"]},
            "embeddings",
            MagicMock(),
        )


@pytest.mark.asyncio
async def test_async_embedding_request_uses_fixed_public_alias(tmp_path, monkeypatch):
    """O pool assíncrono deve rotear pelo alias, não pelo base_model físico."""
    from sei_ia.configs.settings_config import settings

    monkeypatch.setattr(
        settings, "LITELLM_EMBEDDING_MODEL", "provider/embedding-physical"
    )
    client = MagicMock()
    client.base_url = "https://embedding.invalid/"
    client.embeddings.create = AsyncMock(
        return_value=SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])
    )
    db = AsyncMock()
    request = APIRequest(
        task_id=8,
        request_json={"input_texts": ["texto"], "doc_ids": ["doc-async"]},
        token_consumption=0,
        attempts_left=1,
        llm_client=client,
        api_endpoint="embeddings",
        db=db,
    )

    await request.call_api(
        session=MagicMock(),
        llm_client=client,
        api_endpoint="embeddings",
        db=db,
        save_path=tmp_path / "results.jsonl",
        status=StatusTracker(num_tasks_in_progress=1),
    )

    assert client.embeddings.create.await_args.kwargs["model"] == "embedding"


@pytest.mark.asyncio
async def test_legacy_empty_pool_is_rejected_before_embedding_client(tmp_path):
    client = MagicMock()
    client.base_url = "https://embedding.invalid/"
    client.embeddings.create = AsyncMock()
    request = APIRequest(
        task_id=9,
        request_json={"input_texts": [], "doc_ids": ["doc-789"]},
        token_consumption=0,
        attempts_left=1,
        llm_client=client,
        api_endpoint="embeddings",
        db=AsyncMock(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await request.call_api(
            session=MagicMock(),
            llm_client=client,
            api_endpoint="embeddings",
            db=AsyncMock(),
            save_path=tmp_path / "results.jsonl",
            status=StatusTracker(num_tasks_in_progress=1),
        )

    assert type(exc_info.value).__name__ == "EmptyEmbeddingInputException"
    assert exc_info.value.document_id == "doc-789"
    client.embeddings.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_request_path_rejects_empty_input_before_client():
    client = MagicMock()
    client.embeddings.create = AsyncMock()
    request = LegacyAPIRequest(
        task_id=3,
        request_json={"input_texts": [], "doc_ids": ["doc-legacy"]},
        token_consumption=0,
        attempts_left=1,
        metadata={},
    )

    with pytest.raises(HTTPException) as exc_info:
        await request._dispatch_api_call("embeddings", client)

    assert type(exc_info.value).__name__ == "EmptyEmbeddingInputException"
    client.embeddings.create.assert_not_awaited()


def test_provider_rejects_empty_input_before_sync_client():
    provider = AzureOpenAIEmbeddingProvider.__new__(AzureOpenAIEmbeddingProvider)
    provider.client = MagicMock()
    provider.model = "embedding"

    with pytest.raises(HTTPException) as exc_info:
        provider.generate_embeddings([])

    assert type(exc_info.value).__name__ == "EmptyEmbeddingInputException"
    provider.client.embeddings.create.assert_not_called()


@pytest.mark.asyncio
async def test_document_content_error_survives_auto_indexing(monkeypatch):
    error = DocumentContentNotExtractableException("doc-321")
    monkeypatch.setattr(pergunta, "should_auto_index", lambda *args: True)
    monkeypatch.setattr(
        pergunta,
        "auto_index_missing_documents",
        AsyncMock(side_effect=error),
    )

    with pytest.raises(DocumentContentNotExtractableException) as exc_info:
        await pergunta._ensure_docs_indexed(
            {
                "all_indexed": False,
                "missing_documents": ["doc-321"],
                "total_documents": 1,
            },
            {},
        )

    assert exc_info.value is error


@pytest.mark.asyncio
async def test_document_content_error_survives_auto_index_entrypoint(monkeypatch):
    error = DocumentContentNotExtractableException("doc-654")
    monkeypatch.setattr(
        auto_indexing,
        "_find_available_docs",
        lambda *args: ["doc-654"],
    )
    monkeypatch.setattr(
        auto_indexing,
        "index_single_batch",
        AsyncMock(side_effect=error),
    )

    with pytest.raises(AutoIndexingException) as exc_info:
        await auto_indexing.auto_index_missing_documents(["doc-654"], {})

    assert exc_info.value.status_code == 400
    assert exc_info.value.content_failure_count == 1
    assert exc_info.value.internal_failure_count == 0
    assert "doc-654" in exc_info.value.detail


@pytest.mark.asyncio
async def test_batched_auto_index_aggregates_content_errors(monkeypatch):
    errors = {
        "doc-1": DocumentContentNotExtractableException("doc-1"),
        "doc-2": DocumentContentNotExtractableException("doc-2"),
    }

    async def fail_batch(batch_ids, *args):
        raise errors[batch_ids[0]]

    monkeypatch.setattr(
        auto_indexing,
        "process_batch_with_semaphore",
        fail_batch,
    )

    with pytest.raises(AutoIndexingException) as exc_info:
        await auto_indexing.index_documents_in_batches(
            ["doc-1", "doc-2"],
            {},
            batch_size=1,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.content_failure_count == 2
    assert exc_info.value.internal_failure_count == 0
    assert "2 documentos sem conteúdo extraível" in exc_info.value.detail
    assert "doc-1, doc-2" in exc_info.value.detail


@pytest.mark.asyncio
async def test_batched_auto_index_aggregates_mixed_errors_without_leaking(
    monkeypatch,
):
    async def fail_batch(batch_ids, *args):
        if batch_ids[0] == "doc-empty":
            raise DocumentContentNotExtractableException("doc-empty")
        raise RuntimeError("segredo do proxy e stack interna")

    monkeypatch.setattr(
        auto_indexing,
        "process_batch_with_semaphore",
        fail_batch,
    )

    with pytest.raises(AutoIndexingException) as exc_info:
        await auto_indexing.index_documents_in_batches(
            ["doc-empty", "doc-internal"],
            {},
            batch_size=1,
        )

    error = exc_info.value
    assert error.status_code == 400
    assert error.content_failure_count == 1
    assert error.internal_failure_count == 1
    assert "doc-empty" in error.detail
    assert "1 falha interna" in error.detail
    assert "segredo" not in error.detail
    assert "proxy" not in error.detail
    assert "stack" not in error.detail


@pytest.mark.asyncio
async def test_batched_auto_index_sanitizes_internal_errors(monkeypatch):
    errors = [
        HTTPException400(detail="detalhe do banco"),
        RuntimeError("detalhe do LiteLLM"),
    ]

    async def fail_batch(batch_ids, *args):
        raise errors[int(batch_ids[0])]

    monkeypatch.setattr(
        auto_indexing,
        "process_batch_with_semaphore",
        fail_batch,
    )

    with pytest.raises(AutoIndexingException) as exc_info:
        await auto_indexing.index_documents_in_batches(
            ["0", "1"],
            {},
            batch_size=1,
        )

    error = exc_info.value
    assert error.status_code == 500
    assert error.content_failure_count == 0
    assert error.internal_failure_count == 2
    assert error.detail == "A indexação automática falhou: 2 falhas internas."


@pytest.mark.asyncio
async def test_batched_auto_index_treats_other_embedding_errors_as_internal(
    monkeypatch,
):
    errors = {
        "doc-misaligned": EmbeddingInputException(
            detail="chunks desalinhados do produtor",
            document_id="doc-misaligned",
        ),
        "doc-empty-pool": EmptyEmbeddingInputException("doc-empty-pool"),
    }

    async def fail_batch(batch_ids, *args):
        raise errors[batch_ids[0]]

    monkeypatch.setattr(
        auto_indexing,
        "process_batch_with_semaphore",
        fail_batch,
    )

    with pytest.raises(AutoIndexingException) as exc_info:
        await auto_indexing.index_documents_in_batches(
            list(errors),
            {},
            batch_size=1,
        )

    error = exc_info.value
    assert error.status_code == 500
    assert error.content_failure_count == 0
    assert error.internal_failure_count == 2
    assert error.detail == "A indexação automática falhou: 2 falhas internas."
    assert "doc-misaligned" not in error.detail
    assert "doc-empty-pool" not in error.detail
    assert "desalinhados" not in error.detail


@pytest.mark.asyncio
async def test_batched_auto_index_separates_content_and_embedding_internal_errors(
    monkeypatch,
):
    errors = {
        "doc-content": DocumentContentNotExtractableException("doc-content"),
        "doc-producer": EmbeddingInputException(
            detail="detalhe interno do produtor",
            document_id="doc-producer",
        ),
    }

    async def fail_batch(batch_ids, *args):
        raise errors[batch_ids[0]]

    monkeypatch.setattr(
        auto_indexing,
        "process_batch_with_semaphore",
        fail_batch,
    )

    with pytest.raises(AutoIndexingException) as exc_info:
        await auto_indexing.index_documents_in_batches(
            list(errors),
            {},
            batch_size=1,
        )

    error = exc_info.value
    assert error.status_code == 400
    assert error.content_failure_count == 1
    assert error.internal_failure_count == 1
    assert "doc-content" in error.detail
    assert "1 falha interna" in error.detail
    assert "doc-producer" not in error.detail
    assert "detalhe interno" not in error.detail


@pytest.mark.asyncio
async def test_batched_auto_index_limits_document_ids(monkeypatch):
    async def fail_batch(batch_ids, *args):
        raise DocumentContentNotExtractableException(batch_ids[0])

    monkeypatch.setattr(
        auto_indexing,
        "process_batch_with_semaphore",
        fail_batch,
    )
    document_ids = [f"doc-{index}" for index in range(7)]

    with pytest.raises(AutoIndexingException) as exc_info:
        await auto_indexing.index_documents_in_batches(
            document_ids,
            {},
            batch_size=1,
        )

    detail = exc_info.value.detail
    assert "IDs: doc-0, doc-1, doc-2, doc-3, doc-4" in detail
    assert "mais 2 documentos não exibidos" in detail
    assert "doc-5" not in detail
    assert "doc-6" not in detail


@pytest.mark.asyncio
async def test_aggregate_auto_index_error_produces_one_terminal_sse_frame(monkeypatch):
    from sei_ia.routers.chat.stream_error_handler import handle_http_exception

    async def fail_batch(batch_ids, *args):
        if batch_ids[0] == "doc-empty":
            raise DocumentContentNotExtractableException("doc-empty")
        raise RuntimeError("falha interna privada")

    monkeypatch.setattr(
        auto_indexing,
        "process_batch_with_semaphore",
        fail_batch,
    )

    frames = []
    try:
        await auto_indexing.index_documents_in_batches(
            ["doc-empty", "doc-internal"],
            {},
            batch_size=1,
        )
    except AutoIndexingException as error:
        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            frames.append(handle_http_exception(error, MagicMock()))

    assert len(frames) == 1
    assert frames[0]["type"] == "error"
    assert frames[0]["status_code"] == 400
    assert "1 falha interna" in frames[0]["detail"]


@pytest.mark.asyncio
async def test_indexing_embeddings_removes_temp_files_on_failure(
    tmp_path,
    monkeypatch,
):
    request_path = tmp_path / "requests.jsonl"
    result_path = tmp_path / "results.jsonl"
    request_path.touch()
    result_path.touch()
    monkeypatch.setattr(
        pipeline.embedding_generator,
        "create_temp_files",
        lambda: (request_path, result_path),
    )
    monkeypatch.setattr(
        pipeline,
        "get_document_state_by_id",
        lambda *args: ItemDocumentRequest(id_documento="doc-empty", content=""),
    )

    with pytest.raises(DocumentContentNotExtractableException):
        await pipeline.indexing_embeddings(["doc-empty"], {})

    assert not request_path.exists()
    assert not result_path.exists()


def test_document_content_error_serializes_as_sanitized_sse():
    from sei_ia.routers.chat.stream_error_handler import handle_http_exception

    error = DocumentContentNotExtractableException("doc-987")

    async def serialize_error():
        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            return handle_http_exception(error, MagicMock())

    import asyncio

    frame = asyncio.run(serialize_error())

    assert frame["type"] == "error"
    assert frame["status_code"] == 400
    assert frame["detail"] == (
        "O documento doc-987 não possui conteúdo extraível para indexação."
    )
    assert "input_texts" not in frame["detail"]
