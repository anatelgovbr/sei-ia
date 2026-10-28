"""Tests for api_sei/services/jurisprudence.py."""

from datetime import datetime, timezone
from unittest.mock import patch

from api_sei.exception_handling.exceptions import ParsedQueryEmptyException
from api_sei.pydantic_models.jurisprudence import FoundIdsDocs
from api_sei.services.jurisprudence import _compute_normalize_value, doc2doc_search

MODULE = "api_sei.services.jurisprudence"


class TestComputeNormalizeValue:
    def test_returns_one_when_not_normalized(self):
        found = FoundIdsDocs(id_docs_found=set(), id_docs_not_found=set())
        assert _compute_normalize_value(False, "parsedquery", found, "") == 1

    def test_returns_one_when_parsedquery_is_blank(self):
        found = FoundIdsDocs(id_docs_found=set(), id_docs_not_found=set())
        assert _compute_normalize_value(True, "   ", found, "") == 1

    def test_scores_using_not_found_and_found_docs_and_text(self):
        found = FoundIdsDocs(id_docs_found={1}, id_docs_not_found={2})
        with patch(
            f"{MODULE}.get_tokenized_docs",
            return_value=[{"content": ["tok_a"]}],
        ) as mock_tokenized, patch(
            f"{MODULE}.solr_jurisprudence.get_docs",
            return_value=[{"content": "raw text"}],
        ) as mock_get_docs, patch(
            f"{MODULE}.solr_preprocessing", return_value=["tok_b"]
        ) as mock_preprocess, patch(
            f"{MODULE}.get_doc_score", return_value=0.75
        ) as mock_score:
            result = _compute_normalize_value(True, "some parsedquery", found, "texto")

        assert result == 0.75
        mock_tokenized.assert_called_once_with({2})
        mock_get_docs.assert_called_once_with({1}, fl="id_document,content")
        assert mock_preprocess.call_count == 2
        mock_score.assert_called_once()


