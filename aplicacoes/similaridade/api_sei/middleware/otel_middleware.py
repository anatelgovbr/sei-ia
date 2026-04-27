"""Middleware para registrar os logs de recomendação."""

import logging

from fastapi import FastAPI
from opentelemetry.metrics import get_meter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.routing import Match

logger = logging.getLogger(__name__)

meter = get_meter("api_sei.meter")

req_count = meter.create_counter(
    name="request_counter",
    description="Quantidade total de requests",
)

err_count = meter.create_counter(
    name="error_counter",
    description="Quantidade total de erros",
)


class MetricsMeddleware(BaseHTTPMiddleware):
    """Middleware para registrar os logs de recomendação."""

    def __init__(self, app: FastAPI) -> None:
        """Inicializa o middleware de logs.

        Args:
            app: Inst ncia da aplica o FastAPI.
        """
        super().__init__(app=app)
        self.app_name = "api_sei"

    def get_path(self, request: Request) -> str:
        """Retorna o caminho da rota correspondente para a solicitação fornecida.

        Itera sobre todas as rotas no aplicativo da solicitação para encontrar uma correspondência completa
        com o escopo da solicitação. Se uma correspondência for encontrada, retorna o caminho da rota.
        Se nenhuma correspondência for encontrada, retorna o caminho da URL da solicitação.

        Args:
            request: O objeto de solicitação FastAPI.

        Returns:
            O caminho da rota correspondente como uma string ou o caminho da URL da solicitação se nenhuma
            correspondência for encontrada.
        """
        for route in request.app.routes:
            match_, _ = route.matches(request.scope)
            if match_ == Match.FULL:
                return route.path

        return request.url.path

    async def dispatch(self, request: Request, call_next) -> Request:  # noqa: ANN001
        """Intercepta a solicitação e a resposta para registrar métricas.

        Este método é chamado para cada solicitação recebida pela aplicação. Ele registra
        métricas relacionadas ao número de solicitações e erros, bem como aos atributos
        da solicitação e da resposta. Se uma exceção ocorrer ao processar a solicitação,
        a exceção é registrada e a contagem de erros é incrementada.

        Args:
            request: O objeto de solicitação FastAPI que contém os detalhes da solicitação.
            call_next: Uma função assíncrona que representa o próximo middleware ou rota
                na cadeia que processará a solicitação.

        Returns:
            A resposta HTTP gerada após o processamento da solicitação.
        """
        method = request.method
        base_attributes = {"method": method, "path": self.get_path(request)}

        try:
            response = await call_next(request)
            attributes = base_attributes | {
                "status_code": response.status_code,
            }
            req_count.add(1, attributes=attributes)
        except Exception as e:
            attributes = base_attributes | {
                "exception_type": type(e).__name__,
                "status_code": 500,
            }
            req_count.add(1, attributes=attributes)
            err_count.add(1)
            logger.exception(msg=str(e))
            raise e from None

        return response
