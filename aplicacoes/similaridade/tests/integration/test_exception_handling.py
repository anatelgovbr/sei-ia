# """Exception Handling Tests"""
# import unittest

# import psycopg2
# import pytest
# from api_sei.main import app
# from starlette.testclient import TestClient
# from requests.exceptions import Timeout
# from unittest.mock import patch


# class TestExceptionHandling(unittest.TestCase):
#     """Exception Handling Tests"""

#     def setUp(self):
#         """setUp method"""
#         self.client = TestClient(app, raise_server_exceptions=False)

#     @patch("api_sei.resources.custom_parsedquery.SolrRequests.select")
#     def test_solr_mlt_id_not_found(self, mock_requests_get):
#         """tests the return when nr_processo cannot be found"""
#         mock_requests_get.return_value = []
#         response = self.client.get(
#             "/process-recommenders/weighted-mlt-recommender/recommendations/123456"
#         )
#         print(response.text)

#         self.assertEqual(response.status_code, 404, response.text)

#     @patch("api_sei.db_models.solr_select.requests.get")
#     def test_solr_mlt_timeout(self, mock_requests_get):
#         """tests the return when timeout occurs"""
#         mock_requests_get.side_effect = Timeout
#         response = self.client.get(
#             "/process-recommenders/weighted-mlt-recommender/recommendations/123456"
#         )
#         print(response.text)

#         self.assertEqual(response.status_code, 504)

#     @patch("api_sei.resources.custom_parsedquery.read_mlt_fields_weights_json")
#     def test_solr_mlt_id_file_not_found(self, mock_requests_get):
#         """tests the return when nr_processo cannot be found"""
#         mock_requests_get.side_effect = FileNotFoundError
#         response = self.client.get(
#             "/process-recommenders/weighted-mlt-recommender/recommendations/123456"
#         )
#         err_detail = response.json().get("detail")
#         self.assertEqual("FileNotFoundError", err_detail[0])
#         self.assertIsInstance(err_detail[1], int)

#     @patch("api_sei.resources.custom_parsedquery.read_mlt_fields_weights_json")
#     def test_solr_mlt_id_file_type_error(self, mock_requests_get):
#         """tests the return when nr_processo cannot be found"""
#         mock_requests_get.side_effect = TypeError
#         response = self.client.get(
#             "/process-recommenders/weighted-mlt-recommender/recommendations/123456"
#         )
#         err_detail = response.json().get("detail")
#         self.assertEqual("TypeError", err_detail[0], str(err_detail))
#         self.assertIsInstance(err_detail[1], int)

#     @patch("api_sei.resources.custom_parsedquery.read_mlt_fields_weights_json")
#     def test_solr_mlt_id_file_type_error(self, mock_requests_get):
#         """tests the return when nr_processo cannot be found"""
#         mock_requests_get.side_effect = TypeError
#         response = self.client.get(
#             "/process-recommenders/weighted-mlt-recommender/recommendations/123456"
#         )
#         err_detail = response.json().get("detail")
#         self.assertEqual("TypeError", err_detail[0], str(err_detail))
#         self.assertIsInstance(err_detail[1], int)


# if __name__ == "__main__":
#     unittest.main()
from unittest.mock import patch

import pytest
from requests.exceptions import ConnectionError, Timeout

from api_sei.db_models.solr_select import SolrRequests
from api_sei.exception_handling.exceptions import (
    FieldInURLError,
    RowsNotFoundError,
    SolrException,
)


# Teste para FieldInURLError
def test_get_with_field_in_url_exception():
    with pytest.raises(FieldInURLError):
        SolrRequests.get("http://mock.com/solr?rows=10", [], rows=10)


# Teste para RowsNotFoundError
def test_get_with_rows_not_found_exception():
    with pytest.raises(RowsNotFoundError):
        SolrRequests.get("http://mock.com/solr", [])


# Teste para JsonFieldException
@patch("api_sei.db_models.solr_select.requests.get")
def test_get_with_json_decode_exception(mock_get):
    mock_get.return_value.json.side_effect = ValueError(
        "No JSON object could be decoded"
    )
    with pytest.raises(SolrException):
        SolrRequests.get("http://mock.com/solr", [], rows=10)


# Teste para SolrException via ConnectionError
@patch("api_sei.db_models.solr_select.requests.get")
def test_get_with_solr_exception_connection_error(mock_get):
    mock_get.side_effect = ConnectionError("Connection failed")
    with pytest.raises(SolrException):
        SolrRequests.get("http://mock.com/solr", [], rows=10)


# Teste para SolrException via Timeout
@patch("api_sei.db_models.solr_select.requests.get")
def test_get_with_solr_exception_timeout(mock_get):
    mock_get.side_effect = Timeout("The request timed out")
    with pytest.raises(SolrException):
        SolrRequests.get("http://mock.com/solr", [], rows=10)
