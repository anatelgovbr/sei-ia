"""Telemetria estruturada, opcional e restrita aos benchmarks de endpoints."""

from __future__ import annotations

import ast
import hashlib
import threading
import time
from collections import Counter
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from sei_ia.services.counter import token_counter

ToolCategory = Literal["web", "filesystem", "rag", "subagent", "unclassified"]

_FILESYSTEM_TOOLS = {
    "read_file",
    "ls",
    "grep",
    "glob",
    "write_todos",
    "write_file",
    "edit_file",
}
_WEB_TOOLS = {"deep_research_search", "web_research_search"}
_current_collector: ContextVar[BenchmarkToolHandler | None] = ContextVar(
    "benchmark_tool_collector", default=None
)


def set_current_collector(collector: BenchmarkToolHandler | None) -> Token:
    """Liga o coletor ao contexto do request clássico sem serializá-lo no estado."""
    return _current_collector.set(collector)


def reset_current_collector(token: Token) -> None:
    _current_collector.reset(token)


def current_collector() -> BenchmarkToolHandler | None:
    return _current_collector.get()


def classify_tool(name: str) -> ToolCategory:
    """Classifica nomes de tools sem assumir que nomes desconhecidos são RAG."""
    normalized = (name or "").lower()
    if (
        normalized in _WEB_TOOLS
        or "web_research" in normalized
        or "deep_research" in normalized
    ):
        return "web"
    if normalized in _FILESYSTEM_TOOLS:
        return "filesystem"
    if normalized == "task":
        return "subagent"
    if "rag" in normalized or "retriev" in normalized or "similar" in normalized:
        return "rag"
    return "unclassified"


def _references_from_output(output: Any) -> tuple[int | None, set[str] | None]:
    """Extrai contagens de referências sem tratá-las como páginas no crawler clássico."""
    if not isinstance(output, list):
        return None, None
    urls: set[str] = set()
    references = 0
    for item in output:
        if not isinstance(item, dict):
            continue
        for reference in item.get("references") or []:
            if not isinstance(reference, dict):
                continue
            references += 1
            url = reference.get("url")
            if isinstance(url, str) and url:
                urls.add(url)
    return references, urls


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_virtual_path(path: str) -> str:
    normalized = str(path).replace("\\", "/")
    normalized = PurePosixPath(normalized).as_posix()
    if normalized in {"", ".", "/"}:
        return "/"
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _path_reference(path: str, *, kind: str | None = None) -> dict[str, str]:
    """Representa um caminho sem expor processo, documento ou diretório real."""
    normalized = _normalize_virtual_path(path)
    suffix = PurePosixPath(normalized).suffix.lower()
    return {
        "path_sha256": _sha256(normalized),
        "kind": kind or ("document" if suffix == ".txt" else "path"),
        "suffix": suffix,
    }


def _checkpoint_actor(metadata: dict[str, Any] | None) -> str:
    md = metadata or {}
    namespace = md.get("langgraph_checkpoint_ns") or md.get("checkpoint_ns") or ""
    segments = [segment for segment in str(namespace).split("|") if segment]
    if len(segments) <= 1:
        return "main"
    return f"subagent:{_sha256(segments[0])[:12]}"


def _flatten_output_mapping(value: dict[str, Any], depth: int) -> str | None:
    for key in ("content", "output", "messages", "result"):
        if key in value:
            text = _flatten_output_text(value[key], depth=depth + 1)
            if text is not None:
                return text
    return None


def _flatten_output_text(value: Any, *, depth: int = 0) -> str | None:
    """Obtém texto retornado em memória sem persistir ``repr`` ou campos de entrada."""
    result: str | None = None
    if depth <= 5 and value is not None:
        if isinstance(value, str):
            result = value
        elif isinstance(value, bytes):
            result = value.decode("utf-8", errors="replace")
        elif isinstance(value, (list, tuple)):
            parts = [
                text
                for item in value
                if (text := _flatten_output_text(item, depth=depth + 1)) is not None
            ]
            result = "\n".join(parts) if parts else None
        elif isinstance(value, dict):
            result = _flatten_output_mapping(value, depth)
        elif (content := getattr(value, "content", None)) is not None:
            result = _flatten_output_text(content, depth=depth + 1)
        elif (update := getattr(value, "update", None)) is not None:
            result = _flatten_output_text(update, depth=depth + 1)
    return result


