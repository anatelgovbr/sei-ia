from unittest.mock import patch

import pytest
import requests

from api_sei.resources.custom_parsedquery import get_all_str_search_fields
from api_sei.exception_handling.exceptions import ResourceNotFoundException



@patch('api_sei.resources.custom_parsedquery.SolrRequests.get')
def test_get_all_str_search_fields_success(mock_get):
    mock_response = [
        {"id_process": "123", "content_id_type_doc_4": "sample content", "other_field": "data", "rows":10}
    ]

    mock_get.return_value = mock_response

    result = get_all_str_search_fields("123", "http://mocktest.com")

    assert result == ["content_id_type_doc_4"]

@patch('api_sei.resources.custom_parsedquery.SolrRequests.get')
def test_get_all_str_search_fields_empty_response(mock_get):
    mock_response = []
    mock_get.return_value = mock_response

    with pytest.raises(ResourceNotFoundException):
        get_all_str_search_fields("456", "http://mocktest.com")

@patch('api_sei.resources.custom_parsedquery.SolrRequests.get')
def test_get_all_str_search_fields_exception(mock_get):
    mock_get.side_effect = requests.exceptions.RequestException()

    with pytest.raises(Exception):
        get_all_str_search_fields("789", "http://mocktest.com")

