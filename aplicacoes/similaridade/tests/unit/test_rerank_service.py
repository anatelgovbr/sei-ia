"""Tests for api_sei/services/rerank.py."""

from unittest.mock import MagicMock, patch

import pytest

from api_sei.services.rerank import (
    _apply_reranking,
    rerank_process_recommendations_service,
)


class TestApplyReranking:
    def test_normalized_rescales_score_between_min_and_one(self):
        response_mlt = {
            "recommendation": [
                {"id": "1", "score": 0.9},
                {"id": "2", "score": 0.5},
                {"id": "3", "score": 0.3},
            ]
        }
        response_knn = {"recommendation": [{"id": "2", "score": 0.9}]}
        _apply_reranking(
            response_mlt,
            response_knn,
            ["1", "2", "3"],
            min_score_in_top_n=0.3,
            normalized=True,
        )
        by_id = {r["id"]: r["score"] for r in response_mlt["recommendation"]}
        assert by_id["2"] == pytest.approx(0.3 + 0.7 * 0.9)

    def test_non_normalized_adds_min_score_offset(self):
        response_mlt = {
            "recommendation": [{"id": "1", "score": 0.9}, {"id": "2", "score": 0.5}]
        }
        response_knn = {"recommendation": [{"id": "2", "score": 0.9}]}
        _apply_reranking(
            response_mlt,
            response_knn,
            ["1", "2"],
            min_score_in_top_n=0.3,
            normalized=False,
        )
        by_id = {r["id"]: r["score"] for r in response_mlt["recommendation"]}
        assert by_id["2"] == pytest.approx(1.2)

    def test_ignores_knn_items_not_in_mlt_ids(self):
        response_mlt = {"recommendation": [{"id": "1", "score": 0.9}]}
        response_knn = {"recommendation": [{"id": "99", "score": 0.9}]}
        _apply_reranking(
            response_mlt, response_knn, ["1"], min_score_in_top_n=0.3, normalized=True
        )
        assert response_mlt["recommendation"][0]["score"] == 0.9

    def test_result_is_sorted_by_score_descending(self):
        response_mlt = {
            "recommendation": [
                {"id": "1", "score": 0.5},
                {"id": "2", "score": 0.9},
            ]
        }
        _apply_reranking(
            response_mlt,
            {"recommendation": []},
            ["1", "2"],
            min_score_in_top_n=0.3,
            normalized=True,
        )
        assert [r["id"] for r in response_mlt["recommendation"]] == ["2", "1"]


