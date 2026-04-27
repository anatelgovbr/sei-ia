"""dag_mlt_etl_documents module."""

import logging
from datetime import datetime

import pytz
from airflow import DAG
from airflow.decorators import task

from jobs.dags.database.create_solr_core import create_solr_core
from jobs.dags.database.generic_sender import GenericSender
from jobs.dags.preprocessing.process_transformed import ProcessTransformed
from jobs.db_models.sei_db_handlers import SEIDBHandler
from jobs.envs import (
    MLT_DOCUMENTS_CONFIGSET,
    SOLR_ADDRESS,
    SOLR_MLT_DOCUMENTS_CORE,
    auth,
    dags_default_args,
)

logger = logging.getLogger(__name__)

with DAG(
    dag_id="documents_indexing",
    tags=["indexing", "documents"],
    default_args=dags_default_args,
    schedule=None,
) as dag2:

    @task(provide_context=True)
    def extract_transform_load(**kwargs) -> None:
        dag_run = kwargs.get("dag_run")
        batch = dag_run.conf.get("slot_list")
        if batch is None or len(batch) == 0:
            logger.info("No documents to process - slot_list is empty or None")
            return
        batch_id_documents = [x[0] for x in batch]

        if not batch_id_documents:
            logger.info("No document IDs found in batch - aborting processing")
            return

        create_solr_core(
            SOLR_ADDRESS, SOLR_MLT_DOCUMENTS_CORE, MLT_DOCUMENTS_CONFIGSET, auth=auth
        )

        batch_id_documents_str = ",".join(batch_id_documents)
        df_doc_content = SEIDBHandler.md_ia_consulta_documento(
            id_documentos=batch_id_documents_str, conteudo=True
        )
        df_doc_content["content_doc"] = ProcessTransformed.transform_html_to_text(
            df_doc_content["content_doc"].values.tolist(),
            df_doc_content["id_type_document"].values.tolist(),
        )

        doc_data = df_doc_content[
            [
                "id_protocolo_documento",
                "id_protocolo",
                "id_type_document",
                "content_doc",
            ]
        ]

        doc_data = doc_data.rename(
            columns={
                "id_protocolo_documento": "id_document",
                "id_protocolo": "id_process",
                "content_doc": "content",
            }
        )

        doc_data["dt_ref_insert"] = datetime.now(
            pytz.timezone("America/Sao_Paulo")
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        GenericSender(
            doc_data, f"{SOLR_ADDRESS}/solr/{SOLR_MLT_DOCUMENTS_CORE}"
        ).send_docs_in_bulk_to_solr(auth=auth)
        for id_document in df_doc_content["id_protocolo_documento"].values.tolist():
            SEIDBHandler.md_ia_atualiza_documentos_indexaveis(id_documento=id_document)

    extract_transform_load()
