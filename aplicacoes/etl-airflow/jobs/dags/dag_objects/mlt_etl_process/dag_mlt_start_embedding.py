"""DAG responsável por criar os lotes de vetorização (embeddings)."""

import asyncio
import logging
import pickle

import sqlalchemy as sa
from airflow import DAG
from airflow.decorators import task
from pydantic import BaseModel
from tqdm import tqdm

from jobs.dags.dag_objects.mlt_etl_process.utils import split_set
from jobs.db_models.sei_db_handlers import SEIDBHandler
from jobs.envs import (
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN,
    AIRFLOW_API_BASE_URL,
    AIRFLOW_WWW_USER_PASSWORD,
    AIRFLOW_WWW_USER_USERNAME,
    EMBEDDING_BATCH_SIZE,
    LIMIT_QUEUE,
    dags_default_args,
)
from jobs.scripts_airflow.trigger_dag import AirflowDagTrigger

logger = logging.getLogger(__name__)


class EmbeddingTriggerConfig(BaseModel):
    """Configuração para disparo de DAG de geração de embeddings."""

    slot_list: list[str]  # Lista de IDs de documentos


@task(task_id="check_already_in_airflow_queue_embedding")
def check_already_in_airflow_queue_embedding(
    index_list: list[str], store_queue: list[dict]
):
    """Método auxiliar para verificar se os IDs dos documentos já estão na fila de processamento do Airflow.
    Específico para embeddings (usa EmbeddingTriggerConfig).
    """
    id_documents_stored = set()
    no_rep_index_list = []
    already_in_queue = 0

    for item in store_queue:
        conf = EmbeddingTriggerConfig(**item)
        for doc_id in conf.slot_list:
            id_documents_stored.add(doc_id)

    for id_document in index_list:
        if str(id_document) not in id_documents_stored:
            no_rep_index_list.append(id_document)
        else:
            already_in_queue += 1

    return no_rep_index_list, already_in_queue


# Mapeamento de nomes de funções para funções reais (embeddings).
# Permite passar nomes como strings (serializáveis) em vez de referências a funções.
FUNC_MAP_EMBEDDING = {
    "md_ia_lista_documentos_vetorizaveis": SEIDBHandler.md_ia_lista_documentos_vetorizaveis,
}


def _check_already_in_queue_embedding_sync(
    index_list: list[str], store_queue: list[dict]
):
    """Versão síncrona (não-task) para verificar se IDs já estão na fila de embeddings.
    Usada internamente por trigger_embedding para evitar problemas de serialização.
    """
    id_documents_stored = set()
    no_rep_index_list = []
    already_in_queue = 0

    for item in store_queue:
        conf = EmbeddingTriggerConfig(**item)
        for doc_id in conf.slot_list:
            id_documents_stored.add(doc_id)

    for id_document in index_list:
        if str(id_document) not in id_documents_stored:
            no_rep_index_list.append(id_document)
        else:
            already_in_queue += 1

    return no_rep_index_list, already_in_queue