class TestDoc2DocSearch:
    def _base_patches(self, **overrides):
        found_docs = overrides.pop(
            "found_docs", FoundIdsDocs(id_docs_found=set(), id_docs_not_found=set())
        )
        patches = {
            "build_filter": patch(f"{MODULE}.build_filter", return_value="fq_string"),
            "check_has_id_documents": patch(
                f"{MODULE}.solr_jurisprudence.check_has_id_documents",
                return_value=found_docs,
            ),
            "get_tokenized_docs": patch(
                f"{MODULE}.get_tokenized_docs", return_value=[{"content": ["a"]}]
            ),
            "extract_parsedquery": patch(
                f"{MODULE}.extract_parsedquery", return_value="pq_not_found"
            ),
            "get_solr_using_debug_query": patch(
                f"{MODULE}.solr_jurisprudence.get_solr_using_debug_query",
                return_value="pq_found",
            ),
            "get_parsedquery_from_string": patch(
                f"{MODULE}.get_parsedquery_from_string", return_value="pq_from_text"
            ),
            "merge_unweighted_parsed_queries": patch(
                f"{MODULE}.merge_unweighted_parsed_queries", return_value="pq_merged"
            ),
            "get_doc_score": patch(f"{MODULE}.get_doc_score", return_value=1.0),
            "solr_preprocessing": patch(f"{MODULE}.solr_preprocessing", return_value=[]),
            "get_solr_parsedquery": patch(
                f"{MODULE}.solr_jurisprudence.get_solr_parsedquery",
                return_value=[{"id": "1", "score": 1.0}],
            ),
            "add_citations": patch(
                f"{MODULE}.add_citations", return_value=[{"id": "1", "score": 1.0}]
            ),
            "add_mlt_document_recommendation": patch(
                f"{MODULE}.add_mlt_document_recommendation", return_value=42
            ),
        }
        for key, value in overrides.items():
            patches[key] = patch(f"{MODULE}.{value[0]}", **value[1])
        return patches

    def test_returns_recommendation_with_no_ids_and_no_text(self):
        patches = self._base_patches()
        with patches["build_filter"], patches["check_has_id_documents"], patches[
            "get_tokenized_docs"
        ], patches["extract_parsedquery"], patches[
            "get_solr_using_debug_query"
        ], patches["get_doc_score"], patches["solr_preprocessing"], patches[
            "get_solr_parsedquery"
        ] as mock_get_pq, patches["add_mlt_document_recommendation"] as mock_add:
            result = doc2doc_search(
                list_id_doc=[],
                list_type_id_doc=None,
                id_user=None,
                rows=10,
            )

        assert result == {"id_recommendation": 42, "recommendation": [{"id": "1", "score": 1.0}]}
        mock_get_pq.assert_called_once()
        mock_add.assert_called_once()

    def test_applies_list_type_id_doc_filter(self):
        found_docs = FoundIdsDocs(id_docs_found=set(), id_docs_not_found=set())
        patches = self._base_patches(found_docs=found_docs)
        with patches["build_filter"], patches["check_has_id_documents"], patches[
            "get_tokenized_docs"
        ], patches["extract_parsedquery"], patches[
            "get_solr_using_debug_query"
        ], patches["get_doc_score"], patches["solr_preprocessing"], patches[
            "get_solr_parsedquery"
        ] as mock_get_pq, patches["add_mlt_document_recommendation"]:
            doc2doc_search(
                list_id_doc=[1],
                list_type_id_doc=[4, 7],
                id_user=None,
                rows=10,
            )

        fq_used = mock_get_pq.call_args.kwargs["fq"]
        assert "id_type_document:( 4 7 )" in fq_used
        assert "fq_string" in fq_used

    def test_uses_not_found_and_found_docs_to_build_parsedquery(self):
        found_docs = FoundIdsDocs(id_docs_found={1}, id_docs_not_found={2})
        patches = self._base_patches(found_docs=found_docs)
        with patches["build_filter"], patches["check_has_id_documents"], patches[
            "get_tokenized_docs"
        ] as mock_tokenized, patches[
            "extract_parsedquery"
        ] as mock_extract, patches[
            "get_solr_using_debug_query"
        ] as mock_debug_query, patches["get_doc_score"], patches[
            "solr_preprocessing"
        ], patches["get_solr_parsedquery"] as mock_get_pq, patches[
            "add_mlt_document_recommendation"
        ]:
            doc2doc_search(
                list_id_doc=[1, 2],
                list_type_id_doc=None,
                id_user=None,
                rows=10,
            )

        mock_tokenized.assert_called_once_with({2})
        mock_extract.assert_called_once()
        mock_debug_query.assert_called_once_with(1)
        assert mock_get_pq.call_args.kwargs["parsedquery"] == "pq_not_found pq_found"

    def test_uses_text_when_no_id_based_parsedquery_found(self):
        patches = self._base_patches()
        with patches["build_filter"], patches["check_has_id_documents"], patches[
            "get_tokenized_docs"
        ], patches["extract_parsedquery"], patches[
            "get_solr_using_debug_query"
        ], patches["get_parsedquery_from_string"] as mock_from_text, patches[
            "merge_unweighted_parsed_queries"
        ] as mock_merge, patches["get_doc_score"], patches[
            "solr_preprocessing"
        ], patches["get_solr_parsedquery"] as mock_get_pq, patches[
            "add_mlt_document_recommendation"
        ]:
            doc2doc_search(
                list_id_doc=[],
                list_type_id_doc=None,
                id_user=None,
                rows=10,
                text="processo administrativo",
            )

        mock_from_text.assert_called_once_with("processo administrativo")
        mock_merge.assert_not_called()
        assert mock_get_pq.call_args.kwargs["parsedquery"] == "pq_from_text"

    def test_merges_text_with_existing_parsedquery(self):
        found_docs = FoundIdsDocs(id_docs_found={1}, id_docs_not_found=set())
        patches = self._base_patches(found_docs=found_docs)
        with patches["build_filter"], patches["check_has_id_documents"], patches[
            "get_tokenized_docs"
        ], patches["extract_parsedquery"], patches[
            "get_solr_using_debug_query"
        ], patches["get_parsedquery_from_string"] as mock_from_text, patches[
            "merge_unweighted_parsed_queries"
        ] as mock_merge, patches["get_doc_score"], patches[
            "solr_preprocessing"
        ], patches["get_solr_parsedquery"] as mock_get_pq, patches[
            "add_mlt_document_recommendation"
        ]:
            doc2doc_search(
                list_id_doc=[1],
                list_type_id_doc=None,
                id_user=None,
                rows=10,
                text="texto complementar",
                text_weight=0.3,
            )

        mock_from_text.assert_called_once_with("texto complementar")
        mock_merge.assert_called_once_with(["pq_found", "pq_from_text"], [0.7, 0.3])
        assert mock_get_pq.call_args.kwargs["parsedquery"] == "pq_merged"

    def test_returns_empty_list_when_parsedquery_is_empty(self):
        patches = self._base_patches()
        with patches["build_filter"], patches["check_has_id_documents"], patches[
            "get_tokenized_docs"
        ], patches["extract_parsedquery"], patches[
            "get_solr_using_debug_query"
        ], patches["get_doc_score"], patches["solr_preprocessing"], patch(
            f"{MODULE}.solr_jurisprudence.get_solr_parsedquery",
            side_effect=ParsedQueryEmptyException(),
        ), patches["add_mlt_document_recommendation"] as mock_add:
            result = doc2doc_search(
                list_id_doc=[],
                list_type_id_doc=None,
                id_user=None,
                rows=10,
            )

        assert result["recommendation"] == []
        assert mock_add.call_args.kwargs["recommendation"] == {"recommendation": []}

    def test_includes_citations_when_requested(self):
        patches = self._base_patches()
        with patches["build_filter"], patches["check_has_id_documents"], patches[
            "get_tokenized_docs"
        ], patches["extract_parsedquery"], patches[
            "get_solr_using_debug_query"
        ], patches["get_doc_score"], patches["solr_preprocessing"], patches[
            "get_solr_parsedquery"
        ], patches["add_citations"] as mock_citations, patches[
            "add_mlt_document_recommendation"
        ]:
            doc2doc_search(
                list_id_doc=[],
                list_type_id_doc=None,
                id_user=None,
                rows=10,
                include_citations=True,
            )

        mock_citations.assert_called_once_with([{"id": "1", "score": 1.0}])

    def test_defaults_fq_and_requested_at_when_not_given(self):
        patches = self._base_patches()
        with patches["build_filter"] as mock_filter, patches[
            "check_has_id_documents"
        ], patches["get_tokenized_docs"], patches["extract_parsedquery"], patches[
            "get_solr_using_debug_query"
        ], patches["get_doc_score"], patches["solr_preprocessing"], patches[
            "get_solr_parsedquery"
        ], patches["add_mlt_document_recommendation"] as mock_add:
            doc2doc_search(
                list_id_doc=[],
                list_type_id_doc=None,
                id_user=7,
                rows=10,
                fq=None,
                requested_at=None,
            )

        mock_filter.assert_called_once()
        assert mock_add.call_args.kwargs["fq"] == []
        assert isinstance(mock_add.call_args.kwargs["requested_at"], datetime)

    def test_forwards_given_requested_at_and_id_user(self):
        patches = self._base_patches()
        fixed_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with patches["build_filter"], patches["check_has_id_documents"], patches[
            "get_tokenized_docs"
        ], patches["extract_parsedquery"], patches[
            "get_solr_using_debug_query"
        ], patches["get_doc_score"], patches["solr_preprocessing"], patches[
            "get_solr_parsedquery"
        ], patches["add_mlt_document_recommendation"] as mock_add:
            doc2doc_search(
                list_id_doc=[],
                list_type_id_doc=None,
                id_user=99,
                rows=10,
                requested_at=fixed_time,
            )

        assert mock_add.call_args.kwargs["requested_at"] == fixed_time
        assert mock_add.call_args.kwargs["id_user"] == 99
