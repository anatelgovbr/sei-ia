"""Endpoint para healthcheck."""

import logging

from fastapi import APIRouter, status
from pydantic import BaseModel

from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings

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
    response_model=HealthCheck,
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


@api_router.get(
    "/health/websearch",
    tags=["health"],
    summary="Check Environment Variables Configuration",
    response_description="Return true if environment variables are configured",
    status_code=status.HTTP_200_OK,
)
def check_env_config() -> bool:
    """## Check Environment Variables Configuration.

    Verifica se as variáveis de ambiente necessárias para o Azure Web Search
    estão configuradas corretamente.

    Variáveis verificadas:
    - PROJECT_ENDPOINT
    - BING_CONNECTION_NAME
    - MODEL_DEPLOYMENT_NAME
    """

    logger.debug("Verificando configuração das variáveis de ambiente")

    is_configured = all(
        [
            settings.PROJECT_ENDPOINT and settings.PROJECT_ENDPOINT.strip(),
            settings.BING_CONNECTION_NAME and settings.BING_CONNECTION_NAME.strip(),
            settings.MODEL_DEPLOYMENT_NAME and settings.MODEL_DEPLOYMENT_NAME.strip(),
        ]
    )

    logger.debug(f"Variáveis configuradas: {is_configured}")
    logger.debug(f"PROJECT_ENDPOINT: {bool(settings.PROJECT_ENDPOINT)}")
    logger.debug(f"BING_CONNECTION_NAME: {bool(settings.BING_CONNECTION_NAME)}")
    logger.debug(f"MODEL_DEPLOYMENT_NAME: {bool(settings.MODEL_DEPLOYMENT_NAME)}")

    return is_configured
