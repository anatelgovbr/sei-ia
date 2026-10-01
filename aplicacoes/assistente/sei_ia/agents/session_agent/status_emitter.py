"""Callback de status do agente de sessão: tool call → frame SSE `status`.

Sempre-ligado (não depende de `trace=true`). Em cada `on_tool_start`, escreve
``{"_status": <mensagem>}`` no stream writer do LangGraph; o loop do
`session_stream` lê isso no modo `custom` e emite o frame `status` para o
frontend. Mesmo canal `_status` do endpoint clássico (`chat_completion_graph`).

Dedup é responsabilidade do loop (não floodar quando N exploradores disparam em
paralelo): aqui só traduzimos tool → mensagem.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.config import get_stream_writer

# tool → mensagem de status (estilo das mensagens da sessão: espaço inicial).
_STATUS_LENDO_DOCS = " Lendo os documentos"
_TOOL_STATUS = {
    "read_file": _STATUS_LENDO_DOCS,
    "grep": _STATUS_LENDO_DOCS,
    "ls": _STATUS_LENDO_DOCS,
    "glob": _STATUS_LENDO_DOCS,
    "task": " Consultando documentos em paralelo",
    "write_todos": " Planejando a resposta",
    # Tool web real do session é o DeepResearchAgent (name="deep_research_search",
    # deep_research_agent.py). Tools de integrações antigas nunca disparam aqui.
    "deep_research_search": " Pesquisando na Internet",
    "web_research_search": " Pesquisando na Internet",
}


class SessionStatusHandler(BaseCallbackHandler):
    """Emite status por etapa via stream writer a cada início de tool."""

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,  # noqa: ARG002  # NOSONAR
        **_: Any,
    ) -> None:
        name = (serialized or {}).get("name") or ""
        status = _TOOL_STATUS.get(name)
        if not status:
            return
        try:
            writer = get_stream_writer()
        except Exception:  # noqa: BLE001
            return  # fora do contexto do grafo: degrada, nunca derruba o turno
        if writer is not None:
            writer({"_status": status})
