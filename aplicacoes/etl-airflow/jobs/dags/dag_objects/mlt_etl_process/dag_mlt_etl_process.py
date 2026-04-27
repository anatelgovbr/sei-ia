"""dag_mlt_etl_process module."""

import pandas as pd
import pendulum
from airflow import DAG
from airflow.decorators import task
from pydantic import BaseModel
from tqdm import tqdm

from jobs.dags.database.create_solr_core import create_solr_core
from jobs.dags.database.generic_sender import GenericSender
from jobs.dags.logger import logger
from jobs.dags.preprocessing.process_from_sei import ProcessFromSEI
from jobs.dags.preprocessing.text_clean import adapt_nr_processo
from jobs.db_models.sei_db_handlers import SEIDBHandler
from jobs.envs import (
    AIRFLOW__CORE__DEFAULT_TIMEZONE,
    MLT_PROCESS_CONFIGSET,
    SOLR_ADDRESS,
    SOLR_MLT_PROCESS_CORE,
    auth,
    dags_default_args,
)


class ProcessToIndex(BaseModel):
    id_protocolo: int
    id_type_process: int
    created_at: str  # format 2024-01-22T20:24:07Z


def send_bulk_process_to_solr(
    batch: list[ProcessToIndex],
    interested_max: int,
    related_processes_max: int,
    core: str,
    external=True,
    subprocesses=True,
) -> None:
    """Faz o tratamento dos processos e envia para o Solr usando bulk insert.

    batch_process_info precisa ser um json com os campos:
    id_protocolo: int
    id_type_process: int
    dt_update: str # format 2024-01-22T20:24:07Z
    created_at: str # format 2024-01-22T20:24:07Z
    """
    create_solr_core(SOLR_ADDRESS, core, MLT_PROCESS_CONFIGSET, auth=auth)
    store_bulk = []

    for process_info in tqdm(batch):
        process = ProcessFromSEI(
            id_protocolo=str(process_info.id_protocolo),
            id_type_process=process_info.id_type_process,
            interested_max=interested_max,
            related_processes_max=related_processes_max,
            subprocesses=subprocesses,
            dt_ref_insert=process_info.created_at,
        )

        if process.process_transformed:
            store_bulk.append(process.process_transformed.solr_dict)

        if process.process_transformed is None:
            logger.warning(
                f"Processo {process_info.id_protocolo!s} é vazio ou não tem documentos relevantes"
            )
            SEIDBHandler.md_ia_atualiza_processos_indexaveis(process_info.id_protocolo)

    if len(store_bulk) > 0:
        try:
            GenericSender(
                df=adapt_nr_processo(
                    pd.DataFrame(store_bulk), col_name="protocolo_formatado"
                ),
                core_url=f"{SOLR_ADDRESS}/solr/{core}",
            ).send_docs_in_bulk_to_solr(auth=auth)
            for id_protocolo in [x["id_protocolo"] for x in store_bulk]:
                SEIDBHandler.md_ia_atualiza_processos_indexaveis(id_protocolo)

        except Exception as exc:
            logger.error(
                f"Error attempt send process: {[x['id_protocolo'] for x in store_bulk]} to Solr. Error: {exc!s}"
            )
            raise


with DAG(
    dag_id="process_indexing",
    concurrency=20,
    default_args=dags_default_args,
    schedule=None,
    tags=["mlt_etl_process", "indexing"],
) as dag2:

    @task(provide_context=True)
    def bulk_task_send_process(**kwargs) -> None:
        dag_run = kwargs.get("dag_run")
        conf = dag_run.conf

        if conf:
            slot_list = conf.get("slot_list")
            interested_max = conf.get("interested_max")
            related_processes_max = conf.get("related_processes_max")

            if len(slot_list) > 0:
                try:
                    for item in slot_list:
                        id_protocolo = item[0]
                        id_type_process = int(item[1])
                        list_process = []
                        list_process.append(
                            ProcessToIndex(
                                id_protocolo=id_protocolo,
                                id_type_process=id_type_process,
                                created_at=pendulum.now(
                                    AIRFLOW__CORE__DEFAULT_TIMEZONE
                                ).to_datetime_string(),
                            )
                        )

                        send_bulk_process_to_solr(
                            list_process,
                            interested_max,
                            related_processes_max,
                            SOLR_MLT_PROCESS_CORE,
                            external=True,
                            subprocesses=True,
                        )
                except Exception as exc:
                    logger.warning(
                        f"Error attempt send process to Solr. Error: {exc!s}"
                    )
                    raise
            else:
                logger.error(f"length slot_list empty, conf: {conf.keys()}, aborting")
        else:
            logger.info("conf is empty")

    bulk_task_send_process()