def _output_measurements(text: str | None) -> dict[str, int | str | None]:
    if text is None:
        return {
            "returned_bytes": None,
            "returned_tokens": None,
            "returned_sha256": None,
        }
    return {
        "returned_bytes": len(text.encode("utf-8")),
        "returned_tokens": token_counter(text),
        "returned_sha256": _sha256(text),
    }


def _safe_inputs(inputs: dict[str, Any] | None) -> dict[str, Any]:
    source = inputs or {}
    safe: dict[str, Any] = {}
    for key in ("path", "file_path"):
        value = source.get(key)
        if isinstance(value, str) and value:
            safe[key] = _path_reference(value)
    for key in ("offset", "limit"):
        value = source.get(key)
        if isinstance(value, int):
            safe[key] = value
    for key in ("pattern", "glob"):
        value = source.get(key)
        if isinstance(value, str) and value:
            safe[f"{key}_sha256"] = _sha256(value)
    output_mode = source.get("output_mode")
    if output_mode in {"files_with_matches", "content", "count"}:
        safe["output_mode"] = output_mode
    subagent_type = source.get("subagent_type")
    if isinstance(subagent_type, str) and subagent_type:
        safe["subagent_type_sha256"] = _sha256(subagent_type)
    return safe


@dataclass(frozen=True)
class _StartedCall:
    started: float
    sequence: int
    name: str
    category: ToolCategory
    source: str
    actor: str
    parent_sha256: str | None
    safe_inputs: dict[str, Any]
    files_opened: list[dict[str, str]] | None
    files_scanned: list[dict[str, str]] | None


