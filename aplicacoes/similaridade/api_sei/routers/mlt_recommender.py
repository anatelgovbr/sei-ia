#!/usr/bin/env python3
"""MLT Recommender Router."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Path, Query

from api_sei.middleware.custom_middleware import MiddlewareCustom
from api_sei.pydantic_models.process_recommenders import (
    RecommendationByIdProtocoloResponse as ProtResponse,
    RecommnedationByIdProtocoloResponseWithRegisterRecommendation as ProtResponseWithRegister,
)
from api_sei.pydantic_models.solr_mlt import ExtractionMethodEnum
from api_sei.services.hybrid import hwmlt_process_recommendations_service
from api_sei.services.mlt import (
    has_id_protocolo_service,
    mlt_process_recommendations_service,
    wmlt_process_recommendations_service,
)

router = APIRouter(route_class=MiddlewareCustom)

logger = logging.getLogger(__name__)


@router.get(
    "/process-recommenders/mlt-recommender/recommendations/{id_protocolo}",
    response_model=ProtResponse,
    include_in_schema=False,
)
async def mlt_process_recommendations_by_id_protocolo(
    id_protocolo: str = Path(regex=r"^\d+$"),
    rows: int = 10,
    fq: list[str] | None = Query(default=None),
    *,
    normalized: bool = Query(default=False),
    mlt_fields: list[str] | None = Query(default=None),
    mintf: int = 2,
    mindf: int = 5,
    boost: bool = Query(default=False),
    mlt_qf: str | None = Query(default=None),
) -> ProtResponse:
    """Mlt process recommendations by id_protocolo."""
    return mlt_process_recommendations_service(
        id_protocolo,
        rows,
        fq,
        normalized,
        mlt_fields,
        mintf,
        mindf,
        boost,
        mlt_qf,
        id_field="id_protocolo",
    )


@router.get(
    "/process-recommenders/weighted-mlt-recommender/recommendations/{id_protocolo}",
    response_model=ProtResponseWithRegister,
)
async def wmlt_process_recommendations_by_id_protocolo(
    id_protocolo: str = Path(regex=r"^\d+$"),
    id_user: int | None = Query(default=None),
    rows: int = 10,
    # fq: Union[List[str], None] = Query(default=None),
    *,
    debug: bool = Query(default=False),
    # extraction_method: ExtractionMethodEnum = Query(default=ExtractionMethodEnum.solr),
) -> ProtResponseWithRegister:
    """Weighted mlt process recommendations by id_protocolo."""
    return wmlt_process_recommendations_service(
        id_value=id_protocolo,
        rows=rows,
        fq=None,
        debug=debug,
        id_field="id_protocolo",
        extraction_method=ExtractionMethodEnum.solr,
        id_user=id_user,
        requested_at=datetime.now(timezone.utc),
    )


@router.get(
    "/process-recommenders/hwmlt-recommender/recommendations/{id_protocolo}",
    response_model=ProtResponse,
    include_in_schema=False,
)
async def hwmlt_process_recommendations_by_id_protocolo(
    id_protocolo: str = Path(regex=r"^\d+$"),
    rows: int = 10,
    fq: list[str] | None = Query(default=None),
    depth: int = 200,
) -> ProtResponse:
    """Hybrid weighted mlt process recommendations by id_protocolo."""
    return hwmlt_process_recommendations_service(
        id_protocolo, rows, fq, depth=depth, id_field="id_protocolo"
    )


@router.get(
    "/process-recommenders/weighted-mlt-recommender/indexed-ids/{id_protocolo}",
)
async def has_id_protocolo(id_protocolo: int) -> bool:
    """Checks if a given id_protocolo is indexed in the weighted mlt core.

    Args:
    id_protocolo (int): The id_protocolo to check.

    Returns:
    bool: True if the id_protocolo is indexed, False otherwise.
    """
    return has_id_protocolo_service(id_protocolo)
