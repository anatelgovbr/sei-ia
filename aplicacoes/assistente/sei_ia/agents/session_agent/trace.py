"""Trace de debug: loga cada tool call (quem chamou, nome, args, duração).

Callback LangChain ligável por request (``trace=true``) ou ``settings.SESSION_TRACE``.
Propaga para subagentes, então mostra a cronologia completa e distingue o agente
principal dos exploradores pelo namespace de checkpoint do LangGraph. Formato
alinhado e colorido para leitura no terminal (o runner de teste tailha o arquivo).
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

# Caminho fixo do log de trace (lido ao vivo pelo runner de teste).
TRACE_LOG = Path(__file__).resolve().parents[3] / "logs" / "session_trace.log"

# Logger próprio: stderr (terminal da app) + arquivo fixo (o runner tailha). Nível
# INFO para aparecer mesmo com LOG_LEVEL global em WARNING.
logger = logging.getLogger("session.trace")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    _fmt = logging.Formatter("%(message)s")
    _stream = logging.StreamHandler()
    _stream.setFormatter(_fmt)
    logger.addHandler(_stream)
    try:
        TRACE_LOG.parent.mkdir(exist_ok=True)
        _file = logging.FileHandler(TRACE_LOG, encoding="utf-8")
        _file.setFormatter(_fmt)
        logger.addHandler(_file)
    except OSError:
        pass

# Cores ANSI (renderizam no terminal; o runner imprime o que o tail lê).
_RESET, _DIM, _BOLD = "\033[0m", "\033[2m", "\033[1m"
_CYAN, _GREEN, _GREY, _YEL = "\033[36m", "\033[32m", "\033[90m", "\033[33m"
_TODO_SYM = {"completed": "☑", "in_progress": "▣", "pending": "☐"}
_TODO_COLOR = {"completed": _GREEN, "in_progress": _YEL, "pending": _GREY}
_TODO_PAD = " " * 38  # alinha cada item sob o 'tail' das linhas normais do trace
_FILE_RE = re.compile(r"/?proc_\S+?\.txt")
_CONTENT_RE = re.compile(r"content=['\"](.*?)['\"]", re.DOTALL)


def _short(value: Any, limit: int = 90) -> str:
    text = value if isinstance(value, str) else str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def _checkpoint_segments(metadata: dict[str, Any] | None) -> list[str]:
    """Segmentos do `checkpoint_ns` do LangGraph, que aninha por nível.

    Tool/chunk do agente principal tem 1 segmento (``tools:<uuid>``); de um
    explorador tem 2+ (``tools:<task>|tools:<uuid>``).
    """
    md = metadata or {}
    ns = md.get("langgraph_checkpoint_ns") or md.get("checkpoint_ns") or ""
    return [s for s in ns.split("|") if s]


def is_principal(metadata: dict[str, Any] | None) -> bool:
    """True quando o chunk/tool vem do agente principal (≤1 segmento no ns).

    Regra única compartilhada com `routers/session/stream.py` (gate de reasoning).
    """
    return len(_checkpoint_segments(metadata)) <= 1


def _caller(metadata: dict[str, Any] | None) -> str:
    """Quem chamou a tool: 'principal' ou 'sub:<id>' (explorador).

    O rótulo do explorador usa o uuid do `task` que o lançou (1º segmento),
    agrupando todas as suas tools.
    """
    segs = _checkpoint_segments(metadata)
    if len(segs) <= 1:
        return "principal"
    return f"sub:{segs[0].split(':')[-1][:6]}"


def _todo_lines(inputs: dict[str, Any] | None) -> list[str]:
    """Uma linha por todo, com o quadradinho de status colorido (☑/▣/☐)."""
    todos = (inputs or {}).get("todos") or []
    lines: list[str] = []
    for t in todos:
        if not isinstance(t, dict):
            continue
        status = t.get("status", "pending")
        sym = _TODO_SYM.get(status, "·")
        col = _TODO_COLOR.get(status, _GREY)
        lines.append(
            f"{_TODO_PAD}{col}{sym}{_RESET} {_short(t.get('content', ''), 80)}"
        )
    return lines


def _arg_summary(name: str, inputs: dict[str, Any] | None, input_str: str) -> str:
    inp = inputs or {}
    if name == "read_file":
        path = str(inp.get("file_path", "?")).lstrip("/")
        rng = f" [{inp.get('offset', 0)}:+{inp['limit']}]" if inp.get("limit") else ""
        return f"{path}{rng}"
    if name == "task":
        sub = inp.get("subagent_type", "?")
        hit = _FILE_RE.search(inp.get("description", ""))
        alvo = hit.group(0).lstrip("/") if hit else _short(inp.get("description"), 70)
        return f"{sub} → {alvo}"
    if name == "grep":
        pat = inp.get("pattern", "")
        path = str(inp.get("path", "")).lstrip("/")
        return f"'{pat}'" + (f" @ {path}" if path else "")
    simples = inp.get("path") or inp.get("pattern")  # ls / glob
    return str(simples).lstrip("/") or "/" if simples else _short(inp or input_str, 90)


def _out_summary(name: str, output: Any) -> str:
    text = str(output)
    if name == "read_file":
        hit = _CONTENT_RE.search(text)
        return f"{len(hit.group(1))} chars" if hit else f"{len(text)} chars"
    if name == "task":
        hit = _CONTENT_RE.search(text)
        return f'"{_short(hit.group(1), 70)}"' if hit else _short(text, 50)
    if name == "write_todos":
        return ""
    return _short(text, 60)


class SessionTraceHandler(BaseCallbackHandler):
    """Loga início/fim de cada tool com o autor, argumentos e duração."""

    def __init__(self) -> None:
        # run_id -> (t_inicio, caller, nome)
        self._runs: dict[str, tuple[float, str, str]] = {}
        self._t0 = time.perf_counter()

    def _line(self, caller: str, arrow: str, name: str, tail: str) -> str:
        cor = _CYAN if caller == "principal" else _GREY
        seta = _GREEN if arrow == "→" else _GREY
        ts = f"+{time.perf_counter() - self._t0:6.2f}s"
        return (
            f"{_DIM}{ts}{_RESET}  {cor}{caller:<11}{_RESET}  "
            f"{seta}{arrow}{_RESET} {_BOLD}{name:<12}{_RESET} {tail}"
        )

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        name = (serialized or {}).get("name") or "tool"
        caller = _caller(metadata)
        self._runs[str(run_id)] = (time.perf_counter(), caller, name)
        if name == "write_todos":
            # Plano em várias linhas: cabeçalho + um item por linha com o status.
            todos = (inputs or {}).get("todos") or []
            logger.info(
                self._line(caller, "→", name, f"{_DIM}{len(todos)} itens{_RESET}")
            )
            for line in _todo_lines(inputs):
                logger.info(line)
            return
        logger.info(
            self._line(caller, "→", name, _arg_summary(name, inputs, input_str))
        )

    def on_tool_end(self, output: Any, *, run_id: UUID, **_: Any) -> None:
        started, caller, name = self._runs.pop(str(run_id), (None, "?", "tool"))
        dur = f"{time.perf_counter() - started:5.2f}s" if started else "  ?  "
        out = _out_summary(name, output)
        tail = f"{_YEL}{dur}{_RESET}" + (f" {_DIM}· {out}{_RESET}" if out else "")
        logger.info(self._line(caller, "←", name, tail))

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **_: Any) -> None:
        started, caller, name = self._runs.pop(str(run_id), (None, "?", "tool"))
        dur = f"{time.perf_counter() - started:5.2f}s" if started else "  ?  "
        logger.warning(self._line(caller, "←", name, f"✗ {dur} {_short(error, 120)}"))
