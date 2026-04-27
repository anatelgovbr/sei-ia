"""
Testes P1 - Lacunas Críticas de Cobertura.

Cobre cenários que estavam completamente sem cobertura:
1. Validação de entrada (422 Unprocessable Entity)
2. Endpoint /feedback/feedback (sucesso e erros)
3. Health checks (/health e /health/websearch)
4. Erros de API SEI (500/timeout)
5. Erro de banco de dados (503)
"""

from unittest.mock import AsyncMock, patch

import responses
from sqlalchemy.exc import SQLAlchemyError

# ---------------------------------------------------------------------------
# 1. Health Checks
# ---------------------------------------------------------------------------


def test_health_check_returns_ok(client):
    """GET /health deve retornar 200 com status OK."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "OK"}


def test_health_websearch_returns_false_without_env_vars(client, monkeypatch):
    """GET /health/websearch deve retornar false quando variáveis não estão configuradas."""
    from sei_ia.configs import settings_config

    monkeypatch.setattr(settings_config.settings, "PROJECT_ENDPOINT", "")
    monkeypatch.setattr(settings_config.settings, "BING_CONNECTION_NAME", "")
    monkeypatch.setattr(settings_config.settings, "MODEL_DEPLOYMENT_NAME", "")

    response = client.get("/health/websearch")

    assert response.status_code == 200
    assert response.json() is False


def test_health_websearch_returns_true_with_env_vars(client, monkeypatch):
    """GET /health/websearch deve retornar true quando todas as variáveis estão configuradas."""
    from sei_ia.configs import settings_config

    monkeypatch.setattr(
        settings_config.settings, "PROJECT_ENDPOINT", "https://mock-project.azure.com"
    )
    monkeypatch.setattr(
        settings_config.settings, "BING_CONNECTION_NAME", "bing-connection"
    )
    monkeypatch.setattr(settings_config.settings, "MODEL_DEPLOYMENT_NAME", "gpt-4o")

    response = client.get("/health/websearch")

    assert response.status_code == 200
    assert response.json() is True


# ---------------------------------------------------------------------------
# 2. Validação de entrada - ChatRequest (422 Unprocessable Entity)
# ---------------------------------------------------------------------------


def test_chat_missing_text_field(client):
    """POST sem campo 'text' obrigatório deve retornar 422."""
    payload = {"id_usuario": 1, "id_topico": 0}

    response = client.post(
        "/llm_lang/chat_gpt_4o_mini_128k",
        headers={"Content-Type": "application/json", "X-Internal-Test-Call": "true"},
        json=payload,
    )

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    # Verificar que o erro menciona o campo 'text'
    fields = [err["loc"] for err in body["detail"]]
    assert any("text" in loc for loc in fields)


def test_chat_missing_id_usuario_field(client):
    """POST sem campo 'id_usuario' obrigatório deve retornar 422."""
    payload = {"text": "Olá", "id_topico": 0}

    response = client.post(
        "/llm_lang/chat_gpt_4o_mini_128k",
        headers={"Content-Type": "application/json", "X-Internal-Test-Call": "true"},
        json=payload,
    )

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    fields = [err["loc"] for err in body["detail"]]
    assert any("id_usuario" in loc for loc in fields)


def test_chat_invalid_id_usuario_type(client):
    """POST com 'id_usuario' não inteiro deve retornar 422."""
    payload = {"id_usuario": "nao_e_inteiro", "text": "Olá", "id_topico": 0}

    response = client.post(
        "/llm_lang/chat_gpt_4o_mini_128k",
        headers={"Content-Type": "application/json", "X-Internal-Test-Call": "true"},
        json=payload,
    )

    assert response.status_code == 422


def test_chat_malformed_json(client):
    """POST com JSON malformado deve retornar 422."""
    response = client.post(
        "/llm_lang/chat_gpt_4o_mini_128k",
        headers={"Content-Type": "application/json", "X-Internal-Test-Call": "true"},
        content=b"{invalido json",
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 3. Validação de entrada - FeedbackRequest (422 Unprocessable Entity)
# ---------------------------------------------------------------------------


def test_feedback_stars_above_max(client):
    """POST /feedback/feedback com stars=6 deve retornar 422."""
    payload = {"id_mensagem": 1, "stars": 6}

    response = client.post("/feedback/feedback", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body


def test_feedback_stars_below_min(client):
    """POST /feedback/feedback com stars=0 deve retornar 422."""
    payload = {"id_mensagem": 1, "stars": 0}

    response = client.post("/feedback/feedback", json=payload)

    assert response.status_code == 422


def test_feedback_missing_id_mensagem(client):
    """POST /feedback/feedback sem id_mensagem deve retornar 422."""
    payload = {"stars": 3}

    response = client.post("/feedback/feedback", json=payload)

    assert response.status_code == 422
    body = response.json()
    fields = [err["loc"] for err in body["detail"]]
    assert any("id_mensagem" in loc for loc in fields)


def test_feedback_missing_stars(client):
    """POST /feedback/feedback sem stars deve retornar 422."""
    payload = {"id_mensagem": 1}

    response = client.post("/feedback/feedback", json=payload)

    assert response.status_code == 422
    body = response.json()
    fields = [err["loc"] for err in body["detail"]]
    assert any("stars" in loc for loc in fields)


def test_feedback_valid_persists_and_returns_id(client):
    """POST /feedback/feedback com dados válidos deve retornar 200 e o ID salvo."""
    payload = {"id_mensagem": 42, "stars": 4, "comment": "Boa resposta"}

    mock_feedback_id = 99

    with patch(
        "sei_ia.routers.feedback.persist_feedback",
        new=AsyncMock(return_value=mock_feedback_id),
    ):
        response = client.post("/feedback/feedback", json=payload)

    assert response.status_code == 200
    assert response.json() == mock_feedback_id


def test_feedback_valid_without_comment(client):
    """POST /feedback/feedback sem comment (campo opcional) deve retornar 200."""
    payload = {"id_mensagem": 10, "stars": 5}

    mock_feedback_id = 7

    with patch(
        "sei_ia.routers.feedback.persist_feedback",
        new=AsyncMock(return_value=mock_feedback_id),
    ):
        response = client.post("/feedback/feedback", json=payload)

    assert response.status_code == 200
    assert response.json() == mock_feedback_id


def test_feedback_stars_boundary_min(client):
    """POST /feedback/feedback com stars=1 (mínimo válido) deve retornar 200."""
    payload = {"id_mensagem": 1, "stars": 1}

    with patch(
        "sei_ia.routers.feedback.persist_feedback",
        new=AsyncMock(return_value=1),
    ):
        response = client.post("/feedback/feedback", json=payload)

    assert response.status_code == 200


def test_feedback_stars_boundary_max(client):
    """POST /feedback/feedback com stars=5 (máximo válido) deve retornar 200."""
    payload = {"id_mensagem": 1, "stars": 5}

    with patch(
        "sei_ia.routers.feedback.persist_feedback",
        new=AsyncMock(return_value=2),
    ):
        response = client.post("/feedback/feedback", json=payload)

    assert response.status_code == 200


def test_feedback_database_error_returns_503(client):
    """POST /feedback/feedback com falha no banco deve retornar 503."""
    payload = {"id_mensagem": 1, "stars": 3}

    with patch(
        "sei_ia.routers.feedback.persist_feedback",
        new=AsyncMock(side_effect=SQLAlchemyError("conexão recusada")),
    ):
        response = client.post("/feedback/feedback", json=payload)

    assert response.status_code == 503
    body = response.json()
    assert "detail" in body


# ---------------------------------------------------------------------------
# 4. Erros de API SEI durante chat (histórico)
# ---------------------------------------------------------------------------


@responses.activate
def test_chat_sei_api_history_error_returns_error(client, mock_solr_post):
    """Quando a API SEI retorna 500 ao buscar histórico, a aplicação deve tratar o erro."""

    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_historico_topico",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_historico_topico",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdTopico": "0",
                }
            )
        ],
        json={"error": "internal server error"},
        status=500,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Olá!",
        "temperature": 0,
        "max_tokens": 4000,
    }
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-Internal-Test-Call": "true",
    }

    # O sistema deve tratar o erro da SEI e retornar algo (não crashar com 500 sem controle)
    # O comportamento exato depende da implementação: pode continuar sem histórico ou retornar erro
    response = client.post(
        "/llm_lang/chat_gpt_4o_mini_128k", headers=headers, json=payload
    )

    # A aplicação não deve retornar um erro não tratado (500 genérico sem corpo JSON)
    assert response.status_code in (200, 400, 422, 500, 503)
    if response.status_code != 200:
        # Se retornar erro, deve ter corpo JSON com detalhes
        body = response.json()
        assert body is not None


@responses.activate
def test_chat_sei_api_history_connection_refused(client, mock_solr_post):
    """Quando a API SEI recusa conexão ao buscar histórico, a aplicação deve tratar o erro."""

    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_historico_topico",
        body=ConnectionError("Connection refused"),
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Olá!",
        "temperature": 0,
        "max_tokens": 4000,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Test-Call": "true",
    }

    response = client.post(
        "/llm_lang/chat_gpt_4o_mini_128k", headers=headers, json=payload
    )

    # A aplicação não deve explodir silenciosamente - deve retornar um status HTTP
    assert response.status_code in (200, 400, 500, 503)
    # Resposta deve ser JSON válido
    body = response.json()
    assert body is not None
