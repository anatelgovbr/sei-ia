"""Middleware de janela deslizante para o agente de sessão.

Apara os turnos antigos no checkpointer a cada turno novo, mantendo só os
últimos N pares pergunta/resposta. O corte é feito na fronteira de
HumanMessage para preservar integridade de sequências tool-call (uma sequência
de tool vive entre dois HumanMessages consecutivos).
"""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)


class ConversationWindowMiddleware(AgentMiddleware):
    """Mantém só os últimos N turnos no checkpointer, aparando os antigos a cada turno."""

    def __init__(self, max_turns: int) -> None:
        super().__init__()
        self.max_turns = max_turns

    def _removidos(self, messages: list[BaseMessage]) -> list[RemoveMessage]:
        humanos = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
        if len(humanos) <= self.max_turns:
            return []
        cutoff = humanos[-self.max_turns]
        return [
            RemoveMessage(id=m.id)
            for m in messages[:cutoff]
            if m.id and not isinstance(m, SystemMessage)
        ]

    def before_model(self, state, runtime):  # noqa: ARG002
        rem = self._removidos(state["messages"])
        return {"messages": rem} if rem else None

    async def abefore_model(self, state, runtime):  # noqa: ARG002
        return self.before_model(state, runtime)
