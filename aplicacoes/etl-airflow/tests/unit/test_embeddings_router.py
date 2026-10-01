"""Tests for jobs/api_rest/routers/embeddings.py."""

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jobs.api_rest.routers.embeddings import router


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestGenerateEmbeddingsEndpoint:
    def test_returns_processed_response(self):
        fake_result = {
            "status": "processed",
            "processed_count": 1,
            "skipped_count": 0,
            "embeddings": [{"id_documento": "1", "chunks_count": 3}],
        }
        with patch(
            "jobs.api_rest.routers.embeddings.generate_embeddings_for_documents",
            new=AsyncMock(return_value=fake_result),
        ):
            response = _client().post(
                "/embeddings/generate", json={"id_documentos": ["1"]}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "processed"
        assert body["embeddings"][0]["id_documento"] == "1"

    def test_returns_500_on_service_error(self):
        with patch(
            "jobs.api_rest.routers.embeddings.generate_embeddings_for_documents",
            new=AsyncMock(side_effect=RuntimeError("falha ao gerar")),
        ):
            response = _client().post(
                "/embeddings/generate", json={"id_documentos": ["1"]}
            )

        assert response.status_code == 500
        assert "falha ao gerar" in response.json()["detail"]
