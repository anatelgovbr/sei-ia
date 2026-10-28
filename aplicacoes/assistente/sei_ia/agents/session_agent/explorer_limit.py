"""Teto de exploradores paralelos para o agente de sessão.

O system prompt pede "no máximo N exploradores em paralelo", mas era só prosa:
nada impedia o modelo de emitir 20 `task` num único turno. O langchain executa
as tool calls de um turno concorrentemente, então um semáforo em torno da tool
`task` transforma a diretiva em teto real — as chamadas excedentes esperam por uma
vaga em vez de estourar custo e latência. Espelha o padrão de semáforo já usado no
fetch concorrente de documentos (`services/session_fs/manager.py`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

# Nome da tool que dispara um subagente explorador (deepagents `SubAgentMiddleware`).
_TASK_TOOL = "task"


class ExplorerConcurrencyMiddleware(AgentMiddleware):
    """Limita exploradores (`task`) concorrentes a `max_explorers` por invocação.

    Uma instância por agente (o agente é remontado a cada request em
    `build_session_agent`), então o semáforo tem o escopo de uma conversa/turno.
    Só a tool `task` é capada; as demais passam direto.
    """

    def __init__(self, max_explorers: int) -> None:
        super().__init__()
        self._max = max(1, max_explorers)
        # Criado sob demanda para ligar no event loop da invocação.
        self._semaphore: asyncio.Semaphore | None = None

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max)
        return self._semaphore

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        if request.tool_call.get("name") != _TASK_TOOL:
            return await handler(request)
        async with self._get_semaphore():
            return await handler(request)
