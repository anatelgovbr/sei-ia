"""
Testes E2E para sei_ia/routers/chat/gpt_endpoint.py.

Cobre o endpoint POST /llm_lang/chat_gpt_general que usa
process_chat_completion_with_model com ChatRequestWithModel.
"""

from unittest.mock import AsyncMock, MagicMock, patch

ENDPOINT = "/llm_lang/chat_gpt_general"
HEADERS = {"Content-Type": "application/json", "X-Internal-Test-Call": "true"}

# agent_type é campo obrigatório em ChatRequestWithModel (pode ser None)
BASE_PAYLOAD = {"id_usuario": 1, "id_topico": 0, "text": "Olá!", "agent_type": None}


def _make_graph(content="Resposta padrão."):
    """Mock de graph para process_chat_completion_with_model."""

    async def fake_ainvoke(user_state, config=None):
        final = dict(user_state)
        final["response"] = {
            "response": content,
            "n_tokens": [10, 5],
            "finish_reason": "stop",
            "type_choiced_summary": "Not found",
            "reasoning": None,
        }
        return final

    mock_graph = MagicMock()
    mock_graph.ainvoke = fake_ainvoke
    return mock_graph


# ---------------------------------------------------------------------------
# Sucesso
# ---------------------------------------------------------------------------


def test_chat_gpt_general_sucesso(client):
    """
    POST /llm_lang/chat_gpt_general com payload válido deve retornar 200.
    Usa process_chat_completion_with_model com model_type="standard".
    """
    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=_make_graph("Olá do modelo geral!"),
    ):
        response = client.post(ENDPOINT, headers=HEADERS, json=BASE_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    # process_chat_completion_with_model usa ModelResponseWithMetadata (sem "choices")
    assert "usage" in body
    assert "use_websearch" in body


def test_chat_gpt_general_use_thinking_usa_model_think(client):
    """Com use_thinking=True deve usar model_type='think'."""
    capturado = {}

    async def fake_ainvoke(user_state, config=None):
        capturado["model_type"] = user_state["model_type"]
        final = dict(user_state)
        final["response"] = {
            "response": "ok",
            "n_tokens": [1, 1],
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
        response = client.post(
            ENDPOINT,
            headers=HEADERS,
            json={**BASE_PAYLOAD, "use_thinking": True},
        )

    assert response.status_code == 200
    assert capturado["model_type"] == "think"


def test_chat_gpt_general_com_agent_type_explicito(client):
    """ChatRequestWithModel aceita agent_type com valor válido."""
    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=_make_graph(),
    ):
        response = client.post(
            ENDPOINT,
            headers=HEADERS,
            json={**BASE_PAYLOAD, "agent_type": "mini"},
        )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Validação de entrada
# ---------------------------------------------------------------------------


def test_chat_gpt_general_sem_text_retorna_422(client):
    """Payload sem 'text' deve retornar 422."""
    response = client.post(
        ENDPOINT,
        headers=HEADERS,
        json={"id_usuario": 1, "id_topico": 0, "agent_type": None},
    )
    assert response.status_code == 422


def test_chat_gpt_general_agent_type_invalido_retorna_422(client):
    """agent_type fora do Literal permitido deve retornar 422."""
    response = client.post(
        ENDPOINT,
        headers=HEADERS,
        json={**BASE_PAYLOAD, "agent_type": "invalid"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Tratamento de erros (herda de process_chat_completion_with_model)
# ---------------------------------------------------------------------------


def test_chat_gpt_general_excecao_generica_retorna_500(client):
    """Exception não tratada deve resultar em 500."""
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("falha interna"))

    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post(ENDPOINT, headers=HEADERS, json=BASE_PAYLOAD)

    assert response.status_code == 500


def test_chat_gpt_general_http_exception_412_reraise(client):
    """HTTPException412SeiApiTimeout deve ser re-lançada resultando em 412."""
    from sei_ia.services.exceptions.http_exceptions import HTTPException412SeiApiTimeout

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        side_effect=HTTPException412SeiApiTimeout(document_id="0000001")
    )

    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post(ENDPOINT, headers=HEADERS, json=BASE_PAYLOAD)

    assert response.status_code == 412
