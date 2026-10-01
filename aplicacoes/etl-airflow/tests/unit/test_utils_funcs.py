"""Tests for jobs/utils/funcs.py."""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd

from jobs.utils.funcs import (
    add_param_on_url_if_not_exists,
    check_permitted_documents,
    chunker,
    get_job_version_manager,
    group_concat_distinct,
    is_not_nan,
    regexp_replace,
    timing_decorator,
)


def test_timing_decorator_returns_wrapped_result():
    @timing_decorator
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


class TestCheckPermittedDocuments:
    def test_default_permitted(self):
        row = pd.Series({"id_tipo_procedimento": 1, "id_type_document": 7})
        assert check_permitted_documents(row, {"default": ["7"]}) is True

    def test_permitted_by_process_type(self):
        row = pd.Series({"id_tipo_procedimento": 1, "id_type_document": 9})
        permitted = {"default": [], "1": ["9"]}
        assert check_permitted_documents(row, permitted) is True

    def test_not_permitted(self):
        row = pd.Series({"id_tipo_procedimento": 1, "id_type_document": 9})
        permitted = {"default": [], "1": ["4"]}
        assert check_permitted_documents(row, permitted) is False


class TestChunker:
    def test_splits_into_chunks(self):
        assert chunker([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

    def test_empty_list(self):
        assert chunker([], 3) == []


class TestIsNotNan:
    def test_nan_float_is_false(self):
        assert is_not_nan(float("nan")) is False

    def test_regular_float_is_true(self):
        assert is_not_nan(1.5) is True

    def test_ndarray_all_nan_is_false(self):
        assert is_not_nan(np.array([np.nan, np.nan])) is False

    def test_ndarray_some_valid_is_true(self):
        assert is_not_nan(np.array([np.nan, 1.0])) is True

    def test_other_type_is_true(self):
        assert is_not_nan("some string") is True


class TestAddParamOnUrlIfNotExists:
    def test_adds_param_to_bare_url(self):
        result = add_param_on_url_if_not_exists("http://example.com", "foo", "bar")
        assert result == "http://example.com?foo=bar"

    def test_overrides_existing_param(self):
        result = add_param_on_url_if_not_exists(
            "http://example.com?foo=old", "foo", "new"
        )
        assert result == "http://example.com?foo=new"


def test_regexp_replace_strips_non_alphanumeric():
    assert regexp_replace("Olá, Mundo! 123") == "olámundo123"


class TestGroupConcatDistinct:
    def test_concatenates_unique_sorted_desc(self):
        series = pd.Series(["a", "b", "a", "c"])
        assert group_concat_distinct(series) == "c,b,a"


class TestGetJobVersionManager:
    def test_returns_id_when_result_present(self):
        connector = MagicMock()
        connector.execute_query_one.return_value = {"id": 42}
        assert get_job_version_manager(connector) == 42

    def test_returns_none_when_no_result(self):
        connector = MagicMock()
        connector.execute_query_one.return_value = None
        assert get_job_version_manager(connector) is None
