import logging

from api_sei.services.embeddings import solr_embeddings_process_recommendations_service
from api_sei.services.mlt import (
    mlt_process_recommendations_service,
    wmlt_process_recommendations_service,
)
from api_sei.services.n_embeddings import (
    adapter_protocolo_formatado_id_protocolo,
    get_similarity_embedding as get_similarity_embedding_service,
)

logger = logging.getLogger(__name__)


def rerank_process_recommendations_service(
    id_value,
    rows,
    fq,
    normalized,
    top_n=5,
    mlt_fields=None,
    mintf=2,
    mindf=5,
    boost=False,
    mlt_qf=None,
    rerank=True,
    vector_storage_system="pgvector",
    mlt_type="wmlt",
    id_field="id_protocolo",
):
    """Process recommendations mlt and rerank using cosine similarity on bert embeddings"""
    if mlt_type == "mlt":
        response_mlt, solr_mlt_service = mlt_process_recommendations_service(
            id_value,
            rows,
            fq,
            normalized,
            mlt_fields,
            mintf,
            mindf,
            boost,
            mlt_qf,
            True,
            id_field,
        )
    elif mlt_type == "wmlt":
        response_mlt, solr_mlt_service = wmlt_process_recommendations_service(
            id_value,
            rows,
            fq,
            normalized,
            False,
            True,
            "fulltext_parsedquery_t",
            id_field,
        )
    else:
        raise ValueError(mlt_type)

    if rerank:
        mlt_ids = [str(item["id"]) for item in response_mlt["recommendation"]]

        # Searching top n
        response_top_n = solr_mlt_service.mlt(id_value, rows=top_n)
        top_ids = [str(item["id"]) for item in response_top_n["recommendation"]]
        min_score_in_top_n = min(
            float(item["score"]) for item in response_top_n["recommendation"]
        )

        mlt_ids_top_ids_intersection = set(mlt_ids).intersection(set(top_ids))

        if len(mlt_ids_top_ids_intersection) > 0:
            if vector_storage_system == "solr":
                response_knn = solr_embeddings_process_recommendations_service(
                    id_value, top_n, top_ids, filter_query_doc=False, id_field=id_field
                )
            elif vector_storage_system == "pgvector":
                response_knn = adapter_protocolo_formatado_id_protocolo(
                    get_similarity_embedding_service, id_value, top_ids, top_n
                )
            else:
                raise ValueError(vector_storage_system)

            for item in response_knn["recommendation"]:
                if str(item["id"]) in set(mlt_ids):
                    idx = mlt_ids.index(str(item["id"]))
                    response_mlt["recommendation"][idx]["score"] = (
                        min_score_in_top_n
                        + (
                            (1 - min_score_in_top_n) * float(item["score"])
                            if normalized
                            else float(item["score"])
                        )
                    )

            response_mlt["recommendation"] = sorted(
                response_mlt["recommendation"],
                key=lambda x: float(x["score"]),
                reverse=True,
            )

    return response_mlt
