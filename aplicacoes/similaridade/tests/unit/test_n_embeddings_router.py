"""Tests for api_sei/routers/n_embeddings_recommender.py."""

from unittest.mock import patch

import pytest

from api_sei.exception_handling.exceptions import (
    ResourceNotFoundException,
    TableEmbeddingNotFoundException,
)
from api_sei.routers.n_embeddings_recommender import (
    get_similarity,
    n_embeddings_document_recommendations,
)


class TestNEmbeddingsDocumentRecommendations:
    @pytest.mark.asyncio
    async def test_returns_recommendations_with_rounded_scores(self):
        with patch(
            "api_sei.routers.n_embeddings_recommender.NEmbeddingDocumentRecommender"
        ) as mock_cls:
            mock_cls.return_value.run.return_value = [
                {"id": 1, "score": 0.123456789012345},
            ]
            result = await n_embeddings_document_recommendations(
                id_document="135629", embd_tablename="embd_doc_minilm_128"
            )

        assert result.recommendation[0].id == "1"
        assert result.recommendation[0].score == round(0.123456789012345, 10)

    @pytest.mark.asyncio
    async def test_raises_resource_not_found_on_index_error(self):
        with patch(
            "api_sei.routers.n_embeddings_recommender.NEmbeddingDocumentRecommender"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = IndexError()
            with pytest.raises(ResourceNotFoundException) as excinfo:
                await n_embeddings_document_recommendations(
                    id_document="135629", embd_tablename="embd_doc_minilm_128"
                )

        assert excinfo.value.resource_name == "135629"

    @pytest.mark.asyncio
    async def test_raises_table_embedding_not_found_on_type_error(self):
        with patch(
            "api_sei.routers.n_embeddings_recommender.NEmbeddingDocumentRecommender"
        ) as mock_cls:
            mock_cls.return_value.run.side_effect = TypeError()
            with pytest.raises(TableEmbeddingNotFoundException) as excinfo:
                await n_embeddings_document_recommendations(
                    id_document="135629", embd_tablename="embd_doc_minilm_128"
                )

        assert "embd_doc_minilm_128" in excinfo.value.detail


class TestGetSimilarity:
    @pytest.mark.asyncio
    async def test_delegates_to_adapter_with_request_fields(self):
        with patch(
            "api_sei.routers.n_embeddings_recommender.adapter_protocolo_formatado_id_protocolo",
            return_value={"recommendation": []},
        ) as mock_adapter:
            result = await get_similarity(id_protocolo=123, fq=[1, 2], rows=5)

        assert result == {"recommendation": []}
        args, _kwargs = mock_adapter.call_args
        assert args[1] == 123
        assert args[2] == [1, 2]
        assert args[3] == 5
