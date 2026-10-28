"""Manipula o registro de consumo de logs no banco de dados."""

import logging

from sqlalchemy.exc import SQLAlchemyError

from api_sei.db_models.db_instances import app_db
from api_sei.db_models.models import LogConsume
from api_sei.exception_handling.exceptions import SQLAlchemyInsertError
from api_sei.pydantic_models.log_consume import LogConsumeCreate

logger = logging.getLogger(__name__)


def insert_log_consume(log_consume: LogConsumeCreate) -> None:
    """Insere um registro de consumo de log no banco de dados.

    Parameters:
        log_consume (LogConsumeCreate): O objeto de log a ser inserido.

    Returns:
        None
    """
    if not app_db:
        return

    try:
        new_log_consume = LogConsume(
            api_recomend_url=log_consume.api_recomend_url,
            status_code=log_consume.status_code,
            id_protocol=log_consume.id_protocol,
            id_user=log_consume.id_user,
        )

        app_db.add(new_log_consume)
    except SQLAlchemyError as e:
        msg = f"Erro ao Insere um registro de consumo de log no banco de dados {e!s}"
        logger.exception(msg)
        raise SQLAlchemyInsertError(msg) from e