class BenchmarkToolHandler(BaseCallbackHandler):
    """Coleta ferramentas sem guardar argumentos, conteúdo ou caminhos brutos.

    ``document_paths`` é um inventário virtual já materializado. Ele permite provar
    quais arquivos eram candidatos de ``ls``/``glob``/``grep`` sem reler o corpus.
    Só hashes dos caminhos deixam a instância.
    """

    def __init__(
        self,
        document_paths: list[str] | None = None,
        document_inventory: list[dict[str, Any]] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._started: dict[str, _StartedCall] = {}
        self._calls: list[dict[str, Any]] = []
        self._sequence = 0
        self._t0 = time.perf_counter()
        self._document_paths = tuple(
            _normalize_virtual_path(path) for path in (document_paths or [])
        )
        self._document_inventory = tuple(
            {
                "path_sha256": _sha256(_normalize_virtual_path(str(entry["path"]))),
                "content_sha256": str(entry["content_sha256"]),
                "bytes": int(entry["bytes"]),
                "tokens": int(entry["tokens"]),
            }
            for entry in (document_inventory or [])
        )

    def _inventory_for(
        self, name: str, inputs: dict[str, Any] | None
    ) -> tuple[list[dict[str, str]] | None, list[dict[str, str]] | None]:
        source = inputs or {}
        if name == "read_file":
            path = source.get("file_path")
            opened = [_path_reference(path)] if isinstance(path, str) and path else []
            return opened, None
        if name not in {"ls", "glob", "grep"}:
            return None, None

        raw_scope = source.get("path")
        scope = _normalize_virtual_path(raw_scope) if raw_scope else "/"
        scope_prefix = scope.rstrip("/") + "/"
        candidates = [
            path
            for path in self._document_paths
            if path.startswith(scope_prefix) or (name == "grep" and path == scope)
        ]
        if name == "ls":
            entries: set[str] = set()
            for path in candidates:
                relative = path.removeprefix(scope_prefix)
                first = relative.split("/", 1)[0]
                entries.add(
                    path
                    if "/" not in relative
                    else (
                        f"/{first}" if scope == "/" else f"{scope.rstrip('/')}/{first}"
                    )
                )
            return None, [
                _path_reference(
                    path,
                    kind="directory" if path not in self._document_paths else None,
                )
                for path in sorted(entries)
            ]
        if name == "glob":
            pattern = source.get("pattern")
            if isinstance(pattern, str) and pattern:
                pattern = pattern.lstrip("/")
                candidates = [
                    path
                    for path in candidates
                    if PurePosixPath(path.removeprefix(scope_prefix)).match(pattern)
                ]
        elif name == "grep":
            glob_filter = source.get("glob")
            if isinstance(glob_filter, str) and glob_filter:
                candidates = [
                    path
                    for path in candidates
                    if PurePosixPath(path.removeprefix(scope_prefix)).match(glob_filter)
                ]
        return None, [_path_reference(path) for path in sorted(candidates)]

    def _returned_path_references(
        self, started: _StartedCall, text: str | None
    ) -> list[dict[str, str]]:
        if not text or started.name not in {"ls", "glob", "grep"}:
            return []
        scanned = started.files_scanned or []
        by_hash = {item["path_sha256"]: item for item in scanned}

        if started.name in {"ls", "glob"}:
            try:
                values = ast.literal_eval(text.strip())
            except (SyntaxError, ValueError):
                return []
            if not isinstance(values, list):
                return []
            returned: list[dict[str, str]] = []
            for value in values:
                if not isinstance(value, str):
                    continue
                reference = by_hash.get(_sha256(_normalize_virtual_path(value)))
                if reference is not None and reference not in returned:
                    returned.append(reference)
            return returned

        mode = started.safe_inputs.get("output_mode", "files_with_matches")
        scanned_hashes = set(by_hash)
        scanned_paths = {
            path: _sha256(path)
            for path in self._document_paths
            if _sha256(path) in scanned_hashes
        }
        returned_hashes: list[str] = []
        for line in text.splitlines():
            for path, path_hash in scanned_paths.items():
                matches = (
                    line == path
                    if mode == "files_with_matches"
                    else self._grep_content_line_matches(path, line)
                    if mode == "content"
                    else line.startswith(f"{path}: ")
                    and line.removeprefix(f"{path}: ").isdigit()
                )
                if matches and path_hash not in returned_hashes:
                    returned_hashes.append(path_hash)
        return [by_hash[path_hash] for path_hash in returned_hashes]

    @staticmethod
    def _grep_content_line_matches(path: str, line: str) -> bool:
        prefix = f"{path}:"
        if not line.startswith(prefix):
            return False
        remainder = line.removeprefix(prefix)
        line_number, separator, _content = remainder.partition(":")
        return bool(separator) and line_number.isdigit()

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        _input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        """Registra apenas argumentos estruturados permitidos; ignora ``_input_str``."""
        name = str((serialized or {}).get("name") or "tool")
        opened, scanned = self._inventory_for(name, inputs)
        with self._lock:
            self._sequence += 1
            self._started[str(run_id)] = _StartedCall(
                started=time.perf_counter(),
                sequence=self._sequence,
                name=name,
                category=classify_tool(name),
                source="langchain_callback",
                actor=_checkpoint_actor(metadata),
                parent_sha256=(
                    _sha256(str(parent_run_id)) if parent_run_id is not None else None
                ),
                safe_inputs=_safe_inputs(inputs),
                files_opened=opened,
                files_scanned=scanned,
            )

    def on_tool_end(self, output: Any, *, run_id: UUID, **_: Any) -> None:
        self._finish(str(run_id), "success", output)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **_: Any) -> None:
        self._finish(str(run_id), "error", None, error_type=type(error).__name__)

    def start_external_tool(self, name: str) -> str:
        """Registra operação que não passa por ``BaseTool``, como web clássica."""
        run_id = f"external-{time.perf_counter_ns()}"
        with self._lock:
            self._sequence += 1
            self._started[run_id] = _StartedCall(
                started=time.perf_counter(),
                sequence=self._sequence,
                name=name,
                category=classify_tool(name),
                source="classic_web_bridge",
                actor="main",
                parent_sha256=None,
                safe_inputs={},
                files_opened=None,
                files_scanned=None,
            )
        return run_id

    def finish_external_tool(self, run_id: str, output: Any = None) -> None:
        self._finish(run_id, "success", output)

    def fail_external_tool(self, run_id: str) -> None:
        self._finish(run_id, "error", None)

    def _finish(
        self,
        run_id: str,
        outcome: str,
        output: Any,
        *,
        error_type: str | None = None,
    ) -> None:
        with self._lock:
            started = self._started.pop(run_id, None)
            if started is None:
                return
            references, urls = _references_from_output(output)
            text = _flatten_output_text(output)
            output_status = getattr(output, "status", None)
            final_outcome = (
                str(output_status) if output_status in {"success", "error"} else outcome
            )
            self._calls.append(
                {
                    "sequence": started.sequence,
                    "call_id_sha256": _sha256(run_id),
                    "parent_call_id_sha256": started.parent_sha256,
                    "actor": started.actor,
                    "name": started.name,
                    "category": started.category,
                    "outcome": final_outcome,
                    "status": str(output_status or final_outcome),
                    "error_type": error_type,
                    "source": started.source,
                    "started_offset_s": round(started.started - self._t0, 3),
                    "duration_s": round(time.perf_counter() - started.started, 3),
                    "inputs": started.safe_inputs,
                    "files_opened": started.files_opened,
                    "files_scanned": started.files_scanned,
                    "files_returned": (
                        self._returned_path_references(started, text)
                        if final_outcome == "success"
                        else []
                    ),
                    **_output_measurements(text),
                    "web_references_returned": references,
                    "web_url_hashes_returned": (
                        sorted(_sha256(url) for url in urls)
                        if urls is not None
                        else None
                    ),
                }
            )

    def summary(self) -> dict[str, Any]:
        """Fecha pendências e devolve somente hashes, contagens e metadados seguros."""
        with self._lock:
            for run_id, started in list(self._started.items()):
                self._calls.append(
                    {
                        "sequence": started.sequence,
                        "call_id_sha256": _sha256(run_id),
                        "parent_call_id_sha256": started.parent_sha256,
                        "actor": started.actor,
                        "name": started.name,
                        "category": started.category,
                        "outcome": "unfinished",
                        "status": "N/D",
                        "error_type": None,
                        "source": started.source,
                        "started_offset_s": round(started.started - self._t0, 3),
                        "duration_s": None,
                        "inputs": started.safe_inputs,
                        "files_opened": started.files_opened,
                        "files_scanned": started.files_scanned,
                        "files_returned": [],
                        "returned_bytes": None,
                        "returned_tokens": None,
                        "returned_sha256": None,
                        "web_references_returned": None,
                        "web_url_hashes_returned": None,
                    }
                )
            self._started.clear()
            calls = sorted(self._calls, key=lambda call: call["sequence"])

        by_category = Counter(call["category"] for call in calls)
        by_name = Counter(call["name"] for call in calls)
        web_calls = [call for call in calls if call["category"] == "web"]
        incomplete = any(call["outcome"] == "unfinished" for call in calls)
        return {
            "schema_version": "benchmark-tool-telemetry-v2",
            "collector_active": True,
            "observability_status": "N/D" if incomplete else "complete",
            "calls": calls,
            "total_calls": None if incomplete else len(calls),
            "calls_by_category": (
                None if incomplete else dict(sorted(by_category.items()))
            ),
            "calls_by_name": None if incomplete else dict(sorted(by_name.items())),
            "web_calls": None if incomplete else len(web_calls),
            "web_references_returned": (
                None
                if incomplete
                else sum(
                    int(call["web_references_returned"] or 0) for call in web_calls
                )
            ),
            "web_unique_urls_returned": (
                None
                if incomplete
                else len(
                    {
                        url
                        for call in web_calls
                        for url in (call["web_url_hashes_returned"] or [])
                    }
                )
            ),
            "document_inventory": list(self._document_inventory),
            "notes": [
                "A ordem é a sequência monotônica de início das tools; chamadas podem terminar fora de ordem.",
                "Arquivos e escopos são representados somente por SHA-256; conteúdo e _input_str nunca são persistidos.",
                "files_scanned é o inventário candidato no escopo da tool; files_returned é o subconjunto observável no retorno.",
            ],
        }
