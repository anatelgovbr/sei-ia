import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from requests import JSONDecodeError, Timeout

from api_sei.db_models.solr_select import SolrRequests
from api_sei.exception_handling.exceptions import JsonFieldException, SolrException


class TestSolrSelect(unittest.TestCase):
    @patch("api_sei.db_models.solr_select.requests.get")
    def test_successful_select(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": {"numFound": 2, "docs": ["some_data"]}
        }
        mock_get.return_value = mock_response

        url = "http://example.com"
        result = SolrRequests.select(url, nested_fields=["response", "docs"])

        self.assertEqual(result, ["some_data"])

    @patch("api_sei.db_models.solr_select.requests.get")
    def test_timeout_error(self, mock_get):
        mock_get.side_effect = Timeout("Request timeout")

        url = "http://example.com"
        with self.assertRaises(SolrException) as context:
            SolrRequests.select(url)

        self.assertEqual(str(context.exception.detail), "Request timeout")

    @patch("api_sei.db_models.solr_select.requests.get")
    def test_non_200_status_code(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        url = "http://example.com"
        with self.assertRaises(SolrException):
            SolrRequests.select(url)

    @patch("api_sei.db_models.solr_select.requests.get")
    def test_json_decode_error(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = JSONDecodeError("JSON decode error", "", 0)
        mock_get.return_value = mock_response

        url = "http://example.com"
        with self.assertRaises(SolrException):
            SolrRequests.select(url)

    @patch("api_sei.db_models.solr_select.requests.get")
    def test_nested_field_not_found(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": {"numFound": 2},
            "docs": ["some_data"],
        }
        mock_get.return_value = mock_response

        url = "http://example.com"
        with self.assertRaises(JsonFieldException) as context:
            SolrRequests.select(url, nested_fields=["non_existent_field"])
        self.assertEqual(
            str(context.exception.detail), "Missing json field non_existent_field"
        )

    @patch(
        "api_sei.db_models.solr_select.async_solr_requests",
        new_callable=AsyncMock,
    )
    def test_async_read_timeout_returns_503_with_original_cause(
        self, mock_async_solr_requests
    ):
        timeout = httpx.ReadTimeout("read timeout")
        mock_async_solr_requests.return_value = [timeout]
        query = "http://example.com/solr/process/mlt?mlt.fl=content_id_type_doc_104"

        with (
            self.assertLogs("api_sei.db_models.solr_select", level="ERROR") as logs,
            self.assertRaises(SolrException) as context,
        ):
            SolrRequests.async_select([query], nested_fields=["interestingTerms"])

        self.assertEqual(context.exception.status_code, 503)
        self.assertIsInstance(context.exception.__cause__, httpx.ReadTimeout)
        self.assertNotIn("IndexError", str(context.exception.detail))
        self.assertTrue(any(query in entry for entry in logs.output))


if __name__ == "__main__":
    unittest.main()
