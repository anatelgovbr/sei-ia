"""DAG responsável por criar os lotes de indexação."""

import asyncio
import logging
import pickle

import sqlalchemy as sa
from airflow import DAG
from airflow.decorators import task
from pydantic import BaseModel
from tqdm import tqdm

from jobs.db_models.sei_db_handlers import SEIDBHandler
from jobs.envs import (
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN,
    AIRFLOW_API_BASE_URL,
    AIRFLOW_WWW_USER_PASSWORD,
    AIRFLOW_WWW_USER_USERNAME,
    INDEX_BATCH_SIZE,
    LIMIT_QUEUE,
    dags_default_args,
)
from jobs.scripts_airflow.trigger_dag import AirflowDagTrigger

logger = logging.getLogger(__name__)


class IndexTriggerConfig(BaseModel):
    slot_list: list[tuple[str, str]]
    interested_max: int
    related_processes_max: int


@task(task_id="check_already_in_airflow_queue")
def check_already_in_airflow_queue(index_list: list[str], store_queue: list[dict]):
    """Método auxiliar para verificar se os IDs dos processos já estão na fila de processamento do Airflow."""
    id_process_stored = set()
    no_rep_index_list = []
    already_in_queue = 0

    for item in store_queue:
        conf = IndexTriggerConfig(**item)  # Converte dicionário para IndexTriggerConfig
        for slot in conf.slot_list:
            id_process_stored.add(slot[0])
    for id_process in index_list:
        if str(id_process) not in id_process_stored:
            no_rep_index_list.append(id_process)
        else:
            already_in_queue += 1
    return no_rep_index_list, already_in_queue


def split_set(set_id_process_with_type_id_process, slots):
    list_process = list(set_id_process_with_type_id_process)
    result = []
    for i in range(slots):
        result.append(list_process[i::slots])
    return result


# Mapeamento de nomes de funções para funções reais.
# Permite passar nomes como strings (serializáveis) em vez de referências a funções.
FUNC_MAP = {
    "md_ia_lista_processos_indexaveis": SEIDBHandler.md_ia_lista_processos_indexaveis,
    "md_ia_consulta_processo": SEIDBHandler.md_ia_consulta_processo,
    "md_ia_lista_documentos_indexaveis": SEIDBHandler.md_ia_lista_documentos_indexaveis,
    "md_ia_consulta_documento": SEIDBHandler.md_ia_consulta_documento,
}


def _check_already_in_queue_sync(index_list: list[str], store_queue: list[dict]):
    """Versão síncrona (não-task) para verificar se IDs já estão na fila.
    Usada internamente por trigger_index para evitar problemas de serialização.
    """
    id_process_stored = set()
    no_rep_index_list = []
    already_in_queue = 0

    for item in store_queue:
        conf = IndexTriggerConfig(**item)
        for slot in conf.slot_list:
            id_process_stored.add(slot[0])
    for id_process in index_list:
        if str(id_process) not in id_process_stored:
            no_rep_index_list.append(id_process)
        else:
            already_in_queue += 1
    return no_rep_index_list, already_in_queue


