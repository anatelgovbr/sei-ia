"""Módulo usado para RAG em documentos do SEI."""

import logging

from sei_ia.agents.prompts.rag import INSTRUCTIONS_SOURCES, PROMPT_RAG
from sei_ia.agents.rag.similarity import similarity_query
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.embedder.pipeline import (
    check_reindex_embedding,
    embedding_generator,
    indexing_embeddings,
)

setup_logging()

logger = logging.getLogger(__name__)


async def async_make_prompt_with_rag(user_state: UserState) -> UserState:
    """Versão assíncrona da função para gerar um prompt usando o modelo RAG.

    Args:
        user_state (UserState): estado do usuário.

    Returns:
        UserState: O estado do usuário atualizado com o prompt gerado.
    """
    logger.debug("entrou no async_make_prompt_with_rag")
    filter_metadata = []

    for item_proc in user_state["id_procedimentos"]:
        for item_doc in item_proc.id_documentos:
            filter_metadata.append({"id_documento": item_doc.id_documento})

    reindex_ids = await check_reindex_embedding(
        [f["id_documento"] for f in filter_metadata]
    )
    if len(reindex_ids) > 0:
        await indexing_embeddings(reindex_ids, user_state)
    prompt_emb = next(iter(embedding_generator.generate(user_state["user_request"])))
    retrive_doc, document_chunks = await similarity_query(
        prompt_embedding=prompt_emb,
        filter_metadata=filter_metadata,
        min_similarity=settings.MIN_SIMILARITY,
        top_k=settings.TOP_K_DOCUMENTS,
        user_state=user_state,
    )
    logger.debug("saiu do async_make_prompt_with_rag")
    last_prompt = PROMPT_RAG.format(
        prompt=user_state["user_request"],
        emb_text=retrive_doc,
        instrucoes=INSTRUCTIONS_SOURCES,
    )
    user_state["last_prompt"] = last_prompt
    user_state["doc_rag"] = True
    return user_state
