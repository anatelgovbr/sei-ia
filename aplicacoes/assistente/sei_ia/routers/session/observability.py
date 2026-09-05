"""Payloads semânticos e sanitizados do trace Langfuse do endpoint Session."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from sei_ia.configs.langfuse_config import truncate_langfuse_request_body
from sei_ia.data.content_status import ContentReason, ContentState
from sei_ia.data.pydantic_models import ChatRequest
from sei_ia.services.session_fs.manager import ResolvedSession
from sei_ia.services.session_fs.reference_numbers import extract_process_number

DocumentSource = Literal["session_fs", "redis", "sei", "unknown"]


@dataclass(frozen=True)
class DocumentFetchTelemetry:
    """Resultado seguro de uma busca executada durante a materialização."""

    document_id: str
    source: DocumentSource
    duration_ms: float
    status: ContentState
    reason: ContentReason | None = None
    bytes: int | None = None
    content_sha256: str | None = None


def _remove_content_fields(value: Any) -> bool:
    changed = False
    if isinstance(value, dict):
        if "content" in value:
            value.pop("content")
            changed = True
        for child in value.values():
            changed = _remove_content_fields(child) or changed
    elif isinstance(value, list):
        for child in value:
            changed = _remove_content_fields(child) or changed
    return changed


def _sanitize_request_payload(payload: dict[str, Any]) -> bool:
    changed = "ip" in payload
    payload.pop("ip", None)
    if "trace" in payload:
        payload.pop("trace")
        changed = True
    if payload.get("no_cache") is not True and "no_cache" in payload:
        payload.pop("no_cache")
        changed = True

    processes = payload.get("id_procedimentos")
    if isinstance(processes, list):
        for process in processes:
            if not isinstance(process, dict):
                continue
            documents = process.get("id_documentos")
            if isinstance(documents, list):
                for document in documents:
                    changed = _remove_content_fields(document) or changed
    return changed


def original_request_body_text(request: BaseModel, raw_body: Any) -> str:
    """Devolve o JSON observável sem campos internos ou valores default."""
    body_text: str | None = None
    if isinstance(raw_body, bytes):
        try:
            body_text = raw_body.decode("utf-8")
        except UnicodeDecodeError:
            body_text = None
    elif isinstance(raw_body, str):
        body_text = raw_body

    if body_text is not None:
        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            changed = _sanitize_request_payload(payload)
            serialized = (
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                if changed
                else body_text
            )
            return truncate_langfuse_request_body(serialized)

    excluded = {"ip", "trace"}
    if not bool(getattr(request, "no_cache", False)):
        excluded.add("no_cache")
    payload = request.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude=excluded,
    )
    _sanitize_request_payload(payload)
    return truncate_langfuse_request_body(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def encode_langfuse_json_text(value: str) -> str:
    """Codifica texto JSON para o Langfuse persistir o valor como string.

    O collector interpreta um atributo que contenha apenas JSON como objeto. Uma
    camada JSON adicional é removida pelo collector e preserva o body como texto na
    API/UI, sem as barras da representação de transporte.
    """
    return json.dumps(value, ensure_ascii=False)


def build_session_request_summary(
    request: ChatRequest,
    *,
    endpoint: str,
    request_id: str,
) -> dict[str, Any]:
    """Resumo estruturado do request, sem conteúdo materializado do SEI."""
    processes = []
    for process in request.id_procedimentos or []:
        processes.append(
            {
                "process_id": str(process.id_procedimento),
                "document_ids": [
                    str(getattr(document, "id_documento", document))
                    for document in process.id_documentos
                ],
            }
        )
    uploads = [
        {
            "upload_id": upload.id_arquivo_avulso,
            "filename": upload.nome_arquivo_avulso,
            "extension": upload.extensao_arquivo_avulso,
        }
        for upload in request.arquivos_avulsos or []
    ]
    flags = {
        "use_websearch": bool(request.use_websearch),
        "use_thinking": bool(request.use_thinking),
        "skip_memory": bool(request.skip_memory),
    }
    if bool(getattr(request, "no_cache", False)):
        flags["no_cache"] = True
    summary = {
        "endpoint": endpoint,
        "request_id": request_id,
        "user_id": str(request.id_usuario),
        "session_id": str(request.id_topico) if request.id_topico is not None else None,
        "user_request": request.text,
        "processes": processes,
        "uploads": uploads,
        "flags": flags,
    }
    requested_mode = getattr(request, "mode", None)
    if requested_mode is not None:
        summary["mode"] = requested_mode
    return summary


def build_session_trace_tags(
    request: ChatRequest,
    *,
    environment: str,
    result: str | None = None,
    mode: str | None = None,
    is_new: bool | None = None,
    has_unavailable_documents: bool = False,
) -> list[str]:
    """Tags de baixa cardinalidade; IDs permanecem em campos próprios."""
    tags = ["endpoint:session_stream", f"environment:{environment}"]
    if request.use_websearch:
        tags.append("websearch")
    if request.use_thinking:
        tags.append("thinking")
    if request.skip_memory:
        tags.append("skip_memory")
    if getattr(request, "no_cache", False):
        tags.append("no_cache")
    if mode:
        tags.append(f"mode:{mode}")
    if is_new is not None:
        tags.append("session:new" if is_new else "session:resumed")
    if has_unavailable_documents:
        tags.append("documents:unavailable")
    if result:
        tags.append(f"result:{result}")
    return tags


def _process_number(resolved: ResolvedSession, process_id: str) -> str | None:
    """Retorna o número visível do processo, quando o payload o informa."""
    process_entry = resolved.meta.processos.get(process_id, {})
    metadata = process_entry.get("metadata", {})
    number = extract_process_number(metadata)
    return number


def _document_number(resolved: ResolvedSession, document_id: str) -> str | None:
    entry = resolved.meta.documentos.get(document_id, {})
    number = str(entry.get("id_documento_formatado") or "").strip()
    return number or None


def build_materialization_trace_output(
    resolved: ResolvedSession,
    fetches: dict[str, DocumentFetchTelemetry],
) -> dict[str, Any]:
    """Explica a reconciliação sem enviar texto, preview, metadata ou path."""
    materialization = resolved.materialization
    added = set(materialization.added)
    refreshed = set(materialization.refreshed)
    reused = set(materialization.reused)
    empty = set(materialization.empty)
    unavailable = set(materialization.unavailable)
    source_counts: Counter[str] = Counter()
    document_results = []
    seen: set[tuple[str, str]] = set()

    for process_id, document_id in materialization.requested:
        identity = (process_id, document_id)
        if identity in seen:
            continue
        seen.add(identity)
        fetch = fetches.get(document_id)
        manifest_entry = resolved.meta.documentos.get(document_id, {})
        content_state = manifest_entry.get("content_state", "available")
        content_reason = manifest_entry.get("content_reason")
        if content_state == "empty" or document_id in empty:
            status = "empty"
            source = fetch.source if fetch is not None else "session_fs"
        elif content_state == "unavailable" or document_id in unavailable:
            status = "unavailable"
            source = fetch.source if fetch is not None else "unknown"
        elif document_id in reused:
            status = "available"
            source: DocumentSource = "session_fs"
        elif document_id in added or document_id in refreshed:
            status = "available"
            source = fetch.source if fetch is not None else "unknown"
        else:
            status = "available"
            source = fetch.source if fetch is not None else "unknown"

        source_counts[source] += 1
        visible_process_number = _process_number(resolved, process_id)
        visible_document_number = _document_number(resolved, document_id)
        document_results.append(
            {
                "process_id": process_id,
                "process_number": visible_process_number,
                "document_id": document_id,
                "document_number": visible_document_number,
                "status": status,
                "content_reason": (content_reason if status != "available" else None),
                "source": source,
                "duration_ms": fetch.duration_ms if fetch is not None else 0.0,
                "bytes": (
                    fetch.bytes
                    if fetch is not None and status != "unavailable"
                    else None
                ),
                "tokens": (
                    int(manifest_entry.get("tokens", 0) or 0)
                    if status != "unavailable"
                    else 0
                ),
                "content_sha256": (fetch.content_sha256 if fetch is not None else None),
            }
        )

    available_document_ids = [
        document_id
        for document_id in materialization.manifest_after
        if (
            resolved.meta.documentos.get(document_id, {}).get(
                "content_state", "available"
            )
            not in {"empty", "unavailable"}
            and document_id not in empty
            and document_id not in unavailable
        )
    ]

    return {
        "requested": [
            {
                "process_id": process_id,
                "process_number": _process_number(resolved, process_id),
                "document_id": document_id,
                "document_number": _document_number(resolved, document_id),
            }
            for process_id, document_id in materialization.requested
        ],
        "manifest_before": list(materialization.manifest_before),
        "manifest_after": list(materialization.manifest_after),
        "available": available_document_ids,
        "registered": list(materialization.registered),
        "added": list(materialization.added),
        "refreshed": list(materialization.refreshed),
        "materialized": list(materialization.materialized),
        "reused": list(materialization.reused),
        "empty": list(materialization.empty),
        "removed_from_manifest": list(materialization.removed_from_manifest),
        "unavailable": list(materialization.unavailable),
        "files_pruned": materialization.files_pruned,
        "source_counts": dict(source_counts),
        "duration_ms": materialization.duration_ms,
        "total_content_tokens": resolved.total_content_tokens,
        "documents": document_results,
    }


def build_response_summary(content: str) -> dict[str, Any]:
    encoded = content.encode("utf-8")
    return {
        "output": content,
        "chars": len(content),
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def with_response_summary(
    output: Mapping[str, Any], response_content: str | None
) -> dict[str, Any]:
    result = dict(output)
    if response_content is not None:
        result["response"] = build_response_summary(response_content)
    return result


def build_finalization_trace_output(
    *,
    content: str,
    event_counts: Counter[str],
    metadata_sent: bool,
    end_sent: bool,
) -> dict[str, Any]:
    return {
        "result": "success",
        "response": build_response_summary(content),
        "sse_event_counts": dict(event_counts),
        "metadata_sent": metadata_sent,
        "end_sent": end_sent,
    }


def build_error_trace_output(
    *,
    stage: str,
    status_code: int,
    exception: BaseException | None,
    response_content: str | None = None,
) -> dict[str, Any]:
    return with_response_summary(
        {
            "result": "error",
            "stage": stage,
            "status_code": status_code,
            "exception_type": (
                type(exception).__name__ if exception is not None else None
            ),
            "retryable": status_code in {408, 429, 502, 503, 504},
        },
        response_content,
    )
