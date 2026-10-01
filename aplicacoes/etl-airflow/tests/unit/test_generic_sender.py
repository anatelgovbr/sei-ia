"""Tests for jobs/dags/database/generic_sender.py."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from jobs.dags.database.generic_sender import GenericSender, is_not_nan


class TestIsNotNan:
    def test_nan_float_is_false(self):
        assert is_not_nan(float("nan")) is False

    def test_regular_value_is_true(self):
        assert is_not_nan(5) is True

    def test_ndarray_all_nan_is_false(self):
        assert is_not_nan(np.array([np.nan, np.nan])) is False


class TestSendOneDocToSolr:
    def test_success(self):
        response = MagicMock(status_code=200)
        with patch("requests.post", return_value=response) as mock_post:
            result = GenericSender.send_one_doc_to_solr(
                {"id": "1"}, "http://solr/core"
            )

        assert result is response
        mock_post.assert_called_once()

    def test_raises_on_error_status(self):
        response = MagicMock(status_code=500, text="erro interno")
        with patch("requests.post", return_value=response), pytest.raises(
            RuntimeError
        ):
            GenericSender.send_one_doc_to_solr({"id": "1"}, "http://solr/core")


class TestSendAllDocsToSolr:
    def test_sends_each_row(self):
        df = pd.DataFrame([{"id": "1"}, {"id": "2"}])
        sender = GenericSender(df=df, core_url="http://solr/core")

        with patch.object(GenericSender, "send_one_doc_to_solr") as mock_send:
            sender.send_all_docs_to_solr()

        assert mock_send.call_count == 2


class TestSendDocsInBulkToSolr:
    def test_posts_cleaned_records(self):
        df = pd.DataFrame([{"id": "1", "field": np.nan}, {"id": "2", "field": "x"}])
        sender = GenericSender(df=df, core_url="http://solr/core/")
        response = MagicMock(status_code=200)

        with patch("requests.post", return_value=response) as mock_post:
            result = sender.send_docs_in_bulk_to_solr()

        assert result is response
        called_url = mock_post.call_args.args[0]
        assert called_url == "http://solr/core/update/json/docs?commit=true"

    def test_raises_on_error_status(self):
        df = pd.DataFrame([{"id": "1"}])
        sender = GenericSender(df=df, core_url="http://solr/core")
        response = MagicMock(status_code=500, text="erro")

        with patch("requests.post", return_value=response), pytest.raises(
            RuntimeError
        ):
            sender.send_docs_in_bulk_to_solr()


class TestUpdateBulkFields:
    def test_success(self):
        response = MagicMock(status_code=200)
        updates = [("id", "1", "field", "novo_valor")]

        with patch("requests.post", return_value=response) as mock_post:
            result = GenericSender.update_bulk_fields("http://solr/core", updates)

        assert result is response
        mock_post.assert_called_once()

    def test_raises_on_error_status(self):
        response = MagicMock(status_code=500, text="erro")
        updates = [("id", "1", "field", "novo_valor")]

        with patch("requests.post", return_value=response), pytest.raises(
            RuntimeError
        ):
            GenericSender.update_bulk_fields("http://solr/core", updates)
