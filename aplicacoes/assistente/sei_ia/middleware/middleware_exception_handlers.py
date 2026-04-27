"""Modulo responsável por capturar e tratar exceções em geral, retornando um JSON com a mensagem de erro."""

import json
import logging
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


async def _extract_request_payload(request: Request) -> dict[str, Any]:
    """Recupera o payload original da requisição em formato de dict."""
    raw_body: bytes | None = getattr(request.state, "body", None)

    if raw_body is None:
        try:
            raw_body = await request.body()
            request.state.body = raw_body
        except BaseException:
            logger.exception("Erro ao capturar o payload da requisição")
            return {}

    if not raw_body:
        return {}

    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        logger.exception("Erro ao capturar o payload da requisição")
        return {}


async def sqlalchemy_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """SQLAlchemy exception handler."""
    logger.exception("Erro no banco de dados")
    state: dict = request.state.__dict__["_state"]

    # Log para Solr removido - logging desabilitado

    return JSONResponse(
        status_code=503,
        content={
            "detail": f"Erro no banco de dados: {exc!s}",
            "id_request": state.get("id_request"),
        },
    )


async def http_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse | Response:
    """Exception handler.

    Captura e trata exceções em geral, retornando um JSON com a mensagem de erro.
    Adiciona o log da requisição no banco de dados Solr.
    """
    logger.exception("Capturou um erro na request.")
    state: dict = request.state._state  # noqa: SLF001
    if isinstance(exc, HTTPException):
        status = exc.status_code
        message = exc.detail
    else:
        # Preserva status e detalhe de exceções customizadas (ex.: ChatError)
        status = getattr(exc, "status_code", 500)
        message = getattr(exc, "detail", str(exc))

    # Status 204 não deve ter body conforme especificação HTTP
    if status == 204:
        return Response(status_code=204)

    # payload: dict[str, Any] = await _extract_request_payload(request)

    msg_str = message if isinstance(message, str) else str(message)

    # Log para Solr removido - logging desabilitado

    return JSONResponse(
        status_code=int(status),
        content={"message": msg_str, "id_request": state.get("id_request")},
    )
