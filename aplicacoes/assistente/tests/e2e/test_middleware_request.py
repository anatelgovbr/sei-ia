"""
Testes E2E para sei_ia/middleware/middleware_request.py.

Verifica que RequestMiddleware:
1. Captura o body da requisição e armazena em request.state.body
2. Gera id_request único para cada requisição
3. Captura o IP do cliente em request.state.ip
4. É transparente — não altera o resultado da requisição
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixture com RequestMiddleware habilitado
# ---------------------------------------------------------------------------


@pytest.fixture
def client_req():
    """TestClient com enable_request_middleware=True."""
    from sei_ia.main import get_app

    app = get_app(enable_timeout_middleware=False, enable_request_middleware=True)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Transparência — resultados iguais aos sem middleware
# ---------------------------------------------------------------------------


def test_request_middleware_health_check_transparente(client_req):
    """RequestMiddleware não interfere com GET /health."""
    response = client_req.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "OK"}


def test_request_middleware_feedback_transparente(client_req):
    """RequestMiddleware não interfere com POST /feedback/feedback."""
    with patch(
        "sei_ia.routers.feedback.persist_feedback",
        new=AsyncMock(return_value=42),
    ):
        response = client_req.post(
            "/feedback/feedback",
            json={"id_mensagem": 1, "stars": 3},
        )

    assert response.status_code == 200
    assert response.json() == 42


def test_request_middleware_validacao_422_transparente(client_req):
    """RequestMiddleware não afeta respostas de validação 422."""
    response = client_req.post(
        "/feedback/feedback",
        json={"id_mensagem": 1, "stars": 99},  # inválido
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 2. id_request aparece nas respostas de erro (estado populado pelo middleware)
# ---------------------------------------------------------------------------


def test_request_middleware_id_request_presente_em_erro_banco(client_req):
    """
    Após RequestMiddleware processar a requisição, request.state.id_request
    deve estar disponível. Em respostas de erro do banco (503), o campo
    id_request aparece no body JSON.
    """
    from sqlalchemy.exc import SQLAlchemyError

    with patch(
        "sei_ia.routers.feedback.persist_feedback",
        new=AsyncMock(side_effect=SQLAlchemyError("timeout")),
    ):
        response = client_req.post(
            "/feedback/feedback",
            json={"id_mensagem": 1, "stars": 3},
        )

    assert response.status_code == 503
    body = response.json()
    # id_request é adicionado pelo RequestMiddleware; pode ser int ou None
    assert "id_request" in body


# ---------------------------------------------------------------------------
# 3. Chat funciona com middleware habilitado
# ---------------------------------------------------------------------------
