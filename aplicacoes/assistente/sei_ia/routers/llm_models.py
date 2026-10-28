"""Endpoint para consultar o catálogo de modelos do LiteLLM Proxy (nome + tipo de agente)."""

import logging

from fastapi import APIRouter, HTTPException, status

from sei_ia.configs.logging_config import setup_logging
from sei_ia.services.llm_models.model_catalog import (
    ModelCatalogEntry,
    get_model_catalog,
)

setup_logging()

logger = logging.getLogger(__name__)

api_router = APIRouter()


@api_router.get(
    "/models",
    tags=["llm-models"],
    summary="Lista os modelos disponíveis no LiteLLM Proxy e o tipo de agente de cada um",
    response_description="Nomes dos modelos e as tags agents:<papel> declaradas em cada um",
    status_code=status.HTTP_200_OK,
)
def get_models() -> dict[str, list[ModelCatalogEntry]]:
    """## Catálogo de modelos.

    Consulta `GET /model/info` no proxy LiteLLM e devolve, para cada entrada
    do `model_list`, o `model_name` e as `tags` (`agents:<papel>`) declaradas
    em `litellm_params.tags` no `litellm_config.yaml`.
    """
    logger.debug("Entrou em /models")
    try:
        return {"models": get_model_catalog()}
    except Exception as err:
        logger.exception("Falha ao consultar o catálogo de modelos no proxy LiteLLM")
        msg = "Não foi possível consultar o catálogo de modelos no proxy LiteLLM."
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=msg
        ) from err
