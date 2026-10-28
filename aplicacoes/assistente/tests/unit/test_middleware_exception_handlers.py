"""Testes unitários para middleware_exception_handlers.

Módulo testado: sei_ia/middleware/middleware_exception_handlers.py
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from sei_ia.middleware.middleware_exception_handlers import (
    _extract_request_payload,
    http_exception_handler,
    sqlalchemy_exception_handler,
)
from sei_ia.middleware.middleware_request import RequestMiddleware


def build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestMiddleware)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, http_exception_handler)

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    @app.get("/erro/{code}")
    async def erro(code: int):
        raise HTTPException(status_code=code, detail=f"erro {code}")

    @app.get("/erro-generico")
    async def erro_generico():
        raise ValueError("falha interna")

    @app.get("/sem-conteudo")
    async def sem_conteudo():
        raise HTTPException(status_code=204)

    return app


@pytest.fixture
def client():
    return TestClient(build_app(), raise_server_exceptions=False)


class TestHttpExceptionHandler:
    """Testes para http_exception_handler via TestClient."""

    def test_rota_ok_nao_interceptada(self, client):
        resp = client.get("/ok")
        assert resp.status_code == 200

    def test_http_exception_400_retorna_400(self, client):
        resp = client.get("/erro/400")
        assert resp.status_code == 400

    def test_http_exception_404_retorna_404(self, client):
        resp = client.get("/erro/404")
        assert resp.status_code == 404

    def test_http_exception_500_retorna_500(self, client):
        resp = client.get("/erro/500")
        assert resp.status_code == 500

    def test_mensagem_de_erro_no_body(self, client):
        resp = client.get("/erro/400")
        assert "erro 400" in resp.json().get("message", "")

    def test_erro_generico_retorna_500(self, client):
        resp = client.get("/erro-generico")
        assert resp.status_code == 500

    def test_status_204_retorna_body_vazio(self, client):
        resp = client.get("/sem-conteudo")
        assert resp.status_code == 204
        assert resp.content == b""

    def test_body_contem_id_request(self, client):
        resp = client.get("/erro/400")
        assert "id_request" in resp.json()


class TestExtractRequestPayload:
    def _make_request(self, state_body=b"", body_bytes=b"{}"):
        request = MagicMock()
        request.state = MagicMock()
        request.state.body = state_body
        request.body = AsyncMock(return_value=body_bytes)
        return request

    def test_body_em_state_retorna_payload(self):
        req = self._make_request(state_body=b'{"chave": "valor"}')
        result = asyncio.run(_extract_request_payload(req))
        assert result == {"chave": "valor"}

    def test_sem_body_no_state_chama_request_body(self):
        req = self._make_request(state_body=None, body_bytes=b'{"x": 1}')
        result = asyncio.run(_extract_request_payload(req))
        assert result == {"x": 1}
        req.body.assert_called_once()

    def test_excecao_ao_ler_body_retorna_dict_vazio(self):
        request = MagicMock()
        request.state = MagicMock()
        request.state.body = None
        request.body = AsyncMock(side_effect=RuntimeError("leitura falhou"))
        result = asyncio.run(_extract_request_payload(request))
        assert result == {}

    def test_body_bytes_vazio_retorna_dict_vazio(self):
        req = self._make_request(state_body=b"")
        result = asyncio.run(_extract_request_payload(req))
        assert result == {}

    def test_json_invalido_retorna_dict_vazio(self):
        req = self._make_request(state_body=b"nao eh json")
        result = asyncio.run(_extract_request_payload(req))
        assert result == {}


class TestSqlalchemyExceptionHandler:
    def _make_request(self, id_request="req-123"):
        class _State:
            def __init__(self, req_id):
                self._state = {"id_request": req_id}

        request = MagicMock()
        request.state = _State(id_request)
        return request

    def test_retorna_503(self):
        req = self._make_request()
        exc = SQLAlchemyError("DB error")
        resp = asyncio.run(sqlalchemy_exception_handler(req, exc))
        assert resp.status_code == 503

    def test_body_contem_detail_com_excecao(self):
        req = self._make_request()
        exc = SQLAlchemyError("falha crítica no banco")
        resp = asyncio.run(sqlalchemy_exception_handler(req, exc))
        body = json.loads(resp.body)
        assert "falha crítica no banco" in body["detail"]

    def test_body_contem_id_request(self):
        req = self._make_request(id_request="abc-xyz")
        exc = SQLAlchemyError("erro")
        resp = asyncio.run(sqlalchemy_exception_handler(req, exc))
        body = json.loads(resp.body)
        assert body["id_request"] == "abc-xyz"
