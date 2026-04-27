"""Handlers de erro para o endpoint de streaming SSE.

Cada função recebe a exceção e o span do Langfuse, registra o erro,
atualiza o trace e retorna o dict pronto para ser serializado como evento SSE.
O yield e o return continuam sendo responsabilidade do generator.
"""

import asyncio
import logging
from typing import Any

import httpx
import openai
from fastapi import HTTPException

from sei_ia.routers.chat import _update_langfuse_trace
from sei_ia.services.llm_models.chat_workflow import ChatError

logger = logging.getLogger(__name__)


def _make_error_data(status_code: int, detail: str) -> dict:
    return {
        "type": "error",
        "status_code": status_code,
        "detail": detail,
        "timestamp": asyncio.get_running_loop().time(),
    }


def handle_http_exception(exc: HTTPException, span: Any) -> dict:
    """Cobre qualquer HTTPException (400, 401, 403, 404, 408, 409, 411, 412,
    413, 415, 422, 429, 500, 501, 504, etc.)."""
    logger.error(f"HTTPException {exc.status_code} no streaming: {exc.detail}")
    _update_langfuse_trace(
        span,
        output={
            "error": exc.detail,
            "status_code": exc.status_code,
            "status_message": f"HTTP {exc.status_code}: {exc.detail}",
            "level": "ERROR",
        },
        tags=[f"error:{exc.status_code}", "http_error"],
    )
    return _make_error_data(exc.status_code, exc.detail)


def handle_openai_bad_request(exc: openai.BadRequestError, span: Any) -> dict:
    logger.error(f"openai.BadRequestError no streaming: {exc}")

    # Verifica se é bloqueio por content_filter (mesma lógica do não-streaming)
    error_json = None
    if hasattr(exc, "response") and hasattr(exc.response, "json"):
        try:
            error_json = exc.response.json()
        except (ValueError, TypeError, AttributeError):
            error_json = None

    if error_json:
        error_code = error_json.get("error", {}).get("code")
        inner_code = error_json.get("error", {}).get("innererror", {}).get("code")
        if (
            error_code == "content_filter"
            and inner_code == "ResponsibleAIPolicyViolation"
        ):
            msg = (
                "Seu prompt foi bloqueado pela política de uso da OpenAI/Azure. "
                "Por favor, revise o conteúdo e tente novamente."
            )
            _update_langfuse_trace(
                span,
                output={
                    "error": str(exc),
                    "status_code": 403,
                    "status_message": "Content filter: ResponsibleAIPolicyViolation",
                    "level": "ERROR",
                },
                tags=["error:403", "content_filter"],
            )
            return _make_error_data(403, msg)

    _update_langfuse_trace(
        span,
        output={
            "error": str(exc),
            "status_code": 413,
            "status_message": f"Context size exceeded: {exc}",
            "level": "ERROR",
        },
        tags=["error:413", "context_exceeded"],
    )
    return _make_error_data(413, "Tamanho do contexto excedido.")


def handle_openai_internal_server_error(
    exc: openai.InternalServerError, span: Any
) -> dict:
    logger.exception(f"openai.InternalServerError no streaming: {exc}")
    _update_langfuse_trace(
        span,
        output={
            "error": str(exc),
            "status_code": 502,
            "status_message": f"LLM proxy internal error: {exc}",
            "level": "ERROR",
        },
        tags=["error:502", "litellm_proxy_error"],
    )
    return _make_error_data(
        502,
        "Erro no serviço de LLM. O servidor de modelos retornou um erro interno. Tente novamente.",
    )


def handle_rate_limit(exc: openai.RateLimitError, span: Any) -> dict:
    logger.error(f"openai.RateLimitError no streaming: {exc}")
    _update_langfuse_trace(
        span,
        output={
            "error": str(exc),
            "status_code": 429,
            "status_message": f"Rate limit: {exc}",
            "level": "ERROR",
        },
        tags=["error:429", "rate_limit"],
    )
    return _make_error_data(
        429, "Erro de rate limit. Tente novamente em alguns instantes."
    )


def handle_connection_error(
    exc: openai.APIConnectionError | httpx.ConnectError, span: Any
) -> dict:
    logger.error(
        f"Erro de conexão com LLM proxy no streaming: {type(exc).__name__}: {exc}"
    )
    _update_langfuse_trace(
        span,
        output={
            "error": str(exc),
            "status_code": 503,
            "status_message": f"LLM proxy connection error: {exc}",
            "level": "ERROR",
        },
        tags=["error:503", "connection_error"],
    )
    return _make_error_data(
        503,
        "Serviço de LLM indisponível. Não foi possível conectar ao servidor de modelos.",
    )


def handle_timeout(
    exc: openai.APITimeoutError | httpx.TimeoutException, span: Any
) -> dict:
    logger.error(f"Timeout com LLM proxy no streaming: {type(exc).__name__}: {exc}")
    _update_langfuse_trace(
        span,
        output={
            "error": str(exc),
            "status_code": 408,
            "status_message": f"LLM proxy timeout: {exc}",
            "level": "ERROR",
        },
        tags=["error:408", "timeout"],
    )
    return _make_error_data(408, "Timeout na comunicação com o serviço de LLM.")


def handle_chat_error(exc: ChatError, span: Any) -> dict:
    status = 502 if exc.status_code >= 500 else exc.status_code
    logger.error(f"ChatError no streaming: [{exc.status_code}] {exc.detail}")
    _update_langfuse_trace(
        span,
        output={
            "error": exc.detail,
            "status_code": status,
            "status_message": f"Chat error: {exc.detail}",
            "level": "ERROR",
        },
        tags=[f"error:{status}", "chat_error"],
    )
    return _make_error_data(
        status, f"Erro na comunicação com o serviço de LLM: {exc.detail}"
    )


def handle_protocol_error(
    exc: httpx.ReadError | httpx.RemoteProtocolError, span: Any
) -> dict:
    logger.error(
        f"Erro de protocolo/leitura com LLM proxy no streaming: {type(exc).__name__}: {exc}"
    )
    _update_langfuse_trace(
        span,
        output={
            "error": str(exc),
            "status_code": 502,
            "status_message": f"LLM proxy connection interrupted: {exc}",
            "level": "ERROR",
        },
        tags=["error:502", "connection_interrupted"],
    )
    return _make_error_data(
        502, "Conexão com o serviço de LLM foi interrompida. Tente novamente."
    )


def handle_unhandled_exception(exc: Exception, span: Any) -> dict:
    """Fallback para qualquer exceção não mapeada. Preserva status_code e
    detail se a exceção for uma HTTPException."""
    logger.exception(f"Exceção não tratada no streaming: {type(exc).__name__}")
    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", None) or f"Erro interno: {str(exc)}"
    _update_langfuse_trace(
        span,
        output={
            "error": str(exc),
            "status_code": status_code,
            "exception_type": type(exc).__name__,
            "status_message": f"Unexpected error: {type(exc).__name__}",
            "level": "ERROR",
        },
        tags=[f"error:{status_code}", "unhandled_exception"],
    )
    return _make_error_data(status_code, detail)
