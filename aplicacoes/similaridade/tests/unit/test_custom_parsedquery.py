from unittest.mock import patch

import pytest

from api_sei.exception_handling.exceptions import CustomParseValueError
from api_sei.resources.custom_parsedquery import (
    FasterCustomParsedQuery,
    divide_weight_among_subfields,
    find_subfields,
    get_all_str_search_fields,
    init_weights_dict,
    read_fulltext_sections_fields,
    read_mlt_fields_weights,
    read_weight,
    recursive_keys,
    update_weight_for_key,
)


@pytest.mark.parametrize(
    ("mlt_fields", "weights_dict", "input_dict", "expected"),
    [
        (
            ["title", "content"],
            {},
            {"title": {"fields": {}}},
            {"title": {"level": 0, "weight": 1}},
        ),
        (
            ["title", "content"],
            {},
            {"document": {"fields": {"title": {"fields": {}}}}},
            {"title": {"level": 1, "weight": 1}},
        ),
        (
            ["title", "summary"],
            {},
            {"data": {"fields": {"title": {"fields": {}}, "summary": {"fields": {}}}}},
            {"title": {"level": 1, "weight": 1}, "summary": {"level": 1, "weight": 1}},
        ),
        (["title"], {}, {"description": {"fields": {}}}, {}),
    ],
)
def test_init_weights_dict(
    mlt_fields: list, weights_dict: dict, input_dict: dict, expected: dict
) -> None:
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


@pytest.mark.parametrize(
    ("mlt_fields", "expected_output"),
    [
        (
            ["title", "content"],
            {"title": {"level": 0, "weight": 1}, "content": {"level": 0, "weight": 1}},
        ),
        ([], {}),
    ],
)
def test_read_mlt_fields_weights(mlt_fields, expected_output):
    # A configuração de pesos hoje vem do banco (ConfigMltFieldsWeights via
    # app_db.execute_query_one), não mais de um arquivo JSON.
    conf_data = {
        "title": {"weight": 1, "fields": {}},
        "content": {"weight": 1, "fields": {}},
    }
    with patch("api_sei.resources.custom_parsedquery.app_db") as mock_app_db:
        mock_app_db.execute_query_one.return_value = (1, conf_data)

        result = read_mlt_fields_weights(mlt_fields)

        assert result == expected_output, (
            "read_mlt_fields_weights should return the correct weight dictionary"
        )
        mock_app_db.execute_query_one.assert_called_once()


@pytest.mark.parametrize(
    ("input_dict", "expected"),
    [
        ({"a": 1, "b": {"c": 2}}, ["a", "b", "c"]),
        ({"x": {"y": {"z": 3}}}, ["x", "y", "z"]),
        ({}, []),
    ],
)
def test_recursive_keys(input_dict: dict, expected: list) -> None:
    result = recursive_keys(input_dict, [])
    assert result == expected, (
        "The recursive_keys function should return all keys in a nested dictionary"
    )


@pytest.mark.parametrize(
    ("conf_data", "expected_fulltext", "expected_sections"),
    [
        (
            {
                "content": {
                    "fields": {
                        "content_id_type_doc_": {
                            "fields": {"text": {}, "description": {}}
                        }
                    }
                }
            },
            {"text", "description"},
            set(),
        )
    ],
)
def test_read_fulltext_sections_fields(
    conf_data: dict, expected_fulltext: set, expected_sections: set
) -> None:
    with patch("api_sei.resources.custom_parsedquery.app_db") as mock_app_db:
        mock_app_db.execute_query_one.return_value = (1, conf_data)
        fulltext_fields, sections_fields = read_fulltext_sections_fields()
        assert fulltext_fields == expected_fulltext, (
            "Should correctly parse fulltext fields"
        )
        assert sections_fields == expected_sections, (
            "Should correctly parse section fields excluding reserved",
            "words and fulltext fields",
        )


@pytest.mark.parametrize(
    ("docs", "fallback_docs", "expected_result", "raises_exception"),
    [
        ([{"id_protocolo": "123", "content_field": "data"}], None, [], False),
        ([], [{"id_protocolo": "12345", "fallback_field": "data"}], [], False),
        ([], RuntimeError("Fallback failed"), None, True),
    ],
)
def test_get_all_str_search_fields(
    docs, fallback_docs, expected_result, raises_exception
):
    with (
        patch("api_sei.db_models.solr_select.SolrRequests.get") as mock_get,
        patch("api_sei.db_models.solr_select.SolrRequests.select") as mock_select,
    ):
        url = "http://fake-solr-url"
        nr_process = "12345"
        if docs:
            mock_get.side_effect = [docs]
        elif isinstance(fallback_docs, list):
            mock_get.side_effect = [docs, fallback_docs, fallback_docs]
        else:
            mock_get.side_effect = [docs, fallback_docs]

        if raises_exception:
            with pytest.raises(RuntimeError, match="Fallback failed"):
                get_all_str_search_fields(nr_process, url)
        else:
            result = get_all_str_search_fields(nr_process, url)
            assert set(result) == set(expected_result), f"{result}::{expected_result}"
        mock_select.assert_not_called()