@task(task_id="check_queue_embedding")
def check_queue_embedding(
    conn_string: str,
    estados_filtro: list[str],
    dag_id_filtro: str,
    limit_queue: int,
    batch_size: int,
):
    """Consulta a Dag retornando a lista de documentos já enfileirados, ou processando.
    Versão específica para embeddings (usa EmbeddingTriggerConfig).

    Args:
        conn_string: String de conexão do banco de dados (serializável)
        estados_filtro: Lista de estados da Dag a serem filtrados
        dag_id_filtro: ID da Dag a ser filtrada
        limit_queue: Limite de slots disponíveis para vetorização
        batch_size: Tamanho do lote de vetorização
    """
    # Criar engine DENTRO da task para evitar problemas de serialização
    engine = sa.create_engine(conn_string)

    store_queue = []
    sql_dags_estado = """
        SELECT
            dr.dag_id,
            dr.run_id,
            dr.state,
            dr.execution_date,
            dr.queued_at,
            dr.conf
        FROM dag_run dr
        WHERE dr.state IN :estados AND dr.dag_id = :dag_id
        ORDER BY dr.queued_at DESC, dr.execution_date DESC;
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(sql_dags_estado),
                {"estados": tuple(estados_filtro), "dag_id": dag_id_filtro},
            )
            dags_estado = result.fetchall()

        dags_queued = []

        for dag_run in dags_estado:
            if dag_run.conf:
                try:
                    conf = EmbeddingTriggerConfig(
                        **pickle.loads(dag_run.conf.tobytes())  # noqa: S301
                    )
                    store_queue.append(conf.model_dump())

                    if dag_run.state == "queued":
                        dags_queued.append(dag_run)

                except Exception as e:
                    logger.exception(f"Erro ao processar configuração: {e!s}")
                    raise

        slots = limit_queue - len(dags_queued)
        qnt_documents = slots * batch_size

        logger.info(f"Slots disponíveis: {slots}, Documentos a buscar: {qnt_documents}")

        return store_queue, slots, qnt_documents

    finally:
        # Garantir que engine seja descartado para liberar conexões
        engine.dispose()


@task(
    task_id="trigger_embedding",
    max_active_tis_per_dag=1,
)
def trigger_embedding(lista_func_name: str, check_queue_result, dag_id: str) -> None:
    """Busca os IDs de documentos a serem vetorizados e os envia para a DAG de geração de embeddings.
    Apenas se tiver slots disponíveis.
    Compara com a fila de processamento do Airflow para não enviar IDs já enfileirados.

    Args:
        lista_func_name: Nome da função que retorna a lista de IDs (chave do FUNC_MAP_EMBEDDING)
        check_queue_result: Tupla com (store_queue, slots, qnt_documents)
        dag_id: ID da DAG a ser disparada
    """
    # Resolver função por nome DENTRO da task para evitar problemas de serialização
    lista_func = FUNC_MAP_EMBEDDING[lista_func_name]

    store_queue, slots, qnt_documents = check_queue_result

    if slots <= 0:
        logger.info("FILA DE PROCESSAMENTO COMPLETA")
        return

    index_set = set()
    max_id_fetched = 0
    attempts = 0
    max_attempts = 5

    while len(index_set) < qnt_documents and attempts < max_attempts:
        attempts += 1
        needed = qnt_documents - len(index_set)

        new_ids = lista_func(
            quantidade_registros=needed, id_ultimo_registro=max_id_fetched
        )

        if not new_ids:
            break

        new_ids_int = [int(i) for i in new_ids]
        if new_ids_int:
            current_max_id = max(new_ids_int)
            max_id_fetched = max(max_id_fetched, current_max_id)

        unique_new_ids, _ = _check_already_in_queue_embedding_sync(new_ids, store_queue)
        index_set.update(int(x) for x in unique_new_ids)

    if not index_set:
        logger.info("Nenhum documento para vetorizar")
        return

    index_list = sorted(index_set)[:qnt_documents]
    logger.info(f"Vetorizando {len(index_list)} documentos")

    # Converter para strings para garantir consistência
    index_list_str_format = [str(x) for x in index_list]

    # Reutilizar split_set da DAG de indexação
    slots_list = split_set(index_list_str_format, slots)

    airflow_trigger = AirflowDagTrigger(
        base_url=AIRFLOW_API_BASE_URL,
        username=AIRFLOW_WWW_USER_USERNAME,
        password=AIRFLOW_WWW_USER_PASSWORD,
    )

    valid_slots = [chunk for chunk in slots_list if chunk]
    if not valid_slots:
        return

    async def trigger_tasks_async() -> None:
        progress_bar = tqdm(total=len(index_list), desc=f"Disparando DAG {dag_id}")
        for chunk in valid_slots:
            config = EmbeddingTriggerConfig(slot_list=chunk)
            await airflow_trigger.trigger_dag(dag_id=dag_id, conf=config.model_dump())
            progress_bar.update(len(chunk))
        progress_bar.close()

    asyncio.run(trigger_tasks_async())


with DAG(
    "documents_update_embedding",
    default_args=dags_default_args,
    schedule="*/1 * * * *",
    tags=["start-step", "embedding", "documents"],
    max_active_runs=1,
) as dag_documents_embedding:
    ESTADOS_FILTRO = ["queued", "running"]
    DAG_ID_FILTRO = "documents_embedding_generation"

    check_queue_task = check_queue_embedding(
        conn_string=AIRFLOW__DATABASE__SQL_ALCHEMY_CONN,
        estados_filtro=ESTADOS_FILTRO,
        dag_id_filtro=DAG_ID_FILTRO,
        limit_queue=LIMIT_QUEUE,
        batch_size=EMBEDDING_BATCH_SIZE,
    )

    trigger_embedding_task = trigger_embedding(
        lista_func_name="md_ia_lista_documentos_vetorizaveis",
        check_queue_result=check_queue_task,
        dag_id=DAG_ID_FILTRO,
    )

    check_queue_task >> trigger_embedding_task
