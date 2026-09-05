#!/usr/bin/env python3
"""Rerank process recommendations by id_protocolo."""

import logging
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Path, Query

from api_sei.middleware.custom_middleware import MiddlewareCustom
from api_sei.pydantic_models.process_recommenders import (
    RecommendationByIdProtocoloResponse as ProtResponse,
)
from api_sei.services.rerank import MLTConfig, rerank_process_recommendations_service


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
    include_in_schema=False,
)
def rerank_process_recommendations_by_id_protocolo(
    id_protocolo: Annotated[str, Path(regex=r"^\d+$")],
    rows: int = 10,
    fq: Annotated[list[str] | None, Query()] = None,
    *,
    normalized: Annotated[bool, Query()] = True,
    top_n: int = 5,
    mlt_fields: Annotated[list[str] | None, Query()] = None,
    rerank: Annotated[bool, Query()] = True,
    mintf: int = 2,
    mindf: int = 5,
    boost: Annotated[bool, Query()] = False,
    mlt_qf: Annotated[str | None, Query()] = None,
    vector_storage_system: Annotated[
        VectorStorageSystem, Query()
    ] = VectorStorageSystem.pgvector,
    mlt_type: Annotated[MltType, Query()] = MltType.wmlt,
) -> ProtResponse:
    """Process recommendations mlt and rerank using cosine similarity on bert embeddings by id_protocolo."""
    return rerank_process_recommendations_service(
        id_protocolo,
        rows,
        fq,
        normalized,
        top_n,
        MLTConfig(
            mlt_fields=mlt_fields, mintf=mintf, mindf=mindf, boost=boost, mlt_qf=mlt_qf
        ),
        rerank,
        vector_storage_system,
        mlt_type,
        id_field="id_protocolo",
    )
