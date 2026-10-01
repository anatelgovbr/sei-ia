from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

from api_sei.services.n_embeddings import (
    EmbeddingDocument,
    NEmbeddingDocumentRecommender,
    NEmbeddingDocumentSimilarity,
    SimilarityMean,
    get_similarity_embedding,
)


class TestSimilarityMean:
    def test_calc_similarity_returns_mean(self):
        similarity = SimilarityMean(chunks_dist=[])
        result = similarity.calc_similarity(np.array([0.2, 0.4, 0.6]))
        assert result == pytest.approx(0.4)

    def test_get_maxsim_chunks_converts_distance_to_similarity(self):
        similarity = SimilarityMean(chunks_dist=[[0.1, 0.3], [0.5]])
        result = similarity.get_maxsim_chunks()
        # 1-x por chunk, depois o maximo de cada grupo
        assert np.allclose(result, [0.9, 0.5])

    def test_calc_combines_maxsim_and_mean(self):
        similarity = SimilarityMean(chunks_dist=[[0.0], [0.0]])
        assert similarity.calc() == pytest.approx(1.0)


class TestEmbeddingDocument:
    def test_stores_fields(self):
        doc = EmbeddingDocument(
            id_processo="1", id_documento="2", tp_documento=7, embds=[np.array([1.0])]
        )
        assert doc.id_processo == "1"
        assert doc.id_documento == "2"
        assert doc.tp_documento == 7
        assert len(doc.embds) == 1


class TestNEmbeddingDocumentSimilarity:
    def test_dist_cosine_chunks_queries_app_db_per_embd(self):
        doc_search = EmbeddingDocument(
            id_processo="1", id_documento="10", tp_documento=1, embds=[np.array([1.0]), np.array([2.0])]
        )
        doc_compare = EmbeddingDocument(
            id_processo="2", id_documento="20", tp_documento=1, embds=[np.array([3.0])]
        )
        fake_df = pd.DataFrame({"dist_cosine": [0.1]})

        with patch("api_sei.services.n_embeddings.app_db") as mock_app_db:
            mock_app_db.get_dataframe.return_value = fake_df
            similarity = NEmbeddingDocumentSimilarity(
                doc_search=doc_search, doc_compare=doc_compare, embd_tablename="embd_doc_x"
            )

        assert mock_app_db.get_dataframe.call_count == 2
        assert similarity.similarity == pytest.approx(0.9)


