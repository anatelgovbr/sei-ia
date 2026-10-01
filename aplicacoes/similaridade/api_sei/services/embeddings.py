import warnings

from api_sei.db_models.solr_knn import SolrKnn
from api_sei.envs import SOLR_ADDRESS, SOLR_MLT_PROCESS_CORE
from api_sei.pydantic_models.process_recommenders import IdField
from api_sei.pydantic_models.solr_knn import SolrKnnConfigModel


def solr_embeddings_process_recommendations_service(
    id_value, rows, fq, normalized=True, filter_query_doc=True, id_field="id_protocolo"
):
    """Process recommendations based on cosine similarities between embeddings stored with solr"""
    if normalized is False:
        warnings.warn("embeddings recommender is always normalized", stacklevel=2)

    solr_knn_service = SolrKnn(
        SolrKnnConfigModel(
            url=f"{SOLR_ADDRESS}/solr/{SOLR_MLT_PROCESS_CORE}",
            field="embedding_full",
            id_field=IdField(id_field),
        )
    )

    vector = solr_knn_service.find(id_value)

    response_knn = solr_knn_service.knn(
        vector, solr_doc_id=(id_value if filter_query_doc else ""), rows=rows, fq=fq
    )

    return response_knn
