"""Módulo para indexação automática de documentos faltantes no RAG."""

import asyncio
import inspect
import logging

from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.embedder.pipeline import indexing_embeddings
from sei_ia.services.exceptions.embedding_exceptions import (
    AutoIndexingException,
    DocumentContentNotExtractableException,
)
from sei_ia.services.exceptions.rag_exceptions import EmbeddingVerificationException

_indexing_semaphore = asyncio.Semaphore(settings.EMBEDDINGS_MAX_CONCURRENCY)

setup_logging()
logger = logging.getLogger(__name__)


def _aggregate_indexing_failures(errors: list[Exception]) -> AutoIndexingException:
    for error in errors:
        logger.error(
            "Falha em lote de indexação automática: %s",
            type(error).__name__,
            exc_info=(type(error), error, error.__traceback__),
        )

    content_errors = [
        error
        for error in errors
        if isinstance(error, DocumentContentNotExtractableException)
    ]
    document_ids = [
        error.document_id for error in content_errors if error.document_id is not None
    ]
    return AutoIndexingException(
        content_failure_count=len(content_errors),
        document_ids=document_ids,
        internal_failure_count=len(errors) - len(content_errors),
    )


def _find_available_docs(missing_document_ids: list[str], user_state) -> list[str]:
    available = []
    for proc in user_state.get("id_procedimentos", []):
        if hasattr(proc, "id_documentos"):
            for doc in proc.id_documentos:
                if (
                    hasattr(doc, "id_documento")
                    and doc.id_documento in missing_document_ids
                ):
                    available.append(doc.id_documento)
    return available


async def auto_index_missing_documents(
    missing_document_ids: list[str],
    user_state: UserState,
) -> None:
    """
    Executa indexação automática dos documentos faltantes em lotes com controle de concorrência.

    Args:
        missing_document_ids: Lista de IDs de documentos que precisam ser indexados
        user_state: Estado do usuário contendo os documentos
        batch_size: Tamanho do lote para indexação

    Raises:
        EmbeddingVerificationException: Se houver erro na indexação
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.info(
        f"Iniciando indexação automática de {len(missing_document_ids)} documentos"
    )
    logger.debug(
        f"IDs para indexar: {missing_document_ids[:10]}..."
        if len(missing_document_ids) > 10
        else f"IDs para indexar: {missing_document_ids}"
    )

    if not missing_document_ids:
        logger.warning("Lista de documentos para indexar está vazia")
        return

    try:
        available_docs = _find_available_docs(missing_document_ids, user_state)
        missing_in_state = set(missing_document_ids) - set(available_docs)
        if missing_in_state:
            logger.warning(
                f"Documentos não encontrados no user_state: {len(missing_in_state)} de {len(missing_document_ids)}"
            )

        if not available_docs:
            raise EmbeddingVerificationException(
                f"Nenhum dos {len(missing_document_ids)} documentos está disponível no user_state para indexação"
            )

        logger.info(f"Documentos disponíveis para indexação: {len(available_docs)}")

        # Dividir em lotes se necessário
        if len(available_docs) > settings.SEI_API_SEMAPHORE:
            logger.info(
                f"Indexando em lotes de {settings.SEI_API_SEMAPHORE} documentos"
            )
            await index_documents_in_batches(
                available_docs, user_state, settings.SEI_API_SEMAPHORE
            )
        else:
            logger.info("Indexando todos os documentos em lote único")
            await index_single_batch(available_docs, user_state)

        logger.info(
            f"✓ Indexação automática concluída com sucesso para {len(available_docs)} documentos"
        )
        logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")

    except AutoIndexingException:
        raise
    except Exception as e:
        raise _aggregate_indexing_failures([e]) from e


async def index_documents_in_batches(
    document_ids: list[str], user_state: UserState, batch_size: int
) -> None:
    """
    Indexa documentos em lotes com controle de concorrência.

    Args:
        document_ids: Lista de IDs de documentos
        user_state: Estado do usuário
        batch_size: Tamanho de cada lote
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    # Dividir em lotes
    batches = [
        document_ids[i : i + batch_size]
        for i in range(0, len(document_ids), batch_size)
    ]
    logger.info(f"Criados {len(batches)} lotes de até {batch_size} documentos")

    # Executar lotes com semáforo para controlar concorrência
    tasks = []
    for i, batch in enumerate(batches):
        task = process_batch_with_semaphore(batch, user_state, i + 1, len(batches))
        tasks.append(task)

    # Aguardar todos os lotes
    results = await asyncio.gather(*tasks, return_exceptions=True)

    errors = [result for result in results if isinstance(result, Exception)]
    if errors:
        raise _aggregate_indexing_failures(errors) from errors[0]

    logger.info(f"✓ Todos os {len(batches)} lotes indexados com sucesso")
    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")


