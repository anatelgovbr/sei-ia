"""
Testes para sei_ia/middleware/middleware_exception_handlers.py.

Cobre os caminhos sem cobertura:
1. http_exception_handler com status 204 → Response vazia (sem body)  [via TestClient]
2. http_exception_handler com exceção customizada (não HTTPException) → usa getattr [direto]
3. _extract_request_payload — função interna testada diretamente:
   - body None (lido do request)
   - body vazio (bytes b"")
   - body com JSON inválido
   - body com bytes não UTF-8
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. http_exception_handler — status 204 retorna Response vazia
# ---------------------------------------------------------------------------


def test_chat_http_exception_204_retorna_sem_body(client):
    """
    Quando HTTPException204 é levantada dentro do grafo, o http_exception_handler
    deve retornar um Response com status 204 e sem body (conforme especificação HTTP).
    """
    from sei_ia.services.exceptions.http_exceptions import HTTPException204

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(side_effect=HTTPException204())

    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post(
            "/llm_lang/chat_gpt_4o_mini_128k",
            headers={
                "Content-Type": "application/json",
                "X-Internal-Test-Call": "true",
            },
            json={"id_usuario": 0, "id_topico": 0, "text": "Olá!"},
        )

    assert response.status_code == 204
    assert response.content == b""


# ---------------------------------------------------------------------------
# 2. http_exception_handler — exceção customizada (não HTTPException)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_exception_handler_excecao_customizada_usa_getattr():
    """
    http_exception_handler com exceção não-HTTPException usa getattr para obter
    status_code e detail — testado diretamente (sem passar pelo TestClient,
    que re-lança exceções não-HTTPException por padrão).
    """
    from sei_ia.middleware.middleware_exception_handlers import http_exception_handler

    class CustomAppError(Exception):
        status_code = 503
        detail = "Serviço temporariamente indisponível"

    mock_request = MagicMock()
    mock_request.state._state = {}

    response = await http_exception_handler(mock_request, CustomAppError())

    assert response.status_code == 503
    body = json.loads(response.body)
    assert "message" in body
    assert "Serviço temporariamente indisponível" in body["message"]


@pytest.mark.asyncio
async def test_http_exception_handler_excecao_sem_atributos_usa_defaults():
    """
    Exceção sem status_code nem detail deve usar defaults: 500 e str(exc).
    """
    from sei_ia.middleware.middleware_exception_handlers import http_exception_handler

    mock_request = MagicMock()
    mock_request.state._state = {}

    response = await http_exception_handler(mock_request, ValueError("erro genérico"))

    assert response.status_code == 500
    body = json.loads(response.body)
    assert "message" in body
    assert "erro genérico" in body["message"]


# ---------------------------------------------------------------------------
# 3. _extract_request_payload — testes diretos da função interna
# ---------------------------------------------------------------------------


def _run(coro):
    """Executa uma coroutine de forma síncrona para testes."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_request(body: bytes | None = None, body_raises: bool = False):
    """Cria um mock de Request com o body especificado."""
    mock_request = MagicMock()

    if body_raises:
        mock_request.state = MagicMock(spec=[])  # sem atributo 'body'
        mock_request.body = AsyncMock(side_effect=RuntimeError("stream closed"))
    elif body is None:
        # body não está em state (será lido via request.body())
        mock_request.state = MagicMock(spec=[])  # sem atributo 'body'
        mock_request.body = AsyncMock(return_value=b"")
    else:
        mock_request.state.body = body

    return mock_request


def test_extract_payload_body_vazio_retorna_dict_vazio():
    """_extract_request_payload com body vazio deve retornar {}."""
    from sei_ia.middleware.middleware_exception_handlers import _extract_request_payload

    request = _make_request(body=b"")
    result = _run(_extract_request_payload(request))

    assert result == {}


def test_extract_payload_json_valido_retorna_dict():
    """_extract_request_payload com JSON válido deve retornar o dict parseado."""
    from sei_ia.middleware.middleware_exception_handlers import _extract_request_payload

    payload = {"id_usuario": 1, "text": "Olá"}
    request = _make_request(body=json.dumps(payload).encode("utf-8"))
    result = _run(_extract_request_payload(request))

    assert result == payload


def test_extract_payload_json_invalido_retorna_dict_vazio():
    """_extract_request_payload com JSON malformado deve retornar {} sem lançar exceção."""
    from sei_ia.middleware.middleware_exception_handlers import _extract_request_payload

    request = _make_request(body=b"{invalido json")
    result = _run(_extract_request_payload(request))

    assert result == {}


def test_extract_payload_bytes_nao_utf8_retorna_dict_vazio():
    """_extract_request_payload com bytes não UTF-8 deve retornar {} sem lançar exceção."""
    from sei_ia.middleware.middleware_exception_handlers import _extract_request_payload

    request = _make_request(body=b"\xff\xfe bytes inv\xe1lidos")
    result = _run(_extract_request_payload(request))

    assert result == {}


def test_extract_payload_body_none_le_do_request():
    """
    Quando state.body não existe, _extract_request_payload deve ler via request.body().
    Se request.body() retorna b"", retorna {}.
    """
    from sei_ia.middleware.middleware_exception_handlers import _extract_request_payload

    request = _make_request(body=None)  # state sem 'body', request.body() retorna b""
    result = _run(_extract_request_payload(request))

    assert result == {}


def test_extract_payload_body_exception_retorna_dict_vazio():
    """
    Quando request.body() lança exceção (BaseException), deve capturar e retornar {}.
    """
    from sei_ia.middleware.middleware_exception_handlers import _extract_request_payload

    request = _make_request(body_raises=True)
    result = _run(_extract_request_payload(request))

    assert result == {}
