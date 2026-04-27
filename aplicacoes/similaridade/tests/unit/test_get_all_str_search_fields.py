import unittest
from unittest.mock import Mock, patch

from api_sei.resources.custom_parsedquery import get_all_str_search_fields
from api_sei.exception_handling.exceptions import ResourceNotFoundException


class TestGetAllStrSearchFields(unittest.TestCase):
    @patch("api_sei.resources.custom_parsedquery.SolrRequests.get")
    def test_valid_response(self, mock_get):
        mock_response = [
            {
                "protocolo_formatado": "123",
                "id_protocolo": "001",
                "metadata_id_unit_process_generator": "456",
                "content_id_type_doc_4": "Some description",
                "rows":10,
            }
        ]

        mock_get.return_value = mock_response
        search_fields = get_all_str_search_fields("123", "http://example.com")

        self.assertEqual(
            search_fields,
            [
                "metadata_id_unit_process_generator",
                "content_id_type_doc_4",
            ],
        )

    @patch("api_sei.resources.custom_parsedquery.SolrRequests.get")
    def test_invalid_response(self, mock_get):
        mock_response = []
        mock_get.return_value = mock_response
        with self.assertRaises(ResourceNotFoundException):
            get_all_str_search_fields("123", "http://example.com")

    # Add more tests for different cases, such as missing keys, edge cases, etc.
