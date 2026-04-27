"""Handles recommendation requests to database."""

import logging
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError

from api_sei.db_models.db_instances import app_db
from api_sei.db_models.models import (
    DocumentMLTRecommendation,
    LogConsume,
    ProcessWeightedMLTRecommendation,
)
from api_sei.exception_handling.exceptions import SQLAlchemyInsertError

logger = logging.getLogger(__name__)


def save(status_code: int, id_protocol: str, api_recomend_url: str) -> None:
    """Salva um registro de consumo de API no banco de dados.

    Parameters:
        status_code (int): O código de status da resposta.
        id_protocol (str): O ID do protocolo associado.
        api_recomend_url (str): A URL da API de recomendação chamada.

    Returns:
        None
    """
    if not app_db:
        return

    try:
        new_log_consume = LogConsume(
            api_recomend_url=api_recomend_url,
            status_code=status_code,
            id_protocol=id_protocol,
        )
        app_db.add(new_log_consume)
    except Exception as e:
        msg = f"Erro ao salvar um registro de consumo de API no banco de dados {e!s}"
        logger.exception(msg)


def add_mlt_document_recommendation(
    list_id_doc: list[int],
    list_type_id_doc: list[int],
    rows: int,
    text: str,
    *,
    include_citations: bool,
    text_weight: float,
    normalized: bool,
    fq: list[int],
    recommendation: dict,
    requested_at: datetime,
    id_user: int,
) -> int:
    """Adiciona uma recomendação MLT de documento ao banco de dados.

    Parameters:
        list_id_doc (List[int]): Lista de IDs de documentos.
        list_type_id_doc (List[int]): Lista de tipos de IDs de documentos.
        rows (int): Número de linhas.
        text (str): Texto da recomendação.
        include_citations (bool): Indica se deve incluir citações.
        text_weight (float): Peso do texto.
        normalized (bool): Indica se está normalizado.
        fq (List[int]): Lista de filtros.
        recommendation (dict): Dicionário com as recomendações.
        requested_at (datetime): Data e hora da solicitação.
        id_user (int): ID do usuário.

    Returns:
        int: ID da recomendação adicionada.
    """
    if not app_db:
        return None

    try:
        new_document_mlt_recommendation = DocumentMLTRecommendation(
            text=text,
            list_id_doc=list_id_doc,
            list_type_id_doc=list_type_id_doc,
            rows=rows,
            include_citations=include_citations,
            text_weight=text_weight,
            normalized=normalized,
            fq=fq,
            recommendation=recommendation,
            requested_at=requested_at,
            id_user=id_user,
        )

        new_document_mlt_recommendation = app_db.add(new_document_mlt_recommendation)

        return new_document_mlt_recommendation.id_recommendation
    except SQLAlchemyError as e:
        msg = f"SQL insert error: Adiciona uma recomendação MLT de documento ao banco de dados {e!s}"
        logger.exception(msg)
        raise SQLAlchemyInsertError(msg) from e


def add_process_weighted_mlt_recommendation(
    id_protocolo: str,
    id_user: int,
    rows: int,
    parsedquery_field: str,
    id_field: str,
    fq: list[str],
    *,
    debug: bool,
    extraction_method: str,
    recommendation: dict,
    requested_at: datetime,
) -> int | None:
    """Adiciona uma recomendação MLT ponderada de processo ao banco de dados.

    Parameters:
        id_protocolo (str): ID do protocolo.
        id_user (int): ID do usuário.
        rows (int): Número de linhas.
        parsedquery_field (str): Campo da consulta analisada.
        id_field (str): Campo de ID.
        fq (List[str]): Lista de filtros.
        debug (bool): Indica se está no modo de depuração.
        extraction_method (str): Método de extração.
        recommendation (dict): Dicionário com as recomendações.
        requested_at (datetime): Data e hora da solicitação.

    Returns:
        int: ID da recomendação adicionada.
    """
    if not app_db:
        return None

    try:
        new_process_weighted_mlt_recommendation = ProcessWeightedMLTRecommendation(
            id_protocolo=id_protocolo,
            id_user=id_user,
            rows=rows,
            parsedquery_field=parsedquery_field,
            id_field=id_field,
            fq=fq,
            debug=debug,
            extraction_method=extraction_method,
            recommendation=recommendation,
            requested_at=requested_at,
        )

        new_process_weighted_mlt_recommendation = app_db.add(
            new_process_weighted_mlt_recommendation
        )

        return new_process_weighted_mlt_recommendation.id_recommendation
    except SQLAlchemyError as e:
        msg = f"SQL insert error: Adiciona uma recomendação MLT ponderada de processo ao banco de dados {e!s}"
        logger.exception(msg)
        raise SQLAlchemyInsertError(msg) from e
