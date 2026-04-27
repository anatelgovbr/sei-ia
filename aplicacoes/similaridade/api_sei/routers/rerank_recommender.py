#!/usr/bin/env python3
"""Rerank process recommendations by id_protocolo."""

import logging
from enum import Enum

from fastapi import APIRouter, Path, Query

from api_sei.middleware.custom_middleware import MiddlewareCustom
from api_sei.pydantic_models.process_recommenders import (
    RecommendationByIdProtocoloResponse as ProtResponse,
)
from api_sei.services.rerank import rerank_process_recommendations_service


class VectorStorageSystem(str, Enum):
    """Vector storage system."""

    solr = "solr"
    pgvector = "pgvector"


class MltType(str, Enum):
    """mlt type."""

    mlt = "mlt"
    wmlt = "wmlt"


router = APIRouter(route_class=MiddlewareCustom)

logger = logging.getLogger(__name__)


@router.get(
    "/process-recommenders/rerank-recommender/recommendations/{id_protocolo}",
    response_model=ProtResponse,
    include_in_schema=False,
)
async def rerank_process_recommendations_by_id_protocolo(
    id_protocolo: str = Path(regex=r"^\d+$"),
    rows: int = 10,
    fq: list[str] | None = Query(default=None),
    *,
    normalized: bool = Query(default=True),
    top_n: int = 5,
    mlt_fields: list[str] | None = Query(default=None),
    rerank: bool = Query(default=True),
    mintf: int = 2,
    mindf: int = 5,
    boost: bool = Query(default=False),
    mlt_qf: str | None = Query(default=None),
    vector_storage_system: VectorStorageSystem = Query(default="pgvector"),
    mlt_type: MltType = Query(default="wmlt"),
) -> ProtResponse:
    """Process recommendations mlt and rerank using cosine similarity on bert embeddings by id_protocolo."""
    return rerank_process_recommendations_service(
        id_protocolo,
        rows,
        fq,
        normalized,
        top_n,
        mlt_fields,
        mintf,
        mindf,
        boost,
        mlt_qf,
        rerank,
        vector_storage_system,
        mlt_type,
        id_field="id_protocolo",
    )
