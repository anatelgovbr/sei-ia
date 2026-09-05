"""Tests for api_sei/services/mlt.py."""

from unittest.mock import patch

import pytest
from requests.exceptions import ConnectionError as ReqConnectionError

from api_sei.exception_handling.exceptions import SolrCommunicationError
from api_sei.services.mlt import (
    has_id_protocolo_service,
    mlt_process_recommendations_service,
    wmlt_process_recommendations_service,
)


class TestMltProcessRecommendationsService:
    def test_resolves_mlt_fields_when_not_given(self):
        with patch(
            "api_sei.services.mlt.get_all_str_search_fields", return_value=["campo1"]
        ) as mock_fields, patch("api_sei.services.mlt.SolrMlt") as mock_solr_mlt_cls:
            mock_solr_mlt_cls.return_value.mlt.return_value = {"recommendation": []}
            result = mlt_process_recommendations_service(
                id_value=1, rows=10, fq=None, normalized=True
            )

        assert result == {"recommendation": []}
        mock_fields.assert_called_once()

    def test_skips_field_resolution_when_mlt_fields_given(self):
        with patch(
            "api_sei.services.mlt.get_all_str_search_fields"
        ) as mock_fields, patch("api_sei.services.mlt.SolrMlt") as mock_solr_mlt_cls:
            mock_solr_mlt_cls.return_value.mlt.return_value = {"recommendation": []}
            mlt_process_recommendations_service(
                id_value=1, rows=10, fq=None, normalized=True, mlt_fields=["campo1"]
            )

        mock_fields.assert_not_called()

    def test_returns_service_instance_when_requested(self):
        with patch("api_sei.services.mlt.SolrMlt") as mock_solr_mlt_cls:
            mock_solr_mlt_cls.return_value.mlt.return_value = {"recommendation": []}
            result, service = mlt_process_recommendations_service(
                id_value=1,
                rows=10,
                fq=None,
                normalized=True,
                mlt_fields=["campo1"],
                return_service=True,
            )

        assert result == {"recommendation": []}
        assert service is mock_solr_mlt_cls.return_value

    def test_wraps_solr_errors_as_solr_communication_error(self):
        with patch("api_sei.services.mlt.SolrMlt") as mock_solr_mlt_cls:
            mock_solr_mlt_cls.return_value.mlt.side_effect = ReqConnectionError("down")
            with pytest.raises(SolrCommunicationError):
                mlt_process_recommendations_service(
                    id_value=1, rows=10, fq=None, normalized=True, mlt_fields=["campo1"]
                )


class TestWmltProcessRecommendationsService:
    def test_warns_when_normalized_is_false(self):
        with patch("api_sei.services.mlt.SolrMlt") as mock_solr_mlt_cls, patch(
            "api_sei.services.mlt.add_process_weighted_mlt_recommendation",
            return_value=99,
        ):
            mock_solr_mlt_cls.return_value.mlt.return_value = {"recommendation": []}
            with pytest.warns(UserWarning, match="wmlt is always normalized"):
                wmlt_process_recommendations_service(
                    id_value=1, rows=10, fq=None, normalized=False
                )

    def test_persists_recommendation_and_sets_id(self):
        with patch("api_sei.services.mlt.SolrMlt") as mock_solr_mlt_cls, patch(
            "api_sei.services.mlt.add_process_weighted_mlt_recommendation",
            return_value=99,
        ) as mock_add:
            mock_solr_mlt_cls.return_value.mlt.return_value = {"recommendation": []}
            result = wmlt_process_recommendations_service(
                id_value=1, rows=10, fq=None, normalized=True
            )

        assert result["id"] == 99
        assert mock_add.call_args.kwargs["id_protocolo"] == 1
        assert mock_add.call_args.kwargs["rows"] == 10

    def test_returns_service_instance_when_requested(self):
        with patch("api_sei.services.mlt.SolrMlt") as mock_solr_mlt_cls, patch(
            "api_sei.services.mlt.add_process_weighted_mlt_recommendation",
            return_value=99,
        ):
            mock_solr_mlt_cls.return_value.mlt.return_value = {"recommendation": []}
            result, service = wmlt_process_recommendations_service(
                id_value=1, rows=10, fq=None, normalized=True, return_service=True
            )

        assert result["id"] == 99
        assert service is mock_solr_mlt_cls.return_value

    def test_wraps_json_decode_error_as_solr_communication_error(self):
        from requests.exceptions import JSONDecodeError

        with patch("api_sei.services.mlt.SolrMlt") as mock_solr_mlt_cls:
            mock_solr_mlt_cls.return_value.mlt.side_effect = JSONDecodeError(
                "bad json", "doc", 0
            )
            with pytest.raises(SolrCommunicationError):
                wmlt_process_recommendations_service(
                    id_value=1, rows=10, fq=None, normalized=True
                )


class TestHasIdProtocoloService:
    def test_returns_true_when_solr_finds_matches(self):
        with patch("api_sei.services.mlt.SolrRequests.get", return_value=5):
            assert has_id_protocolo_service(123) is True

    def test_returns_false_when_no_matches(self):
        with patch("api_sei.services.mlt.SolrRequests.get", return_value=0):
            assert has_id_protocolo_service(123) is False
