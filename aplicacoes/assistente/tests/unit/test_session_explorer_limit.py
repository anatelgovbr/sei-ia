"""Testes do teto de exploradores paralelos (`ExplorerConcurrencyMiddleware`).

Garante que o semáforo capa de fato as tool calls `task` concorrentes e que
outras tools passam sem limite. Um bump do deepagents/langchain que renomeie a
tool ou mude a assinatura de `awrap_tool_call` quebra estes testes.
"""

import asyncio
from types import SimpleNamespace

import pytest

from sei_ia.agents.session_agent.explorer_limit import ExplorerConcurrencyMiddleware


def _request(tool_name: str) -> SimpleNamespace:
    # Só `tool_call["name"]` importa para o middleware.
    return SimpleNamespace(tool_call={"name": tool_name, "id": "x", "args": {}})


class _ConcurrencyProbe:
    """Handler que registra o pico de execuções simultâneas."""

    def __init__(self) -> None:
        self.active = 0
        self.peak = 0

    async def __call__(self, request):
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.02)  # segura a vaga para forçar sobreposição
            return f"done:{request.tool_call['name']}"
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_task_paralelo_respeita_o_teto():
    mw = ExplorerConcurrencyMiddleware(2)
    probe = _ConcurrencyProbe()

    results = await asyncio.gather(
        *(mw.awrap_tool_call(_request("task"), probe) for _ in range(6))
    )

    assert results == ["done:task"] * 6
    assert probe.peak <= 2  # nunca mais que o teto simultâneos


@pytest.mark.asyncio
async def test_outras_tools_nao_sao_capadas():
    mw = ExplorerConcurrencyMiddleware(1)
    probe = _ConcurrencyProbe()

    await asyncio.gather(*(mw.awrap_tool_call(_request("ls"), probe) for _ in range(4)))

    # Sem semáforo para tools que não são `task`: as 4 correm juntas.
    assert probe.peak == 4


@pytest.mark.asyncio
async def test_teto_minimo_de_um():
    # max<1 é saneado para 1 (semáforo válido), nunca 0 (que travaria tudo).
    mw = ExplorerConcurrencyMiddleware(0)
    probe = _ConcurrencyProbe()

    await asyncio.gather(
        *(mw.awrap_tool_call(_request("task"), probe) for _ in range(3))
    )

    assert probe.peak == 1
