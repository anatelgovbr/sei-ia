"""Tests for api_sei/routers/rerank_recommender.py."""

from unittest.mock import patch

from api_sei.routers.rerank_recommender import (
    MltType,
    VectorStorageSystem,
    rerank_process_recommendations_by_id_protocolo,
)


class TestRerankProcessRecommendationsByIdProtocolo:
    def test_delegates_to_service_with_mlt_config_and_defaults(self):
        with patch(
            "api_sei.routers.rerank_recommender.rerank_process_recommendations_service",
            return_value={"recommendation": []},
        ) as mock_service:
            result = rerank_process_recommendations_by_id_protocolo(id_protocolo="123")

        assert result == {"recommendation": []}
        args, kwargs = mock_service.call_args
        assert args[0] == "123"
        assert args[1] == 10  # rows default
        assert args[2] is None  # fq default
        assert args[3] is True  # normalized default
        assert args[4] == 5  # top_n default
        mlt_config = args[5]
        assert mlt_config.mintf == 2
        assert mlt_config.mindf == 5
        assert mlt_config.boost is False
        assert args[6] is True  # rerank default
        assert args[7] == VectorStorageSystem.pgvector
        assert args[8] == MltType.wmlt
        assert kwargs["id_field"] == "id_protocolo"

    def test_forwards_custom_vector_storage_and_mlt_type(self):
        with patch(
            "api_sei.routers.rerank_recommender.rerank_process_recommendations_service",
            return_value={"recommendation": []},
        ) as mock_service:
            rerank_process_recommendations_by_id_protocolo(
                id_protocolo="123",
                vector_storage_system=VectorStorageSystem.solr,
                mlt_type=MltType.mlt,
            )

        args, _kwargs = mock_service.call_args
        assert args[7] == VectorStorageSystem.solr
        assert args[8] == MltType.mlt
