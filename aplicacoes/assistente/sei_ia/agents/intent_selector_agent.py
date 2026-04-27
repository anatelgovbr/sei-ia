"""Módulo responsável pela seleção de intenção do usuário baseado no pedido."""

import inspect
import json
import logging
from typing import Literal

from sei_ia.agents.prompts.intent_selector import (
    DICT_DOCUMENTS_INTENTIONS,
    INTENT_DOCUMENTS_SELECTION_PROMPT,
)
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.exceptions.http_exceptions import HTTPException413
from sei_ia.services.llm_models.get_model import get_llm_model

setup_logging()
logger = logging.getLogger(__name__)

intent_options = Literal[
    "conversar",
    "pergunta",
    "resumo",
    "escrever",
    "reescrever",
    "multi_pergunta",
    "outras",
    "analise",
]


async def intent_selector_agent(state: UserState) -> UserState:
    """Determina a intenção do usuário com base no texto da requisição.

    Args:
        state: Estado atual contendo a requisição do usuário

    Returns:
        Um comando indicando a próxima etapa e a intenção identificada
    """
    llm = get_llm_model(
        model_type=state["model_type"],
        temperature=0.01,
        response_format={"type": "json_object"},
    )
    prompt = INTENT_DOCUMENTS_SELECTION_PROMPT.format(
        prompt=state["user_request"],
        intentions=str(DICT_DOCUMENTS_INTENTIONS).replace("{", "{{").replace("}", "}}"),
    )
    model_response = llm.invoke(prompt).content

    intent_value = None
    try:
        intent_value = json.loads(model_response).get("intencao")
    except Exception:
        logger.warning(
            "Falha ao fazer json.loads em model_response do seletor de intenção; tentando fallback"
        )
        # Fallback: tenta extrair o primeiro objeto JSON válido dentro da string
        start = model_response.find("{")
        end = model_response.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = model_response[start : end + 1]
            try:
                intent_value = json.loads(snippet).get("intencao")
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

    if intent_value not in (
        "conversar",
        "pergunta",
        "resumo",
        "escrever",
        "reescrever",
        "multi_pergunta",
        "outras",
        "analise",
    ):
        logger.warning(
            "Intenção inválida ou ausente no parsing. Usando 'outras'. model_response=%s",
            model_response[:500],
        )
        intent_value = "outras"

    state["intent"] = intent_value

    if not check_length_context(state):
        logger.debug(
            f">> {inspect.currentframe().f_code.co_name}: atingiu o limite de tokens."
        )
        msg = f"Tamanho do contexto excedido ({state['all_tokens_counter']} tokens)."
        raise HTTPException413(detail=msg)
    return state


def check_length_context(user_state: UserState) -> bool:
    """Verifica se o tamanho do contexto é maior que o limite.

    Args:
        user_state (UserState): Estado do usuário.

    Returns:
        bool: True se o tamanho do contexto é maior que o limite, considerando a intencao do usuario.
    """
    if user_state["intent"] in ("conversar", "resumo", "escrever", "outras"):
        limit_summarize = (
            settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER
            * user_state["general_max_ctx_len"]
        )
        if user_state["all_tokens_counter"] < limit_summarize:
            return True
        msg = f">> {inspect.currentframe().f_code.co_name}: atingiu o limite de sumarização ({int(limit_summarize)})."
        logger.debug(msg)

    # Para "pergunta", não verificar mais limit_false_rag (novo fluxo)
    if user_state["intent"] in ("multi_pergunta", "analise", "pergunta"):
        if user_state["all_tokens_counter"] < user_state["limit_rag"]:
            return True
        msg = (
            f">> {inspect.currentframe().f_code.co_name}: "
            f"atingiu o limite de rag ({int(user_state['limit_rag'])})."
        )
        logger.debug(msg)

    if user_state["all_tokens_counter"] > user_state["general_max_ctx_len"]:
        msg = (
            f">> {inspect.currentframe().f_code.co_name}: "
            f"atingiu o limite de contexto ({int(user_state['general_max_ctx_len'])})."
        )
        logger.debug(msg)

    return user_state["all_tokens_counter"] <= user_state["general_max_ctx_len"]
