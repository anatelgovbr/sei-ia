"""Routers for n-embeddings recommender."""

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Path, Query

from api_sei.exception_handling.exceptions import (
    ResourceNotFoundException,
    TableEmbeddingNotFoundException,
)
from api_sei.middleware.custom_middleware import MiddlewareCustom
from api_sei.pydantic_models.document_recommenders import RecommendationResponseDocument
from api_sei.pydantic_models.n_embeddings_recommender import NEmbeddingRecomenderRequest
from api_sei.pydantic_models.process_recommenders import (
    RecommendationByIdProtocoloResponse,
)
from api_sei.services.n_embeddings import (
    NEmbeddingDocumentRecommender,
    adapter_protocolo_formatado_id_protocolo,
    get_similarity_embedding as get_similarity_embedding_service,
)

router = APIRouter(route_class=MiddlewareCustom)

logger = logging.getLogger(__name__)


@router.get(
    "/document-recommenders/n_embeddings/recommendations/{id_document}",
    include_in_schema=False,
)
async def n_embeddings_document_recommendations(
    id_document: Annotated[str, Path(..., example="135629")],
    embd_tablename: Annotated[str, Query(..., example="embd_doc_minilm_128")],
    top_k: Annotated[int, Query()] = 10,
    tp_doc_allowed: Annotated[list[int], Query(example=[])] = [],  # noqa: B006
    top_k_first_tier: Annotated[int, Query()] = 20,
) -> RecommendationResponseDocument:
    """Documment recommendation based on embeddings of chunks and compared similarity with other chunks."""
    n_embd = NEmbeddingDocumentRecommender(
        search_id=id_document,
        top_k=top_k,
        tp_doc_allowed=tp_doc_allowed,
        embd_tablename=embd_tablename,
        top_k_first_tier=top_k_first_tier,
    )
    try:
        response_docs = n_embd.run()
        recommendations = {
            "recommendation": [
                {"id": str(doc["id"]), "score": round(doc["score"], 10)}
                for doc in response_docs
            ]
        }

        json.dumps(recommendations)
    except IndexError as exc:
        raise ResourceNotFoundException(resource_name=id_document) from exc
    except TypeError as exc:
        raise TableEmbeddingNotFoundException(resource_name=embd_tablename) from exc
    return RecommendationResponseDocument(**recommendations)


@router.get(
    "/process-recommenders/similarity-embedding/recommendations/{id_protocolo}",
    include_in_schema=False,
)
async def get_similarity(
    id_protocolo: int,
    fq: Annotated[list[int], Query(example=[])] = [],  # noqa: B006
    rows: int = 10,
) -> RecommendationByIdProtocoloResponse:
    """Obtém documentos similares a um dado id_protocolo.

    Args:
        id_protocolo (int): O id do protocolo para obter documentos similares.
        fq (List[int], opcional): A lista de ids de protocolos para filtrar as recomendações. Padrão é [].
        rows (int, opcional): O número de recomendações a serem retornadas. Padrão é 10.


    Returns:
        RecommendationByIdProtocoloResponse: Um dicionário com uma única chave "recommendation" contendo uma lista de
        dicionários com duas chaves "id" e "score".
    """
    n_embeddings_recommender_request = NEmbeddingRecomenderRequest(
        id_protocolo=id_protocolo, fq=fq, rows=rows
    )

    return adapter_protocolo_formatado_id_protocolo(
        get_similarity_embedding_service,
        n_embeddings_recommender_request.id_protocolo,
        n_embeddings_recommender_request.fq,
        n_embeddings_recommender_request.rows,
    )
