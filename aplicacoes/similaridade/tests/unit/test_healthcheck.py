"""Tests for the healthcheck router endpoints."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api_sei.routers.healthcheck import (
    get_health,
    get_health_database,
    get_health_document_recommendation,
    get_health_process_recommendation,
    get_health_solr,
)


class TestGetHealth:
    def test_returns_ok(self):
        result = get_health()
        assert result.status == "OK"
        assert result.response_time is None


class TestGetHealthSolr:
    def test_returns_ok_without_core_name(self):
        with patch(
            "api_sei.routers.healthcheck.SolrRequests.check_solr_service",
            return_value=True,
        ):
            result = get_health_solr(core_name=None)
        assert result.status == "OK"

    def test_returns_ok_with_core_name(self):
        with patch(
            "api_sei.routers.healthcheck.SolrRequests.check_core_exists",
            return_value=True,
        ) as mock_check:
            result = get_health_solr(core_name="processos_bm25")
        assert result.status == "OK"
        mock_check.assert_called_once()

    def test_raises_503_when_solr_unavailable(self):
        with patch(
            "api_sei.routers.healthcheck.SolrRequests.check_solr_service",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as excinfo:
                get_health_solr(core_name=None)
        assert excinfo.value.status_code == 503


class TestGetHealthDatabase:
    def test_returns_ok_when_connected(self):
        with patch("api_sei.routers.healthcheck.app_db") as mock_app_db:
            mock_app_db.test_connection.return_value = True
            result = get_health_database()
        assert result.status == "OK"

    def test_raises_503_when_not_connected(self):
        with patch("api_sei.routers.healthcheck.app_db") as mock_app_db:
            mock_app_db.test_connection.return_value = False
            with pytest.raises(HTTPException) as excinfo:
                get_health_database()
        assert excinfo.value.status_code == 503


class TestGetHealthProcessRecommendation:
    def test_returns_ok_with_response_time(self):
        with patch(
            "api_sei.routers.healthcheck.SolrRequests.get",
            return_value=[{"id_protocolo": "123"}],
        ), patch(
            "api_sei.routers.healthcheck.wmlt_process_recommendations_service"
        ) as mock_wmlt:
            result = get_health_process_recommendation()

        assert result.status == "OK"
        assert result.response_time is not None
        mock_wmlt.assert_called_once()
        assert mock_wmlt.call_args.kwargs["id_value"] == "123"

    def test_raises_503_when_no_docs_found(self):
        with patch("api_sei.routers.healthcheck.SolrRequests.get", return_value=[]):
            with pytest.raises(HTTPException) as excinfo:
                get_health_process_recommendation()
        assert excinfo.value.status_code == 503
        assert "No id_protocolo found" in excinfo.value.detail

    def test_raises_503_when_recommendation_fails(self):
        with patch(
            "api_sei.routers.healthcheck.SolrRequests.get",
            return_value=[{"id_protocolo": "123"}],
        ), patch(
            "api_sei.routers.healthcheck.wmlt_process_recommendations_service",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as excinfo:
                get_health_process_recommendation()
        assert excinfo.value.status_code == 503
        assert "boom" in excinfo.value.detail


class TestGetHealthDocumentRecommendation:
    def test_returns_ok_with_response_time(self):
        with patch(
            "api_sei.routers.healthcheck.SolrRequests.get",
            return_value=[{"id_document": "456"}],
        ), patch("api_sei.routers.healthcheck.doc2doc_search") as mock_doc2doc:
            result = get_health_document_recommendation()

        assert result.status == "OK"
        assert result.response_time is not None
        mock_doc2doc.assert_called_once()
        assert mock_doc2doc.call_args.kwargs["list_id_doc"] == [456]

    def test_raises_503_when_no_docs_found(self):
        with patch("api_sei.routers.healthcheck.SolrRequests.get", return_value=[]):
            with pytest.raises(HTTPException) as excinfo:
                get_health_document_recommendation()
        assert excinfo.value.status_code == 503
        assert "No id_document found" in excinfo.value.detail

    def test_raises_503_when_recommendation_fails(self):
        with patch(
            "api_sei.routers.healthcheck.SolrRequests.get",
            return_value=[{"id_document": "456"}],
        ), patch(
            "api_sei.routers.healthcheck.doc2doc_search",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as excinfo:
                get_health_document_recommendation()
        assert excinfo.value.status_code == 503
        assert "boom" in excinfo.value.detail
