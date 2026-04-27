"""Rota para o modelo mini.

NOTA: O nome do endpoint contém "gpt_4o_mini" por razões históricas (legado).
Este endpoint utiliza o modelo "mini" configurado em settings.
A família GPT-4o não é mais utilizada diretamente - o model_type "mini"
é mapeado para o modelo atual definido na configuração do Azure OpenAI.
"""

import inspect  # noqa: I001
import logging

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import ChatRequest
from fastapi import APIRouter, Request
from sei_ia.routers.chat import process_chat_completion
from sei_ia.services.exceptions.http_exceptions import fast_api_responses

setup_logging()
logger = logging.getLogger(__name__)

ENDPOINT_NAME = "/llm_lang/chat_gpt_4o_mini_128k"

router = APIRouter()


@router.post(
    ENDPOINT_NAME,
    tags=["llm_lang"],
    summary="Chat com modelo mini (nome do endpoint é legado)",
    responses=fast_api_responses,
)
async def chat_completation_gpt_4o_mini_128k(
    request: ChatRequest, request_starllete: Request
) -> dict:
    """Endpoint para chat usando o modelo 'mini'.

    NOTA: O nome "gpt_4o_mini_128k" é legado. Este endpoint usa model_type="mini",
    que é mapeado para o modelo atual configurado no Azure OpenAI.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    result = await process_chat_completion(
        request=request,
        request_starllete=request_starllete,
        model_data={
            "model_type": "mini" if not request.use_thinking else "think",
            "endpoint_name": ENDPOINT_NAME,
            "temperature": 0.0,
        },
    )

    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
    return result
