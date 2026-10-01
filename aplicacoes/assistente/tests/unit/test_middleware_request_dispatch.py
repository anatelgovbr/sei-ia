"""Testes unitários para sei_ia/middleware/middleware_request.py."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sei_ia.middleware.middleware_request import RequestMiddleware


def build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestMiddleware)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    @app.post("/echo")
    async def echo(request_obj: dict):
        return request_obj

    return app


@pytest.fixture
def client():
    return TestClient(build_app())


class TestRequestMiddleware:
    def test_get_request_passa(self, client):
        resp = client.get("/ping")
        assert resp.status_code == 200

    def test_post_request_passa(self, client):
        resp = client.post("/echo", json={"key": "value"})
        assert resp.status_code == 200

    def test_rota_inexistente_retorna_404(self, client):
        resp = client.get("/inexistente")
        assert resp.status_code == 404

    def test_multiplas_requisicoes_funcionam(self, client):
        for _ in range(3):
            resp = client.get("/ping")
            assert resp.status_code == 200
