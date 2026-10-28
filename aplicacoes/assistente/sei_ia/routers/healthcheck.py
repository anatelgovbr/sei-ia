"""Endpoint para healthcheck."""

import logging

from fastapi import APIRouter, status
from pydantic import BaseModel

from sei_ia.configs.logging_config import setup_logging

setup_logging()

logger = logging.getLogger(__name__)

api_router = APIRouter()


class HealthCheck(BaseModel):
    """Response model to perform a health check."""

    status: str = "OK"


@api_router.get(
    "/health",
    tags=["health"],
    summary="Perform a Health Check",
    response_description="Return HTTP Status Code 200 (OK)",
    status_code=status.HTTP_200_OK,
)
def get_health() -> HealthCheck:
    """## Perform a Health Check.

    Endpoint to perform a healthcheck on. This endpoint can primarily
    be used Docker to ensure a robust container orchestration and
    management is in place. Other services which rely on proper
    functioning of the API service will not deploy if this
    endpoint returns any other HTTP status code except 200 (OK).

    Returns:
        HealthCheck: Returns a JSON response with the health status
    """
    logger.debug("Entrou em /health")
    return HealthCheck(status="OK")
