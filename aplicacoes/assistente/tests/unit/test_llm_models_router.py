"""Testes unitários para sei_ia/routers/llm_models.py."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sei_ia.routers.llm_models import api_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api_router)
    return TestClient(app)


class TestGetModels:
    def test_retorna_200_com_o_catalogo(self, client):
        catalog = [
            {
                "model_name": "openai/seiia-ds",
                "tags": ["agents:principal"],
                "reasoning_effort_levels": ["none", "low", "medium", "high"],
            },
            {
                "model_name": "openai/seiia-ds-nano",
                "tags": ["agents:ocr"],
                "reasoning_effort_levels": [],
            },
        ]
        with patch("sei_ia.routers.llm_models.get_model_catalog", return_value=catalog):
            resp = client.get("/models")

        assert resp.status_code == 200
        assert resp.json() == {"models": catalog}

    def test_lista_vazia_retorna_200(self, client):
        with patch("sei_ia.routers.llm_models.get_model_catalog", return_value=[]):
            resp = client.get("/models")

        assert resp.status_code == 200
        assert resp.json() == {"models": []}

    def test_falha_no_proxy_retorna_502(self, client):
        with patch(
            "sei_ia.routers.llm_models.get_model_catalog",
            side_effect=Exception("proxy indisponível"),
        ):
            resp = client.get("/models")

        assert resp.status_code == 502
        assert "catálogo de modelos" in resp.json()["detail"]
