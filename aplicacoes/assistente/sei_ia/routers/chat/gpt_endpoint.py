"""Rota para qualquer modelo."""

import inspect  # noqa: I001
import logging

from sei_ia.configs.logging_config import setup_logging
from fastapi import APIRouter, Request
from sei_ia.routers.chat import process_chat_completion_with_model
from sei_ia.services.exceptions.http_exceptions import fast_api_responses

from sei_ia.data.pydantic_models import ChatRequestWithModel

setup_logging()
logger = logging.getLogger(__name__)

ENDPOINT_NAME = "/llm_lang/chat_gpt_general"

router = APIRouter()


@router.post(
    ENDPOINT_NAME,
    tags=["llm_lang"],
    summary="Modelo de resposta do standard with model",
    responses=fast_api_responses,
)
async def chat_completation_gpt_4o_mini_128k(
    request: ChatRequestWithModel, request_starllete: Request
) -> dict:
    """Endpoint para lidar com solicitações de resposta do modelo GPT-4 mini."""
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    result = await process_chat_completion_with_model(
        request=request,
        request_starllete=request_starllete,
        model_data={
            "model_type": "standard" if not request.use_thinking else "think",
            "endpoint_name": ENDPOINT_NAME,
            "temperature": 0.0,
        },
    )

    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
    return result
