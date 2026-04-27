#!/usr/bin/env python
"""Exception Handlers."""

import traceback

import psycopg2
import pymysql
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from requests.exceptions import Timeout

from api_sei.exception_handling.exceptions import (
    ResourceNotFoundException,
    SolrCommunicationError,
    SQLAlchemySelectError,
)


async def resource_not_found_exception_handler(
    request: Request, exc: ResourceNotFoundException
) -> JSONResponse:  # noqa: ARG001
    """Exception handler for the IdNotFoundException exception."""
    return JSONResponse(
        status_code=404,
        content={"detail": f"{exc.resource_name} not found"},
    )


async def solr_communication_exception_handler(
    request: Request, exc: SolrCommunicationError
) -> JSONResponse:  # noqa: ARG001
    """Exception handler for the SolrCommunicationError exception."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Either Solr did not respond or it responded with an unexpected response."
        },
    )


async def sqlalchemy_select_error_handler(
    request: Request, exc: SQLAlchemySelectError
) -> JSONResponse:  # noqa: ARG001
    """Exception handler for the SQLAlchemySelectError exception."""
    return JSONResponse(
        status_code=503,
        content={"detail": "Falha ao consultar o banco."},
    )


exception_handlers = {
    SolrCommunicationError: solr_communication_exception_handler,
    SQLAlchemySelectError: sqlalchemy_select_error_handler,
}


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
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
    if isinstance(exc, (ValidationError, TypeError)):
        return JSONResponse(status_code=422, content={"detail": exception_info})
    if isinstance(
        exc,
        (
            pymysql.OperationalError,
            psycopg2.OperationalError,
            pymysql.DatabaseError,
            psycopg2.DatabaseError,
        ),
    ):
        return JSONResponse(status_code=500, content={"detail": exception_info})
    if isinstance(exc, Timeout):
        return JSONResponse(status_code=504, content={"detail": exception_info})
    return JSONResponse(status_code=500, content={"detail": exception_info})
