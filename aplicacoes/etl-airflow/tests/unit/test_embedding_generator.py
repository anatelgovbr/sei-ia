"""Tests for jobs/services/embedder/embedding_generator.py."""

import json
from unittest.mock import MagicMock, patch

import pytest

from jobs.services.embedder.embedding_generator import (
    EmbeddingGenerator,
    InputPoolEmbd,
    append_to_jsonl,
    get_last_jsonl_line,
)


@pytest.fixture
def generator():
    with patch(
        "jobs.services.embedder.embedding_generator.LiteLLMEmbeddingProvider"
    ) as mock_provider_cls:
        mock_provider = MagicMock()
        mock_provider_cls.return_value = mock_provider
        gen = EmbeddingGenerator()
        yield gen


class TestGenerate:
    def test_delegates_to_provider(self, generator):
        generator.provider.generate_embeddings.return_value = [[0.1, 0.2]]
        result = generator.generate(["texto"])
        assert result == [[0.1, 0.2]]
        generator.provider.generate_embeddings.assert_called_once_with(["texto"])


class TestApplyTokenizer:
    def test_delegates_to_provider(self, generator):
        generator.provider.apply_tokenizer.return_value = [[1, 2, 3]]
        result = generator.apply_tokenizer(["texto"])
        assert result == [[1, 2, 3]]


class TestCreateTempFiles:
    def test_creates_two_distinct_paths(self, generator, tmp_path):
        req_path, save_path = generator.create_temp_files()
        try:
            assert req_path != save_path
            assert req_path.suffix == ".jsonl"
            assert save_path.suffix == ".jsonl"
        finally:
            req_path.unlink(missing_ok=True)
            save_path.unlink(missing_ok=True)


class TestAppendToJsonlAndGetLastLine:
    def test_get_last_jsonl_line_returns_none_for_missing_file(self, tmp_path):
        assert get_last_jsonl_line(tmp_path / "missing.jsonl") is None

    def test_get_last_jsonl_line_returns_none_for_empty_file(self, tmp_path):
        empty_file = tmp_path / "empty.jsonl"
        empty_file.touch()
        assert get_last_jsonl_line(empty_file) is None

    def test_append_and_read_last_line(self, tmp_path):
        filepath = tmp_path / "pool.jsonl"
        append_to_jsonl({"a": 1}, filepath)
        append_to_jsonl({"a": 2}, filepath)

        last_line = get_last_jsonl_line(filepath)
        assert json.loads(last_line) == {"a": 2}


class TestAppendPoolFile:
    def test_adds_single_item_within_context_size(self, generator, tmp_path):
        generator.provider.get_tokenizer.return_value.encode.side_effect = (
            lambda text: [0] * len(text)
        )
        generator.provider.max_context_size = 1000

        req_filepath = tmp_path / "pool_req.jsonl"
        pool_input = InputPoolEmbd(
            input_texts=["hello"],
            doc_id="doc1",
            chunk_ids=[0],
            positions=[(0, 5)],
        )

        generator.append_pool_file(pool_input, req_filepath)

        line = get_last_jsonl_line(req_filepath)
        item = json.loads(line)
        assert item["doc_ids"] == ["doc1"]
        assert item["input_texts"] == ["hello"]

    def test_flushes_batch_when_context_size_exceeded(self, generator, tmp_path):
        generator.provider.get_tokenizer.return_value.encode.side_effect = (
            lambda text: [0] * len(text)
        )
        # "hello" (5) fits alone; adding "bye" (3) would bring the running
        # batch to 8, over the limit, so it must flush "hello" first.
        generator.provider.max_context_size = 6

        req_filepath = tmp_path / "pool_req.jsonl"
        pool_input = InputPoolEmbd(
            input_texts=["hello", "bye"],
            doc_id="doc1",
            chunk_ids=[0, 1],
            positions=[(0, 5), (5, 8)],
        )

        generator.append_pool_file(pool_input, req_filepath)

        with req_filepath.open() as f:
            lines = [json.loads(line) for line in f]

        assert len(lines) == 2
        assert lines[0]["input_texts"] == ["hello"]
        assert lines[1]["input_texts"] == ["bye"]

    def test_continues_from_existing_last_line(self, generator, tmp_path):
        generator.provider.get_tokenizer.return_value.encode.side_effect = (
            lambda text: [0] * len(text)
        )
        generator.provider.max_context_size = 1000

        req_filepath = tmp_path / "pool_req.jsonl"
        append_to_jsonl(
            {
                "doc_ids": ["existing"],
                "chunk_ids": [9],
                "positions": [(0, 1)],
                "input_texts": ["prev"],
                "count_context_size": 4,
            },
            req_filepath,
        )

        pool_input = InputPoolEmbd(
            input_texts=["novo"],
            doc_id="doc2",
            chunk_ids=[0],
            positions=[(0, 4)],
        )
        generator.append_pool_file(pool_input, req_filepath)

        with req_filepath.open() as f:
            lines = [json.loads(line) for line in f]

        assert lines[-1]["doc_ids"] == ["existing", "doc2"]
        assert lines[-1]["input_texts"] == ["prev", "novo"]