@task(task_id="check_queue")
def check_queue(
    conn_string: str,
    estados_filtro: list[str],
    dag_id_filtro: str,
    limit_queue: int,
    batch_size: int,
):
    """Consulta a Dag retornando a lista de processos já enfileirados, ou processando.

    Args:
        conn_string: String de conexão do banco de dados (serializável)
        estados_filtro: Lista de estados da Dag a serem filtrados
        dag_id_filtro: ID da Dag a ser filtrada
        limit_queue: Limite de slots disponíveis para indexação
        batch_size: Tamanho do lote de indexação
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
                    conf = IndexTriggerConfig(**pickle.loads(dag_run.conf.tobytes()))  # noqa: S301
                    store_queue.append(conf.model_dump())

                    if dag_run.state == "queued":
                        dags_queued.append(dag_run)

                except Exception as e:
                    logger.exception(f"Erro ao processar configuração: {e!s}")
                    raise

        slots = limit_queue - len(dags_queued)
        qnt_processes = slots * batch_size

        logger.info(f"Slots disponíveis: {slots}, Processos a buscar: {qnt_processes}")

        return store_queue, slots, qnt_processes

    finally:
        # Garantir que engine seja descartado para liberar conexões
        engine.dispose()


@task(
    task_id="trigger_index",
    max_active_tis_per_dag=1,
)
def trigger_index(
    lista_func_name: str,
    consulta_func_name: str,
    check_queue_result,
    dag_id: str,
    type_index_entity: str = "process",
) -> None:
    """Busca os IDs a serem indexados e os envia para a DAG de indexação.
    Apenas se tiver slots disponíveis.
    Compara com a fila de processamento do Airflow para não enviar IDs já enfileirados.

    Args:
        lista_func_name: Nome da função que retorna a lista de IDs (chave do FUNC_MAP)
        consulta_func_name: Nome da função que retorna os metadados (chave do FUNC_MAP)
        check_queue_result: Tupla com (store_queue, slots, qnt_processes)
        dag_id: ID da DAG a ser indexada
        type_index_entity: Tipo de entidade a ser indexada (process ou document)
    """
    # Resolver funções por nome DENTRO da task para evitar problemas de serialização
    lista_func = FUNC_MAP[lista_func_name]
    consulta_func = FUNC_MAP[consulta_func_name]

    store_queue, slots, qnt_processes = check_queue_result

    if slots <= 0:
        logger.info("FILA DE PROCESSAMENTO COMPLETA")
        return

    index_set = set()
    max_id_fetched = 0
    attempts = 0
    max_attempts = 5

    while len(index_set) < qnt_processes and attempts < max_attempts:
        attempts += 1
        needed = qnt_processes - len(index_set)

        new_ids = lista_func(
            quantidade_registros=needed, id_ultimo_registro=max_id_fetched
        )

        if not new_ids:
            break

        new_ids_int = [int(i) for i in new_ids]
        if new_ids_int:
            current_max_id = max(new_ids_int)
            max_id_fetched = max(max_id_fetched, current_max_id)

        unique_new_ids, _ = _check_already_in_queue_sync(new_ids, store_queue)
        index_set.update(int(x) for x in unique_new_ids)

    if not index_set:
        logger.info("Nenhum item para indexar")
        return

    index_list = sorted(index_set)[:qnt_processes]
    logger.info(f"Indexando {len(index_list)} itens")

    index_list_str = ",".join([str(x) for x in index_list])

    # md_ia_consulta_documento requer parâmetro conteudo, md_ia_consulta_processo não
    if consulta_func_name == "md_ia_consulta_documento":
        metadados_processos = consulta_func(index_list_str, conteudo=False)
    else:
        metadados_processos = consulta_func(index_list_str)

    if metadados_processos.empty:
        msg = f"Nenhum metadado encontrado para os IDs {index_list_str}"
        raise Exception(msg)

    id_type = (
        "id_type_process" if type_index_entity == "process" else "id_type_document"
    )
    index_type = (
        "id_protocolo" if type_index_entity == "process" else "id_protocolo_documento"
    )
    set_id_process_with_type_id_process = set(
        zip(
            metadados_processos[index_type].astype(str),
            metadados_processos[id_type].astype(str),
            strict=False,
        )
    )

    slots_list = split_set(set_id_process_with_type_id_process, slots)

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
            config = IndexTriggerConfig(
                slot_list=chunk, interested_max=902, related_processes_max=596
            )
            await airflow_trigger.trigger_dag(dag_id=dag_id, conf=config.model_dump())
            progress_bar.update(len(chunk))
        progress_bar.close()

    asyncio.run(trigger_tasks_async())


with DAG(
    "process_update_index",
    default_args=dags_default_args,
    schedule="*/1 * * * *",
    tags=["mlt_etl_process", "start-step"],
    max_active_runs=1,
) as dag:
    ESTADOS_FILTRO = ["queued", "running"]
    DAG_ID_FILTRO = "process_indexing"

    check_queue_task = check_queue(
        conn_string=AIRFLOW__DATABASE__SQL_ALCHEMY_CONN,
        estados_filtro=ESTADOS_FILTRO,
        dag_id_filtro=DAG_ID_FILTRO,
        limit_queue=LIMIT_QUEUE,
        batch_size=INDEX_BATCH_SIZE,
    )

    trigger_index_task = trigger_index(
        lista_func_name="md_ia_lista_processos_indexaveis",
        consulta_func_name="md_ia_consulta_processo",
        check_queue_result=check_queue_task,
        dag_id=DAG_ID_FILTRO,
        type_index_entity="process",
    )

    check_queue_task >> trigger_index_task


with DAG(
    "documents_update_index",
    schedule="*/1 * * * *",
    default_args=dags_default_args,
    tags=["start-step", "documents"],
    max_active_runs=1,
) as dag_documents:
    ESTADOS_FILTRO = ["queued", "running"]
    DAG_ID_FILTRO = "documents_indexing"

    check_queue_task = check_queue(
        conn_string=AIRFLOW__DATABASE__SQL_ALCHEMY_CONN,
        estados_filtro=ESTADOS_FILTRO,
        dag_id_filtro=DAG_ID_FILTRO,
        limit_queue=LIMIT_QUEUE,
        batch_size=INDEX_BATCH_SIZE,
    )

    trigger_index_task = trigger_index(
        lista_func_name="md_ia_lista_documentos_indexaveis",
        consulta_func_name="md_ia_consulta_documento",
        check_queue_result=check_queue_task,
        dag_id=DAG_ID_FILTRO,
        type_index_entity="document",
    )

    check_queue_task >> trigger_index_task