class TestRerankProcessRecommendationsService:
    def test_mlt_type_mlt_dispatches_to_mlt_service_with_config(self):
        with patch(
            "api_sei.services.rerank.mlt_process_recommendations_service"
        ) as mock_mlt:
            mock_mlt.return_value = ({"recommendation": []}, MagicMock())
            rerank_process_recommendations_service(
                1, 10, None, True, mlt_type="mlt", rerank=False
            )

        assert mock_mlt.call_args.args == (
            1,
            10,
            None,
            True,
            None,
            2,
            5,
            False,
            None,
            True,
            "id_protocolo",
        )

    def test_mlt_type_wmlt_dispatches_to_wmlt_service(self):
        with patch(
            "api_sei.services.rerank.wmlt_process_recommendations_service"
        ) as mock_wmlt:
            mock_wmlt.return_value = ({"recommendation": []}, MagicMock())
            rerank_process_recommendations_service(
                1, 10, None, True, mlt_type="wmlt", rerank=False
            )

        assert mock_wmlt.call_args.args == (
            1,
            10,
            None,
            True,
            False,
            True,
            "fulltext_parsedquery_t",
            "id_protocolo",
        )

    def test_unknown_mlt_type_raises_value_error(self):
        with pytest.raises(ValueError, match="bogus"):
            rerank_process_recommendations_service(
                1, 10, None, True, mlt_type="bogus", rerank=False
            )

    def test_rerank_false_returns_mlt_response_unmodified(self):
        mock_service = MagicMock()
        with patch(
            "api_sei.services.rerank.wmlt_process_recommendations_service"
        ) as mock_wmlt:
            mock_wmlt.return_value = (
                {"recommendation": [{"id": "1", "score": 0.9}]},
                mock_service,
            )
            result = rerank_process_recommendations_service(
                1, 10, None, True, rerank=False
            )

        assert result == {"recommendation": [{"id": "1", "score": 0.9}]}
        mock_service.mlt.assert_not_called()

    def test_empty_mlt_response_returns_without_reranking(self):
        mock_service = MagicMock()
        with patch(
            "api_sei.services.rerank.wmlt_process_recommendations_service"
        ) as mock_wmlt:
            mock_wmlt.return_value = ({"recommendation": []}, mock_service)

            result = rerank_process_recommendations_service(
                1, 10, None, True, rerank=True
            )

        assert result == {"recommendation": []}
        mock_service.mlt.assert_not_called()

    def test_rerank_skips_knn_when_no_intersection(self):
        mock_service = MagicMock()
        mock_service.mlt.return_value = {"recommendation": [{"id": "99", "score": 0.9}]}
        with (
            patch(
                "api_sei.services.rerank.wmlt_process_recommendations_service"
            ) as mock_wmlt,
            patch(
                "api_sei.services.rerank.adapter_protocolo_formatado_id_protocolo"
            ) as mock_adapter,
        ):
            mock_wmlt.return_value = (
                {
                    "recommendation": [
                        {"id": "1", "score": 0.9},
                        {"id": "2", "score": 0.5},
                    ]
                },
                mock_service,
            )
            result = rerank_process_recommendations_service(
                1, 10, None, True, rerank=True, vector_storage_system="pgvector"
            )

        mock_adapter.assert_not_called()
        assert result == {
            "recommendation": [{"id": "1", "score": 0.9}, {"id": "2", "score": 0.5}]
        }

    def test_rerank_pgvector_calls_adapter_and_reorders(self):
        mock_service = MagicMock()
        mock_service.mlt.return_value = {"recommendation": [{"id": "2", "score": 0.9}]}
        with (
            patch(
                "api_sei.services.rerank.wmlt_process_recommendations_service"
            ) as mock_wmlt,
            patch(
                "api_sei.services.rerank.adapter_protocolo_formatado_id_protocolo"
            ) as mock_adapter,
        ):
            mock_wmlt.return_value = (
                {
                    "recommendation": [
                        {"id": "1", "score": 0.9},
                        {"id": "2", "score": 0.5},
                    ]
                },
                mock_service,
            )
            mock_adapter.return_value = {"recommendation": [{"id": "2", "score": 0.95}]}
            result = rerank_process_recommendations_service(
                1,
                10,
                None,
                True,
                top_n=5,
                rerank=True,
                vector_storage_system="pgvector",
            )

        assert mock_adapter.call_args.args[1:] == (1, ["2"], 5)
        assert result["recommendation"][0]["id"] == "2"

    def test_rerank_solr_calls_solr_embeddings_service(self):
        mock_service = MagicMock()
        mock_service.mlt.return_value = {"recommendation": [{"id": "2", "score": 0.9}]}
        with (
            patch(
                "api_sei.services.rerank.wmlt_process_recommendations_service"
            ) as mock_wmlt,
            patch(
                "api_sei.services.rerank.solr_embeddings_process_recommendations_service"
            ) as mock_solr_emb,
        ):
            mock_wmlt.return_value = (
                {
                    "recommendation": [
                        {"id": "1", "score": 0.9},
                        {"id": "2", "score": 0.5},
                    ]
                },
                mock_service,
            )
            mock_solr_emb.return_value = {
                "recommendation": [{"id": "2", "score": 0.95}]
            }
            rerank_process_recommendations_service(
                1, 10, None, True, top_n=5, rerank=True, vector_storage_system="solr"
            )

        mock_solr_emb.assert_called_once_with(
            1, 5, ["2"], filter_query_doc=False, id_field="id_protocolo"
        )

    def test_unknown_vector_storage_system_raises_value_error(self):
        mock_service = MagicMock()
        mock_service.mlt.return_value = {"recommendation": [{"id": "2", "score": 0.9}]}
        with patch(
            "api_sei.services.rerank.wmlt_process_recommendations_service"
        ) as mock_wmlt:
            mock_wmlt.return_value = (
                {
                    "recommendation": [
                        {"id": "1", "score": 0.9},
                        {"id": "2", "score": 0.5},
                    ]
                },
                mock_service,
            )
            with pytest.raises(ValueError, match="bogus"):
                rerank_process_recommendations_service(
                    1, 10, None, True, rerank=True, vector_storage_system="bogus"
                )
