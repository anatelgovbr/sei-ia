"""
Testes E2E para sei_ia/routers/chat/gpt_4o_128k.py.

Cobre os três endpoints do arquivo:
  POST /llm_lang/chat_gpt_4o_128k  → process_chat_completion (model_type="standard")
  POST /llm_lang/chat_gpt_4_128k   → process_chat_completion (DEFAULT_RESPONSE_MODEL)
  POST /llm_lang/stream             → streaming SSE via graph_workflow.astream()

E a função auxiliar:
  json_serializer() → serialização de datetime
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest

HEADERS = {"Content-Type": "application/json", "X-Internal-Test-Call": "true"}
BASIC_PAYLOAD = {"id_usuario": 1, "id_topico": 0, "text": "Olá!"}


# ---------------------------------------------------------------------------
# Helpers compartilhados
# ---------------------------------------------------------------------------


def _make_graph_ainvoke(content="Resposta padrão"):
    """Mock de graph para endpoints não-streaming (ainvoke)."""

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


def _make_graph_astream(events_fn):
    """
    Mock de graph para o endpoint de streaming (astream).
    events_fn(user_state) deve ser um async generator.
    """
    mock_graph = MagicMock()
    mock_graph.astream = events_fn
    return mock_graph


def _parse_sse(response_text: str) -> list[dict]:
    """Extrai eventos de um texto SSE (text/event-stream)."""
    events = []
    for line in response_text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ---------------------------------------------------------------------------
# 1. POST /llm_lang/chat_gpt_4o_128k
# ---------------------------------------------------------------------------


def test_chat_gpt_4o_128k_sucesso(client):
    """
    Endpoint /llm_lang/chat_gpt_4o_128k deve retornar 200 com choices
    quando o grafo completa com sucesso. Usa model_type="standard".
    """
    mock_graph = _make_graph_ainvoke("Resposta do modelo standard.")

    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post(
            "/llm_lang/chat_gpt_4o_128k", headers=HEADERS, json=BASIC_PAYLOAD
        )

    assert response.status_code == 200
    body = response.json()
    assert "choices" in body
    assert body["choices"][0]["message"]["content"] == "Resposta do modelo standard."


def test_chat_gpt_4o_128k_use_thinking_usa_model_think(client):
    """
    Com use_thinking=True, deve usar model_type="think" ao invés de "standard".
    """
    capturado = {}

    async def fake_ainvoke(user_state, config=None):
        capturado["model_type"] = user_state["model_type"]
        final = dict(user_state)
        final["response"] = {
            "response": "Resposta com thinking.",
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
        response = client.post(
            "/llm_lang/chat_gpt_4o_128k",
            headers=HEADERS,
            json={**BASIC_PAYLOAD, "use_thinking": True},
        )

    assert response.status_code == 200
    assert capturado["model_type"] == "think"


def test_chat_gpt_4o_128k_validacao_422(client):
    """Payload sem campo obrigatório deve retornar 422."""
    response = client.post(
        "/llm_lang/chat_gpt_4o_128k",
        headers=HEADERS,
        json={"id_usuario": 1},  # falta text
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 2. POST /llm_lang/chat_gpt_4_128k
# ---------------------------------------------------------------------------


def test_chat_gpt_4_128k_sucesso(client):
    """
    Endpoint legado /llm_lang/chat_gpt_4_128k retorna 200 usando DEFAULT_RESPONSE_MODEL.
    """
    mock_graph = _make_graph_ainvoke("Resposta do modelo default.")

    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post(
            "/llm_lang/chat_gpt_4_128k", headers=HEADERS, json=BASIC_PAYLOAD
        )

    assert response.status_code == 200
    body = response.json()
    assert "choices" in body
    assert body["choices"][0]["message"]["content"] == "Resposta do modelo default."


def test_chat_gpt_4_128k_use_thinking_usa_model_think(client):
    """Com use_thinking=True no endpoint legado, deve usar model_type='think'."""
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
            "/llm_lang/chat_gpt_4_128k",
            headers=HEADERS,
            json={**BASIC_PAYLOAD, "use_thinking": True},
        )

    assert response.status_code == 200
    assert capturado["model_type"] == "think"


# ---------------------------------------------------------------------------
# 3. POST /llm_lang/stream — caminho feliz
# ---------------------------------------------------------------------------


def test_stream_sucesso_retorna_eventos_sse(client):
    """
    Streaming bem-sucedido deve retornar 200 com Content-Type text/event-stream
    e conter eventos dos tipos: content, metadata, end.
    """

    async def fake_astream(user_state, config=None, stream_mode=None):
        yield ("custom", "Olá! ")
        yield ("custom", "Como posso ajudá-lo?")
        final = dict(user_state)
        final["response"] = {
            "response": "Olá! Como posso ajudá-lo?",
            "n_tokens": [10, 5],
            "finish_reason": "stop",
            "type_choiced_summary": "Not found",
            "reasoning": None,
        }
        yield ("values", final)

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    events = _parse_sse(response.text)
    tipos = [e["type"] for e in events]

    assert "content" in tipos
    assert "metadata" in tipos
    assert "end" in tipos

    # Verifica conteúdo do evento metadata
    metadata_event = next(e for e in events if e["type"] == "metadata")
    assert "choices" in metadata_event["data"] or "usage" in metadata_event["data"]


def test_stream_evento_status_emitido(client):
    """
    Evento ("custom", {"_status": "..."}) deve gerar SSE de tipo "status".
    """

    async def fake_astream(user_state, config=None, stream_mode=None):
        yield ("custom", {"_status": "Buscando documentos..."})
        yield ("custom", "Resposta.")
        final = dict(user_state)
        final["response"] = {
            "response": "Resposta.",
            "n_tokens": [5, 3],
            "finish_reason": "stop",
            "type_choiced_summary": "Not found",
            "reasoning": None,
        }
        yield ("values", final)

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    tipos = [e["type"] for e in events]
    assert "status" in tipos


# ---------------------------------------------------------------------------
# 4. POST /llm_lang/stream — tratamento de erros no astream
# ---------------------------------------------------------------------------


def test_stream_http_exception_413_emite_evento_erro(client):
    """
    HTTPException413 levantada durante astream deve gerar evento SSE de erro
    com status_code=413 (sem abortar o response HTTP com erro).
    """
    from sei_ia.services.exceptions.http_exceptions import HTTPException413

    async def fake_astream(user_state, config=None, stream_mode=None):
        raise HTTPException413()
        yield  # torna a função um async generator

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 200  # HTTP sempre 200; erro fica no payload SSE
    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 413


def test_stream_http_exception_404_emite_evento_erro(client):
    """HTTPException404 dentro do astream deve gerar evento de erro com status_code=404."""
    from sei_ia.services.exceptions.http_exceptions import HTTPException404

    async def fake_astream(user_state, config=None, stream_mode=None):
        raise HTTPException404()
        yield

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 404


def test_stream_openai_bad_request_emite_erro_413(client):
    """openai.BadRequestError no streaming deve gerar evento de erro com status_code=413."""

    async def fake_astream(user_state, config=None, stream_mode=None):
        mock_http = httpx.Response(
            400,
            json={"error": {"code": "context_length_exceeded"}},
            request=httpx.Request("POST", "https://mock.openai.azure.com/"),
        )
        raise openai.BadRequestError("context exceeded", response=mock_http, body={})
        yield

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 413


def test_stream_openai_bad_request_content_filter_emite_erro_403(client):
    """openai.BadRequestError com content_filter no streaming deve gerar evento de erro com status_code=403."""

    async def fake_astream(user_state, config=None, stream_mode=None):
        error_body = {
            "error": {
                "code": "content_filter",
                "innererror": {"code": "ResponsibleAIPolicyViolation"},
            }
        }
        mock_http = httpx.Response(
            400,
            json=error_body,
            request=httpx.Request("POST", "https://mock.openai.azure.com/"),
        )
        raise openai.BadRequestError(
            "content filter violation", response=mock_http, body=error_body
        )
        yield

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 403
    assert (
        "bloqueado" in error_events[0]["detail"].lower()
        or "política" in error_events[0]["detail"].lower()
    )


def test_stream_openai_rate_limit_emite_erro_429(client):
    """openai.RateLimitError no streaming deve gerar evento de erro com status_code=429."""

    async def fake_astream(user_state, config=None, stream_mode=None):
        mock_http = httpx.Response(
            429,
            json={"error": {"code": "rate_limit"}},
            request=httpx.Request("POST", "https://mock.openai.azure.com/"),
        )
        raise openai.RateLimitError("rate limit", response=mock_http, body={})
        yield

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 429


def test_stream_openai_internal_server_error_emite_erro_502(client):
    """openai.InternalServerError no streaming deve gerar evento de erro com status_code=502."""

    async def fake_astream(user_state, config=None, stream_mode=None):
        mock_http = httpx.Response(
            500,
            json={"error": {"code": "internal"}},
            request=httpx.Request("POST", "https://mock.openai.azure.com/"),
        )
        raise openai.InternalServerError("internal error", response=mock_http, body={})
        yield

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 502


def test_stream_openai_connection_error_emite_erro_503(client):
    """openai.APIConnectionError no streaming deve gerar evento de erro com status_code=503."""

    async def fake_astream(user_state, config=None, stream_mode=None):
        raise openai.APIConnectionError(request=MagicMock(spec=httpx.Request))
        yield

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 503


def test_stream_httpx_timeout_emite_erro_408(client):
    """
    httpx.TimeoutException no streaming deve gerar evento de erro com status_code=408.

    Nota: openai.APITimeoutError herda de openai.APIConnectionError, portanto é capturado
    pelo handler de APIConnectionError (503) antes de chegar ao handler de timeout (408).
    Para exercitar o caminho 408 usa-se httpx.TimeoutException diretamente.
    """

    async def fake_astream(user_state, config=None, stream_mode=None):
        raise httpx.TimeoutException("timeout")
        yield

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 408


def test_stream_openai_api_timeout_capturado_como_503(client):
    """
    openai.APITimeoutError herda de APIConnectionError, portanto é capturado
    pelo handler de conexão e gera evento de erro com status_code=503 (não 408).
    """

    async def fake_astream(user_state, config=None, stream_mode=None):
        raise openai.APITimeoutError(request=MagicMock(spec=httpx.Request))
        yield

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 503


def test_stream_excecao_generica_emite_erro_500(client):
    """
    Exceção genérica (não tratada pelos handlers específicos) deve ser capturada
    pelo fallback e gerar evento de erro com status_code=500.
    """

    async def fake_astream(user_state, config=None, stream_mode=None):
        yield ("custom", "token inicial")
        raise RuntimeError("erro inesperado genérico")

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 500


# ---------------------------------------------------------------------------
# 5. Handlers restantes do streaming
# ---------------------------------------------------------------------------


def test_stream_chat_error_emite_evento_erro(client):
    """
    ChatError levantada durante astream deve gerar evento SSE de erro.
    status_code >= 500 é mapeado para 502; < 500 usa o valor original.
    """
    from sei_ia.services.llm_models.chat_workflow import ChatError

    async def fake_astream(user_state, config=None, stream_mode=None):
        raise ChatError(status_code=503, detail="LLM retornou erro interno")
        yield

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 502  # >= 500 → mapeado para 502


def test_stream_chat_error_4xx_mantém_status(client):
    """ChatError com status_code 4xx deve manter o status original (não 502)."""
    from sei_ia.services.llm_models.chat_workflow import ChatError

    async def fake_astream(user_state, config=None, stream_mode=None):
        raise ChatError(status_code=403, detail="Acesso negado")
        yield

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 403


def test_stream_httpx_read_error_emite_evento_502(client):
    """httpx.ReadError durante astream deve gerar evento de erro com status_code=502."""

    async def fake_astream(user_state, config=None, stream_mode=None):
        raise httpx.ReadError("conexão interrompida")
        yield

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status_code"] == 502


# ---------------------------------------------------------------------------
# 6. json_serializer
# ---------------------------------------------------------------------------


def test_json_serializer_datetime():
    """json_serializer deve converter datetime para string ISO 8601."""
    from sei_ia.routers.chat.gpt_4o_128k import json_serializer

    dt = datetime(2024, 6, 15, 12, 30, 0)
    result = json_serializer(dt)

    assert result == "2024-06-15T12:30:00"


def test_json_serializer_tipo_desconhecido_levanta_type_error():
    """json_serializer deve levantar TypeError para tipos não suportados."""
    from sei_ia.routers.chat.gpt_4o_128k import json_serializer

    with pytest.raises(TypeError, match="is not JSON serializable"):
        json_serializer(object())


# ---------------------------------------------------------------------------
# 7. Streaming — eventos especiais (None, não-tupla, tupla malformada)
# ---------------------------------------------------------------------------


def _make_state_with_response(user_state: dict, content: str = "Resposta") -> dict:
    """Cria final_state com response preenchido."""
    state = dict(user_state)
    state["endpoint_name"] = "stream"
    state["doc_rag"] = False
    state["rag_documents_count"] = 0
    state["tool_web_search"] = None
    state["id_to_formatted_map"] = {}
    state["id_procedimentos"] = []
    state["response"] = {
        "response": content,
        "n_tokens": [10, 5],
        "finish_reason": "stop",
        "type_choiced_summary": "Not found",
        "reasoning": None,
    }
    return state


def test_stream_evento_none_ignorado(client):
    """
    Evento None emitido pelo astream deve ser ignorado (linha 400: continue).
    O stream deve completar normalmente com eventos metadata e end.
    """

    async def fake_astream(user_state, config=None, stream_mode=None):
        yield None  # evento None — deve ser ignorado
        yield ("values", _make_state_with_response(user_state))

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 200
    events = _parse_sse(response.text)
    tipos = [e["type"] for e in events]
    assert "end" in tipos


def test_stream_evento_nao_tupla_ignorado(client):
    """
    Evento que não é tupla deve gerar warning e ser ignorado (linhas 402-403).
    O stream deve completar normalmente.
    """

    async def fake_astream(user_state, config=None, stream_mode=None):
        yield "evento_string_invalido"  # não é tupla
        yield ("values", _make_state_with_response(user_state))

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert any(e["type"] == "end" for e in events)


def test_stream_tupla_comprimento_errado_ignorada(client):
    """
    Tupla com comprimento != 2 deve gerar warning e ser ignorada (linhas 405-408).
    """

    async def fake_astream(user_state, config=None, stream_mode=None):
        yield ("um", "dois", "tres")  # comprimento 3 — inválido
        yield ("values", _make_state_with_response(user_state))

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert any(e["type"] == "end" for e in events)


# ---------------------------------------------------------------------------
# 8. Streaming — token de reasoning (<reasoning>...</reasoning>)
# ---------------------------------------------------------------------------


def test_stream_reasoning_token_emite_evento_reasoning(client):
    """
    Token no formato <reasoning>text</reasoning> deve gerar SSE do tipo 'reasoning'
    com o conteúdo extraído (linhas 441-454).
    """

    async def fake_astream(user_state, config=None, stream_mode=None):
        yield ("custom", "<reasoning>Analisando a questão...</reasoning>")
        yield ("values", _make_state_with_response(user_state))

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 200
    events = _parse_sse(response.text)
    reasoning_events = [e for e in events if e["type"] == "reasoning"]
    assert len(reasoning_events) == 1
    assert reasoning_events[0]["data"] == "Analisando a questão..."


def test_stream_reasoning_token_vazio_nao_emite_evento(client):
    """
    Token <reasoning></reasoning> com conteúdo vazio não deve emitir evento reasoning.
    """

    async def fake_astream(user_state, config=None, stream_mode=None):
        yield ("custom", "<reasoning></reasoning>")  # conteúdo vazio
        yield ("values", _make_state_with_response(user_state))

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    events = _parse_sse(response.text)
    reasoning_events = [e for e in events if e["type"] == "reasoning"]
    assert len(reasoning_events) == 0


# ---------------------------------------------------------------------------
# 9. Streaming — stream_processor flush com conteúdo pendente
# ---------------------------------------------------------------------------


def test_stream_processor_flush_emite_conteudo_pendente(client):
    """
    Quando doc_rag=True, o StreamTagProcessorFinal é inicializado.
    Token com '<' parcial fica no accumulator; flush() o emite ao final (linhas 505-510).
    """

    async def fake_astream(user_state, config=None, stream_mode=None):
        # State com doc_rag=True para inicializar stream_processor
        state = dict(user_state)
        state["endpoint_name"] = "stream"
        state["doc_rag"] = True
        state["rag_documents_count"] = 0
        state["tool_web_search"] = None
        state["id_to_formatted_map"] = {}
        state["id_procedimentos"] = []
        state["response"] = {
            "response": "Resposta",
            "n_tokens": [10, 5],
            "finish_reason": "stop",
            "type_choiced_summary": "Not found",
            "reasoning": None,
        }
        yield ("values", state)
        # Token com '<' parcial — fica acumulado, não emitido durante o loop
        yield ("custom", "<")

    mock_graph = _make_graph_astream(fake_astream)

    with (
        patch(
            "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
            return_value=mock_graph,
        ),
        patch(
            "sei_ia.agents.rag.stream_processor_final.get_document_count",
            return_value=0,
        ),
    ):
        response = client.post("/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 200
    events = _parse_sse(response.text)
    # O conteúdo pendente "<" deve ser emitido como evento "content" pelo flush()
    content_events = [e for e in events if e["type"] == "content"]
    assert any(e["data"] == "<" for e in content_events)


# ---------------------------------------------------------------------------
# 10. Streaming — ValueError quando final_user_state sem 'response'
# ---------------------------------------------------------------------------


def test_stream_final_state_sem_response_levanta_value_error():
    """
    Quando final_user_state existe mas não tem 'response', o código levanta ValueError
    (linha 530). Como está fora do try/except do loop, propaga via ASGI.
    Testa com raise_server_exceptions=False para inspecionar a resposta parcial.
    """
    from fastapi.testclient import TestClient

    from sei_ia.main import get_app

    app = get_app(enable_timeout_middleware=False, enable_request_middleware=False)
    local_client = TestClient(app, raise_server_exceptions=False)

    async def fake_astream(user_state, config=None, stream_mode=None):
        state = dict(user_state)
        state["endpoint_name"] = "stream"
        state["doc_rag"] = False
        state["rag_documents_count"] = 0
        state["tool_web_search"] = None
        state["id_to_formatted_map"] = {}
        state["id_procedimentos"] = []
        # Sem 'response' key → vai provocar ValueError na linha 530
        yield ("values", state)

    mock_graph = _make_graph_astream(fake_astream)

    with patch(
        "sei_ia.routers.chat.gpt_4o_128k.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = local_client.post(
            "/llm_lang/stream", headers=HEADERS, json=BASIC_PAYLOAD
        )

    # Com raise_server_exceptions=False, a resposta HTTP ainda é 200
    # mas o body pode ser incompleto (streaming cortado pela exceção)
    assert response.status_code == 200
