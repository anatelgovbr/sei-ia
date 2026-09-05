"""Rota para o modelo mini.

NOTA: O nome do endpoint contém "gpt_4o_mini" por razões históricas (legado).
A família GPT-4o não é mais utilizada diretamente. O endpoint precisa
continuar no tier "mini" (`agent_tag` determina o tier físico — ver
AGENT_TAG_TO_TIER em services/llm_models/get_model.py), mas nenhuma das duas
tags do mini (`agents:classificador`/`agents:busca_web`) descreve de
verdade esse uso (resposta direta a um chamador externo, não um passo interno
do pipeline). Usa `agents:classificador` como decisão provisória só pra manter
o tier certo — revisar com o time se vale criar uma tag própria no
litellm_config.template.yaml.
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

    NOTA: O nome "gpt_4o_mini_128k" é legado. Este endpoint usa o tier "mini"
    (`agent_tag="classificador"` — ver nota do módulo), mapeado para o modelo
    atual configurado no Azure OpenAI.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    result = await process_chat_completion(
        request=request,
        request_starllete=request_starllete,
        model_data={
            "agent_tag": "classificador",
            "endpoint_name": ENDPOINT_NAME,
        },
    )

    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
    return result
