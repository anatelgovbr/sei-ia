"""Tests for api_sei/services/citations_search.py."""

from unittest.mock import patch

from api_sei.services.citations_search import (
    add_citations,
    get_doc_content,
    get_docs_in_doc,
    get_regex_citations,
    get_regex_citations2,
)


class TestGetDocContent:
    def test_returns_first_doc_content(self):
        with patch(
            "api_sei.services.citations_search.SolrRequests.select",
            return_value=[{"content": "texto aqui"}],
        ):
            assert get_doc_content(123) == "texto aqui"


class TestGetDocsInDoc:
    def test_finds_seven_digit_ids_surrounded_by_non_digits(self):
        result = get_docs_in_doc(
            "veja o documento 1234567 e tambem 7654321a e x9876543"
        )
        assert result == ["1234567", "7654321", "9876543"]

    def test_returns_empty_list_when_no_matches(self):
        assert get_docs_in_doc("sem numeros aqui") == []

    def test_ignores_numbers_with_wrong_digit_count(self):
        assert get_docs_in_doc("codigo 123456 e 12345678") == []


class TestGetRegexCitations:
    def test_finds_resolucao_and_acordao_windows(self):
        text = (
            "nos termos da resolução número 123 de 2020 sobre telecomunicações, "
            "e tambem o acórdão 456 do tribunal."
        )
        result = get_regex_citations(text, max_words=3)
        assert len(result) == 2
        assert result[0][0].lower().startswith("resolução")
        assert result[1][0].lower().startswith("acórdão")

    def test_returns_empty_when_no_citation_keywords(self):
        assert get_regex_citations("texto sem citações relevantes", max_words=3) == []


class TestGetRegexCitations2:
    def test_finds_citation_window_lowercased(self):
        text = "nos termos da resolução número 123 de 2020 sobre telecomunicações."
        result = get_regex_citations2(text, max_words=3)
        assert len(result) == 1
        assert result[0][0].startswith("resolução")
        assert result[0][1:] == (0, 0)

    def test_returns_empty_when_no_citation_keywords(self):
        assert get_regex_citations2("texto sem citações relevantes", max_words=3) == []


class TestAddCitations:
    def test_adds_citations_matching_by_sorted_id_and_sorts_result_by_score_desc(self):
        docs = [
            {"id_document": 2, "score": 0.5},
            {"id_document": 1, "score": 0.9},
        ]
        with patch(
            "api_sei.services.citations_search.get_doc_content_lazy",
            return_value=[
                {"id_document": "1", "content": "resolução número um dois"},
                {"id_document": "2", "content": "acórdão numero tres quatro"},
            ],
        ) as mock_content:
            result = add_citations(docs)

        assert mock_content.call_args.kwargs["list_id_docs"] == ["1", "2"]
        assert [d["id_document"] for d in result] == [1, 2]
        assert result[0]["citations"][0][0].startswith("resolução")
        assert result[1]["citations"][0][0].startswith("acórdão")
