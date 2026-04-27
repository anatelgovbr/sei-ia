from unittest.mock import MagicMock, patch

import pytest

from api_sei.exception_handling.exceptions import ResourceNotFoundException
from api_sei.resources.custom_parsedquery import (
    get_all_str_search_fields,
    init_weights_dict,
    read_fulltext_sections_fields,
    read_mlt_fields_weights,
    recursive_keys,
)


@pytest.mark.parametrize(("mlt_fields", "weights_dict", "input_dict", "expected"), [
    (["title", "content"], {}, {"title": {"fields": {}}}, {"title": {"level": 0, "weight": 1}}),
    (
        ["title", "content"],
        {},
        {"document": {"fields": {"title": {"fields": {}}}}},
        {"title": {"level": 1, "weight": 1}}
    ),
    (
        ["title", "summary"],
        {},
        {"data": {"fields": {"title": {"fields": {}}, "summary": {"fields": {}}}}},
        {"title": {"level": 1, "weight": 1}, "summary": {"level": 1, "weight": 1}}
    ),
    (
        ["title"],
        {},
        {"description": {"fields": {}}},
        {}
    )
])
def test_init_weights_dict(mlt_fields: list, weights_dict: dict, input_dict: dict, expected: dict) -> None:
    """Test the `init_weights_dict` function with different inputs.

    This function uses the `pytest.mark.parametrize` decorator to generate multiple test cases.
    Each test case consists of four parameters: `mlt_fields`, `weights_dict`, `input_dict`, and `expected`.

    The function asserts that the output of `init_weights_dict` is equal to the expected value.

    Parameters:
        mlt_fields (list): A list of strings representing the fields to be used for More Like This (MLT) query.
        weights_dict (dict): A dictionary of weights for each field.
        input_dict (dict): A dictionary representing the input data.
        expected (dict): The expected output of the `init_weights_dict` function.

    Returns:
        None
    """
    assert init_weights_dict(mlt_fields, weights_dict, input_dict) == expected  # noqa: S101


@pytest.mark.parametrize(("mlt_fields", "expected_output"), [
    (["title", "content"], {"title": {"level": 0, "weight": 1}, "content": {"level": 0, "weight": 1}}),
    ([], {})
])
def test_read_mlt_fields_weights(mlt_fields, expected_output):
    with patch("api_sei.resources.custom_parsedquery.read_mlt_fields_weights_json") as mock_read_json, \
         patch("api_sei.resources.custom_parsedquery.init_weights_dict") as mock_init_weights, \
         patch("api_sei.resources.custom_parsedquery.read_weight") as mock_read_weight:

        # Configurar os mocks
        mock_read_json.return_value = {"title": {"fields": {}}, "content": {"fields": {}}}
        mock_init_weights.return_value = {"title": {"level": 0, "weight": 1}, "content": {"level": 0, "weight": 1}}
        mock_read_weight.return_value = expected_output

        # Chamar a função sob teste
        result = read_mlt_fields_weights(mlt_fields)

        # Verificar o resultado
        assert result == expected_output, "read_mlt_fields_weights should return the correct weight dictionary"

        # Verificar se as funções foram chamadas corretamente
        mock_read_json.assert_called_once()
        mock_init_weights.assert_called_once_with(mlt_fields, {}, mock_read_json.return_value, 0)
        mock_read_weight.assert_called_once_with(mock_init_weights.return_value, mock_read_json.return_value, 0)

@pytest.mark.parametrize(("input_dict", "expected"), [
    ({"a": 1, "b": {"c": 2}}, ["a", "b", "c"]),
    ({"x": {"y": {"z": 3}}}, ["x", "y", "z"]),
    ({}, [])
])
def test_recursive_keys(input_dict: dict, expected: list) -> None:
    result = recursive_keys(input_dict, [])
    assert result == expected, "The recursive_keys function should return all keys in a nested dictionary"


@pytest.mark.parametrize(("conf_data", "expected_fulltext", "expected_sections"), [
    ({
        "content": {
            "fields": {
                "content_id_type_doc_": {
                    "fields": {
                        "text": {}, "description": {}
                    }
                }
            }
        }
    }, {"text", "description"}, set())
])
def test_read_fulltext_sections_fields(conf_data: dict, expected_fulltext: set, expected_sections: set) -> None:
    with patch("api_sei.resources.custom_parsedquery.read_mlt_fields_weights_json", return_value=conf_data):
        fulltext_fields, sections_fields = read_fulltext_sections_fields()
        assert fulltext_fields == expected_fulltext, "Should correctly parse fulltext fields"
        assert sections_fields == expected_sections, ("Should correctly parse section fields excluding reserved",
                                                      "words and fulltext fields")


@pytest.mark.parametrize(("docs", "fallback_docs", "expected_result", "raises_exception"), [
    ([{"id_protocolo": "123", "content_field": "data"}], None, [], False),
    ([], [{"id_protocolo": "123", "fallback_field": "data"}], [], False),
    ([], Exception("Fallback failed"), None, True)
])
def test_get_all_str_search_fields(docs, fallback_docs, expected_result, raises_exception):
    with patch("api_sei.db_models.solr_select.SolrRequests.get") as mock_get, \
         patch("api_sei.db_models.solr_select.SolrRequests.select") as mock_select:

        url = "http://fake-solr-url"
        nr_process = "12345"
        SEARCH_FIELDS_PREFIXES = ["content_", "fallback_"]

        mock_get.return_value = docs
        if isinstance(fallback_docs, Exception):
            mock_select.side_effect = fallback_docs
        else:
            mock_select.return_value = fallback_docs

        if raises_exception:
            with pytest.raises(ResourceNotFoundException):
                get_all_str_search_fields(nr_process, url)
        else:
            result = get_all_str_search_fields(nr_process, url)
            assert set(result) == set(expected_result), f"{result}::{expected_result}"
