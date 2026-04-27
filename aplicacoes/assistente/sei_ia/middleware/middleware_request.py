"""Modulo para capturar o corpo da requisição."""

import logging
from collections.abc import Callable
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


class RequestMiddleware(BaseHTTPMiddleware):
    """Middleware para capturar o corpo da requisição e armazenar na variável state do request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Request:
        """Captura o corpo da requisição e armazena na variável state do request."""
        body = await request.body()
        request.state.body = body

        # Geração de id_request mantida para compatibilidade
        if not hasattr(request.state, "id_request"):
            id_request = int(datetime.now().timestamp())  # noqa: DTZ005
            request.state.id_request = id_request
        if request.client:
            request.state.ip = request.client.host

        return await call_next(request)
