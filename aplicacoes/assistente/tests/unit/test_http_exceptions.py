"""Testes unitários para o módulo http_exceptions.

Módulo testado: sei_ia/services/exceptions/http_exceptions.py
"""

import pytest
from fastapi import HTTPException

from sei_ia.services.exceptions.http_exceptions import (
    HTTPException204,
    HTTPException400,
    HTTPException401,
    HTTPException403,
    HTTPException404,
    HTTPException405,
    HTTPException406,
    HTTPException408,
    HTTPException409,
    HTTPException411,
    HTTPException411DocumentTimeout,
    HTTPException412,
    HTTPException412SeiApiTimeout,
    HTTPException413,
    HTTPException415,
    HTTPException422,
    HTTPException429,
    HTTPException500,
    HTTPException501,
    HTTPException503,
    HTTPException504,
    fast_api_responses,
)


class TestStatusCodes:
    """Verifica que cada exceção usa o status code correto por padrão."""

    @pytest.mark.parametrize(
        "cls,expected_code",
        [
            (HTTPException204, 204),
            (HTTPException400, 400),
            (HTTPException401, 401),
            (HTTPException403, 403),
            (HTTPException404, 404),
            (HTTPException405, 405),
            (HTTPException406, 406),
            (HTTPException408, 408),
            (HTTPException409, 409),
            (HTTPException411, 411),
            (HTTPException412, 412),
            (HTTPException413, 413),
            (HTTPException415, 415),
            (HTTPException422, 422),
            (HTTPException429, 429),
            (HTTPException500, 500),
            (HTTPException501, 501),
            (HTTPException503, 503),
            (HTTPException504, 504),
        ],
    )
    def test_status_code_padrao(self, cls, expected_code):
        exc = cls()
        assert exc.status_code == expected_code

    def test_http_exception_411_document_timeout_status_code(self):
        exc = HTTPException411DocumentTimeout(document_id="doc123")
        assert exc.status_code == 411

    def test_http_exception_412_sei_api_timeout_status_code(self):
        exc = HTTPException412SeiApiTimeout(document_id="doc123")
        assert exc.status_code == 412


class TestHeranca:
    """Verifica que todas as exceções herdam de HTTPException do FastAPI."""

    @pytest.mark.parametrize(
        "cls",
        [
            HTTPException204,
            HTTPException400,
            HTTPException403,
            HTTPException404,
            HTTPException408,
            HTTPException411,
            HTTPException413,
            HTTPException500,
        ],
    )
    def test_herda_de_http_exception(self, cls):
        exc = cls()
        assert isinstance(exc, HTTPException)


class TestMensagensDinamicas:
    """Testa exceções com mensagens que interpolam o ID do documento."""

    def test_411_document_timeout_contem_document_id(self):
        exc = HTTPException411DocumentTimeout(document_id="doc_abc")
        assert "doc_abc" in exc.detail

    def test_412_sei_api_timeout_contem_document_id(self):
        exc = HTTPException412SeiApiTimeout(document_id="doc_xyz")
        assert "doc_xyz" in exc.detail

    def test_411_document_timeout_detail_customizado(self):
        exc = HTTPException411DocumentTimeout(document_id="x", detail="mensagem custom")
        assert exc.detail == "mensagem custom"

    def test_412_sei_api_timeout_detail_customizado(self):
        exc = HTTPException412SeiApiTimeout(document_id="x", detail="custom detail")
        assert exc.detail == "custom detail"


class TestDetailPersonalizado:
    """Testa que o detail pode ser sobrescrito em todas as exceções."""

    def test_detail_customizado_e_preservado(self):
        exc = HTTPException500(detail="erro customizado")
        assert exc.detail == "erro customizado"

    def test_status_code_customizado_e_preservado(self):
        exc = HTTPException500(status_code=502)
        assert exc.status_code == 502


class TestFastApiResponses:
    """Testa o dicionário fast_api_responses."""

    def test_contem_todos_os_status_codes_principais(self):
        for code in [204, 400, 401, 403, 404, 408, 411, 412, 413, 500]:
            assert code in fast_api_responses

    def test_cada_entrada_tem_chave_description(self):
        for code, value in fast_api_responses.items():
            assert "description" in value, f"Status {code} sem 'description'"

    def test_descriptions_nao_sao_vazias(self):
        for code, value in fast_api_responses.items():
            assert value["description"], f"Status {code} com description vazia"
