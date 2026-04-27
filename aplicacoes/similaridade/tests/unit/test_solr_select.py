import unittest
from unittest.mock import Mock, patch

from requests import JSONDecodeError, Timeout

from api_sei.db_models.solr_select import SolrRequests
from api_sei.exception_handling.exceptions import JsonFieldException, SolrException


class TestSolrSelect(unittest.TestCase):
    @patch("api_sei.db_models.solr_select.requests.get")
    def test_successful_select(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": { "numFound": 2, "docs": ["some_data"]}}
        mock_get.return_value = mock_response

        url = "http://example.com"
        result = SolrRequests.select(url , nested_fields=["response","docs"])

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
        with self.assertRaises(Exception):
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
        mock_response.json.return_value = {"response":{ "numFound": 2},"docs":["some_data"]}
        mock_get.return_value = mock_response

        url = "http://example.com"
        with self.assertRaises(JsonFieldException) as context:
            SolrRequests.select(url, nested_fields=["non_existent_field"])
        self.assertEqual(str(context.exception.detail), "Missing json field non_existent_field")

if __name__ == "__main__":
    unittest.main()