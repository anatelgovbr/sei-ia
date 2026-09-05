"""Módulo para extração de trechos relevantes quando documentos excedem limite."""

import inspect
import logging

from sei_ia.agents.prompts.rag import INSTRUCTIONS_SOURCES, PROMPT_RAG
from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.counter import token_counter

setup_logging()
logger = logging.getLogger(__name__)


def extract_relevant_chunks(
    user_state: UserState, document_chunks: list[tuple[str, float]]
) -> str:
    """Extrai trechos relevantes respeitando limite de tokens.

    Args:
        user_state: Estado do usuário
        document_chunks: Lista de tuplas (chunk_text, similarity_score)

    Returns:
        String com trechos concatenados formatados
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    max_tokens = user_state["general_max_ctx_len"]
    user_request = user_state["user_request"]

    # Tokens já usados pelo template base
    base_prompt = PROMPT_RAG.format(
        prompt=user_request, emb_text="", instrucoes=INSTRUCTIONS_SOURCES
    )
    base_tokens = token_counter(base_prompt)

    # Tokens disponíveis para chunks
    available_tokens = max_tokens - base_tokens - 500  # margem de segurança

    logger.debug(f"Tokens disponíveis para chunks: {available_tokens}")

    selected_chunks = []
    total_chunk_tokens = 0

    # Selecionar chunks por ordem de relevância até atingir limite
    for chunk_text, similarity in document_chunks:  # noqa: B007
        chunk_tokens = token_counter(chunk_text)

        if total_chunk_tokens + chunk_tokens <= available_tokens:
            selected_chunks.append(chunk_text)
            total_chunk_tokens += chunk_tokens
            logger.debug(
                f"Chunk adicionado: {chunk_tokens} tokens, total: {total_chunk_tokens}"
            )
        else:
            logger.debug(f"Chunk ignorado (excederia limite): {chunk_tokens} tokens")
            break

    # Concatenar chunks selecionados
    emb_text = "\n\n".join(selected_chunks)

    logger.debug(
        f"Selecionados {len(selected_chunks)} chunks com {total_chunk_tokens} tokens"
    )
    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")

    return emb_text


def build_chunk_prompt(user_state: UserState, emb_text: str) -> str:
    """Constrói prompt final com chunks extraídos.

    Args:
        user_state: Estado do usuário
        emb_text: Texto dos chunks concatenados

    Returns:
        Prompt final formatado
    """
    return PROMPT_RAG.format(
        prompt=user_state["user_request"],
        emb_text=emb_text,
        instrucoes=INSTRUCTIONS_SOURCES,
    )
