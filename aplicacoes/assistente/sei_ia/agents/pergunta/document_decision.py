"""Decisão entre documentos completos ou chunks baseado no tamanho."""

import inspect
import logging

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.counter import token_counter

setup_logging()
logger = logging.getLogger(__name__)


def check_if_complete_documents_fit(
    document_ids: set[str], user_state: UserState
) -> tuple[bool, int]:
    """
    Verifica se os documentos completos dos IDs retornados cabem no contexto.

    Args:
        document_ids: Set de IDs de documentos encontrados pelo RAG
        user_state: Estado com configurações e documentos

    Returns:
        Tuple[bool, int]: (cabem_no_contexto, total_tokens)
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug(f"Verificando se {len(document_ids)} documentos cabem no contexto")

    total_tokens = 0
    documents_found = 0

    # Somar tokens de todos os documentos únicos
    for proc in user_state["id_procedimentos"]:
        for doc in proc.id_documentos:
            if doc.id_documento in document_ids:
                documents_found += 1
                total_tokens += doc.doc_tokens

    max_ctx_len = user_state["general_max_ctx_len"]
    fits = total_tokens <= max_ctx_len

    logger.info(
        f"Documentos completos: {documents_found} docs, {total_tokens} tokens, "
        f"Limite: {max_ctx_len}, Cabem: {fits}"
    )
    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")

    return fits, total_tokens


def calculate_max_chunks(chunks: list, user_state: UserState) -> int:
    """
    Calcula quantos chunks cabem no contexto disponível.

    Args:
        chunks: Lista de chunks ordenados por relevância
        user_state: Estado com configurações

    Returns:
        Número máximo de chunks que cabem no contexto
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug(f"Calculando máximo de chunks para {len(chunks)} chunks disponíveis")

    max_tokens = user_state["general_max_ctx_len"]
    total_tokens = 0
    max_chunks = 0

    # Contar tokens da pergunta do usuário (estimativa)
    user_request_tokens = token_counter(user_state["user_request"])
    total_tokens += user_request_tokens

    # Adicionar margem para formatação do prompt (tags, metadados, etc)
    formatting_margin = 500  # Margem conservadora para tags e metadados
    total_tokens += formatting_margin

    logger.debug(f"Tokens base (pergunta + formatação): {total_tokens}")

    for i, chunk in enumerate(chunks):
        chunk_text = chunk.get("text", "")
        chunk_tokens = token_counter(chunk_text)

        # Adicionar margem por chunk para metadados
        chunk_with_metadata_tokens = chunk_tokens + 50  # Tags por chunk

        if total_tokens + chunk_with_metadata_tokens <= max_tokens:
            total_tokens += chunk_with_metadata_tokens
            max_chunks += 1
            logger.debug(
                f"Chunk {i}: +{chunk_with_metadata_tokens} tokens, total: {total_tokens}"
            )
        else:
            logger.debug(
                f"Chunk {i}: excederia limite ({total_tokens + chunk_with_metadata_tokens} > {max_tokens})"
            )
            break

    logger.info(
        f"Máximo de chunks que cabem: {max_chunks} de {len(chunks)} disponíveis"
    )
    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")

    return max_chunks
