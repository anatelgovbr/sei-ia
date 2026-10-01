"""Tests for api_sei/repository/recommendation.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from api_sei.exception_handling.exceptions import SQLAlchemyInsertError
from api_sei.repository.recommendation import (
    add_mlt_document_recommendation,
    add_process_weighted_mlt_recommendation,
    save,
)


class TestSave:
    def test_no_op_when_app_db_is_falsy(self):
        with patch("api_sei.repository.recommendation.app_db", None):
            assert save(200, "1", "url") is None

    def test_persists_log_consume(self):
        with patch("api_sei.repository.recommendation.app_db") as mock_db:
            save(200, "1", "url")
        mock_db.add.assert_called_once()

    def test_swallows_exceptions_without_raising(self):
        with patch("api_sei.repository.recommendation.app_db") as mock_db:
            mock_db.add.side_effect = RuntimeError("boom")
            result = save(200, "1", "url")
        assert result is None


class TestAddMltDocumentRecommendation:
    def _kwargs(self, **overrides):
        defaults = {
            "list_id_doc": [1],
            "list_type_id_doc": [1],
            "rows": 10,
            "text": "t",
            "include_citations": False,
            "text_weight": 0.5,
            "normalized": True,
            "fq": [],
            "recommendation": {},
            "requested_at": datetime.now(tz=timezone.utc),
            "id_user": 1,
        }
        defaults.update(overrides)
        return defaults

    def test_no_op_when_app_db_is_falsy(self):
        with patch("api_sei.repository.recommendation.app_db", None):
            assert add_mlt_document_recommendation(**self._kwargs()) is None

    def test_returns_id_recommendation_on_success(self):
        with patch("api_sei.repository.recommendation.app_db") as mock_db:
            mock_db.add.return_value = MagicMock(id_recommendation=42)
            result = add_mlt_document_recommendation(**self._kwargs())
        assert result == 42

    def test_raises_insert_error_on_sqlalchemy_error(self):
        with patch("api_sei.repository.recommendation.app_db") as mock_db:
            mock_db.add.side_effect = SQLAlchemyError("db error")
            with pytest.raises(SQLAlchemyInsertError):
                add_mlt_document_recommendation(**self._kwargs())


class TestAddProcessWeightedMltRecommendation:
    def _kwargs(self, **overrides):
        defaults = {
            "id_protocolo": "1",
            "id_user": 1,
            "rows": 10,
            "parsedquery_field": "fulltext_parsedquery_t",
            "id_field": "id_protocolo",
            "fq": [],
            "debug": False,
            "extraction_method": "solr",
            "recommendation": {},
            "requested_at": datetime.now(tz=timezone.utc),
        }
        defaults.update(overrides)
        return defaults

    def test_no_op_when_app_db_is_falsy(self):
        with patch("api_sei.repository.recommendation.app_db", None):
            assert add_process_weighted_mlt_recommendation(**self._kwargs()) is None

    def test_returns_id_recommendation_on_success(self):
        with patch("api_sei.repository.recommendation.app_db") as mock_db:
            mock_db.add.return_value = MagicMock(id_recommendation=77)
            result = add_process_weighted_mlt_recommendation(**self._kwargs())
        assert result == 77

    def test_raises_insert_error_on_sqlalchemy_error(self):
        with patch("api_sei.repository.recommendation.app_db") as mock_db:
            mock_db.add.side_effect = SQLAlchemyError("db error")
            with pytest.raises(SQLAlchemyInsertError):
                add_process_weighted_mlt_recommendation(**self._kwargs())
