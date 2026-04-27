"""Busca RAG com múltiplas perguntas de forma assíncrona."""

import asyncio
import inspect
import logging

from sei_ia.agents.rag.similarity import similarity_query
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.embedder.pipeline import embedding_generator

setup_logging()
logger = logging.getLogger(__name__)


async def search_with_multiple_questions(
    questions: list[str], user_state: UserState
) -> dict:
    """
    Executa busca RAG para cada pergunta e agrega resultados.

    Args:
        questions: Lista de perguntas para buscar
        user_state: Estado com configurações e documentos

    Returns:
        Dict com:
        - 'chunks': Lista de chunks únicos ordenados por relevância
        - 'document_ids': Set de IDs de documentos únicos encontrados
        - 'document_scores': Dict de scores por documento
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug(f"Executando busca com {len(questions)} perguntas")

    # Validação inicial
    if not questions:
        logger.warning("Lista de perguntas vazia para busca RAG")
        return {"chunks": [], "document_ids": set(), "document_scores": {}}

    # Preparar metadados dos documentos para filtro
    filter_metadata = []
    for item_proc in user_state.get("id_procedimentos", []):
        if hasattr(item_proc, "id_documentos"):
            for item_doc in item_proc.id_documentos:
                if hasattr(item_doc, "id_documento"):
                    filter_metadata.append({"id_documento": item_doc.id_documento})
                    logger.debug(
                        f"Adicionado filtro para documento: {item_doc.id_documento}"
                    )

    logger.debug(f"Filtros de metadados: {len(filter_metadata)} documentos")
    logger.debug(
        f"IDs dos documentos para filtro: {[f['id_documento'] for f in filter_metadata]}"
    )

    if not filter_metadata:
        logger.warning("Nenhum metadado de documento disponível para filtro RAG")
        return {"chunks": [], "document_ids": set(), "document_scores": {}}

    all_chunks = []
    document_ids = set()
    document_scores = {}

    # Buscar para cada pergunta de forma assíncrona
    tasks = []
    for question in questions:
        task = search_single_question(question, filter_metadata, user_state)
        tasks.append(task)

    # Executar todas as buscas em paralelo
    search_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Processar resultados
    for i, result in enumerate(search_results):
        if isinstance(result, Exception):
            logger.error(f"Erro na busca da pergunta {i}: {result}")
            continue

        chunks = result

        if not isinstance(chunks, list):
            error_msg = f"Erro: Pergunta {i} retornou tipo {type(chunks)} ao invés de lista. Valor: {chunks}"
            logger.error(error_msg)
            continue

        logger.debug(f"Pergunta {i}: encontrados {len(chunks)} chunks")

        if not chunks:
            logger.debug(f"Pergunta {i} não retornou chunks")

        for chunk in chunks:
            # Verificar se chunk é um dicionário válido
            if not isinstance(chunk, dict):
                error_msg = f"Chunk inválido: esperado dict, recebido {type(chunk)}"
                logger.error(error_msg)
                raise TypeError(error_msg)
            doc_id = chunk.get("id_documento")
            score = chunk.get("similarity_score", 0)

            all_chunks.append(chunk)
            document_ids.add(doc_id)

            # Agregar score por documento
            if doc_id not in document_scores:
                document_scores[doc_id] = []
            document_scores[doc_id].append(score)

    # Calcular score médio por documento
    for doc_id in document_scores:
        document_scores[doc_id] = sum(document_scores[doc_id]) / len(
            document_scores[doc_id]
        )

    # Remover chunks duplicados e ordenar por score
    unique_chunks = remove_duplicate_chunks(all_chunks)
    sorted_chunks = sorted(
        unique_chunks, key=lambda x: x.get("similarity_score", 0), reverse=True
    )

    logger.info(
        f"Busca múltipla retornou {len(sorted_chunks)} chunks únicos de {len(document_ids)} documentos"
    )
    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")

    return {
        "chunks": sorted_chunks,
        "document_ids": document_ids,
        "document_scores": document_scores,
    }


async def search_single_question(
    question: str, filter_metadata: list[dict], user_state: UserState
) -> list[dict]:
    """
    Executa busca para uma única pergunta.

    Args:
        question: Pergunta para buscar
        filter_metadata: Lista de filtros de metadados

    Returns:
        Lista de chunks encontrados
    """
    logger.debug(f"Buscando para pergunta: {question[:100]}...")

    if not question or not question.strip():
        logger.warning("Pergunta vazia fornecida para busca")
        return []

    try:
        prompt_emb = next(iter(embedding_generator.generate(question)))

        logger.debug(
            f"Executando similarity_query com min_similarity={settings.MIN_SIMILARITY}, top_k={settings.TOP_K_DOCUMENTS}"
        )
        retrieved_text, document_chunks_dict = await similarity_query(
            prompt_embedding=prompt_emb,
            filter_metadata=filter_metadata,
            min_similarity=settings.MIN_SIMILARITY,  # Threshold mais baixo para múltiplas perguntas
            top_k=settings.TOP_K_DOCUMENTS,  # Top K por pergunta
            user_state=user_state,
        )

        logger.debug(
            f"Resultado da busca: {len(document_chunks_dict)} documentos retornados"
        )
        logger.debug(
            f"IDs dos documentos retornados: {list(document_chunks_dict.keys())}"
        )

        chunks_list = []
        for doc_id, chunks in document_chunks_dict.items():
            for chunk in chunks:
                if isinstance(chunk, dict):
                    chunk["id_documento"] = doc_id
                    chunks_list.append(chunk)
                else:
                    # Se chunk não for dict, criar um
                    chunks_list.append(
                        {
                            "id_documento": doc_id,
                            "text": str(
                                chunk.get("text", "")
                                if hasattr(chunk, "get")
                                else chunk
                            ),
                            "similarity_score": chunk.get("cosine_similarity", 0.0)
                            if hasattr(chunk, "get")
                            else 0.0,
                        }
                    )

        logger.debug(
            f"Pergunta retornou {len(chunks_list)} chunks de {len(document_chunks_dict)} documentos"
        )
        return chunks_list

    except Exception as e:
        logger.error(f"Erro na busca da pergunta \n '{question}': {e}", exc_info=True)
        # Não lançar erro, retornar lista vazia para continuar com outras perguntas
        return []


def remove_duplicate_chunks(chunks: list[dict]) -> list[dict]:
    """
    Remove chunks duplicados baseado no conteúdo.

    Args:
        chunks: Lista de chunks que pode conter duplicatas

    Returns:
        Lista de chunks únicos
    """
    logger.debug(f"Removendo duplicatas de {len(chunks)} chunks")

    seen = set()
    unique = []

    for chunk in chunks:
        chunk_text = chunk.get("text", "")
        # Usar hash do texto para identificar duplicatas
        chunk_hash = hash(chunk_text.strip())

        if chunk_hash not in seen:
            seen.add(chunk_hash)
            unique.append(chunk)

    logger.debug(f"Mantidos {len(unique)} chunks únicos após remoção de duplicatas")
    return unique
