"""Endpoints de autotest da API SEI."""

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, validator

from api_sei.db_models.db_instances import app_db
from api_sei.db_models.solr_select import SolrRequests
from api_sei.envs import (
    SOLR_ADDRESS,
    SOLR_MLT_JURISPRUDENCE_CORE,
    SOLR_MLT_PROCESS_CORE,
    auth,
)
from api_sei.pydantic_models.solr_mlt import ExtractionMethodEnum
from api_sei.services.jurisprudence import doc2doc_search
from api_sei.services.mlt import wmlt_process_recommendations_service

logger = logging.getLogger(__name__)
router = APIRouter()


class HealthCheck(BaseModel):
    """Response model to validate and return when performing a health check."""

    status: str = "OK"
    response_time: float | None = None

    @validator("response_time", pre=True, always=True)
    def round_response_time(cls, v: float | None) -> float | None:
        """Arredonda o tempo de resposta para 3 casas decimais."""
        if v is not None:
            return round(v, 3)
        return v


@router.get(
    "/health",
    tags=["healthcheck"],
    summary="Perform a Health Check",
    response_description="Return HTTP Status Code 200 (OK)",
    status_code=status.HTTP_200_OK,
    response_model=HealthCheck,
)
def get_health() -> HealthCheck:
    """Perform a general health check.

    This endpoint can be used to ensure that the API service is up and running.
    Returns HTTP 200 status code if the service is operational.

    Returns:
        HealthCheck: A JSON response with the health status.
    """
    return HealthCheck(status="OK")


@router.get(
    "/health/solr",
    tags=["healthcheck"],
    summary="Perform a Solr Health Check",
    response_description="Return HTTP Status Code 200 (OK)",
)
def get_health_solr(core_name: str = Query(default=None)) -> HealthCheck:
    """Realiza um teste de integridade no serviço Solr.

    Args:
        core_name (str, opcional): O nome do core Solr a ser verificado. Padrão é None.


    Returns:
        HealthCheck: Uma resposta JSON com o status de integridade se Solr estiver acessível.
    """
    resp = (
        SolrRequests.check_core_exists(
            solr_url=SOLR_ADDRESS, core_name=core_name, auth=auth
        )
        if core_name
        else SolrRequests.check_solr_service(solr_url=SOLR_ADDRESS, auth=auth)
    )

    if resp:
        return HealthCheck(status="OK")

    logger.error("Erro ao pingar no Solr")
    raise HTTPException(status_code=503, detail="Erro ao pingar no Solr")


@router.get(
    "/health/database",
    tags=["healthcheck"],
    summary="Perform a Database Health Check",
    response_description="Return HTTP Status Code 200 (OK)",
)
def get_health_database() -> HealthCheck:
    """Perform a health check on the database connection.

    Returns:
        HealthCheck: A JSON response with the health status if the database is reachable.
    """
    if app_db.test_connection():
        return HealthCheck(status="OK")

    logger.error("Erro ao testar conexão com BD!")
    raise HTTPException(status_code=503, detail="Erro ao pingar no banco Postgres")


@router.get(
    "/health/process-recommendation",
    tags=["healthcheck"],
    summary="Perform a Process Recommendation Health Check",
    response_description="Return HTTP Status Code 200 (OK)",
    response_model=HealthCheck,
)
def get_health_process_recommendation() -> HealthCheck:
    """Realiza um teste de integridade criando uma recomendação de processo.

    Returns:
        HealthCheck: Uma resposta JSON com o status de integridade e tempo de resposta.
    """
    start_time = time.time()
    try:
        solr_url = f"{SOLR_ADDRESS}/solr/{SOLR_MLT_PROCESS_CORE}/select"
        params = {
            "q": "*:*",
            "sort": "dt_ref_insert asc",
            "fl": "id_protocolo",
        }
        response = SolrRequests.get(
            url=solr_url,
            params=params,
            nested_fields=["response", "docs"],
            rows=1,
            auth=auth,
        )
        if not response:
            raise HTTPException(status_code=503, detail="No id_protocolo found in Solr")
        id_protocolo = response[0]["id_protocolo"]

        wmlt_process_recommendations_service(
            id_value=id_protocolo,
            rows=10,
            fq=None,
            debug=False,
            id_field="id_protocolo",
            extraction_method=ExtractionMethodEnum.solr,
            id_user=None,
            requested_at=datetime.now(timezone.utc),
        )
    except Exception as e:
        logger.exception("Error in process recommendation health check")
        raise HTTPException(status_code=503, detail=str(e)) from e
    finally:
        end_time = time.time()
        elapsed_time = end_time - start_time

    return HealthCheck(status="OK", response_time=elapsed_time)


@router.get(
    "/health/document-recommendation",
    tags=["healthcheck"],
    summary="Perform a Document Recommendation Health Check",
    response_description="Return HTTP Status Code 200 (OK)",
    response_model=HealthCheck,
)
def get_health_document_recommendation() -> HealthCheck:
    """Perform a health check by creating a document recommendation.

    Returns:
        HealthCheck: A JSON response with the health status and response time.
    """
    start_time = time.time()
    try:
        solr_url = f"{SOLR_ADDRESS}/solr/{SOLR_MLT_JURISPRUDENCE_CORE}/select"
        params = {
            "q": "*:*",
            "sort": "dt_ref_insert asc",
            "fl": "id_document",
        }
        response = SolrRequests.get(
            url=solr_url,
            params=params,
            nested_fields=["response", "docs"],
            rows=1,
            auth=auth,
        )
        if not response:
            raise HTTPException(status_code=503, detail="No id_document found in Solr")
        id_document = int(response[0]["id_document"])

        list_id_doc = [id_document]

        doc2doc_search(
            list_id_doc=list_id_doc,
            list_type_id_doc=None,
            rows=10,
            text="",
            include_citations=False,
            text_weight=0.5,
            normalized=False,
            fq=[],
            requested_at=datetime.now(timezone.utc),
            id_user=None,
        )
    except Exception as e:
        logger.exception("Error in document recommendation health check")
        raise HTTPException(status_code=503, detail=str(e)) from e
    finally:
        end_time = time.time()
        elapsed_time = end_time - start_time

    return HealthCheck(status="OK", response_time=elapsed_time)
