"""Testes unitários para sei_ia/routers/healthcheck.py."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sei_ia.routers.healthcheck import HealthCheck, api_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api_router)
    return TestClient(app)


class TestHealthCheckModel:
    def test_status_default_ok(self):
        hc = HealthCheck()
        assert hc.status == "OK"

    def test_status_customizado(self):
        hc = HealthCheck(status="DEGRADED")
        assert hc.status == "DEGRADED"

    def test_eh_pydantic_model(self):
        from pydantic import BaseModel

        assert issubclass(HealthCheck, BaseModel)

    def test_serializavel_para_dict(self):
        hc = HealthCheck()
        assert hc.model_dump() == {"status": "OK"}


class TestHealthEndpoint:
    def test_retorna_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_retorna_status_ok(self, client):
        resp = client.get("/health")
        assert resp.json()["status"] == "OK"

    def test_content_type_json(self, client):
        resp = client.get("/health")
        assert "application/json" in resp.headers["content-type"]


def test_legacy_azure_websearch_health_endpoint_is_not_published(client):
    response = client.get("/health/websearch")

    assert response.status_code == 404
