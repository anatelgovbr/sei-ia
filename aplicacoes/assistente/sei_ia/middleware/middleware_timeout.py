"""Middleware para timeout de requisicao."""

import logging
import time
from collections.abc import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings

setup_logging()

logger = logging.getLogger(__name__)


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Middleware para tiemout de requisicoes."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Faz o timeout."""
        timeout = settings.TIMEOUT_API
        start_time = time.time()
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            if process_time > timeout:
                logging.error(f"Request timeout: {process_time} seconds.")
                return JSONResponse(
                    status_code=408, content={"detail": "Request timeout"}
                )
            response.headers["X-Process-Time"] = str(process_time)
        except Exception as exc:
            process_time = time.time() - start_time
            if process_time > timeout:
                logging.exception(f"Request timeout: {process_time} seconds.")
                return JSONResponse(
                    status_code=408, content={"detail": "Request timeout"}
                )
            msg = f"Error on request: {exc}"
            logging.exception(f"Error on request: {msg}")
            return JSONResponse(
                status_code=500, content={"detail": "Internal server error"}
            )
        else:
            return response
