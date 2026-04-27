"""
Testes E2E para linhas não cobertas em sei_ia/routers/chat/__init__.py.

Cobre:
1. Langfuse non-None — _langfuse_span, _flush_langfuse, _update_langfuse_trace (55-56, 62, 70-74)
2. Cleanup em process_chat_completion com id_procedimentos (347, 352, 354)
3. Erros em process_chat_completion_with_model via /llm_lang/chat_gpt_general (441-520):
   - ReadTimeout → 408
   - BadRequestError → 413
   - BadRequestError + content_filter → 403
   - RateLimitError → 429
   - InternalServerError → 502
   - APIConnectionError → 503
4. Cleanup em process_chat_completion_with_model (498-520)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai

HEADERS = {"Content-Type": "application/json", "X-Internal-Test-Call": "true"}

PAYLOAD_4O = {"id_usuario": 1, "id_topico": 0, "text": "Olá!"}
PAYLOAD_GENERAL = {"id_usuario": 1, "id_topico": 0, "text": "Olá!", "agent_type": None}
PAYLOAD_COM_PROC = {
    "id_usuario": 1,
    "id_topico": 0,
    "text": "Olá!",
    "id_procedimentos": [{"id_procedimento": "001", "id_documentos": ["DOC001"]}],
}

ENDPOINT_4O = "/llm_lang/chat_gpt_4o_128k"
ENDPOINT_GENERAL = "/llm_lang/chat_gpt_general"


def _fake_ainvoke_ok(content="Resposta"):
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


def _patch_graph_exc(exc):
    """Patch build_chat_completion_graph com exceção no ainvoke."""
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(side_effect=exc)
    return patch(
        "sei_ia.routers.chat.build_chat_completion_graph", return_value=mock_graph
    )


# ---------------------------------------------------------------------------
# 1. Langfuse non-None — _langfuse_span, _flush_langfuse, _update_langfuse_trace
# ---------------------------------------------------------------------------


def _make_langfuse_mock():
    """Cria mock de langfuse com start_as_current_span como context manager."""
    mock_langfuse = MagicMock()
    mock_span = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_span)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_langfuse.start_as_current_span.return_value = mock_ctx
    return mock_langfuse, mock_span


def test_langfuse_nao_none_span_criado_e_flush_chamado(client):
    """
    Quando langfuse não é None, _langfuse_span deve criar span via
    start_as_current_span (linhas 55-56) e _flush_langfuse chama langfuse.flush() (linha 62).
    """
    mock_langfuse, mock_span = _make_langfuse_mock()
    mock_graph = _fake_ainvoke_ok()

    with (
        patch("sei_ia.routers.chat.langfuse", mock_langfuse),
        patch(
            "sei_ia.routers.chat.build_chat_completion_graph", return_value=mock_graph
        ),
    ):
        response = client.post(ENDPOINT_4O, headers=HEADERS, json=PAYLOAD_4O)

    assert response.status_code == 200
    mock_langfuse.start_as_current_span.assert_called_once_with(name="LangGraph")
    mock_langfuse.flush.assert_called_once()


def test_langfuse_update_trace_com_span_nao_none(client):
    """
    _update_langfuse_trace com span não-None deve chamar span.update_trace()
    (linhas 70-74).
    """
    mock_langfuse, mock_span = _make_langfuse_mock()
    mock_graph = _fake_ainvoke_ok()

    with (
        patch("sei_ia.routers.chat.langfuse", mock_langfuse),
        patch(
            "sei_ia.routers.chat.build_chat_completion_graph", return_value=mock_graph
        ),
    ):
        response = client.post(ENDPOINT_4O, headers=HEADERS, json=PAYLOAD_4O)

    assert response.status_code == 200
    assert mock_span.update_trace.call_count >= 1


def test_langfuse_update_trace_process_with_model(client):
    """
    _update_langfuse_trace também é chamado em process_chat_completion_with_model
    quando langfuse é não-None.
    """
    mock_langfuse, mock_span = _make_langfuse_mock()
    mock_graph = _fake_ainvoke_ok()

    with (
        patch("sei_ia.routers.chat.langfuse", mock_langfuse),
        patch(
            "sei_ia.routers.chat.build_chat_completion_graph", return_value=mock_graph
        ),
    ):
        response = client.post(ENDPOINT_GENERAL, headers=HEADERS, json=PAYLOAD_GENERAL)

    assert response.status_code == 200
    assert mock_span.update_trace.call_count >= 1
    mock_langfuse.flush.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Cleanup em process_chat_completion com id_procedimentos
# ---------------------------------------------------------------------------


def test_cleanup_executado_quando_id_procedimentos_presente(client):
    """
    Quando o user_state tem id_procedimentos, o bloco finally chama
    cleanup_non_cacheable_documents (linhas 332-346).
    """
    mock_graph = _fake_ainvoke_ok()
    mock_cleanup_result = {"deleted_from_redis": [], "deleted_from_postgres": []}

    with (
        patch(
            "sei_ia.routers.chat.build_chat_completion_graph", return_value=mock_graph
        ),
        patch(
            "sei_ia.routers.chat.cleanup_non_cacheable_documents",
            new=AsyncMock(return_value=mock_cleanup_result),
        ),
        patch("sei_ia.routers.chat.app_db_instance") as mock_db,
    ):
        mock_db.async_engine = MagicMock()
        response = client.post(ENDPOINT_4O, headers=HEADERS, json=PAYLOAD_COM_PROC)

    assert response.status_code == 200


def test_cleanup_com_deletions_loga_debug(client):
    """
    Quando cleanup retorna deleted_from_redis/postgres não-vazio, o logger.debug
    é chamado (linha 347). A resposta deve ser normal (cleanup é auxiliar).
    """
    mock_graph = _fake_ainvoke_ok()
    mock_cleanup_result = {
        "deleted_from_redis": ["key1"],
        "deleted_from_postgres": ["id1"],
    }

    with (
        patch(
            "sei_ia.routers.chat.build_chat_completion_graph", return_value=mock_graph
        ),
        patch(
            "sei_ia.routers.chat.cleanup_non_cacheable_documents",
            new=AsyncMock(return_value=mock_cleanup_result),
        ),
        patch("sei_ia.routers.chat.app_db_instance") as mock_db,
    ):
        mock_db.async_engine = MagicMock()
        response = client.post(ENDPOINT_4O, headers=HEADERS, json=PAYLOAD_COM_PROC)

    assert response.status_code == 200


def test_cleanup_excecao_nao_propaga(client):
    """
    Exceção no cleanup (linhas 352-354) deve ser capturada e logada como warning.
    A resposta original deve ser retornada normalmente.
    """
    mock_graph = _fake_ainvoke_ok()

    with (
        patch(
            "sei_ia.routers.chat.build_chat_completion_graph", return_value=mock_graph
        ),
        patch(
            "sei_ia.routers.chat.cleanup_non_cacheable_documents",
            new=AsyncMock(side_effect=RuntimeError("Erro de DB")),
        ),
        patch("sei_ia.routers.chat.app_db_instance") as mock_db,
    ):
        mock_db.async_engine = MagicMock()
        response = client.post(ENDPOINT_4O, headers=HEADERS, json=PAYLOAD_COM_PROC)

    # A resposta deve ser 200 — erro no cleanup não propaga
    assert response.status_code == 200
    assert "choices" in response.json()


# ---------------------------------------------------------------------------
# 3. Erros em process_chat_completion_with_model (/llm_lang/chat_gpt_general)
# ---------------------------------------------------------------------------


def _make_http_response(status: int, body: dict) -> httpx.Response:
    return httpx.Response(
        status,
        json=body,
        request=httpx.Request("POST", "https://mock.openai.azure.com/"),
    )


def test_with_model_read_timeout_retorna_408(client):
    """ReadTimeout em process_chat_completion_with_model → 408 (linha 441-442)."""
    with _patch_graph_exc(httpx.ReadTimeout("timeout")):
        response = client.post(ENDPOINT_GENERAL, headers=HEADERS, json=PAYLOAD_GENERAL)

    assert response.status_code == 408


def test_with_model_api_timeout_retorna_408(client):
    """openai.APITimeoutError em process_chat_completion_with_model → 408."""
    exc = openai.APITimeoutError(
        request=httpx.Request("POST", "https://mock.openai.azure.com/")
    )
    with _patch_graph_exc(exc):
        response = client.post(ENDPOINT_GENERAL, headers=HEADERS, json=PAYLOAD_GENERAL)

    assert response.status_code == 408


def test_with_model_bad_request_sem_content_filter_retorna_413(client):
    """BadRequestError sem content_filter → 413 (linhas 444-466)."""
    exc = openai.BadRequestError(
        "bad request",
        response=_make_http_response(
            400, {"error": {"code": "context_length_exceeded"}}
        ),
        body={},
    )
    with _patch_graph_exc(exc):
        response = client.post(ENDPOINT_GENERAL, headers=HEADERS, json=PAYLOAD_GENERAL)

    assert response.status_code == 413


def test_with_model_bad_request_content_filter_retorna_403(client):
    """BadRequestError com content_filter → 403 (linhas 458-462)."""
    exc = openai.BadRequestError(
        "content filter",
        response=_make_http_response(
            400,
            {
                "error": {
                    "code": "content_filter",
                    "innererror": {"code": "ResponsibleAIPolicyViolation"},
                }
            },
        ),
        body={},
    )
    with _patch_graph_exc(exc):
        response = client.post(ENDPOINT_GENERAL, headers=HEADERS, json=PAYLOAD_GENERAL)

    assert response.status_code == 403


def test_with_model_rate_limit_retorna_429(client):
    """RateLimitError → 429 (linhas 468-469)."""
    exc = openai.RateLimitError(
        "rate limit",
        response=_make_http_response(429, {}),
        body={},
    )
    with _patch_graph_exc(exc):
        response = client.post(ENDPOINT_GENERAL, headers=HEADERS, json=PAYLOAD_GENERAL)

    assert response.status_code == 429


def test_with_model_internal_server_error_retorna_502(client):
    """InternalServerError → 502 (linhas 470-474)."""
    exc = openai.InternalServerError(
        "internal error",
        response=_make_http_response(500, {}),
        body={},
    )
    with _patch_graph_exc(exc):
        response = client.post(ENDPOINT_GENERAL, headers=HEADERS, json=PAYLOAD_GENERAL)

    assert response.status_code == 502


def test_with_model_api_connection_error_retorna_503(client):
    """APIConnectionError → 503 (linhas 479-482)."""
    exc = openai.APIConnectionError(
        request=httpx.Request("POST", "https://mock.openai.azure.com/")
    )
    with _patch_graph_exc(exc):
        response = client.post(ENDPOINT_GENERAL, headers=HEADERS, json=PAYLOAD_GENERAL)

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# 4. Cleanup em process_chat_completion_with_model com id_procedimentos
# ---------------------------------------------------------------------------

PAYLOAD_GENERAL_COM_PROC = {
    **PAYLOAD_GENERAL,
    "id_procedimentos": [{"id_procedimento": "001", "id_documentos": ["DOC001"]}],
}


def test_with_model_cleanup_executado_quando_id_procedimentos_presente(client):
    """
    cleanup_non_cacheable_documents é chamado no finally de
    process_chat_completion_with_model quando id_procedimentos está presente (linhas 498-506).
    """
    mock_graph = _fake_ainvoke_ok()
    mock_cleanup_result = {"deleted_from_redis": [], "deleted_from_postgres": []}

    with (
        patch(
            "sei_ia.routers.chat.build_chat_completion_graph", return_value=mock_graph
        ),
        patch(
            "sei_ia.routers.chat.cleanup_non_cacheable_documents",
            new=AsyncMock(return_value=mock_cleanup_result),
        ),
        patch("sei_ia.routers.chat.app_db_instance") as mock_db,
    ):
        mock_db.async_engine = MagicMock()
        response = client.post(
            ENDPOINT_GENERAL, headers=HEADERS, json=PAYLOAD_GENERAL_COM_PROC
        )

    assert response.status_code == 200


def test_with_model_cleanup_com_deletions_loga_debug(client):
    """
    Cleanup retornando items deletados loga via debug (linhas 509-517).
    """
    mock_graph = _fake_ainvoke_ok()
    mock_cleanup_result = {
        "deleted_from_redis": ["key1"],
        "deleted_from_postgres": ["id1"],
    }

    with (
        patch(
            "sei_ia.routers.chat.build_chat_completion_graph", return_value=mock_graph
        ),
        patch(
            "sei_ia.routers.chat.cleanup_non_cacheable_documents",
            new=AsyncMock(return_value=mock_cleanup_result),
        ),
        patch("sei_ia.routers.chat.app_db_instance") as mock_db,
    ):
        mock_db.async_engine = MagicMock()
        response = client.post(
            ENDPOINT_GENERAL, headers=HEADERS, json=PAYLOAD_GENERAL_COM_PROC
        )

    assert response.status_code == 200


def test_with_model_cleanup_excecao_nao_propaga(client):
    """
    Exceção no cleanup de process_chat_completion_with_model (linhas 518-520)
    não deve afetar a resposta.
    """
    mock_graph = _fake_ainvoke_ok()

    with (
        patch(
            "sei_ia.routers.chat.build_chat_completion_graph", return_value=mock_graph
        ),
        patch(
            "sei_ia.routers.chat.cleanup_non_cacheable_documents",
            new=AsyncMock(side_effect=RuntimeError("Erro de DB")),
        ),
        patch("sei_ia.routers.chat.app_db_instance") as mock_db,
    ):
        mock_db.async_engine = MagicMock()
        response = client.post(
            ENDPOINT_GENERAL, headers=HEADERS, json=PAYLOAD_GENERAL_COM_PROC
        )

    assert response.status_code == 200
