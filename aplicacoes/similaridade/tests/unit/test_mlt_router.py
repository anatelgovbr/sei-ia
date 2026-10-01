"""Tests for api_sei/routers/mlt_recommender.py."""

from unittest.mock import patch

import pytest

from api_sei.routers.mlt_recommender import (
    has_id_protocolo,
    hwmlt_process_recommendations_by_id_protocolo,
    mlt_process_recommendations_by_id_protocolo,
    wmlt_process_recommendations_by_id_protocolo,
)


class TestMltProcessRecommendationsByIdProtocolo:
    def test_delegates_to_service_with_id_protocolo_field(self):
        with patch(
            "api_sei.routers.mlt_recommender.mlt_process_recommendations_service",
            return_value={"recommendation": []},
        ) as mock_service:
            result = mlt_process_recommendations_by_id_protocolo(
                id_protocolo="123", rows=5
            )

        assert result == {"recommendation": []}
        args, kwargs = mock_service.call_args
        assert args[0] == "123"
        assert args[1] == 5
        assert kwargs["id_field"] == "id_protocolo"


class TestWmltProcessRecommendationsByIdProtocolo:
    def test_delegates_to_service_with_solr_extraction_method(self):
        with patch(
            "api_sei.routers.mlt_recommender.wmlt_process_recommendations_service",
            return_value={"recommendation": []},
        ) as mock_service:
            result = wmlt_process_recommendations_by_id_protocolo(
                id_protocolo="456", id_user=1, rows=7, debug=True
            )

        assert result == {"recommendation": []}
        kwargs = mock_service.call_args.kwargs
        assert kwargs["id_value"] == "456"
        assert kwargs["rows"] == 7
        assert kwargs["fq"] is None
        assert kwargs["debug"] is True
        assert kwargs["id_field"] == "id_protocolo"
        assert kwargs["id_user"] == 1
        assert kwargs["requested_at"] is not None


class TestHwmltProcessRecommendationsByIdProtocolo:
    def test_delegates_to_hybrid_service_with_depth(self):
        with patch(
            "api_sei.routers.mlt_recommender.hwmlt_process_recommendations_service",
            return_value={"recommendation": []},
        ) as mock_service:
            result = hwmlt_process_recommendations_by_id_protocolo(
                id_protocolo="789", rows=3, depth=100
            )

        assert result == {"recommendation": []}
        mock_service.assert_called_once_with(
            "789", 3, None, depth=100, id_field="id_protocolo"
        )


class TestHasIdProtocolo:
    @pytest.mark.asyncio
    async def test_delegates_to_service(self):
        with patch(
            "api_sei.routers.mlt_recommender.has_id_protocolo_service",
            return_value=True,
        ) as mock_service:
            result = await has_id_protocolo(id_protocolo=123)

        assert result is True
        mock_service.assert_called_once_with(123)
