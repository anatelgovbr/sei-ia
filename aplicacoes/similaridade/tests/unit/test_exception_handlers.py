"""Tests for exception handlers."""
from unittest.mock import AsyncMock

import psycopg2
import pytest
from fastapi import HTTPException, Request
from pydantic import BaseModel, ValidationError
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


def test_resource_not_found_exception_handler():
    request = AsyncMock(Request)
    exc = ResourceNotFoundException(resource_name="TestResource")
    response = resource_not_found_exception_handler(request, exc)
    assert response.status_code == 404
    assert response.body.decode() == '{"detail":"TestResource not found"}'

def test_solr_communication_exception_handler():
    request = AsyncMock(Request)
    exc = SolrCommunicationError()
    response = solr_communication_exception_handler(request, exc)
    assert response.status_code == 503
    assert response.body.decode() == '{"detail":"Either Solr did not respond or it responded with an unexpected response."}'

def test_sqlalchemy_select_error_handler():
    request = AsyncMock(Request)
    exc = SQLAlchemySelectError()
    response = sqlalchemy_select_error_handler(request, exc)
    assert response.status_code == 503
    assert response.body.decode() == '{"detail":"Falha ao consultar o banco."}'

def test_global_exception_handler_http_exception():
    request = AsyncMock(Request)
    exc = HTTPException(status_code=400, detail="Bad Request")
    response = global_exception_handler(request, exc)
    assert response.status_code == 400
    assert "HTTPException" in response.body.decode()

def test_global_exception_handler_file_not_found():
    request = AsyncMock(Request)
    exc = FileNotFoundError()
    response = global_exception_handler(request, exc)
    assert response.status_code == 444
    assert "FileNotFoundError" in response.body.decode()

def test_global_exception_handler_validation_error():
    class RequiredFieldModel(BaseModel):
        value: int

    request = AsyncMock(Request)
    with pytest.raises(ValidationError) as exc_info:
        RequiredFieldModel.model_validate({})
    response = global_exception_handler(request, exc_info.value)
    assert response.status_code == 422
    assert "ValidationError" in response.body.decode()

def test_global_exception_handler_type_error():
    request = AsyncMock(Request)
    exc = TypeError()
    response = global_exception_handler(request, exc)
    assert response.status_code == 422
    assert "TypeError" in response.body.decode()

def test_global_exception_handler_operational_error():
    request = AsyncMock(Request)
    exc = psycopg2.OperationalError()
    response = global_exception_handler(request, exc)
    assert response.status_code == 500
    assert "OperationalError" in response.body.decode()

def test_global_exception_handler_database_error():
    request = AsyncMock(Request)
    exc = psycopg2.DatabaseError()
    response = global_exception_handler(request, exc)
    assert response.status_code == 500
    assert "DatabaseError" in response.body.decode()

def test_global_exception_handler_timeout():
    request = AsyncMock(Request)
    exc = Timeout()
    response = global_exception_handler(request, exc)
    assert response.status_code == 504
    assert "Timeout" in response.body.decode()

def test_global_exception_handler_unhandled_exception():
    request = AsyncMock(Request)
    exc = Exception("Unhandled Exception")
    response = global_exception_handler(request, exc)
    assert response.status_code == 500
    assert "Exception" in response.body.decode()
