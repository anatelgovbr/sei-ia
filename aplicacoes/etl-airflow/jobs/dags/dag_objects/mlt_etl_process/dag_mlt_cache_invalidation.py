"""DAG responsável por invalidar cache de documentos e processos cancelados."""

import asyncio
import logging

from airflow import DAG
from airflow.decorators import task

from jobs.api_rest.services.embedding_service import delete_embeddings_by_document_ids
from jobs.db_models.sei_db_handlers import SEIDBHandler
from jobs.db_models.solr_handlers import SolrHandlers
from jobs.envs import (
    INDEX_BATCH_SIZE,
    SOLR_ADDRESS,
    SOLR_MLT_DOCUMENTS_CORE,
    SOLR_MLT_PROCESS_CORE,
    auth,
    dags_default_args,
)
from jobs.services.cache import invalidate_document_cache

logger = logging.getLogger(__name__)


@task(task_id="drop_canceled_processes_from_solr")
def drop_canceled_processes_from_solr(
    batch_size: int, solr_url: str, solr_core: str, auth
) -> None:
    """Remove processos cancelados do Solr.

    Args:
        batch_size: Tamanho do lote de remoção
        solr_url: URL do Solr
        solr_core: Core do Solr para processos
        auth: Autenticação
    """
    id_ultimo = 0
    total_removed = 0

    while True:
        delete_list, id_ultimo = (
            SEIDBHandler.md_ia_lista_processos_indexaveis_cancelados(
                batch_size, id_ultimo
            )
        )

        if not delete_list:
            logger.info(f"Total de processos removidos do Solr: {total_removed}")
            break

        # Remover do Solr
        SolrHandlers.drop_by_field(
            id_values=delete_list,
            solr_url=solr_url,
            solr_core=solr_core,
            field="id_protocolo",
            auth=auth,
        )

        total_removed += len(delete_list)

        # Enviar status para remover da lista de cancelados na API SEI
        async def remove_ids_async(ids_to_remove=delete_list) -> None:
            tasks = [
                SEIDBHandler.md_ia_remove_processos_indexaveis_cancelados(_id)
                for _id in ids_to_remove
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        f"Erro ao remover processo {ids_to_remove[i]}: {result}"
                    )

        asyncio.run(remove_ids_async())
        logger.info(
            f"Removidos {len(delete_list)} processos do Solr (total: {total_removed})"
        )


@task(task_id="drop_canceled_documents_and_embeddings")
def drop_canceled_documents_and_embeddings(
    batch_size: int, solr_url: str, solr_core: str, auth
) -> None:
    """Remove documentos cancelados do Solr e seus respectivos embeddings do PostgreSQL.

    Args:
        batch_size: Tamanho do lote de remoção
        solr_url: URL do Solr
        solr_core: Core do Solr para documentos
        auth: Autenticação
    """
    id_ultimo = 0
    total_removed_solr = 0
    total_removed_embeddings = 0

    while True:
        delete_list, id_ultimo = (
            SEIDBHandler.md_ia_lista_documentos_indexaveis_cancelados(
                batch_size, id_ultimo
            )
        )

        if not delete_list:
            logger.info(f"Total de documentos removidos do Solr: {total_removed_solr}")
            logger.info(f"Total de embeddings removidos: {total_removed_embeddings}")
            break

        # Remover do Solr
        SolrHandlers.drop_by_field(
            id_values=delete_list,
            solr_url=solr_url,
            solr_core=solr_core,
            field="id_document",
            auth=auth,
        )

        total_removed_solr += len(delete_list)

        # Remover embeddings do PostgreSQL
        try:
            # Converter para inteiros
            doc_ids_int = [int(doc_id) for doc_id in delete_list]

            # Remover embeddings de forma assíncrona
            async def remove_embeddings(ids=doc_ids_int):
                return await delete_embeddings_by_document_ids(ids)

            embeddings_deleted = asyncio.run(remove_embeddings())
            total_removed_embeddings += embeddings_deleted

        except Exception as e:
            logger.exception(
                f"Erro ao remover embeddings dos documentos {delete_list}: {e}"
            )

        # Invalidar cache Redis dos documentos
        try:

            async def invalidate_cache(ids=delete_list):
                return await invalidate_document_cache(ids)

            cache_keys_deleted = asyncio.run(invalidate_cache())
            logger.info(
                f"Cache Redis invalidado: {cache_keys_deleted} chaves removidas para {len(delete_list)} documentos"
            )

        except Exception as e:
            logger.exception(
                f"Erro ao invalidar cache Redis dos documentos {delete_list}: {e}"
            )

        # Enviar status para remover da lista de cancelados na API SEI
        async def remove_ids_async(ids_to_remove=delete_list) -> None:
            tasks = [
                SEIDBHandler.md_ia_remove_documentos_indexaveis_cancelados(_id)
                for _id in ids_to_remove
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        f"Erro ao remover documento {ids_to_remove[i]}: {result}"
                    )

        asyncio.run(remove_ids_async())
        logger.info(
            f"Removidos {len(delete_list)} documentos do Solr "
            f"(total Solr: {total_removed_solr}, total embeddings: {total_removed_embeddings})"
        )


with DAG(
    "cache_invalidation",
    default_args=dags_default_args,
    schedule="*/5 * * * *",
    tags=["cache-invalidation", "cleanup"],
    max_active_runs=1,
) as dag:
    # Task 1: Remover processos cancelados do Solr
    drop_processes_task = drop_canceled_processes_from_solr(
        batch_size=INDEX_BATCH_SIZE * 5,
        solr_url=SOLR_ADDRESS,
        solr_core=SOLR_MLT_PROCESS_CORE,
        auth=auth,
    )

    # Task 2: Remover documentos cancelados do Solr e embeddings do PostgreSQL
    drop_documents_task = drop_canceled_documents_and_embeddings(
        batch_size=INDEX_BATCH_SIZE * 5,
        solr_url=SOLR_ADDRESS,
        solr_core=SOLR_MLT_DOCUMENTS_CORE,
        auth=auth,
    )

    # Dependência: processos primeiro, depois documentos
    drop_processes_task >> drop_documents_task
