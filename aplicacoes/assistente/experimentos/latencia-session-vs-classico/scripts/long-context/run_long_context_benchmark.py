"""Runner auditável do benchmark ``benchmark-long-context``.

O modo padrão apenas relê e valida dataset/projeto. A execução real aceita o fluxo
canário/continuação legado e ``--execute-full-battery`` para uma campanha N=1 que
continua após falhas de item. Não há retry de inferência, warmup, concorrência ou
endpoint clássico; o readback do Langfuse usa polling configurável e todo modo real
valida o preflight sanitizado antes do primeiro POST.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from langfuse import Langfuse
from long_context_contract import (
    CONTEXT_DISCLOSURE_THRESHOLD,
    DATASET_NAME,
    EXPECTED_CASE_METRICS,
    EXPECTED_ITEM_IDS,
    EXPECTED_ITEM_TYPES,
    PREFLIGHT_ENDPOINT,
    SESSION_ENDPOINT,
    TARGET_PROJECT,
    ContractError,
    ExecutionPolicy,
    TopicFactory,
    aggregate_agent_calls,
    aggregate_tool_calls,
    build_execution_payload,
    combine_call_metrics,
    consume_sse,
    plain,
    project_id_from_response,
    stable_digest,
    validate_dataset,
    validate_preflight,
)
from long_context_evidence import build_evidence_package
from long_context_scorer import (
    JudgeContractError,
    calculate_scores,
    create_judge_client,
    emit_sanitized_scores,
    judge_response,
)

CANARY_ITEM_ID = "case-0960k-q2-synthesis"
ISOLATED_BASE_URL = "https://127.0.0.1:8188"
_LEDGER_NAME = "execution-ledger.jsonl"
_RUN_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}")
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_SAFE_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{1,120}")

TraceReadStatus = Literal[
    "complete", "absent", "incomplete", "terminal_error", "retry_exhausted"
]


@dataclass(frozen=True)
class TraceReadResult:
    trace: Any | None
    status: TraceReadStatus
    attempts: int
    error_type: str | None = None
    error_status_code: int | None = None


_LANGFUSE_SOURCES = {
    "LANGFUSE_URL": ("LANGFUSE_URL", "LANGFUSE_COMPARATIVO_URL"),
    "LANGFUSE_PUBLIC_KEY": (
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_COMPARATIVO_PUBLIC_KEY",
    ),
    "LANGFUSE_SECRET_KEY": (
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_COMPARATIVO_SECRET_KEY",
    ),
}
_TOOL_CALL_KEYS = {
    "sequence",
    "call_id_sha256",
    "parent_call_id_sha256",
    "actor",
    "name",
    "category",
    "outcome",
    "status",
    "error_type",
    "source",
    "started_offset_s",
    "duration_s",
    "inputs",
    "files_opened",
    "files_scanned",
    "files_returned",
    "returned_bytes",
    "returned_tokens",
    "returned_sha256",
    "web_references_returned",
    "web_url_hashes_returned",
}
_SAFE_INPUT_KEYS = {
    "path",
    "file_path",
    "offset",
    "limit",
    "pattern_sha256",
    "glob_sha256",
    "output_mode",
    "subagent_type_sha256",
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ContractError("diretório protegido inválido")
    path.chmod(stat.S_IRWXU)
    return path


def _write_private_json(path: Path, value: Any) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")


def _append_private_jsonl(path: Path, value: Any) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _replace_private_jsonl_record(path: Path, record: dict[str, Any]) -> None:
    records = _read_execution_ledger(path)
    item_id = record.get("item_id")
    matches = [
        index for index, current in enumerate(records) if current["item_id"] == item_id
    ]
    if len(matches) != 1:
        raise ContractError("ledger protegido não encontrou reserva única")
    reservation = records[matches[0]]
    if reservation.get("execution_attempted") is True:
        record = {**record, "execution_attempted": True}
    records[matches[0]] = record
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            os.fchmod(handle.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            for current in records:
                handle.write(
                    json.dumps(current, ensure_ascii=False, default=str) + "\n"
                )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _reserve_execution_attempt(path: Path, item_id: str) -> None:
    records = _read_execution_ledger(path)
    if any(current["item_id"] == item_id for current in records):
        raise ContractError("item já contém tentativa; N=1 impede repetição")
    if any(current.get("status") == "in-progress" for current in records):
        raise ContractError("ledger contém tentativa sem conclusão")
    _append_private_jsonl(
        path,
        {
            "record_type": "item_execution",
            "item_id": item_id,
            "execution_attempted": True,
            "status": "in-progress",
        },
    )


def _configured_values(env_file: Path | None) -> dict[str, str | None]:
    """Resolve configuração com o arquivo explícito como fonte autoritativa."""
    values: dict[str, str | None] = {
        key: value for key, value in os.environ.items() if value
    }
    if env_file is not None:
        values.update(dotenv_values(env_file))
    return values


def _load_langfuse_credentials(env_file: Path | None) -> dict[str, str]:
    values = _configured_values(env_file)
    credentials: dict[str, str] = {}
    missing: list[str] = []
    for target, sources in _LANGFUSE_SOURCES.items():
        source = next((name for name in sources if values.get(name)), None)
        if source is None:
            missing.append(target)
        else:
            credentials[target] = str(values[source])
    if missing:
        raise ContractError("variáveis Langfuse ausentes: " + ",".join(missing))
    for target in _LANGFUSE_SOURCES:
        os.environ[target] = credentials[target]
    return credentials


def _load_judge_config(
    env_file: Path | None, *, judge_url: str | None, judge_model: str | None
) -> tuple[str, str, str]:
    values = _configured_values(env_file)
    url = judge_url or values.get("BENCHMARK_LONG_CONTEXT_JUDGE_URL")
    key = values.get("BENCHMARK_LONG_CONTEXT_JUDGE_KEY") or values.get(
        "LITELLM_PROXY_API_KEY"
    )
    model = judge_model or values.get("BENCHMARK_LONG_CONTEXT_JUDGE_MODEL")
    if not url or not key or not model:
        raise ContractError("URL, chave e modelo explícitos do juiz são obrigatórios")
    parsed = urlsplit(str(url))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ContractError("URL do juiz inválida")
    if parsed.query or parsed.fragment:
        raise ContractError("URL do juiz não pode conter query ou fragment")
    return str(url).rstrip("/"), str(key), str(model)


def _guard_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ContractError("base HTTP do deployment deve ser HTTPS explícito")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ContractError("base HTTP não pode conter path, query ou fragment")
    return value.rstrip("/")


def _guard_isolated_base_url(value: str) -> str:
    base_url = _guard_base_url(value)
    if base_url != ISOLATED_BASE_URL:
        raise ContractError("execução real exige a stack isolada local na porta 8188")
    return base_url


def _project_gate(credentials: dict[str, str]) -> str:
    response = httpx.get(
        credentials["LANGFUSE_URL"].rstrip("/") + "/api/public/projects",
        auth=(credentials["LANGFUSE_PUBLIC_KEY"], credentials["LANGFUSE_SECRET_KEY"]),
        timeout=30,
        follow_redirects=False,
    )
    if response.status_code != 200:
        raise ContractError(f"project gate HTTP {response.status_code}")
    return project_id_from_response(response.json())


def _langfuse_client(credentials: dict[str, str]) -> Langfuse:
    client = Langfuse(
        host=credentials["LANGFUSE_URL"],
        public_key=credentials["LANGFUSE_PUBLIC_KEY"],
        secret_key=credentials["LANGFUSE_SECRET_KEY"],
        timeout=90,
    )
    if not client.auth_check():
        raise ContractError("Langfuse auth_check falhou")
    return client


def _preflight(base_url: str, client: httpx.Client) -> dict[str, object]:
    """Valida configuração sanitizada sem abrir corpus nem chamar modelo."""
    response = client.get(base_url + PREFLIGHT_ENDPOINT)
    if response.status_code != 200:
        raise ContractError(f"preflight HTTP {response.status_code}")
    payload = response.json()
    validate_preflight(payload)
    return {
        "status": "ready",
        "endpoint": SESSION_ENDPOINT,
        "context_disclosure_threshold": payload["context_disclosure_threshold"],
        "session_main_model_profile": payload.get("session_main_model_profile"),
        "session_main_model": payload.get("session_main_model"),
        "session_classifier_model_profile": payload.get(
            "session_classifier_model_profile"
        ),
        "session_classifier_model": payload.get("session_classifier_model"),
        "session_explorer_model_profile": payload.get("session_explorer_model_profile"),
        "session_explorer_model": payload.get("session_explorer_model"),
        "session_ocr_model": payload.get("session_ocr_model"),
        "session_reasoning_effort_requested": payload.get(
            "session_reasoning_effort_requested"
        ),
        "session_main_model_client_retries": payload.get(
            "session_main_model_client_retries"
        ),
        "session_main_model_context_window_tokens": payload.get(
            "session_main_model_context_window_tokens"
        ),
        "benchmark_no_cache_required": payload["benchmark_no_cache_required"],
        "benchmark_document_source": payload["benchmark_document_source"],
        "benchmark_process_source": payload["benchmark_process_source"],
        "tool_telemetry_schema": payload["tool_telemetry_schema"],
        "preparation_heartbeat_interval_s": payload["preparation_heartbeat_interval_s"],
        "benchmark_evidence_pin_enabled": payload["benchmark_evidence_pin_enabled"],
        "benchmark_evidence_design": payload["benchmark_evidence_design"],
    }


def _http_client(timeout_s: float, *, isolated: bool = False) -> httpx.Client:
    return httpx.Client(
        transport=httpx.HTTPTransport(retries=0, verify=not isolated),
        timeout=httpx.Timeout(timeout_s, connect=min(timeout_s, 30.0)),
        follow_redirects=False,
    )


def _validation_ledger(
    dataset: Any, project_id: str
) -> tuple[list[Any] | None, list[dict[str, object]]]:
    """Sempre materializa nove linhas, inclusive quando o guard falha fechado."""
    try:
        items = validate_dataset(dataset, project_id)
        status = "validated"
    except ContractError:
        items = None
        status = "validation_failed"
    ledger = [
        {
            "record_type": "item_validation",
            "item_id": item_id,
            "status": status,
            "execution_attempted": False,
        }
        for item_id in sorted(EXPECTED_ITEM_IDS)
    ]
    return items, ledger


def _run_root(protected_root: Path, run_name: str, *, create: bool) -> Path:
    if _RUN_NAME_PATTERN.fullmatch(run_name) is None:
        raise ContractError("run_name contém caracteres não permitidos")
    base = _private_directory(protected_root.expanduser().resolve())
    candidate = (base / run_name).resolve()
    if candidate.parent != base:
        raise ContractError("run_name escapou do root protegido")
    if create:
        if candidate.exists() and any(candidate.iterdir()):
            raise ContractError("run canário já existe e não está vazio")
        return _private_directory(candidate)
    if not candidate.is_dir() or candidate.is_symlink():
        raise ContractError("run protegido não existe")
    candidate.chmod(stat.S_IRWXU)
    return candidate


def _read_execution_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ContractError("ledger protegido contém JSON inválido") from exc
            if not isinstance(record, dict):
                raise ContractError("ledger protegido contém registro inválido")
            item_id = record.get("item_id")
            if item_id not in EXPECTED_ITEM_IDS:
                raise ContractError("ledger protegido contém item alheio")
            if item_id in seen:
                raise ContractError("ledger protegido viola N=1")
            if record.get("execution_attempted") is not True:
                raise ContractError("ledger de execução sem tentativa explícita")
            seen.add(item_id)
            records.append(record)
    return records


def _select_canary(items: Iterable[Any]) -> Any:
    matches = [item for item in items if str(getattr(item, "id", "")) == CANARY_ITEM_ID]
    if len(matches) != 1:
        raise ContractError("canário positivo integrativo não é único")
    question_type, category = EXPECTED_ITEM_TYPES[CANARY_ITEM_ID]
    expected = plain(getattr(matches[0], "expected_output", None))
    metadata = plain(getattr(matches[0], "metadata", None))
    if (
        question_type != "synthesis"
        or category != "cross-document"
        or not isinstance(expected, dict)
        or expected.get("categoria") != category
        or not isinstance(metadata, dict)
        or metadata.get("question_type") != question_type
    ):
        raise ContractError("ID canário não representa o item positivo integrativo")
    return matches[0]


def _remaining_items(items: Iterable[Any], attempted: set[str]) -> list[Any]:
    remaining = [
        item for item in items if str(getattr(item, "id", "")) not in attempted
    ]
    return sorted(remaining, key=lambda item: str(getattr(item, "id", "")))


def _validate_continuation_ledger(records: list[dict[str, Any]]) -> set[str]:
    if not records:
        raise ContractError("continuação exige ledger do canário")
    if any(record.get("status") == "in-progress" for record in records):
        raise ContractError("continuação bloqueada: tentativa sem conclusão")
    canary = [record for record in records if record.get("item_id") == CANARY_ITEM_ID]
    if len(canary) != 1 or canary[0].get("canary_gate_status") != "passed":
        raise ContractError("continuação bloqueada: canário não aprovado")
    return {str(record["item_id"]) for record in records}


def _observation_value(observation: Any, field: str) -> Any:
    if isinstance(observation, dict):
        return observation.get(field)
    return getattr(observation, field, None)


def _observation_ready(observations: list[Any]) -> bool:
    if not all(
        _observation_value(observation, "end_time") is not None
        for observation in observations
    ):
        return False
    has_generation = any(
        "GENERATION" in str(_observation_value(obs, "type") or "").upper()
        for obs in observations
    )
    session_roots = [
        obs
        for obs in observations
        if _observation_value(obs, "name") == "session_agent"
        and "SPAN" in str(_observation_value(obs, "type") or "").upper()
    ]
    return has_generation and any(
        _observation_value(root, "end_time") is not None for root in session_roots
    )


def _trace_error_details(exc: Exception) -> tuple[str, int | None]:
    response = getattr(exc, "response", None)
    status_code = getattr(exc, "status_code", None) or getattr(
        response, "status_code", None
    )
    if not isinstance(status_code, int):
        status_code = None
    return type(exc).__name__, status_code


def _trace_error_class(
    status_code: int | None,
) -> Literal["absent", "terminal_error", "retry"]:
    if status_code == 404:
        return "absent"
    if (
        status_code is not None
        and 400 <= status_code < 500
        and status_code not in {408, 429}
    ):
        return "terminal_error"
    return "retry"


def _fetch_trace_stable(
    langfuse: Langfuse,
    trace_id: str,
    *,
    max_wait_s: float,
    poll_s: float,
    max_retries: int = 120,
    backoff_factor: float = 1.5,
    backoff_max_s: float = 30.0,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> TraceReadResult:
    """Aguarda a ingestão do trace sem repetir a chamada do benchmark."""
    deadline = clock() + max_wait_s
    previous_fingerprint: tuple[tuple[str, str], ...] | None = None
    stable_reads = 0
    last: Any | None = None
    last_status: TraceReadStatus = "retry_exhausted"
    last_error_type: str | None = None
    last_error_status_code: int | None = None
    attempts = 0
    delay = poll_s
    while attempts <= max_retries and clock() < deadline:
        attempts += 1
        try:
            current = langfuse.api.trace.get(trace_id)
        except Exception as exc:  # noqa: BLE001 - leitura eventual do Langfuse
            error_type, status_code = _trace_error_details(exc)
            error_class = _trace_error_class(status_code)
            if error_class == "terminal_error":
                return TraceReadResult(
                    trace=last,
                    status="terminal_error",
                    attempts=attempts,
                    error_type=error_type,
                    error_status_code=status_code,
                )
            last_status = "absent" if error_class == "absent" else "retry_exhausted"
            last_error_type = error_type
            last_error_status_code = status_code
        else:
            if current is None:
                last_status = "absent"
            else:
                last = current
                observations = list(getattr(current, "observations", None) or [])
                fingerprint = tuple(
                    sorted(
                        (
                            str(_observation_value(observation, "id") or ""),
                            str(_observation_value(observation, "end_time") or ""),
                        )
                        for observation in observations
                    )
                )
                if (
                    _observation_ready(observations)
                    and fingerprint == previous_fingerprint
                ):
                    stable_reads += 1
                    if stable_reads >= 2:
                        return TraceReadResult(
                            trace=current,
                            status="complete",
                            attempts=attempts,
                        )
                else:
                    stable_reads = 0
                previous_fingerprint = fingerprint
                last_status = "incomplete"
        if attempts > max_retries or clock() >= deadline:
            break
        sleeper(min(delay, max(0.0, deadline - clock())))
        delay = min(backoff_max_s, delay * backoff_factor)
    status = "incomplete" if last is not None else last_status
    return TraceReadResult(
        trace=last,
        status=status,
        attempts=attempts,
        error_type=last_error_type,
        error_status_code=last_error_status_code,
    )


def _dataset_run_linked(
    langfuse: Langfuse,
    *,
    dataset_id: str,
    run_name: str,
    item_id: str,
    trace_id: str,
    max_wait_s: float,
    poll_s: float,
    max_retries: int,
    backoff_factor: float,
    backoff_max_s: float,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> bool:
    deadline = clock() + max_wait_s
    attempts = 0
    delay = poll_s
    while attempts <= max_retries and clock() < deadline:
        attempts += 1
        try:
            page = langfuse.api.dataset_run_items.list(
                dataset_id=dataset_id,
                run_name=run_name,
                limit=100,
            )
        except Exception as exc:  # noqa: BLE001 - associação também é eventual
            error_type, status_code = _trace_error_details(exc)
            if _trace_error_class(status_code) == "terminal_error":
                raise ContractError(
                    f"leitura da associação do trace falhou: {error_type}"
                ) from exc
        else:
            if any(
                row.dataset_item_id == item_id and row.trace_id == trace_id
                for row in page.data
            ):
                return True
        if attempts > max_retries or clock() >= deadline:
            break
        sleeper(min(delay, max(0.0, deadline - clock())))
        delay = min(backoff_max_s, delay * backoff_factor)
    return False


def _path_reference_valid(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and set(value) == {"path_sha256", "kind", "suffix"}
        and isinstance(value.get("path_sha256"), str)
        and _HASH_PATTERN.fullmatch(value["path_sha256"])
        and isinstance(value.get("kind"), str)
        and _SAFE_NAME_PATTERN.fullmatch(value["kind"])
        and isinstance(value.get("suffix"), str)
        and len(value["suffix"]) <= 16
        and "/" not in value["suffix"]
        and "\\" not in value["suffix"]
    )


def _safe_inputs_valid(value: Any) -> bool:
    if not isinstance(value, dict) or not set(value).issubset(_SAFE_INPUT_KEYS):
        return False
    for key, item in value.items():
        if key in {"path", "file_path"} and not _path_reference_valid(item):
            return False
        if key in {"offset", "limit"} and not isinstance(item, int):
            return False
        if key.endswith("_sha256") and (
            not isinstance(item, str) or _HASH_PATTERN.fullmatch(item) is None
        ):
            return False
        if key == "output_mode" and item not in {
            "files_with_matches",
            "content",
            "count",
        }:
            return False
    return True


def _reference_list_valid(value: Any) -> bool:
    return value is None or (
        isinstance(value, list) and all(_path_reference_valid(item) for item in value)
    )


def _sanitized_tool_summary(  # noqa: C901, PLR0912, PLR0915
    summary: Any,
) -> dict[str, Any]:
    aggregate = aggregate_tool_calls(summary)
    if aggregate.get("observability_status") != "complete":
        raise ContractError("telemetria de tools está N/D")
    calls = summary.get("calls") if isinstance(summary, dict) else None
    if not isinstance(calls, list) or summary.get("total_calls") != len(calls):
        raise ContractError("telemetria de tools tem cardinalidade inválida")
    if [call.get("sequence") for call in calls if isinstance(call, dict)] != list(
        range(1, len(calls) + 1)
    ):
        raise ContractError("telemetria de tools perdeu ordem de início")

    safe_calls: list[dict[str, Any]] = []
    for call in calls:
        if not isinstance(call, dict) or set(call) != _TOOL_CALL_KEYS:
            raise ContractError("telemetria de tool contém campos inesperados")
        hash_fields = ("call_id_sha256", "returned_sha256")
        if any(
            call.get(field) is not None
            and (
                not isinstance(call[field], str)
                or _HASH_PATTERN.fullmatch(call[field]) is None
            )
            for field in hash_fields
        ):
            raise ContractError("telemetria de tool contém hash inválido")
        parent = call.get("parent_call_id_sha256")
        if parent is not None and (
            not isinstance(parent, str) or _HASH_PATTERN.fullmatch(parent) is None
        ):
            raise ContractError("telemetria de tool contém parent inválido")
        actor = call.get("actor")
        if (
            not isinstance(actor, str)
            or re.fullmatch(r"main|subagent:[0-9a-f]{12}", actor) is None
        ):
            raise ContractError("telemetria de tool contém ator inválido")
        for field in ("name", "category", "outcome", "status", "source"):
            value = call.get(field)
            if (
                not isinstance(value, str)
                or _SAFE_NAME_PATTERN.fullmatch(value) is None
            ):
                raise ContractError("telemetria de tool contém rótulo inválido")
        error_type = call.get("error_type")
        if error_type is not None and (
            not isinstance(error_type, str)
            or _SAFE_NAME_PATTERN.fullmatch(error_type) is None
        ):
            raise ContractError("telemetria de tool contém erro inválido")
        if not _safe_inputs_valid(call.get("inputs")):
            raise ContractError("telemetria de tool contém input não sanitizado")
        if not all(
            _reference_list_valid(call.get(field))
            for field in ("files_opened", "files_scanned", "files_returned")
        ):
            raise ContractError("telemetria de tool contém referência inválida")
        for field in ("started_offset_s", "duration_s"):
            value = call.get(field)
            if not isinstance(value, (int, float)) or value < 0:
                raise ContractError("telemetria de tool contém duração inválida")
        for field in ("returned_bytes", "returned_tokens"):
            value = call.get(field)
            if not isinstance(value, int) or value < 0:
                raise ContractError("telemetria de tool contém medição N/D")
        references = call.get("web_references_returned")
        if references is not None and (
            not isinstance(references, int) or references < 0
        ):
            raise ContractError("telemetria web contém contagem inválida")
        url_hashes = call.get("web_url_hashes_returned")
        if url_hashes is not None and (
            not isinstance(url_hashes, list)
            or not all(
                isinstance(value, str) and _HASH_PATTERN.fullmatch(value)
                for value in url_hashes
            )
        ):
            raise ContractError("telemetria web contém hash inválido")
        safe_calls.append({key: call[key] for key in sorted(_TOOL_CALL_KEYS)})

    inventory = summary.get("document_inventory")
    if not isinstance(inventory, list) or not inventory:
        raise ContractError("inventário de conteúdo do corpus ausente")
    safe_inventory = []
    for entry in inventory:
        if not isinstance(entry, dict) or set(entry) != {
            "path_sha256",
            "content_sha256",
            "bytes",
            "tokens",
        }:
            raise ContractError("inventário de conteúdo contém campos inválidos")
        if any(
            not isinstance(entry.get(field), str)
            or _HASH_PATTERN.fullmatch(entry[field]) is None
            for field in ("path_sha256", "content_sha256")
        ):
            raise ContractError("inventário de conteúdo contém hash inválido")
        if any(
            not isinstance(entry.get(field), int) or entry[field] < 0
            for field in ("bytes", "tokens")
        ):
            raise ContractError("inventário de conteúdo contém medição inválida")
        safe_inventory.append(dict(entry))

    return {
        "schema_version": "benchmark-tool-telemetry-v2",
        "observability_status": "complete",
        "total_calls": len(safe_calls),
        "calls_by_name": dict(summary["calls_by_name"]),
        "calls": safe_calls,
        "document_inventory": sorted(
            safe_inventory, key=lambda entry: entry["path_sha256"]
        ),
    }


def _context_disclosure_observed(
    *, item: Any, metadata: Any, tool_summary: dict[str, Any]
) -> bool:
    item_metadata = plain(getattr(item, "metadata", None))
    if not isinstance(item_metadata, dict) or not isinstance(metadata, dict):
        return False
    case_id = str(item_metadata.get("case_id"))
    expected = EXPECTED_CASE_METRICS.get(case_id, {})
    content_tokens = metadata.get("all_tokens_counter")
    documents = metadata.get("documentos")
    if (
        not isinstance(content_tokens, int)
        or content_tokens <= CONTEXT_DISCLOSURE_THRESHOLD
        or documents != expected.get("documents")
    ):
        return False
    inventory_paths = {
        entry.get("path_sha256")
        for entry in tool_summary.get("document_inventory", [])
        if isinstance(entry, dict)
    }
    for call in tool_summary["calls"]:
        references = [
            reference
            for field in ("files_opened", "files_scanned", "files_returned")
            for reference in (call.get(field) or [])
        ]
        if (
            call.get("category") == "filesystem"
            and call.get("outcome") == "success"
            and call.get("returned_bytes", 0) > 0
            and call.get("returned_tokens", 0) > 0
            and any(
                isinstance(reference, dict)
                and reference.get("path_sha256") in inventory_paths
                for reference in references
            )
        ):
            return True
    return False


def _stream_once(
    *,
    client: httpx.Client,
    base_url: str,
    payload: dict[str, Any],
    trace_id: str,
    raw_path: Path,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[int, str, Any]:
    """Executa exatamente um POST e cronometra até o terminal SSE."""
    started = clock()
    descriptor = os.open(
        raw_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
    with (
        os.fdopen(descriptor, "wb") as raw,
        client.stream(
            "POST",
            base_url + SESSION_ENDPOINT,
            json=payload,
            headers={
                "X-Langfuse-Trace-Id": trace_id,
                "X-Experiment-Collect-Tools": "1",
                "Accept": "text/event-stream",
            },
        ) as response,
    ):
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        if response.status_code != 200:
            raise ContractError(f"session endpoint HTTP {response.status_code}")
        if content_type != "text/event-stream":
            raise ContractError("session endpoint não retornou text/event-stream")
        outcome = consume_sse(
            response.iter_bytes(), started_at=started, clock=clock, raw=raw
        )
        raw.flush()
        os.fsync(raw.fileno())
        return response.status_code, content_type, outcome


def _item_identity(item: Any) -> tuple[str, str, bool]:
    item_id = str(getattr(item, "id", ""))
    metadata = plain(getattr(item, "metadata", None)) or {}
    expected_type = EXPECTED_ITEM_TYPES.get(item_id)
    if expected_type is None:
        raise ContractError("item sem classificação validada")
    return (
        item_id,
        str(metadata.get("case_id", "unknown")),
        (expected_type[0] == "insufficient-evidence"),
    )


def _base_execution_record(item: Any, topic_id: int) -> dict[str, Any]:
    item_id, case_id, _ = _item_identity(item)
    metrics = EXPECTED_CASE_METRICS[case_id]
    return {
        "record_type": "item_execution",
        "item_id": item_id,
        "case_id": case_id,
        "canonical_corpus_documents": metrics["documents"],
        "canonical_corpus_tokens": metrics["tokens"],
        "n": 1,
        "execution_attempted": False,
        "status": "error",
        "topic_id_sha256": _sha256_text(str(topic_id)),
        "http_status": None,
        "content_type": None,
        "terminal_type": None,
        "answer_nonempty": False,
        "answer_sha256": None,
        "observed_response_time_s": None,
        "context_disclosure_observed": False,
        "observed_content_tokens": None,
        "preparation_heartbeat_frames": 0,
        "preparation_duration_s": None,
        "server_preparation_heartbeat_count": None,
        "benchmark_evidence_preflight": "N/D",
        "tool_telemetry": "N/D",
        "evidence_observability": "N/D",
        "calls": "N/D",
        "scores": "N/D",
        "trace": {
            "trace_id_sha256": None,
            "project": TARGET_PROJECT,
            "located": False,
            "stable": False,
            "dataset_linked": False,
            "read_status": "not_started",
            "read_attempts": 0,
        },
    }


def _assessment_payload(assessment: Any, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_alignment": assessment.target_alignment,
        "checklist": assessment.checklist,
        "claims": [
            {
                "text": claim.text,
                "verdict": claim.verdict,
                "evidence_references": claim.evidence_references,
            }
            for claim in assessment.claims
        ],
        "abstract_understanding": assessment.abstract_understanding,
        "rationale": assessment.rationale,
        "negative_safety": {
            "abstained": assessment.abstained,
            "numerator_missing": assessment.numerator_missing,
            "denominator_missing": assessment.denominator_missing,
            "invented_rate": assessment.invented_rate,
            "universal_absence_claim": assessment.universal_absence_claim,
        },
        "raw": raw,
    }


def _execute_item(  # noqa: C901, PLR0912, PLR0915
    item: Any,
    *,
    langfuse: Langfuse,
    http_client: httpx.Client,
    base_url: str,
    run_name: str,
    root: Path,
    topic_factory: TopicFactory,
    trace_wait_s: float,
    trace_poll_s: float,
    trace_max_retries: int,
    trace_backoff_factor: float,
    trace_backoff_max_s: float,
    judge_client: Any,
    judge_model: str,
    evidence_index: Path,
) -> dict[str, Any]:
    item_id, case_id, is_negative = _item_identity(item)
    item_root = _private_directory(root / "items" / item_id)
    topic_id = topic_factory.new()
    payload = build_execution_payload(item.input, topic_id)
    safe = _base_execution_record(item, topic_id)
    protected: dict[str, Any] = {
        "item_id": item_id,
        "case_id": case_id,
        "topic_id": topic_id,
        "payload_sha256": stable_digest(payload),
        "trace_id": None,
        "answer": None,
        "judge_assessment": None,
    }
    trace_id: str | None = None
    started = time.monotonic()
    try:
        with item.run(
            run_name=run_name,
            run_metadata={
                "benchmark": DATASET_NAME,
                "case_id": case_id,
                "n": 1,
                "transport": "http",
                "endpoint": SESSION_ENDPOINT,
                "websearch": False,
                "no_cache": True,
                "document_source": "sei_no_cache_with_pinned_validation",
                "process_source": "sei_no_cache",
                "retry": False,
                "warmup": False,
                "canary": item_id == CANARY_ITEM_ID,
            },
        ) as span:
            trace_id = span.trace_id
            protected["trace_id"] = trace_id
            safe["trace"]["trace_id_sha256"] = _sha256_text(trace_id)
            safe["execution_attempted"] = True
            http_status, content_type, outcome = _stream_once(
                client=http_client,
                base_url=base_url,
                payload=payload,
                trace_id=trace_id,
                raw_path=item_root / "stream.raw.sse",
            )
            safe.update(
                {
                    "http_status": http_status,
                    "content_type": content_type,
                    "terminal_type": outcome.terminal_type,
                    "answer_nonempty": bool(outcome.content.strip()),
                    "answer_sha256": _sha256_text(outcome.content),
                    "observed_response_time_s": outcome.observed_response_time_s,
                    "preparation_heartbeat_frames": (
                        outcome.preparation_heartbeat_frames
                    ),
                }
            )
            if isinstance(outcome.metadata, dict):
                safe["preparation_duration_s"] = outcome.metadata.get(
                    "preparation_duration_s"
                )
                safe["server_preparation_heartbeat_count"] = outcome.metadata.get(
                    "preparation_heartbeat_count"
                )
                safe["benchmark_evidence_preflight"] = outcome.metadata.get(
                    "benchmark_evidence_preflight"
                )
            protected.update(
                {
                    "answer": outcome.content,
                    "answer_sha256": safe["answer_sha256"],
                    "terminal_type": outcome.terminal_type,
                    "terminal_status_code": outcome.terminal_status_code,
                    "observed_response_time_s": outcome.observed_response_time_s,
                }
            )
            span.update(
                output={
                    "terminal_type": outcome.terminal_type,
                    "answer_sha256": safe["answer_sha256"],
                    "observed_response_time_s": outcome.observed_response_time_s,
                }
            )

        if outcome.terminal_type != "end":
            raise ContractError("stream terminou em frame de erro")
        if outcome.terminal_status_code == 413:
            raise ContractError("stream sinalizou estouro de contexto")
        if not outcome.content.strip():
            raise ContractError("stream terminou sem resposta")

        langfuse.flush()
        trace_read = _fetch_trace_stable(
            langfuse,
            trace_id,
            max_wait_s=trace_wait_s,
            poll_s=trace_poll_s,
            max_retries=trace_max_retries,
            backoff_factor=trace_backoff_factor,
            backoff_max_s=trace_backoff_max_s,
        )
        full_trace = trace_read.trace
        observations = (
            list(getattr(full_trace, "observations", None) or [])
            if full_trace is not None
            else None
        )
        safe["trace"]["located"] = full_trace is not None
        safe["trace"]["stable"] = trace_read.status == "complete"
        safe["trace"]["read_status"] = trace_read.status
        safe["trace"]["read_attempts"] = trace_read.attempts
        if trace_read.status == "terminal_error":
            raise ContractError("leitura do trace terminou em erro terminal")
        if trace_read.status == "absent":
            raise ContractError("trace ausente após o polling de ingestão")
        if trace_read.status == "retry_exhausted":
            raise ContractError("leitura do trace esgotou as tentativas")
        if trace_read.status == "incomplete":
            raise ContractError("trace ainda incompleto após o polling de ingestão")
        trace_stable = trace_read.status == "complete"
        safe["trace"]["dataset_linked"] = _dataset_run_linked(
            langfuse,
            dataset_id=str(getattr(item, "dataset_id", "")),
            run_name=run_name,
            item_id=item_id,
            trace_id=trace_id,
            max_wait_s=trace_wait_s,
            poll_s=trace_poll_s,
            max_retries=trace_max_retries,
            backoff_factor=trace_backoff_factor,
            backoff_max_s=trace_backoff_max_s,
        )
        if not safe["trace"]["dataset_linked"]:
            raise ContractError("trace não está associado ao item/run")

        llm_calls = aggregate_agent_calls(observations, stable=trace_stable)
        benchmark_metrics = (
            outcome.metadata.get("benchmark_metrics")
            if isinstance(outcome.metadata, dict)
            else None
        )
        tool_summary = _sanitized_tool_summary(benchmark_metrics)
        tool_calls = aggregate_tool_calls(benchmark_metrics)
        calls = combine_call_metrics(llm_calls, tool_calls)
        if not isinstance(calls.get("calls_llm"), int):
            raise ContractError("contagem de gerações LLM está N/D")
        if not isinstance(calls.get("calls_tools"), int):
            raise ContractError("contagem de tools está N/D")
        disclosure_observed = _context_disclosure_observed(
            item=item,
            metadata=outcome.metadata,
            tool_summary=tool_summary,
        )
        if not disclosure_observed:
            raise ContractError("context disclosure não foi observado")
        safe["tool_telemetry"] = tool_summary
        safe["calls"] = calls
        safe["context_disclosure_observed"] = True
        safe["observed_content_tokens"] = outcome.metadata.get("all_tokens_counter")

        evidence_package, evidence_summary = build_evidence_package(
            index_path=evidence_index,
            case_id=case_id,
            answer=outcome.content,
            tool_summary=tool_summary,
            fresh_evidence=outcome.metadata.get("benchmark_fresh_evidence"),
        )
        safe["evidence_observability"] = evidence_summary
        protected["evidence_package"] = evidence_package
        protected["evidence_observability"] = evidence_summary

        item_input = plain(item.input)
        expected_output = plain(item.expected_output)
        assessment, raw_assessment = judge_response(
            client=judge_client,
            model=judge_model,
            question=str(item_input.get("text", "")),
            expected_output=expected_output,
            answer=outcome.content,
            is_negative=is_negative,
            evidence_package=evidence_package,
        )
        scores = calculate_scores(
            expected_output,
            outcome.content,
            assessment,
            is_negative=is_negative,
        )
        safe["scores"] = scores.sanitized()
        protected["judge_assessment"] = _assessment_payload(assessment, raw_assessment)
        protected["tool_telemetry"] = tool_summary
        protected["calls"] = calls
        protected["scores"] = scores.sanitized()
        emit_sanitized_scores(
            langfuse,
            trace_id,
            observed_response_time_s=outcome.observed_response_time_s,
            calls=calls,
            scores=scores,
        )
        langfuse.flush()
        safe["status"] = "ok"
        _write_private_json(item_root / "result-protected.json", protected)
        return safe
    except Exception as exc:  # noqa: BLE001 - uma tentativa deve sempre gerar ledger
        if isinstance(exc, JudgeContractError):
            safe["judge_diagnostic"] = exc.diagnostic
            protected["judge_diagnostic"] = exc.diagnostic
        safe["error_type"] = type(exc).__name__
        safe["error_sha256"] = _sha256_text(str(exc))
        if safe["observed_response_time_s"] is None:
            safe["observed_response_time_s"] = max(0.0, time.monotonic() - started)
        protected.update(
            {
                "error_type": type(exc).__name__,
                "error_sha256": safe["error_sha256"],
                "execution_attempted": safe["execution_attempted"],
            }
        )
        _write_private_json(item_root / "result-protected.json", protected)
        return safe


def _canary_failures(record: dict[str, Any]) -> list[str]:  # noqa: PLR0912
    failures: list[str] = []
    required = {
        "item_id": record.get("item_id") == CANARY_ITEM_ID,
        "execution_attempted": record.get("execution_attempted") is True,
        "status": record.get("status") == "ok",
        "http_200": record.get("http_status") == 200,
        "sse": record.get("content_type") == "text/event-stream",
        "terminal_end": record.get("terminal_type") == "end",
        "answer_nonempty": record.get("answer_nonempty") is True,
        "context_disclosure": record.get("context_disclosure_observed") is True,
        "observed_time": isinstance(
            record.get("observed_response_time_s"), (int, float)
        ),
    }
    failures.extend(name for name, passed in required.items() if not passed)
    calls = record.get("calls")
    if not isinstance(calls, dict) or not isinstance(calls.get("calls_llm"), int):
        failures.append("calls_llm")
    if not isinstance(calls, dict) or not isinstance(calls.get("calls_tools"), int):
        failures.append("calls_tools")
    telemetry = record.get("tool_telemetry")
    if (
        not isinstance(telemetry, dict)
        or telemetry.get("observability_status") != "complete"
        or not telemetry.get("calls")
    ):
        failures.append("tool_telemetry")
    evidence = record.get("evidence_observability")
    if not isinstance(evidence, dict) or evidence.get("status") != "complete":
        failures.append("evidence_observability")
    scores = record.get("scores")
    for name in (
        "completude",
        "groundedness",
        "entendimento_abstrato",
        "hallucination_count",
    ):
        if not isinstance(scores, dict) or not isinstance(
            scores.get(name), (int, float)
        ):
            failures.append(name)
    if not isinstance(scores, dict) or scores.get("target_alignment") is not True:
        failures.append("target_alignment")
    if not isinstance(scores, dict) or scores.get("completude", 0) < 0.8:
        failures.append("completude_threshold")
    if (
        not isinstance(scores, dict)
        or not isinstance(scores.get("groundedness"), (int, float))
        or scores["groundedness"] < 0.8
    ):
        failures.append("groundedness_threshold")
    if not isinstance(scores, dict) or scores.get("entendimento_abstrato") != 1.0:
        failures.append("entendimento_abstrato_threshold")
    if not isinstance(scores, dict) or scores.get("hallucination_zero") is not True:
        failures.append("hallucination_zero")
    if isinstance(scores, dict) and scores.get("unverified_claims") != 0:
        failures.append("unverified_claims")
    trace = record.get("trace")
    if not isinstance(trace, dict) or not all(
        trace.get(name) is True for name in ("located", "stable", "dataset_linked")
    ):
        failures.append("trace_observability")
    if not isinstance(trace, dict) or trace.get("project") != TARGET_PROJECT:
        failures.append("trace_project")
    return sorted(set(failures))


def _execute_canary(
    *,
    items: list[Any],
    execute_one: Callable[[Any], dict[str, Any]],
    ledger_path: Path,
) -> dict[str, Any]:
    if _read_execution_ledger(ledger_path):
        raise ContractError("run canário já contém tentativa; N=1 impede repetição")
    item = _select_canary(items)
    _reserve_execution_attempt(ledger_path, str(item.id))
    record = execute_one(item)
    failures = _canary_failures(record)
    record["canary_gate_status"] = "passed" if not failures else "failed"
    record["canary_gate_failures"] = failures
    _replace_private_jsonl_record(ledger_path, record)
    return record


def _execute_remaining(
    *,
    items: list[Any],
    execute_one: Callable[[Any], dict[str, Any]],
    ledger_path: Path,
) -> list[dict[str, Any]]:
    existing = _read_execution_ledger(ledger_path)
    attempted = _validate_continuation_ledger(existing)
    records: list[dict[str, Any]] = []
    for item in _remaining_items(items, attempted):
        _reserve_execution_attempt(ledger_path, str(item.id))
        record = execute_one(item)
        record["canary_gate_status"] = "not-applicable"
        _replace_private_jsonl_record(ledger_path, record)
        records.append(record)
    return records


def _progress_record(record: dict[str, Any]) -> dict[str, Any]:
    """Resumo pequeno por item; nunca inclui resposta, tools ou identificadores."""
    return {
        "record_type": "item_progress",
        "item_id": record.get("item_id"),
        "status": record.get("status"),
        "error_type": record.get("error_type"),
        "observed_response_time_s": record.get("observed_response_time_s"),
        "preparation_heartbeat_frames": record.get("preparation_heartbeat_frames", 0),
        "trace_stable": (
            record.get("trace", {}).get("stable")
            if isinstance(record.get("trace"), dict)
            else False
        ),
    }


def _execute_full_battery(
    *,
    items: list[Any],
    execute_one: Callable[[Any], dict[str, Any]],
    ledger_path: Path,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Executa as nove identidades uma vez e não para por falha de item."""
    if _read_execution_ledger(ledger_path):
        raise ContractError("run completo já contém tentativa; N=1 impede repetição")
    records: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda value: str(getattr(value, "id", ""))):
        _reserve_execution_attempt(ledger_path, str(item.id))
        record = execute_one(item)
        record["canary_gate_status"] = "not-applicable-full-battery"
        _replace_private_jsonl_record(ledger_path, record)
        records.append(record)
        if on_progress is not None:
            on_progress(_progress_record(record))
    return records


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute-canary", action="store_true")
    mode.add_argument("--continue-run", action="store_true")
    mode.add_argument("--execute-full-battery", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument(
        "--base-url", default=os.environ.get("BENCHMARK_LONG_CONTEXT_BASE_URL")
    )
    parser.add_argument("--protected-root", type=Path)
    parser.add_argument("--run-name")
    parser.add_argument("--judge-url")
    parser.add_argument("--judge-model")
    parser.add_argument("--evidence-index", type=Path)
    parser.add_argument("--timeout-s", type=float, default=7200.0)
    parser.add_argument("--trace-wait-s", type=float, default=900.0)
    parser.add_argument("--trace-poll-s", type=float, default=4.0)
    parser.add_argument("--trace-max-retries", type=int, default=120)
    parser.add_argument("--trace-backoff-factor", type=float, default=1.5)
    parser.add_argument("--trace-backoff-max-s", type=float, default=30.0)
    return parser.parse_args()


def _main() -> int:  # noqa: C901, PLR0915
    args = _parse_args()
    policy = ExecutionPolicy()
    if policy != ExecutionPolicy():
        raise ContractError("política imutável foi alterada")
    credentials = _load_langfuse_credentials(args.env_file)
    project_id = _project_gate(credentials)
    langfuse = _langfuse_client(credentials)
    dataset = langfuse.get_dataset(DATASET_NAME, fetch_items_page_size=100)
    items, validation_ledger = _validation_ledger(dataset, project_id)
    for record in validation_ledger:
        print(json.dumps(record, ensure_ascii=False))
    if items is None:
        return 1

    execution_mode = (
        args.execute_canary or args.continue_run or args.execute_full_battery
    )
    if not args.preflight and not execution_mode:
        print(
            json.dumps(
                {
                    "status": "validated",
                    "project": TARGET_PROJECT,
                    "dataset": DATASET_NAME,
                    "items": len(items),
                    "execution_attempted": False,
                }
            )
        )
        return 0

    if not args.base_url:
        raise ContractError("base URL do deployment é obrigatória")
    if args.preflight:
        base_url = _guard_base_url(args.base_url)
        with _http_client(
            args.timeout_s, isolated=base_url == ISOLATED_BASE_URL
        ) as http_client:
            result = _preflight(base_url, http_client)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    base_url = _guard_isolated_base_url(args.base_url)
    values = _configured_values(args.env_file)
    configured_root = args.protected_root or (
        Path(str(values["BENCHMARK_LONG_CONTEXT_ROOT"]))
        if values.get("BENCHMARK_LONG_CONTEXT_ROOT")
        else None
    )
    if configured_root is None:
        raise ContractError("root protegido é obrigatório para execução real")
    if (
        args.timeout_s <= 0
        or args.trace_wait_s <= 0
        or args.trace_poll_s <= 0
        or args.trace_max_retries < 0
        or args.trace_backoff_factor < 1
        or args.trace_backoff_max_s <= 0
    ):
        raise ContractError("timeouts, retries e backoff têm configuração inválida")
    run_name = args.run_name or (
        "long-context-stage3-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    )
    root = _run_root(
        configured_root,
        run_name,
        create=args.execute_canary or args.execute_full_battery,
    )
    ledger_path = root / _LEDGER_NAME
    judge_url, judge_key, judge_model = _load_judge_config(
        args.env_file,
        judge_url=args.judge_url,
        judge_model=args.judge_model,
    )
    if args.evidence_index is None:
        raise ContractError("índice protegido de evidências é obrigatório")
    evidence_index = args.evidence_index.expanduser().resolve()
    judge_client = create_judge_client(base_url=judge_url, api_key=judge_key)
    topic_factory = TopicFactory()

    with _http_client(args.timeout_s, isolated=True) as http_client:
        runtime_preflight = _preflight(base_url, http_client)
        print(
            json.dumps(
                {"record_type": "runtime_preflight", **runtime_preflight},
                ensure_ascii=False,
            )
        )

        def execute_one(item: Any) -> dict[str, Any]:
            return _execute_item(
                item,
                langfuse=langfuse,
                http_client=http_client,
                base_url=base_url,
                run_name=run_name,
                root=root,
                topic_factory=topic_factory,
                trace_wait_s=args.trace_wait_s,
                trace_poll_s=args.trace_poll_s,
                trace_max_retries=args.trace_max_retries,
                trace_backoff_factor=args.trace_backoff_factor,
                trace_backoff_max_s=args.trace_backoff_max_s,
                judge_client=judge_client,
                judge_model=judge_model,
                evidence_index=evidence_index,
            )

        if args.execute_canary:
            record = _execute_canary(
                items=items,
                execute_one=execute_one,
                ledger_path=ledger_path,
            )
            print(json.dumps(record, ensure_ascii=False))
            return 0 if record["canary_gate_status"] == "passed" else 2

        if args.execute_full_battery:
            records = _execute_full_battery(
                items=items,
                execute_one=execute_one,
                ledger_path=ledger_path,
                on_progress=lambda progress: print(
                    json.dumps(progress, ensure_ascii=False)
                ),
            )
        else:
            records = _execute_remaining(
                items=items,
                execute_one=execute_one,
                ledger_path=ledger_path,
            )
    print(
        json.dumps(
            {
                "status": "finished",
                "run_name": run_name,
                "new_items": len(records),
                "total_items": len(_read_execution_ledger(ledger_path)),
                "ok": sum(record["status"] == "ok" for record in records),
                "errors": sum(record["status"] != "ok" for record in records),
                "execution_policy": policy.__dict__,
            },
            ensure_ascii=False,
        )
    )
    return 0 if all(record["status"] == "ok" for record in records) else 2


def main() -> int:
    try:
        return _main()
    except Exception as exc:  # noqa: BLE001 - CLI nunca imprime payload sensível
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error_sha256": _sha256_text(str(exc)),
                }
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