class TestUpdateWeightForKey:
    def test_multiplies_weight_when_key_and_level_match(self):
        weights_dict = {"metadata_x": {"level": 1, "weight": 1.0}}
        update_weight_for_key(weights_dict, "metadata", 0.5, level=1)
        assert weights_dict["metadata_x"]["weight"] == 0.5

    def test_ignores_entries_with_different_level(self):
        weights_dict = {"metadata_x": {"level": 2, "weight": 1.0}}
        update_weight_for_key(weights_dict, "metadata", 0.5, level=1)
        assert weights_dict["metadata_x"]["weight"] == 1.0

    def test_ignores_entries_without_key_substring(self):
        weights_dict = {"content_x": {"level": 1, "weight": 1.0}}
        update_weight_for_key(weights_dict, "metadata", 0.5, level=1)
        assert weights_dict["content_x"]["weight"] == 1.0


class TestDivideWeightAmongSubfields:
    def test_divides_weight_equally(self):
        weights_dict = {
            "content_id_type_doc_1": {"level": 1, "weight": 1.0},
            "content_id_type_doc_2": {"level": 1, "weight": 1.0},
        }
        divide_weight_among_subfields(
            weights_dict,
            "content_id_type_doc_",
            ["content_id_type_doc_1", "content_id_type_doc_2"],
        )
        assert weights_dict["content_id_type_doc_1"]["weight"] == 0.5
        assert weights_dict["content_id_type_doc_2"]["weight"] == 0.5

    def test_ignores_unrelated_keys(self):
        weights_dict = {"metadata_x": {"level": 1, "weight": 1.0}}
        divide_weight_among_subfields(weights_dict, "content_id_type_doc_", ["a", "b"])
        assert weights_dict["metadata_x"]["weight"] == 1.0


class TestFindSubfields:
    def test_finds_matching_level_and_key(self):
        weights_dict = {
            "content_id_type_doc_1": {"level": 1, "weight": 1.0},
            "content_id_type_doc_2": {"level": 2, "weight": 1.0},
        }
        result = find_subfields(weights_dict, "content_id_type_doc_", level=1)
        assert result == ["content_id_type_doc_1"]

    def test_includes_fields_present_in_out_key(self):
        weights_dict = {"content_id_type_doc_1_teste": {"level": 1, "weight": 1.0}}
        result = find_subfields(
            weights_dict, "content_id_type_doc_", level=1, fields=["teste"]
        )
        assert "teste" in result


class TestReadWeightVariableSubfields:
    def test_divides_weight_among_variable_subfields(self):
        weights_dict = {
            "metadata_name_id_type_doc_1": {"level": 1, "weight": 1.0},
            "metadata_name_id_type_doc_2": {"level": 1, "weight": 1.0},
        }
        d = {
            "metadata_name_id_type_doc_": {
                "weight": 1.0,
                "variable_subfields": 1,
            }
        }
        result = read_weight(weights_dict, d, level=0)
        assert result["metadata_name_id_type_doc_1"]["weight"] == 0.5
        assert result["metadata_name_id_type_doc_2"]["weight"] == 0.5


def _bare_faster_custom_parsed_query(**attrs) -> FasterCustomParsedQuery:
    """Instancia FasterCustomParsedQuery sem rodar __init__ (que faz chamadas ao Solr)."""
    instance = object.__new__(FasterCustomParsedQuery)
    instance.id_protocolo = "422762"
    instance.base_url = "http://fakehost:0000/solr/process"
    instance.maxqt_per_field = 25
    for key, value in attrs.items():
        setattr(instance, key, value)
    return instance


class TestGetFieldGroupsAndRequestTypes:
    def test_speed_1_returns_all_fields_multiple(self):
        instance = _bare_faster_custom_parsed_query(
            all_fields=["metadata_x", "content_y"]
        )
        groups, request_types = instance._get_field_groups_and_request_types(1)
        assert groups == [["metadata_x", "content_y"]]
        assert request_types == ["multiple"]

    def test_speed_2_splits_metadata_and_content(self):
        instance = _bare_faster_custom_parsed_query(
            all_fields=["metadata_x", "content_y"]
        )
        groups, request_types = instance._get_field_groups_and_request_types(2)
        assert groups == [["metadata_x"], ["content_y"]]
        assert request_types == ["single", "multiple"]

    def test_speed_3_splits_metadata_and_content_single(self):
        instance = _bare_faster_custom_parsed_query(
            all_fields=["metadata_x", "content_y"]
        )
        groups, request_types = instance._get_field_groups_and_request_types(3)
        assert groups == [["metadata_x"], ["content_y"]]
        assert request_types == ["single", "single"]

    def test_speed_4_returns_all_fields_single(self):
        instance = _bare_faster_custom_parsed_query(
            all_fields=["metadata_x", "content_y"]
        )
        groups, request_types = instance._get_field_groups_and_request_types(4)
        assert groups == [["metadata_x", "content_y"]]
        assert request_types == ["single"]

    def test_invalid_speed_level_raises(self):
        # Speed(speed_level) ja levanta ValueError para valores fora do enum,
        # antes mesmo de chegar no "else: raise CustomParseValueError" do metodo
        # (esse branch e inalcancavel na pratica).
        instance = _bare_faster_custom_parsed_query(all_fields=[])
        with pytest.raises(ValueError, match="99 is not a valid Speed"):
            instance._get_field_groups_and_request_types(99)


