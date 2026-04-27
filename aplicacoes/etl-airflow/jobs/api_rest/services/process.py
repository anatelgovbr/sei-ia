"""process module."""

import logging

import pandas as pd

from jobs.dags.database.generic_sender import GenericSender
from jobs.dags.preprocessing.process_from_sei import ProcessFromSEI
from jobs.dags.preprocessing.text_clean import adapt_nr_processo
from jobs.db_models.sei_db_handlers import SEIDBHandler
from jobs.envs import SOLR_ADDRESS, SOLR_MLT_PROCESS_CORE, auth

logger = logging.getLogger(__name__)


def get_process_by_nr_process(nr_process):
    df_metadata = SEIDBHandler.md_ia_consulta_processo(nr_process)
    if df_metadata.empty:
        id_type_process = None
    else:
        id_type_process = df_metadata["id_type_process"].to_numpy()[0]

    process = ProcessFromSEI(
        id_protocolo=nr_process,
        subprocesses=True,
        id_type_process=id_type_process,
        interested_max=90,
        related_processes_max=596,
    )

    if process.process_transformed is None:
        logger.warning(
            f"Processo {nr_process!s} é vazio ou não tem documentos relevantes"
        )
        return {
            "error": f"Processo {nr_process!s} é vazio ou não tem documentos relevantes"
        }

    if process.process_transformed:
        df = adapt_nr_processo(
            pd.DataFrame([process.process_transformed.solr_dict]),
            col_name="protocolo_formatado",
        )
        GenericSender(
            df=df, core_url=f"{SOLR_ADDRESS}/solr/{SOLR_MLT_PROCESS_CORE}"
        ).send_all_docs_to_solr(auth=auth)

        logger.info(f"Processo {nr_process!s} enviado para o Solr!!")

        return [row.to_dict() for _, row in df.iterrows()]
    return None