async def process_batch_with_semaphore(
    batch_ids: list[str], user_state: UserState, batch_num: int, total_batches: int
) -> None:
    """
    Processa um lote de documentos com controle de semáforo.

    Args:
        batch_ids: IDs do lote
        user_state: Estado do usuário
        batch_num: Número do lote atual
        total_batches: Total de lotes
    """
    async with _indexing_semaphore:
        logger.info(
            f"Iniciando lote {batch_num}/{total_batches} com {len(batch_ids)} documentos"
        )
        try:
            await index_single_batch(batch_ids, user_state)
            logger.info(f"✓ Lote {batch_num}/{total_batches} concluído")
        except Exception as e:
            error_msg = str(e) or repr(e)
            error_type = type(e).__name__
            logger.error(
                f"✗ Lote {batch_num}/{total_batches} falhou: [{error_type}] {error_msg}",
                exc_info=True,
            )
            # Se falhar, lançar erro - sem fallback
            raise


async def index_single_batch(document_ids: list[str], user_state: UserState) -> None:
    """
    Indexa um único lote de documentos.

    Args:
        document_ids: Lista de IDs para indexar
        user_state: Estado do usuário
    """
    logger.debug(f"Indexando lote com {len(document_ids)} documentos")
    await indexing_embeddings(document_ids, user_state)
    logger.debug("Lote indexado com sucesso")


async def verify_indexation_after_auto_index(
    document_ids: list[str], user_state: UserState
) -> bool:
    """
    Verifica se os documentos foram indexados com sucesso após a indexação automática.

    Args:
        document_ids: Lista de IDs que deveriam ter sido indexados
        user_state: Estado do usuário

    Returns:
        True se todos os documentos foram indexados, False caso contrário
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.info("Verificando se indexação automática foi bem-sucedida...")

    try:
        from sei_ia.agents.pergunta.document_validation import (
            check_all_documents_indexed,
        )

        # Criar user_state temporário apenas com os documentos que tentamos indexar
        temp_state = user_state.copy()
        temp_procedures = []

        for proc in user_state.get("id_procedimentos", []):
            if hasattr(proc, "id_documentos"):
                filtered_docs = [
                    doc
                    for doc in proc.id_documentos
                    if hasattr(doc, "id_documento") and doc.id_documento in document_ids
                ]
                if filtered_docs:
                    temp_proc = proc.copy() if hasattr(proc, "copy") else proc
                    temp_proc.id_documentos = filtered_docs
                    temp_procedures.append(temp_proc)

        temp_state["id_procedimentos"] = temp_procedures

        # Verificar indexação
        result = await check_all_documents_indexed(temp_state)

        success = result["all_indexed"]
        total_count = result["total_documents"]

        if success:
            logger.info(
                f"✓ Verificação concluída: todos os {total_count} documentos foram indexados"
            )
        else:
            missing_count = len(result["missing_documents"])
            logger.warning(
                f"✗ Verificação falhou: {missing_count} de {total_count} documentos ainda não estão indexados"
            )
            logger.debug(f"Documentos ainda faltantes: {result['missing_documents']}")

        logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
        return success  # noqa: TRY300

    except Exception as e:
        logger.error(f"Erro na verificação pós-indexação: {e}", exc_info=True)
        return False


def should_auto_index(missing_count: int, total_count: int) -> bool:
    """
    Determina se deve executar indexação automática.

    Args:
        missing_count: Número de documentos faltantes
        total_count: Total de documentos

    Returns:
        True se deve indexar automaticamente, False caso contrário
    """
    if missing_count == 0:
        return False

    # Sempre indexar documentos faltantes, independente da quantidade
    logger.info(
        f"Indexação automática aprovada para {missing_count} de {total_count} documentos"
    )
    return True
