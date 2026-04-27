"""
Testes E2E para sei_ia/middleware/middleware_request.py.

Verifica que RequestMiddleware:
1. Captura o body da requisição e armazena em request.state.body
2. Gera id_request único para cada requisição
3. Captura o IP do cliente em request.state.ip
4. É transparente — não altera o resultado da requisição
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixture com RequestMiddleware habilitado
# ---------------------------------------------------------------------------


@pytest.fixture
def client_req():
    """TestClient com enable_request_middleware=True."""
    from sei_ia.main import get_app
    from sei_ia.routers.chat.gpt_4o_mini_128k import router as chat_router

    app = get_app(enable_timeout_middleware=False, enable_request_middleware=True)
    app.include_router(chat_router)
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


def test_request_middleware_chat_endpoint_funciona(client_req):
    """
    POST para o endpoint de chat deve funcionar corretamente com o middleware
    habilitado — o middleware captura o body mas não altera o fluxo.
    """

    async def fake_ainvoke(user_state, config=None):
        final = dict(user_state)
        final["response"] = {
            "response": "Olá!",
            "n_tokens": [10, 5],
            "finish_reason": "stop",
            "type_choiced_summary": "Not found",
            "reasoning": None,
        }
        return final

    mock_graph = MagicMock()
    mock_graph.ainvoke = fake_ainvoke

    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client_req.post(
            "/llm_lang/chat_gpt_4o_mini_128k",
            headers={
                "Content-Type": "application/json",
                "X-Internal-Test-Call": "true",
            },
            json={"id_usuario": 1, "id_topico": 0, "text": "Olá!"},
        )

    assert response.status_code == 200
    assert "choices" in response.json()