class TestProcessRequestType:
    def test_single_delegates_to_execute_single_request(self):
        instance = _bare_faster_custom_parsed_query()
        with patch.object(
            instance, "_execute_single_request", return_value=["x"]
        ) as mock_single:
            result = instance._process_request_type(
                field_group=["a"], request_type="single", raw_maxqt=1024, parallel=False
            )
        assert result == ["x"]
        mock_single.assert_called_once_with(["a"], 1024)

    def test_multiple_delegates_to_execute_multiple_requests(self):
        instance = _bare_faster_custom_parsed_query()
        with patch.object(
            instance, "_execute_multiple_requests", return_value=["y"]
        ) as mock_multiple:
            result = instance._process_request_type(
                field_group=["a"],
                request_type="multiple",
                raw_maxqt=1024,
                parallel=True,
            )
        assert result == ["y"]
        mock_multiple.assert_called_once_with(field_group=["a"], parallel=True)

    def test_invalid_request_type_raises(self):
        instance = _bare_faster_custom_parsed_query()
        with pytest.raises(CustomParseValueError):
            instance._process_request_type(
                field_group=["a"],
                request_type="invalid",
                raw_maxqt=1024,
                parallel=False,
            )


class TestSortTerms:
    def test_sorts_by_value_descending(self):
        instance = _bare_faster_custom_parsed_query()
        it = ["term_a", 1.0, "term_b", 3.0, "term_c", 2.0]
        result = instance.sort_terms(it)
        assert result == ["term_b", 3.0, "term_c", 2.0, "term_a", 1.0]

    def test_empty_list(self):
        instance = _bare_faster_custom_parsed_query()
        assert instance.sort_terms([]) == []


class TestExecuteSingleAndMultipleRequests:
    def test_execute_single_request_calls_solr_get(self):
        instance = _bare_faster_custom_parsed_query()
        with patch(
            "api_sei.resources.custom_parsedquery.SolrRequests.get",
            return_value=["metadata_x:term", 1.0],
        ) as mock_get:
            result = instance._execute_single_request(["metadata_x"], raw_maxqt=1024)
        assert result == ["metadata_x:term", 1.0]
        mock_get.assert_called_once()
        assert mock_get.call_args.args[1] == ["interestingTerms"]

    def test_execute_multiple_requests_sequential(self):
        instance = _bare_faster_custom_parsed_query()
        with patch(
            "api_sei.resources.custom_parsedquery.SolrRequests.get",
            side_effect=[["metadata_x:a", 1.0], ["metadata_y:b", 2.0]],
        ) as mock_get:
            result = instance._execute_multiple_requests(
                field_group=["metadata_x", "metadata_y"], parallel=False
            )
        assert result == ["metadata_x:a", 1.0, "metadata_y:b", 2.0]
        assert mock_get.call_count == 2

    def test_execute_multiple_requests_parallel_uses_async_select(self):
        instance = _bare_faster_custom_parsed_query()
        with patch(
            "api_sei.resources.custom_parsedquery.SolrRequests.async_select",
            return_value=[["metadata_x:a", 1.0], ["metadata_y:b", 2.0]],
        ) as mock_async_select:
            result = instance._execute_multiple_requests(
                field_group=["metadata_x", "metadata_y"], parallel=True
            )
        assert result == ["metadata_x:a", 1.0, "metadata_y:b", 2.0]
        mock_async_select.assert_called_once()
        async_queries = mock_async_select.call_args.args[0]
        assert all("&rows=0" in query for query in async_queries)

    def test_execute_multiple_requests_single_field_skips_parallel(self):
        instance = _bare_faster_custom_parsed_query()
        with patch(
            "api_sei.resources.custom_parsedquery.SolrRequests.get",
            return_value=["metadata_x:a", 1.0],
        ) as mock_get:
            result = instance._execute_multiple_requests(
                field_group=["metadata_x"], parallel=True
            )
        assert result == ["metadata_x:a", 1.0]
        mock_get.assert_called_once()


class TestGetAllFields:
    def test_delegates_to_get_all_str_search_fields(self):
        instance = _bare_faster_custom_parsed_query()
        with patch(
            "api_sei.resources.custom_parsedquery.get_all_str_search_fields",
            return_value=["metadata_x"],
        ) as mock_search_fields:
            result = instance.get_all_fields()
        assert result == ["metadata_x"]
        mock_search_fields.assert_called_once_with(
            "422762", "http://fakehost:0000/solr/process", id_field="id_protocolo"
        )
