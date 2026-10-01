#!/usr/bin/env python
"""Exception Handlers."""

import traceback

import psycopg2
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from requests.exceptions import Timeout

from api_sei.exception_handling.exceptions import (
    ResourceNotFoundException,
    SolrCommunicationError,
    SQLAlchemySelectError,
)


def resource_not_found_exception_handler(
    _request: Request, exc: ResourceNotFoundException
) -> JSONResponse:
    """Exception handler for the IdNotFoundException exception."""
    return JSONResponse(
        status_code=404,
        content={"detail": f"{exc.resource_name} not found"},
    )


def solr_communication_exception_handler(
    _request: Request, _exc: SolrCommunicationError
) -> JSONResponse:
    """Exception handler for the SolrCommunicationError exception."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Either Solr did not respond or it responded with an unexpected response."
        },
    )


def sqlalchemy_select_error_handler(
    _request: Request, _exc: SQLAlchemySelectError
) -> JSONResponse:
    """Exception handler for the SQLAlchemySelectError exception."""
    return JSONResponse(
        status_code=503,
        content={"detail": "Falha ao consultar o banco."},
    )


exception_handlers = {
    SolrCommunicationError: solr_communication_exception_handler,
    SQLAlchemySelectError: sqlalchemy_select_error_handler,
}


def global_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler."""
    tb = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []

    file_path, line_num = tb[-1][:2] if tb else (None, None)

    exception_info = [type(exc).__name__, line_num, file_path]

    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exception_info + [exc.detail]},  # noqa: RUF005
        )
    if isinstance(exc, FileNotFoundError):
        return JSONResponse(status_code=444, content={"detail": exception_info})
    if isinstance(exc, ValidationError | TypeError):
        return JSONResponse(status_code=422, content={"detail": exception_info})
    if isinstance(exc, psycopg2.OperationalError | psycopg2.DatabaseError):
        return JSONResponse(status_code=500, content={"detail": exception_info})
    if isinstance(exc, Timeout):
        return JSONResponse(status_code=504, content={"detail": exception_info})
    return JSONResponse(status_code=500, content={"detail": exception_info})
