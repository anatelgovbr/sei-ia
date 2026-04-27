"""Tests for exception handlers."""
from unittest.mock import AsyncMock

import psycopg2
import pymysql
import pytest
from fastapi import HTTPException, Request
from pydantic import ValidationError
from requests.exceptions import Timeout

from api_sei.exception_handling.exception_handlers import (
    global_exception_handler,
    resource_not_found_exception_handler,
    solr_communication_exception_handler,
    sqlalchemy_select_error_handler,
)
from api_sei.exception_handling.exceptions import (
    ResourceNotFoundException,
    SolrCommunicationError,
    SQLAlchemySelectError,
)


@pytest.mark.asyncio
async def test_resource_not_found_exception_handler():
    request = AsyncMock(Request)
    exc = ResourceNotFoundException(resource_name="TestResource")
    response = await resource_not_found_exception_handler(request, exc)
    assert response.status_code == 404
    assert response.body.decode() == '{"detail":"TestResource not found"}'

@pytest.mark.asyncio
async def test_solr_communication_exception_handler():
    request = AsyncMock(Request)
    exc = SolrCommunicationError()
    response = await solr_communication_exception_handler(request, exc)
    assert response.status_code == 503
    assert response.body.decode() == '{"detail":"Either Solr did not respond or it responded with an unexpected response."}'

@pytest.mark.asyncio
async def test_sqlalchemy_select_error_handler():
    request = AsyncMock(Request)
    exc = SQLAlchemySelectError()
    response = await sqlalchemy_select_error_handler(request, exc)
    assert response.status_code == 503
    assert response.body.decode() == '{"detail":"Falha ao consultar o banco."}'

@pytest.mark.asyncio
async def test_global_exception_handler_http_exception():
    request = AsyncMock(Request)
    exc = HTTPException(status_code=400, detail="Bad Request")
    response = await global_exception_handler(request, exc)
    assert response.status_code == 400
    assert "HTTPException" in response.body.decode()

@pytest.mark.asyncio
async def test_global_exception_handler_file_not_found():
    request = AsyncMock(Request)
    exc = FileNotFoundError()
    response = await global_exception_handler(request, exc)
    assert response.status_code == 444
    assert "FileNotFoundError" in response.body.decode()

@pytest.mark.asyncio
async def test_global_exception_handler_validation_error():
    request = AsyncMock(Request)
    exc = ValidationError([], model=None)
    response = await global_exception_handler(request, exc)
    assert response.status_code == 422
    assert "ValidationError" in response.body.decode()

@pytest.mark.asyncio
async def test_global_exception_handler_type_error():
    request = AsyncMock(Request)
    exc = TypeError()
    response = await global_exception_handler(request, exc)
    assert response.status_code == 422
    assert "TypeError" in response.body.decode()

@pytest.mark.asyncio
async def test_global_exception_handler_operational_error():
    request = AsyncMock(Request)
    exc = pymysql.OperationalError()
    response = await global_exception_handler(request, exc)
    assert response.status_code == 500
    assert "OperationalError" in response.body.decode()

@pytest.mark.asyncio
async def test_global_exception_handler_database_error():
    request = AsyncMock(Request)
    exc = psycopg2.DatabaseError()
    response = await global_exception_handler(request, exc)
    assert response.status_code == 500
    assert "DatabaseError" in response.body.decode()

@pytest.mark.asyncio
async def test_global_exception_handler_timeout():
    request = AsyncMock(Request)
    exc = Timeout()
    response = await global_exception_handler(request, exc)
    assert response.status_code == 504
    assert "Timeout" in response.body.decode()

@pytest.mark.asyncio
async def test_global_exception_handler_unhandled_exception():
    request = AsyncMock(Request)
    exc = Exception("Unhandled Exception")
    response = await global_exception_handler(request, exc)
    assert response.status_code == 500
    assert "Exception" in response.body.decode()