class TestNEmbeddingDocumentRecommender:
    def _recommender(self, **overrides):
        defaults = {
            "search_id": 1,
            "tp_doc_allowed": [],
            "embd_tablename": "embd_doc_x",
            "top_k": 2,
            "top_k_first_tier": 10,
        }
        defaults.update(overrides)
        return NEmbeddingDocumentRecommender(**defaults)

    def test_get_search_embds_from_db_builds_embedding_document(self):
        fake_df = pd.DataFrame(
            {
                "id_processo": ["100"],
                "id_documento": ["1"],
                "tp_documento": [7],
                "embd": [np.array([1.0, 2.0])],
            }
        )
        recommender = self._recommender()
        with patch("api_sei.services.n_embeddings.app_db") as mock_app_db:
            mock_app_db.get_dataframe.return_value = fake_df
            doc = recommender.get_search_embds_from_db(id_documento=1)

        assert doc.id_processo == "100"
        assert doc.id_documento == "1"
        assert doc.tp_documento == 7

    def test_recommend_sorts_by_score_desc_and_limits_top_k(self):
        recommender = self._recommender(top_k=2)
        doc_search = EmbeddingDocument("1", "1", 1, [np.array([0.0])])
        compare_docs = [
            EmbeddingDocument("2", "2", 1, [np.array([0.0])]),
            EmbeddingDocument("3", "3", 1, [np.array([0.0])]),
            EmbeddingDocument("4", "4", 1, [np.array([0.0])]),
        ]

        similarities = iter([0.5, 0.9, 0.1])

        class _FakeSimilarity:
            def __init__(self, *args, **kwargs):  # noqa: ARG002
                self.similarity = next(similarities)

        with patch("api_sei.services.n_embeddings.NEmbeddingDocumentSimilarity", _FakeSimilarity):
            result = recommender.recommend(doc_search, compare_docs)

        assert len(result) == 2
        assert result[0] == {"id": "3", "score": 0.9}
        assert result[1] == {"id": "2", "score": 0.5}

    def test_search_first_tier_documents_without_validacao(self):
        recommender = self._recommender(top_k_first_tier=1)
        query_embd = EmbeddingDocument("1", "1", 1, [np.array([0.0])])
        fake_df = pd.DataFrame(
            {"id_documento": [2, 3], "dist_cosine": [0.5, 0.1]}
        )

        with patch("api_sei.services.n_embeddings.app_db") as mock_app_db:
            mock_app_db.get_dataframe.return_value = fake_df
            result = recommender._search_first_tier_documents(query_embd)

        assert list(result["id_documento"]) == [3]

    def test_search_first_tier_documents_with_validacao(self):
        recommender = self._recommender(top_k_first_tier=5)
        query_embd = EmbeddingDocument("1", "1", 1, [np.array([0.0])])
        fake_df = pd.DataFrame(
            {"id_documento": [2, 3], "dist_cosine": [0.3, 0.2]}
        )

        with patch("api_sei.services.n_embeddings.app_db") as mock_app_db:
            mock_app_db.get_dataframe.return_value = fake_df
            result = recommender._search_first_tier_documents(query_embd, validacao=[2, 3])

        assert set(result["id_documento"]) == {2, 3}

    def test_run_returns_empty_when_no_first_tier_docs(self):
        recommender = self._recommender()
        with patch.object(
            recommender, "get_search_embds_from_db", return_value=MagicMock()
        ), patch.object(
            recommender, "_search_first_tier_documents", return_value=pd.DataFrame()
        ):
            result = recommender.run()

        assert result == []

    def test_run_builds_recommendations_from_first_tier_docs(self):
        recommender = self._recommender(top_k=1)
        doc_search = MagicMock()
        first_tier_df = pd.DataFrame({"id_documento": [10, 20]})

        with patch.object(
            recommender, "get_search_embds_from_db", return_value=doc_search
        ) as mock_get_embds, patch.object(
            recommender, "_search_first_tier_documents", return_value=first_tier_df
        ), patch.object(
            recommender, "recommend", return_value=[{"id": 10, "score": 0.9}]
        ) as mock_recommend:
            result = recommender.run()

        assert result == [{"id": 10, "score": 0.9}]
        # 1 chamada para o doc de busca + 2 chamadas para os docs de comparacao
        assert mock_get_embds.call_count == 3
        mock_recommend.assert_called_once()


class TestGetSimilarityEmbedding:
    def test_delegates_to_resource_on_valid_input(self):
        with patch(
            "api_sei.services.n_embeddings.get_similarity_embedding_resource",
            return_value={"recommendation": []},
        ) as mock_resource:
            result = get_similarity_embedding(id_processo=1, list_id_processos=[1, 2], rows=10)

        assert result == {"recommendation": []}
        mock_resource.assert_called_once_with(id_processo=1, list_id_processos=[1, 2], rows=10)

    def test_invalid_id_processo_raises_400(self):
        with pytest.raises(HTTPException) as excinfo:
            get_similarity_embedding(id_processo="not-an-int", list_id_processos=[1], rows=10)
        assert excinfo.value.status_code == 400

    def test_invalid_list_id_processos_raises_400(self):
        with pytest.raises(HTTPException) as excinfo:
            get_similarity_embedding(id_processo=1, list_id_processos="not-a-list", rows=10)
        assert excinfo.value.status_code == 400
