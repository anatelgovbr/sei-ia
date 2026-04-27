"""
Testes E2E para sei_ia/middleware/middleware_timeout.py.

Cobre TimeoutMiddleware:
1. Caminho normal — response retornada com header X-Process-Time
2. Timeout excedido (sem exceção) — retorna 408
3. Exceção + timeout excedido — retorna 408
4. Exceção dentro do timeout — retorna 500
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixture com TimeoutMiddleware habilitado
# ---------------------------------------------------------------------------


@pytest.fixture
def client_timeout():
    """TestClient com enable_timeout_middleware=True."""
    from sei_ia.main import get_app

    app = get_app(enable_timeout_middleware=True, enable_request_middleware=False)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Caminho normal — X-Process-Time presente na resposta
# ---------------------------------------------------------------------------


def test_timeout_middleware_health_retorna_x_process_time(client_timeout):
    """
    Requisição normal deve retornar o header X-Process-Time e status 200.
    """
    response = client_timeout.get("/health")

    assert response.status_code == 200
    assert "x-process-time" in response.headers


def test_timeout_middleware_header_x_process_time_e_numero(client_timeout):
    """X-Process-Time deve ser conversível para float."""
    response = client_timeout.get("/health")

    assert response.status_code == 200
    process_time = float(response.headers["x-process-time"])
    assert process_time >= 0


# ---------------------------------------------------------------------------
# 2. Timeout excedido (sem exceção) — retorna 408
# ---------------------------------------------------------------------------


def test_timeout_middleware_timeout_excedido_retorna_408(client_timeout):
    """
    Quando process_time > TIMEOUT_API, deve retornar 408 com detail 'Request timeout'.
    Simula timeout configurando TIMEOUT_API=-1 (qualquer process_time > -1 é verdadeiro).
    """
    from sei_ia.configs import settings_config

    with patch.object(settings_config.settings, "TIMEOUT_API", -1):
        response = client_timeout.get("/health")

    assert response.status_code == 408
    assert response.json() == {"detail": "Request timeout"}


# ---------------------------------------------------------------------------
# 3. Exceção + timeout excedido — retorna 408
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_middleware_excecao_com_timeout_retorna_408():
    """
    Quando call_next lança exceção E process_time > timeout, deve retornar 408.
    Testado diretamente no dispatch para controlar o tempo de processamento.
    """
    from sei_ia.middleware.middleware_timeout import TimeoutMiddleware

    middleware = TimeoutMiddleware(app=AsyncMock())

    mock_request = AsyncMock()

    async def slow_call_next(req):
        raise RuntimeError("Conexão encerrada")

    # TIMEOUT_API = -1 garante que qualquer process_time > timeout seja verdadeiro
    from sei_ia.configs import settings_config

    with patch.object(settings_config.settings, "TIMEOUT_API", -1):
        response = await middleware.dispatch(mock_request, slow_call_next)

    assert response.status_code == 408
    import json

    body = json.loads(response.body)
    assert body == {"detail": "Request timeout"}


# ---------------------------------------------------------------------------
# 4. Exceção dentro do timeout — retorna 500
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_middleware_excecao_sem_timeout_retorna_500():
    """
    Quando call_next lança exceção mas process_time <= timeout, deve retornar 500.
    """
    from sei_ia.middleware.middleware_timeout import TimeoutMiddleware

    middleware = TimeoutMiddleware(app=AsyncMock())

    mock_request = AsyncMock()

    async def failing_call_next(req):
        raise RuntimeError("Erro interno inesperado")

    # TIMEOUT_API alto para garantir que não entre no branch de timeout
    from sei_ia.configs import settings_config

    with patch.object(settings_config.settings, "TIMEOUT_API", 9999):
        response = await middleware.dispatch(mock_request, failing_call_next)

    assert response.status_code == 500
    import json

    body = json.loads(response.body)
    assert body == {"detail": "Internal server error"}
