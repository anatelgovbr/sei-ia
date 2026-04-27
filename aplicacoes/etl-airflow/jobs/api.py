"""API de Acesso ao projeto jobs."""

import logging

from fastapi import FastAPI, Path

from jobs.api_rest.routers.embeddings import router as embeddings_router
from jobs.api_rest.services.process import get_process_by_nr_process
from jobs.dags.database.create_solr_core import create_solr_core
from jobs.envs import (
    MLT_DOCUMENTS_CONFIGSET,
    MLT_PROCESS_CONFIGSET,
    SOLR_ADDRESS,
    SOLR_MLT_DOCUMENTS_CORE,
    SOLR_MLT_PROCESS_CORE,
    auth,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    redoc_url="/",
    title="API de Acesso ao projeto jobs.",
    version="1.0.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Healthcheck leve do serviço."""
    return {"status": "ok"}


# Registrar routers
app.include_router(embeddings_router)

try:
    create_solr_core(
        SOLR_ADDRESS, SOLR_MLT_DOCUMENTS_CORE, MLT_DOCUMENTS_CONFIGSET, auth=auth
    )
except Exception as e:
    logger.exception(f"Erro ao criar core {SOLR_MLT_DOCUMENTS_CORE}: {e!s}")

try:
    create_solr_core(
        SOLR_ADDRESS, SOLR_MLT_PROCESS_CORE, MLT_PROCESS_CONFIGSET, auth=auth
    )
except Exception as e:
    logger.exception(f"Erro ao criar core {SOLR_MLT_PROCESS_CORE}: {e!s}")


@app.get("/process/unindexed/nr_process/{nr_process}")
async def get_unindexed_process(nr_process: str = Path(regex=r"^\d+$")) -> dict:
    """Retorna o processo com o numero de processo informado, sem fazer nenhuma filtragem.

    Parameters
    ----------
    nr_process : str
        N mero de processo a ser retornado.

    Returns:
    -------
    dict
        Dicion rio com a informa o do processo.
    """
    return get_process_by_nr_process(nr_process)
