"""Testes unitários para sei_ia/routers/chat/stream_error_handler.py."""

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import openai
from fastapi import HTTPException


def _with_loop(fn, *args):
    async def _inner():
        return fn(*args)

    return asyncio.run(_inner())


class TestHandleHttpException:
    def test_retorna_type_error(self):
        from sei_ia.routers.chat.stream_error_handler import handle_http_exception

        exc = HTTPException(status_code=404, detail="não encontrado")
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_http_exception, exc, span)

        assert result["type"] == "error"

    def test_retorna_status_code_correto(self):
        from sei_ia.routers.chat.stream_error_handler import handle_http_exception

        exc = HTTPException(status_code=422, detail="unprocessable")
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_http_exception, exc, span)

        assert result["status_code"] == 422

    def test_retorna_detail_correto(self):
        from sei_ia.routers.chat.stream_error_handler import handle_http_exception

        exc = HTTPException(status_code=403, detail="proibido")
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_http_exception, exc, span)

        assert result["detail"] == "proibido"


class TestHandleOpenAIInternalServerError:
    def test_retorna_status_502(self):
        from sei_ia.routers.chat.stream_error_handler import (
            handle_openai_internal_server_error,
        )

        exc = MagicMock(spec=openai.InternalServerError)
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_openai_internal_server_error, exc, span)

        assert result["status_code"] == 502
        assert result["type"] == "error"


class TestHandleRateLimit:
    def test_retorna_status_429(self):
        from sei_ia.routers.chat.stream_error_handler import handle_rate_limit

        exc = MagicMock(spec=openai.RateLimitError)
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_rate_limit, exc, span)

        assert result["status_code"] == 429
        assert result["type"] == "error"


class TestHandleConnectionError:
    def test_retorna_status_503(self):
        from sei_ia.routers.chat.stream_error_handler import handle_connection_error

        exc = MagicMock(spec=openai.APIConnectionError)
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_connection_error, exc, span)

        assert result["status_code"] == 503
        assert result["type"] == "error"


class TestHandleTimeout:
    def test_retorna_status_408(self):
        from sei_ia.routers.chat.stream_error_handler import handle_timeout

        exc = MagicMock(spec=openai.APITimeoutError)
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_timeout, exc, span)

        assert result["status_code"] == 408
        assert result["type"] == "error"


class TestHandleProtocolError:
    def test_retorna_status_502(self):
        from sei_ia.routers.chat.stream_error_handler import handle_protocol_error

        exc = MagicMock(spec=httpx.RemoteProtocolError)
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_protocol_error, exc, span)

        assert result["status_code"] == 502
        assert result["type"] == "error"


class TestHandleUnhandledException:
    def test_retorna_status_500_para_excecao_generica(self):
        from sei_ia.routers.chat.stream_error_handler import handle_unhandled_exception

        exc = RuntimeError("erro inesperado")
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_unhandled_exception, exc, span)

        assert result["status_code"] == 500
        assert result["type"] == "error"

    def test_usa_status_code_da_excecao_se_disponivel(self):
        from sei_ia.routers.chat.stream_error_handler import handle_unhandled_exception

        exc = HTTPException(status_code=413, detail="payload grande")
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_unhandled_exception, exc, span)

        assert result["status_code"] == 413

    def test_detail_da_excecao_generica_contem_mensagem(self):
        from sei_ia.routers.chat.stream_error_handler import handle_unhandled_exception

        exc = ValueError("valor inválido")
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_unhandled_exception, exc, span)

        assert "valor inválido" in result["detail"]


class TestHandleChatError:
    def test_status_500_mapeado_para_502(self):
        from sei_ia.routers.chat.stream_error_handler import handle_chat_error
        from sei_ia.services.llm_models.chat_workflow import ChatError

        exc = MagicMock(spec=ChatError)
        exc.status_code = 500
        exc.detail = "erro interno do chat"
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_chat_error, exc, span)

        assert result["status_code"] == 502

    def test_status_400_mantido(self):
        from sei_ia.routers.chat.stream_error_handler import handle_chat_error
        from sei_ia.services.llm_models.chat_workflow import ChatError

        exc = MagicMock(spec=ChatError)
        exc.status_code = 400
        exc.detail = "requisição inválida"
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_chat_error, exc, span)

        assert result["status_code"] == 400


class TestHandleOpenAIBadRequest:
    def test_sem_content_filter_retorna_413(self):
        from sei_ia.routers.chat.stream_error_handler import handle_openai_bad_request

        exc = MagicMock(spec=openai.BadRequestError)
        exc.response = MagicMock()
        exc.response.json.return_value = {"error": {"code": "other_error"}}
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_openai_bad_request, exc, span)

        assert result["status_code"] == 413

    def test_com_content_filter_retorna_403(self):
        from sei_ia.routers.chat.stream_error_handler import handle_openai_bad_request

        exc = MagicMock(spec=openai.BadRequestError)
        exc.response = MagicMock()
        exc.response.json.return_value = {
            "error": {
                "code": "content_filter",
                "innererror": {"code": "ResponsibleAIPolicyViolation"},
            }
        }
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_openai_bad_request, exc, span)

        assert result["status_code"] == 403

    def test_sem_response_retorna_413(self):
        from sei_ia.routers.chat.stream_error_handler import handle_openai_bad_request

        exc = MagicMock(spec=openai.BadRequestError)
        del exc.response
        span = MagicMock()

        with patch("sei_ia.routers.chat.stream_error_handler._update_langfuse_trace"):
            result = _with_loop(handle_openai_bad_request, exc, span)

        assert result["status_code"] == 413
