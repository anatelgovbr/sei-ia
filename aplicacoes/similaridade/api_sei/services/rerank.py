import logging
from dataclasses import dataclass

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


@dataclass
class MLTConfig:
    mlt_fields: list[str] | None = None
    mintf: int = 2
    mindf: int = 5
    boost: bool = False
    mlt_qf: str | None = None


def _apply_reranking(
    response_mlt, response_knn, mlt_ids, min_score_in_top_n, normalized
):
    for item in response_knn["recommendation"]:
        if str(item["id"]) in set(mlt_ids):
            idx = mlt_ids.index(str(item["id"]))
            response_mlt["recommendation"][idx]["score"] = min_score_in_top_n + (
                (1 - min_score_in_top_n) * float(item["score"])
                if normalized
                else float(item["score"])
            )
    response_mlt["recommendation"] = sorted(
        response_mlt["recommendation"],
        key=lambda x: float(x["score"]),
        reverse=True,
    )


def rerank_process_recommendations_service(
    id_value,
    rows,
    fq,
    normalized,
    top_n=5,
    mlt_config: MLTConfig | None = None,
    rerank=True,
    vector_storage_system="pgvector",
    mlt_type="wmlt",
    id_field="id_protocolo",
):
    """Process recommendations mlt and rerank using cosine similarity on bert embeddings"""
    if mlt_config is None:
        mlt_config = MLTConfig()
    if mlt_type == "mlt":
        response_mlt, solr_mlt_service = mlt_process_recommendations_service(
            id_value,
            rows,
            fq,
            normalized,
            mlt_config.mlt_fields,
            mlt_config.mintf,
            mlt_config.mindf,
            mlt_config.boost,
            mlt_config.mlt_qf,
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

    if not response_mlt["recommendation"]:
        return response_mlt

    if rerank:
        mlt_ids = [str(item["id"]) for item in response_mlt["recommendation"]]
        response_top_n = solr_mlt_service.mlt(id_value, rows=top_n)
        top_ids = [str(item["id"]) for item in response_top_n["recommendation"]]
        min_score_in_top_n = min(
            float(item["score"]) for item in response_top_n["recommendation"]
        )

        if set(mlt_ids).intersection(set(top_ids)):
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

            _apply_reranking(
                response_mlt, response_knn, mlt_ids, min_score_in_top_n, normalized
            )

    return response_mlt
