import pytest
from unittest.mock import patch, MagicMock
from api_sei.services.embeddings import solr_embeddings_process_recommendations_service
from api_sei.pydantic_models.process_recommenders import IdField

# Mocking the SolrKnnConfigModel, SolrKnn and the response
@pytest.fixture
def mock_solr_knn():
    with patch('api_sei.services.embeddings.SolrKnn') as mock:
        instance = mock.return_value
        instance.find.return_value = "mock_vector"
        instance.knn.return_value = "mock_response_knn"
        yield mock

@pytest.fixture
def mock_solr_knn_config_model():
    with patch('api_sei.services.embeddings.SolrKnnConfigModel') as mock:
        yield mock

@pytest.fixture
def solr_knn_service(mock_solr_knn, mock_solr_knn_config_model):
    return solr_embeddings_process_recommendations_service

def test_solr_embeddings_process_recommendations_service_normalized_true(solr_knn_service):
    response = solr_knn_service(
        id_value="test_id",
        rows=10,
        fq="test_fq",
        normalized=True,
        filter_query_doc=True,
        id_field='id_protocolo'
    )
    assert response == "mock_response_knn"

def test_solr_embeddings_process_recommendations_service_normalized_false(solr_knn_service):
    with pytest.warns(UserWarning, match="embeddings recommender is always normalized"):
        response = solr_knn_service(
            id_value="test_id",
            rows=10,
            fq="test_fq",
            normalized=False,
            filter_query_doc=True,
            id_field='id_protocolo'
        )
    assert response == "mock_response_knn"

def test_solr_embeddings_process_recommendations_service_filter_query_doc_false(solr_knn_service):
    response = solr_knn_service(
        id_value="test_id",
        rows=10,
        fq="test_fq",
        normalized=True,
        filter_query_doc=False,
        id_field='id_protocolo'
    )
    assert response == "mock_response_knn"

def test_solr_embeddings_process_recommendations_service_different_id_field(solr_knn_service):
    response = solr_knn_service(
        id_value="test_id",
        rows=10,
        fq="test_fq",
        normalized=True,
        filter_query_doc=True,
        id_field=IdField.id_process
    )
    assert response == "mock_response_knn"
