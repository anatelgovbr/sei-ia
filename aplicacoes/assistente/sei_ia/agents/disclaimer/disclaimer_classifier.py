"""Node otimizado para classificação paralela da necessidade de disclaimer."""

import inspect
import json
import logging

from sei_ia.agents.prompts.disclaimer_need_identifier import (
    DICT_DISCLAIMER_CASES,
    PONDER_DISCLAIMER_ADDITION_PROMPT,
)
from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.llm_models.get_model import get_llm_model

setup_logging()
logger = logging.getLogger(__name__)


async def classify_disclaimer_need(state: UserState) -> UserState:
    """Node paralelo que apenas classifica a necessidade de disclaimer.

    Este node executa em paralelo com generate_response para otimizar o tempo
    de resposta, economizando ~1.5 segundos por requisição.

    Args:
        state: Estado do usuário contendo user_request e model_type

    Returns:
        UserState com disclaimer_case preenchido
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    llm = get_llm_model(
        model_type=state["model_type"],
        temperature=0.01,
        response_format={"type": "json_object"},
    )

    prompt = PONDER_DISCLAIMER_ADDITION_PROMPT.format(
        prompt=state["user_request"],
        intentions=str(DICT_DISCLAIMER_CASES).replace("{", "{{").replace("}", "}}"),
    )

    model_response = llm.invoke(prompt).content

    disclaimer_case = None
    try:
        disclaimer_case = json.loads(model_response).get("caso")
    except Exception:
        logger.warning(
            "Falha ao fazer json.loads em model_response do classificador de disclaimer; tentando fallback"
        )
        # Fallback: tenta extrair o primeiro objeto JSON válido dentro da string
        start = model_response.find("{")
        end = model_response.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = model_response[start : end + 1]
            try:
                disclaimer_case = json.loads(snippet).get("caso")
            except Exception:
                logger.error(
                    "Fallback de parsing JSON também falhou. model_response=%s",
                    model_response[:500],
                )
        else:
            logger.error(
                "Conteúdo sem chaves JSON aparentes. model_response=%s",
                model_response[:500],
            )

    if disclaimer_case not in (
        "orientacao_sobre_uso_do_sei",
        "totalidade_do_sei",
        "outro",
    ):
        logger.warning(
            "Caso inválido ou ausente no parsing. Usando 'outro'. model_response=%s",
            model_response[:500],
        )
        disclaimer_case = "outro"

    logger.debug(
        f">> saindo de {inspect.currentframe().f_code.co_name} com disclaimer_case={disclaimer_case}"
    )

    # Retorna apenas o campo modificado para evitar conflitos de atualização concorrente
    return {"disclaimer_case": disclaimer_case}
