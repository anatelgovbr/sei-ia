"""DAG responsável por gerar embeddings para lotes de documentos."""

import asyncio
import logging
from typing import Any

from airflow import DAG
from airflow.decorators import task

from jobs.api_rest.services.embedding_service import generate_embeddings_for_documents
from jobs.db_models.sei_db_handlers import SEIDBHandler
from jobs.envs import EMBEDDING_MAX_ACTIVE_RUNS, dags_default_args

logger = logging.getLogger(__name__)

with DAG(
    dag_id="documents_embedding_generation",
    tags=["embedding", "generation", "documents"],
    default_args=dags_default_args,
    schedule=None,
    max_active_runs=EMBEDDING_MAX_ACTIVE_RUNS,
) as dag:

    @task(provide_context=True)
    def generate_embeddings_for_batch(**kwargs: Any) -> None:
        """Task que gera embeddings para um lote de documentos.

        Recebe via dag_run.conf:
            - slot_list: lista de IDs de documentos [id_documento1, id_documento2, ...]

        Fluxo:
            1. Recebe lista de IDs de documentos do slot_list
            2. Chama função de serviço diretamente: generate_embeddings_for_documents
            3. Para cada documento processado com sucesso, atualiza status no SEI
        """
        dag_run = kwargs.get("dag_run")
        batch_id_documents = dag_run.conf.get("slot_list")

        if batch_id_documents is None or len(batch_id_documents) == 0:
            logger.info("No documents to process - slot_list is empty or None")
            return

        logger.info(
            f"Iniciando geração de embeddings para {len(batch_id_documents)} documentos"
        )

        # Lista para rastrear quais documentos foram processados
        processed_documents = []

        try:
            # Chamar serviço de geração de embeddings diretamente
            result = asyncio.run(generate_embeddings_for_documents(batch_id_documents))

            logger.info(
                f"Resposta do serviço: status={result.get('status')}, "
                f"processados={result.get('processed_count')}, "
                f"já existentes={result.get('skipped_count')}"
            )

            # Obter lista de documentos processados
            embeddings_info = result.get("embeddings", [])
            for emb_info in embeddings_info:
                id_doc = emb_info.get("id_documento")
                chunks_count = emb_info.get("chunks_count", 0)

                if chunks_count > 0:
                    processed_documents.append(id_doc)

            # Incluir documentos que já tinham embeddings (skipped)
            skipped_ids = result.get("skipped_ids", [])
            for id_doc in skipped_ids:
                if id_doc not in processed_documents:
                    processed_documents.append(id_doc)

            if skipped_ids:
                logger.info(
                    f"{len(skipped_ids)} documentos já tinham embeddings e serão sinalizados ao SEI"
                )

        except Exception as e:
            logger.error(f"Erro ao gerar embeddings: {e}", exc_info=True)
            raise

        # Atualizar status no SEI para documentos processados com sucesso (em paralelo)
        async def update_all_statuses():
            tasks = [
                SEIDBHandler.md_ia_atualiza_documentos_vetorizaveis_async(int(id_doc))
                for id_doc in processed_documents
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

        results = asyncio.run(update_all_statuses())
        success_count = sum(1 for r in results if r is True)
        failed_count = len(results) - success_count

        if failed_count > 0:
            logger.warning(
                f"⚠️ {failed_count} documentos falharam na atualização de status"
            )

        logger.info(
            f"✅ Processamento concluído: "
            f"{success_count}/{len(processed_documents)} documentos atualizados no SEI"
        )

    generate_embeddings_for_batch()
