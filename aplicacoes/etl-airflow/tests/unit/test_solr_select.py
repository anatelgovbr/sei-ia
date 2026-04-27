import unittest
from unittest.mock import Mock, patch

from requests import JSONDecodeError, Timeout

from jobs.db_models.solr_handlers import SolrHandlers


class TestSolrHandlers(unittest.TestCase):
    @patch("jobs.db_models.solr_select.requests.get")
    def test_successful_select(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "some_data"}
        mock_get.return_value = mock_response

        url = "http://example.com"
        result = SolrHandlers.get(url=url, rows=1)

        self.assertEqual(result, {"data": "some_data"}, )

    @patch("jobs.db_models.solr_select.requests.get")
    def test_timeout_error(self, mock_get):
        mock_get.side_effect = Timeout("Request timeout")

        url = "http://example.com"
        with self.assertRaises(Exception) as context:
            SolrHandlers.select(url)

            self.assertEqual(str(context.exception), "Request timeout", str(context.exception))

    @patch("jobs.db_models.solr_select.requests.get")
    def test_non_200_status_code(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        url = "http://example.com"
        with self.assertRaises(Exception):
            SolrHandlers.select(url)

    @patch("jobs.db_models.solr_select.requests.get")
    def test_json_decode_error(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = JSONDecodeError("JSON decode error", "", 0)
        mock_get.return_value = mock_response

        url = "http://example.com"
        with self.assertRaises(Exception):
            SolrHandlers.select(url)

    @patch("jobs.db_models.solr_select.requests.get")
    def test_nested_field_not_found(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "some_data"}
        mock_get.return_value = mock_response

        url = "http://example.com"
        with self.assertRaises(Exception) as context:
            SolrHandlers.select(url=url, nested_fields=["non_existent_field"])

        self.assertEqual(str(context.exception), "JsonFieldException() takes no keyword arguments")
