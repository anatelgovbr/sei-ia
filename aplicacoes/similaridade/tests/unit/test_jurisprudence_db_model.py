"""Tests for SolrJurisprudence (api_sei/db_models/jurisprudence.py)."""

from unittest.mock import patch

import pytest

from api_sei.db_models.jurisprudence import (
    BASE_URL_JURISPRUDENCE_MLT,
    BASE_URL_JURISPRUDENCE_SELECT,
    SolrJurisprudence,
)
from api_sei.exception_handling.exceptions import (
    JsonFieldException,
    ParsedQueryEmptyException,
    ResourceNotFoundException,
)


@pytest.fixture()
def sj() -> SolrJurisprudence:
    return SolrJurisprudence()


class TestGetDocs:
    def test_empty_list_short_circuits_without_solr_call(self, sj):
        with patch("api_sei.db_models.jurisprudence.SolrRequests.select") as mock_select:
            result = sj.get_docs([])
        assert result == []
        mock_select.assert_not_called()

    def test_queries_solr_with_joined_ids(self, sj):
        with patch(
            "api_sei.db_models.jurisprudence.SolrRequests.select",
            return_value=[{"id_document": "1", "score": 1.0}],
        ) as mock_select:
            result = sj.get_docs([1, 2])
        assert result == [{"id_document": "1", "score": 1.0}]
        assert mock_select.call_args.kwargs["params"]["q"] == "id_document:(1 2)"


class TestCheckHasIdDocuments:
    def test_empty_list_returns_empty_sets(self, sj):
        result = sj.check_has_id_documents([])
        assert result.id_docs_found == set()
        assert result.id_docs_not_found == set()

    def test_partitions_found_and_missing_ids(self, sj):
        with patch.object(
            sj, "get_docs", return_value=[{"id_document": "1"}, {"id_document": "2"}]
        ):
            result = sj.check_has_id_documents([1, 2, 3])
        assert result.id_docs_found == {1, 2}
        assert result.id_docs_not_found == {3}


class TestGetSolrUsingDebugQuery:
    def test_returns_parsedquery_on_success(self, sj):
        with patch(
            "api_sei.db_models.jurisprudence.SolrRequests.get",
            return_value="titulo:teste",
        ):
            result = sj.get_solr_using_debug_query(123)
        assert result == "titulo:teste"

    def test_json_field_exception_raises_resource_not_found(self, sj):
        with patch(
            "api_sei.db_models.jurisprudence.SolrRequests.get",
            side_effect=JsonFieldException(status_code=400, field="parsedquery"),
        ):
            with pytest.raises(ResourceNotFoundException):
                sj.get_solr_using_debug_query(999)


class TestGetSolrParsedquery:
    def test_blank_parsedquery_raises(self, sj):
        with pytest.raises(ParsedQueryEmptyException):
            sj.get_solr_parsedquery(parsedquery="   ", fq="")

    def test_normalizes_scores_against_max(self, sj):
        with patch(
            "api_sei.db_models.jurisprudence.SolrRequests.get",
            return_value=[
                {"id_document": "1", "score": 2.0},
                {"id_document": "2", "score": 4.0},
            ],
        ):
            result = sj.get_solr_parsedquery(
                parsedquery="titulo:teste", fq="", normalize_value=None
            )
        assert result[0]["score"] == pytest.approx(0.5)
        assert result[1]["score"] == pytest.approx(1.0)

    def test_normalizes_scores_against_given_value(self, sj):
        with patch(
            "api_sei.db_models.jurisprudence.SolrRequests.get",
            return_value=[{"id_document": "1", "score": 2.0}],
        ):
            result = sj.get_solr_parsedquery(
                parsedquery="titulo:teste", fq="", normalize_value=8.0
            )
        assert result[0]["score"] == pytest.approx(0.25)


class TestGetJurisprudence1Doc:
    def _fake_get(self, url, **kwargs):
        if url == BASE_URL_JURISPRUDENCE_MLT and kwargs.get("nested_fields") == [
            "response",
            "docs",
        ]:
            return [{"id_document": "2", "score": 8.0, "id_type_document": "7"}]
        if url == BASE_URL_JURISPRUDENCE_MLT and kwargs.get("nested_fields") == [
            "debug",
            "parsedquery",
        ]:
            return "titulo:teste"
        raise AssertionError(f"unexpected SolrRequests.get call: {url} {kwargs}")

    def _fake_select(self, url, **kwargs):  # noqa: ARG002
        if url == BASE_URL_JURISPRUDENCE_SELECT:
            return [{"id_document": "1", "score": 10.0, "id_type_document": "7"}]
        raise AssertionError(f"unexpected SolrRequests.select call: {url} {kwargs}")

    def test_returns_formatted_and_normalized_recommendation(self, sj):
        with patch(
            "api_sei.db_models.jurisprudence.SolrRequests.get", side_effect=self._fake_get
        ), patch(
            "api_sei.db_models.jurisprudence.SolrRequests.select",
            side_effect=self._fake_select,
        ):
            result = sj.get_jurisprudence_1doc(id_doc=1, rows=10, fq="")

        assert result == {"recommendation": [{"id": "2", "score": 0.8}]}

    def test_propagates_and_logs_exceptions(self, sj, caplog):
        with patch(
            "api_sei.db_models.jurisprudence.SolrRequests.get",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                sj.get_jurisprudence_1doc(id_doc=1, rows=10, fq="")
        assert "Erro em get_jurisprudence_1doc" in caplog.text


class TestGetJurisprudenceNDoc:
    def test_merges_parsedqueries_from_all_docs(self, sj):
        with patch.object(
            sj,
            "get_solr_using_debug_query",
            side_effect=["titulo:teste corpo:abc", "titulo:teste corpo:xyz"],
        ), patch.object(
            sj, "get_solr_parsedquery", return_value=[{"id": "1"}]
        ) as mock_parsedquery:
            result = sj.get_jurisprudence_ndoc(list_id_doc=[1, 2], rows=5, fq="")

        assert result == [{"id": "1"}]
        called_terms = set(mock_parsedquery.call_args.kwargs["parsedquery"].split())
        assert called_terms == {"titulo:teste", "corpo:abc", "corpo:xyz"}
        assert mock_parsedquery.call_args.kwargs["rows"] == 5
        assert mock_parsedquery.call_args.kwargs["fq"] == ""
