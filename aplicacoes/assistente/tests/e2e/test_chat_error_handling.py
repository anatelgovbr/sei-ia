"""
Testes E2E para tratamento de exceções no router de chat.

Cobre os caminhos de exceção em process_chat_completion que estavam sem cobertura:
1. ReadTimeout / openai.APITimeoutError → 408
2. openai.BadRequestError (genérico, sem content_filter) → 413
3. openai.BadRequestError com content_filter → 403
4. openai.RateLimitError → 429
5. openai.InternalServerError → 502
6. openai.APIConnectionError → 503
7. Exception genérica não tratada → 500
8. HTTPExceptions customizadas são re-lançadas (404, 204, 413, 429, 412)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai

CHAT_ENDPOINT = "/llm_lang/chat_gpt_4o_mini_128k"
CHAT_HEADERS = {
    "Content-Type": "application/json",
    "X-Internal-Test-Call": "true",
}
BASIC_PAYLOAD = {"id_usuario": 0, "id_topico": 0, "text": "Olá!"}


def _make_mock_graph(exc):
    """Cria um mock de graph que levanta a exceção fornecida em ainvoke."""
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(side_effect=exc)
    return mock_graph


def _patch_graph(exc):
    """Patch de build_chat_completion_graph para levantar exc em ainvoke."""
    mock_graph = _make_mock_graph(exc)
    return patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    )


# ---------------------------------------------------------------------------
# 1. Timeout de leitura HTTP → 408
# ---------------------------------------------------------------------------


def test_read_timeout_retorna_408(client):
    """httpx.ReadTimeout durante execução do grafo deve retornar 408."""
    with _patch_graph(httpx.ReadTimeout("timeout")):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 408


def test_openai_api_timeout_retorna_408(client):
    """openai.APITimeoutError deve retornar 408."""
    mock_request = MagicMock(spec=httpx.Request)
    exc = openai.APITimeoutError(request=mock_request)

    with _patch_graph(exc):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 408


# ---------------------------------------------------------------------------
# 2. BadRequestError genérico (sem content_filter) → 413
# ---------------------------------------------------------------------------


def test_bad_request_error_sem_content_filter_retorna_413(client):
    """
    openai.BadRequestError sem code content_filter deve retornar 413.
    O router interpreta como contexto excedido.
    """
    mock_http_response = httpx.Response(
        400,
        json={"error": {"code": "context_length_exceeded"}},
        request=httpx.Request("POST", "https://mock.openai.azure.com/"),
    )
    exc = openai.BadRequestError(
        "context exceeded", response=mock_http_response, body={"error": {}}
    )

    with _patch_graph(exc):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 413


def test_bad_request_error_sem_response_retorna_413(client):
    """
    openai.BadRequestError com response.json() levantando exceção deve cair
    no caminho padrão → 413.
    """
    mock_http_response = MagicMock()
    mock_http_response.json.side_effect = ValueError("invalid json")
    exc = MagicMock(spec=openai.BadRequestError)
    exc.__class__ = openai.BadRequestError
    exc.response = mock_http_response

    # Usar um BadRequestError real com response inválido
    real_http_response = httpx.Response(
        400,
        content=b"not json",
        request=httpx.Request("POST", "https://mock.openai.azure.com/"),
    )
    real_exc = openai.BadRequestError(
        "bad request", response=real_http_response, body=None
    )

    with _patch_graph(real_exc):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 413


# ---------------------------------------------------------------------------
# 3. BadRequestError com content_filter → 403
# ---------------------------------------------------------------------------


def test_bad_request_error_content_filter_retorna_403(client):
    """
    openai.BadRequestError com code=content_filter e
    innererror.code=ResponsibleAIPolicyViolation deve retornar 403.
    """
    error_body = {
        "error": {
            "code": "content_filter",
            "innererror": {"code": "ResponsibleAIPolicyViolation"},
        }
    }
    mock_http_response = httpx.Response(
        400,
        json=error_body,
        request=httpx.Request("POST", "https://mock.openai.azure.com/"),
    )
    exc = openai.BadRequestError(
        "content filter violation", response=mock_http_response, body=error_body
    )

    with _patch_graph(exc):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 403
    body = response.json()
    assert "message" in body
    assert "bloqueado" in body["message"].lower() or "política" in body["message"]


# ---------------------------------------------------------------------------
# 4. RateLimitError → 429
# ---------------------------------------------------------------------------


def test_rate_limit_error_retorna_429(client):
    """openai.RateLimitError deve retornar 429."""
    mock_http_response = httpx.Response(
        429,
        json={"error": {"code": "rate_limit_exceeded"}},
        request=httpx.Request("POST", "https://mock.openai.azure.com/"),
    )
    exc = openai.RateLimitError(
        "rate limit exceeded", response=mock_http_response, body={"error": {}}
    )

    with _patch_graph(exc):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 429


# ---------------------------------------------------------------------------
# 5. InternalServerError → 502
# ---------------------------------------------------------------------------


def test_internal_server_error_retorna_502(client):
    """openai.InternalServerError deve retornar 502 (erro no servidor LLM)."""
    mock_http_response = httpx.Response(
        500,
        json={"error": {"code": "internal_server_error"}},
        request=httpx.Request("POST", "https://mock.openai.azure.com/"),
    )
    exc = openai.InternalServerError(
        "internal server error", response=mock_http_response, body={"error": {}}
    )

    with _patch_graph(exc):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 502
    body = response.json()
    assert "message" in body


# ---------------------------------------------------------------------------
# 6. APIConnectionError → 503
# ---------------------------------------------------------------------------


def test_api_connection_error_retorna_503(client):
    """openai.APIConnectionError deve retornar 503 (LLM indisponível)."""
    mock_request = MagicMock(spec=httpx.Request)
    exc = openai.APIConnectionError(request=mock_request)

    with _patch_graph(exc):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 503
    body = response.json()
    assert "message" in body


# ---------------------------------------------------------------------------
# 7. Exception genérica → 500
# ---------------------------------------------------------------------------


def test_exception_generica_retorna_500(client):
    """Exception não mapeada deve ser capturada pelo handler genérico → 500."""
    with _patch_graph(RuntimeError("erro interno inesperado")):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 500


def test_value_error_retorna_500(client):
    """ValueError também deve cair no handler genérico → 500."""
    with _patch_graph(ValueError("valor inválido")):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 500


# ---------------------------------------------------------------------------
# 8. HTTPExceptions customizadas: re-lançadas com o status correto
# ---------------------------------------------------------------------------


def test_http_exception_404_reraise(client):
    """HTTPException404 levantada no grafo deve ser re-lançada e resultar em 404."""
    from sei_ia.services.exceptions.http_exceptions import HTTPException404

    with _patch_graph(HTTPException404()):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 404


def test_http_exception_204_reraise(client):
    """HTTPException204 levantada no grafo deve ser re-lançada e resultar em 204."""
    from sei_ia.services.exceptions.http_exceptions import HTTPException204

    with _patch_graph(HTTPException204()):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 204


def test_http_exception_413_reraise(client):
    """HTTPException413 levantada no grafo deve ser re-lançada e resultar em 413."""
    from sei_ia.services.exceptions.http_exceptions import HTTPException413

    with _patch_graph(HTTPException413()):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 413


def test_http_exception_429_reraise(client):
    """HTTPException429 levantada no grafo deve ser re-lançada e resultar em 429."""
    from sei_ia.services.exceptions.http_exceptions import HTTPException429

    with _patch_graph(HTTPException429()):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 429


def test_http_exception_412_reraise(client):
    """HTTPException412SeiApiTimeout levantada no grafo deve ser re-lançada → 412."""
    from sei_ia.services.exceptions.http_exceptions import HTTPException412SeiApiTimeout

    with _patch_graph(HTTPException412SeiApiTimeout(document_id="0000001")):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 412


def test_http_exception_406_reraise(client):
    """HTTPException406 levantada no grafo deve ser re-lançada e resultar em 406."""
    from sei_ia.services.exceptions.http_exceptions import HTTPException406

    with _patch_graph(HTTPException406()):
        response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=BASIC_PAYLOAD)

    assert response.status_code == 406
