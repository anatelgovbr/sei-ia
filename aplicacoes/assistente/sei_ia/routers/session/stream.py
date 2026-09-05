"""Rota /llm_lang/session_stream — endpoint Deep Agents com sessão escopada (SSE).

Paradigma novo (vs. /llm_lang/stream): em vez de RAG, o agente vasculha os
documentos do tópico como filesystem virtual, com escopo fechado por
{id_usuario}_{id_topico}, multi-turn via checkpointer Postgres e TTL deslizante.

Por escolha de design, NÃO há classificação de intenção, RAG por embeddings nem
map-reduce de summarization dedicado: um único deep-agent resolve tudo via tools
de filesystem (ls/grep/read_file) e delega leitura pesada a um subagente
explorador. O `classify_complexity` (modelo mini) roda antes do agente **só no
modo filesystem** e ajusta a diretiva de ESFORÇO anexada ao system prompt
(easy/medium/high), sem mudar a topologia; no modo injetado é pulado (a diretiva
não entra no prompt — seria uma chamada serial inútil). Não toca no fluxo
LangGraph antigo.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import inspect
import json
import logging
import re
import time
from collections import Counter
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import openai
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from sei_extraction.ocr.client import collect_ocr_usage

from sei_ia.agents.rag.stream_processor_final import StreamTagProcessorFinal
from sei_ia.agents.session_agent.agent import build_session_agent
from sei_ia.agents.session_agent.classifier import classify_complexity
from sei_ia.agents.session_agent.inject import build_injected_context
from sei_ia.agents.session_agent.langfuse_callback import SessionLangfuseCallback
from sei_ia.agents.session_agent.mode import decide_mode
from sei_ia.agents.session_agent.status_emitter import SessionStatusHandler
from sei_ia.agents.session_agent.trace import SessionTraceHandler
from sei_ia.agents.session_agent.usage import (
    SessionModelUsageHandler,
    aggregate_ocr_usage,
)
from sei_ia.agents.session_agent.web_speculative import (
    build_doc_hint,
    plan_speculative_web_queries,
)
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.content_status import ContentStatus
from sei_ia.data.etl.extract.uploads import ArquivoAvulsoProcessingError
from sei_ia.data.pydantic_models import ChatRequest
from sei_ia.routers.chat import (
    _apply_arquivos_avulsos_to_state,
    _flush_langfuse,
    _langfuse_span,
    _new_trace_id,
    _remove_arquivos_avulsos_no_sei,
    _update_langfuse_observation,
    _update_langfuse_trace,
    cleanup_arquivos_avulsos_temp_files,
)
from sei_ia.routers.session.observability import (
    DocumentFetchTelemetry,
    build_error_trace_output,
    build_finalization_trace_output,
    build_materialization_trace_output,
    build_session_request_summary,
    build_session_trace_tags,
    encode_langfuse_json_text,
    original_request_body_text,
    with_response_summary,
)
from sei_ia.services.benchmark_metrics import BenchmarkToolHandler
from sei_ia.services.exceptions.http_exceptions import fast_api_responses
from sei_ia.services.llm_models.get_model import get_model_config
from sei_ia.services.llm_models.model_catalog import (
    validate_model_override,
    validate_reasoning_effort,
)
from sei_ia.services.session_fs.benchmark_evidence import (
    BenchmarkEvidenceError,
    load_benchmark_evidence_snapshot,
)
from sei_ia.services.session_fs.checkpointer import get_session_checkpointer
from sei_ia.services.session_fs.manager import (
    SessionDocumentMaterializationError,
    SessionDocumentOutcome,
)
from sei_ia.services.session_fs.runtime import get_session_manager

setup_logging()
logger = logging.getLogger(__name__)
# Configurado em trace.py (handler próprio); reusado para o timing da coleta.
_trace_logger = logging.getLogger("session.trace")

ENDPOINT_NAME = "/llm_lang/session_stream"
_LANGFUSE_TRACE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
router = APIRouter()


def _trace_id_for_request(request: Request) -> str | None:
    supplied_trace_id = request.headers.get("X-Langfuse-Trace-Id")
    if supplied_trace_id and _LANGFUSE_TRACE_ID_PATTERN.fullmatch(supplied_trace_id):
        return supplied_trace_id
    return _new_trace_id()


@dataclass(frozen=True)
class _HeartbeatEvent:
    """Evento interno: heartbeat periódico ou resultado final da preparação."""

    completed: bool
    elapsed_s: float
    result: Any | None = None


async def _run_with_heartbeat(
    awaitable: Awaitable[Any], *, interval_s: float
) -> AsyncIterator[_HeartbeatEvent]:
    """Executa uma etapa longa sem deixar o gerador SSE silencioso."""
    if interval_s <= 0:
        raise ValueError("interval_s deve ser positivo")
    task = asyncio.ensure_future(awaitable)
    started = time.monotonic()
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=interval_s)
            elapsed_s = max(0.0, time.monotonic() - started)
            if task in done:
                yield _HeartbeatEvent(
                    completed=True,
                    elapsed_s=elapsed_s,
                    result=task.result(),
                )
                return
            yield _HeartbeatEvent(completed=False, elapsed_s=elapsed_s)
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


@dataclass(frozen=True)
class _StreamHeartbeatEvent:
    """Evento do agente ou heartbeat emitido enquanto o agente está silencioso."""

    heartbeat: bool
    elapsed_s: float
    result: Any | None = None


async def _stream_events_with_heartbeat(
    stream: AsyncIterator[Any], *, interval_s: float
) -> AsyncIterator[_StreamHeartbeatEvent]:
    """Lê um stream assíncrono sem cancelar a leitura pendente no timeout.

    ``asyncio.wait`` deixa a chamada ``__anext__`` viva quando o intervalo expira;
    isso é necessário para que um agente que está aguardando o upstream não perca
    seu próximo evento ao emitir um heartbeat SSE.
    """
    if interval_s <= 0:
        raise ValueError("interval_s deve ser positivo")

    iterator = stream.__aiter__()
    pending: asyncio.Task[Any] | None = None
    started = time.monotonic()
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(iterator.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=interval_s)
            elapsed_s = max(0.0, time.monotonic() - started)
            if not done:
                yield _StreamHeartbeatEvent(heartbeat=True, elapsed_s=elapsed_s)
                continue

            try:
                result = pending.result()
            except StopAsyncIteration:
                return
            finally:
                pending = None
            yield _StreamHeartbeatEvent(
                heartbeat=False,
                elapsed_s=elapsed_s,
                result=result,
            )
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            await aclose()


class SessionStreamRequest(ChatRequest):
    """Request do /llm_lang/session_stream.

    Estende o ChatRequest com controles de debug: ``no_cache=True`` zera a sessão
    (dir + thread do checkpointer), pula o cache Redis e apaga os registros dos
    documentos (tudo fresco a cada run); ``trace=true`` loga a cronologia de tool
    calls (nome/args/duração) no terminal; ``inject_tokens_threshold`` sobrepõe o
    knob do threshold de modo (fase 5) só para experimentação; ``mode`` força
    `injected` ou `filesystem` quando um teste precisa ignorar o threshold.
    """

    no_cache: bool = False
    trace: bool = False
    inject_tokens_threshold: int | None = None
    mode: Literal["injected", "filesystem"] | None = None


async def _prepare_session_user_message(
    request: SessionStreamRequest,
    temp_files: set[str],
    removal_ids: set[int] | None = None,
) -> object:
    """Processa uploads e monta a mensagem do agente da sessão.

    O arquivo já está disponível no SEI; o payload carrega apenas seus
    metadados. Texto/PDF/áudio vira parte do texto do turno e imagens seguem
    como conteúdo multimodal. O processamento e a persistência reutilizam os
    helpers do fluxo clássico; este endpoint adia a sinalização de remoção no
    SEI até o agente concluir com sucesso.

    O upload-fonte no SEI tem janela externa de 1h, independente do TTL do cache
    Redis de anexos. Cenários E2E precisam criar um upload fresco e chamar este
    endpoint dentro dessa janela; não reutilize IDs de um teste anterior.
    """
    if not request.arquivos_avulsos:
        return {"role": "user", "content": request.text}

    if removal_ids is None:
        removal_ids = set()

    upload_state = {
        "user_request": request.text,
        "all_tokens_counter": 0,
        "system_prompt": request.system_prompt or "",
        "id_topico": request.id_topico,
    }
    processed_temp_files = await _apply_arquivos_avulsos_to_state(
        request,
        upload_state,
        remove_from_sei=False,
        tolerant_uploads=True,
    )
    temp_files.update(processed_temp_files)
    removal_ids.update(upload_state.get("upload_removal_ids") or [])

    image_attachments = upload_state.get("image_attachments") or []
    if image_attachments:
        # Import tardio: chat_workflow puxa a stack pesada do fluxo clássico.
        from sei_ia.services.llm_models.chat_workflow import (
            _build_multimodal_human_message,
        )

        return _build_multimodal_human_message(
            upload_state["user_request"], image_attachments
        )
    return {"role": "user", "content": upload_state["user_request"]}


def _now() -> float:
    return time.time()


def _frame(frame_type: str, **fields) -> str:
    payload = {"type": frame_type, "timestamp": _now(), **fields}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _error_frame(
    status_code: int, detail: str, *, diagnostic: dict[str, Any] | None = None
) -> str:
    fields: dict[str, Any] = {"status_code": status_code, "detail": detail}
    if diagnostic is not None:
        fields["diagnostic"] = diagnostic
    return _frame("error", **fields)


def _preparation_heartbeat_frame(elapsed_s: float) -> str:
    """Frame sem payload de usuário para manter o proxy ativo na preparação."""
    return _frame(
        "status",
        data=" Preparando sessão",
        stage="session_preparation",
        heartbeat=True,
        elapsed_s=round(max(0.0, elapsed_s), 3),
    )


def _agent_heartbeat_frame(elapsed_s: float) -> str:
    """Frame sanitizado para manter o proxy ativo durante o trabalho do agente."""
    return _frame(
        "status",
        data=" Processando resposta",
        stage="session_agent",
        heartbeat=True,
        elapsed_s=round(max(0.0, elapsed_s), 3),
    )


def _map_exception(exc: Exception) -> tuple[int, str]:  # noqa: PLR0911
    """Mapeia exceptions do LLM para (status_code, detail), igual ao /stream."""
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if not isinstance(detail, str):
            detail = json.dumps(detail, ensure_ascii=False, default=str)
        return exc.status_code, detail
    if isinstance(exc, ArquivoAvulsoProcessingError):
        return 422, str(exc)
    if isinstance(exc, openai.RateLimitError):
        return 429, "Limite de requisições atingido. Tente novamente em instantes."
    if isinstance(exc, (openai.APITimeoutError, httpx.TimeoutException)):
        return 408, "Tempo de resposta excedido."
    if isinstance(exc, openai.BadRequestError):
        return 400, "Requisição rejeitada pelo modelo (conteúdo ou tamanho)."
    if isinstance(exc, openai.InternalServerError):
        return 502, "Erro interno no serviço de LLM. Tente novamente."
    if isinstance(exc, (openai.APIConnectionError, httpx.ConnectError)):
        return 503, "Serviço de LLM indisponível."
    return 500, f"Erro interno: {exc}"


# Failover do reasoning: erro do provedor ANTES do 1º byte do stream
# — a janela de reasoning oculto (dezenas de segundos) é onde os APIError crus
# vêm sendo observados. Quando isso acontece e nada foi transmitido, o agente é
# reconstruído UMA vez com `reasoning_effort="none"` (mesmo modelo/tools/prompt),
# encurtando a janela. `InternalServerError`/`APIConnectionError`/
# `APITimeoutError` já são subclasses de `openai.APIError`.
_REASONING_FAILOVER_ERRORS = (openai.APIError,)
# 4xx determinístico e rate limit: menos reasoning não muda o desfecho (e o rate
# limit tem política de retry própria no proxy) — propaga sem failover.
_REASONING_FAILOVER_EXCLUDE = (
    openai.BadRequestError,
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    openai.NotFoundError,
    openai.UnprocessableEntityError,
    openai.ConflictError,
    openai.RateLimitError,
)


async def _fetch_document(
    id_documento: str, download_ext: bool | None, no_cache: bool
) -> SessionDocumentOutcome:
    """Wrapper cache-aware que classifica conteúdo sem propagar erro ao SSE.

    Usa o mesmo cache Redis de documentos do app. Com ``no_cache=False`` faz
    read-through (cache hit pula a ida ao SEI). Com ``no_cache=True`` apaga o
    registro do Redis (se houver) e busca fresh. ``download_ext`` (do payload)
    governa tanto a rota de extração quanto a chave de cache.

    Import tardio: extração e cache puxam o stack DB/Redis que conecta no import.
    Mantê-lo aqui deixa o módulo do router importável sem banco (testabilidade).
    """
    from sei_ia.data.etl.concatenate_documents import get_doc_from_id_async
    from sei_ia.services.cache import get_cache

    cache = get_cache()
    if no_cache:
        await cache.purge_document(id_documento)  # apaga todas as variantes no Redis
    else:
        cached = await cache.get_document(id_documento, download_ext=download_ext)
        if cached and cached.get("content") is not None:
            formatted_id = str(cached.get("id_documento_formatado") or "").strip()
            content = str(cached["content"])
            return SessionDocumentOutcome(
                content=content,
                formatted_document_number=formatted_id or None,
                formatted_process_number=None,
                status=(
                    ContentStatus.empty("no_text_extracted")
                    if content == ""
                    else ContentStatus.available()
                ),
                source="redis",
            )

    try:
        content, num_doc_formatado, provenance = await get_doc_from_id_async(
            id_documento, download_ext=download_ext
        )
    except HTTPException as exc:
        formatted_id = str(getattr(exc, "formatted_document_number", "") or "").strip()
        formatted_process = str(
            getattr(exc, "formatted_process_number", "") or ""
        ).strip()
        if exc.status_code == 204:
            return SessionDocumentOutcome(
                content="",
                formatted_document_number=formatted_id or None,
                formatted_process_number=formatted_process or None,
                status=ContentStatus.empty("content_doc_empty"),
                source="sei",
            )
        reason = getattr(exc, "content_reason", None)
        if reason not in {
            "binary_not_found",
            "source_not_found",
            "download_failed",
            "extraction_failed",
            "unsupported_format",
            "timeout",
        }:
            if exc.status_code in {408, 411, 412}:
                reason = "timeout"
            elif exc.status_code in {406, 415}:
                reason = "unsupported_format"
            elif exc.status_code == 404:
                reason = (
                    "binary_not_found"
                    if download_ext is True and formatted_id
                    else "source_not_found"
                )
            else:
                reason = "extraction_failed"
        return SessionDocumentOutcome(
            content=None,
            formatted_document_number=formatted_id or None,
            formatted_process_number=formatted_process or None,
            status=ContentStatus.unavailable(reason),
            source="sei",
        )
    except Exception:
        logger.warning(
            "Falha ao buscar conteúdo do documento %s para a sessão",
            id_documento,
            exc_info=True,
        )
        return SessionDocumentOutcome(
            content=None,
            formatted_document_number=None,
            formatted_process_number=None,
            status=ContentStatus.unavailable("download_failed"),
            source="sei",
        )
    formatted_id = str(num_doc_formatado or "").strip()
    formatted_process = str(provenance.get("id_protocolo_formatado") or "").strip()
    if content is None:
        return SessionDocumentOutcome(
            content=None,
            formatted_document_number=formatted_id or None,
            formatted_process_number=formatted_process or None,
            status=ContentStatus.unavailable("extraction_failed"),
            source="sei",
        )
    return SessionDocumentOutcome(
        content=content,
        formatted_document_number=formatted_id or None,
        formatted_process_number=formatted_process or None,
        status=(
            ContentStatus.empty("no_text_extracted")
            if content == ""
            else ContentStatus.available()
        ),
        source="sei",
        provenance=provenance,
    )


async def _fetch_session_document(
    id_documento: str,
    download_ext: bool | None,
    *,
    no_cache: bool,
    pinned_snapshot: Any | None,
) -> SessionDocumentOutcome:
    """Busca no SEI/cache e usa o snapshot somente como validador de bytes."""
    if pinned_snapshot is not None and not no_cache:
        raise BenchmarkEvidenceError("benchmark_no_cache_required")
    outcome = await _fetch_document(id_documento, download_ext, no_cache)
    if pinned_snapshot is not None and outcome.status.state != "unavailable":
        await asyncio.to_thread(
            pinned_snapshot.validate_fresh_document,
            id_documento,
            outcome.content,
            outcome.provenance,
        )
    return outcome


def _extract_doc_specs(
    request: ChatRequest,
) -> list[tuple[str, str, bool | None, bool]]:
    """Especificação de materialização de cada documento do payload.

    A 'árvore' vem no payload (não há endpoint para listá-la). O id_procedimento
    determina a pasta de armazenamento (``proc_{numero}/``).
    """
    specs: list[tuple[str, str, bool | None, bool]] = []
    for proc in request.id_procedimentos or []:
        proc_id = str(getattr(proc, "id_procedimento", "") or "")
        for doc in getattr(proc, "id_documentos", None) or []:
            if hasattr(doc, "id_documento"):
                specs.append(
                    (
                        proc_id,
                        str(doc.id_documento),
                        getattr(doc, "download_ext", None),
                        getattr(doc, "sin_armazena_cache", None) == "N",
                    )
                )
            else:
                specs.append((proc_id, str(doc), None, False))
    return specs


def _parse_raw_metadata(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {"description": raw.strip()}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _extract_proc_metadata(request: ChatRequest) -> dict[str, dict]:
    """``id_procedimento`` → ``metadata`` do payload (o que o frontend mandou).

    ``ItemRequestIdProcedimento.metadata`` é ``dict | str`` (str é legado): strings
    JSON viram dict; strings textuais ficam em ``description`` para preservar o
    número visível do processo; dict passa direto; qualquer outro tipo vira ``{}``.
    Não fabrica campo quando o payload não mandou nada.
    """
    out: dict[str, dict] = {}
    for proc in request.id_procedimentos or []:
        proc_id = str(getattr(proc, "id_procedimento", "") or "")
        if not proc_id:
            continue
        out[proc_id] = _parse_raw_metadata(getattr(proc, "metadata", None))
    return out


async def _fetch_benchmark_process_metadata(
    process_ids: list[str],
) -> dict[str, dict[str, str]]:
    """Rebusca metadados processuais no SEI e falha se algum processo faltar."""
    if not process_ids:
        return {}
    from sei_ia.data.etl.extract.metadata import fetch_procedimentos_metadata_batch

    fetched = await fetch_procedimentos_metadata_batch(process_ids)
    missing = set(process_ids) - set(fetched)
    if missing:
        raise BenchmarkEvidenceError("fresh_process_metadata_missing")
    return {
        process_id: {"description": fetched[process_id], "source": "sei_no_cache"}
        for process_id in process_ids
    }


def _benchmark_fresh_evidence_export(
    session_root: Path, tool_summary: dict[str, Any]
) -> dict[str, Any]:
    """Exporta somente documentos fresh abertos, por hash, no SSE protegido."""
    inventory = {
        str(entry["path_sha256"]): str(entry["content_sha256"])
        for entry in tool_summary.get("document_inventory", [])
        if isinstance(entry, dict)
        and entry.get("path_sha256")
        and entry.get("content_sha256")
    }
    opened = {
        str(reference["path_sha256"])
        for call in tool_summary.get("calls", [])
        if isinstance(call, dict)
        for reference in (call.get("files_opened") or [])
        if isinstance(reference, dict) and reference.get("path_sha256") in inventory
    }
    documents: list[dict[str, Any]] = []
    found: set[str] = set()
    for path in sorted(session_root.rglob("*.txt")):
        relative = path.relative_to(session_root).as_posix()
        path_sha256 = hashlib.sha256(f"/{relative}".encode()).hexdigest()
        if path_sha256 not in opened:
            continue
        raw = path.read_bytes()
        content_sha256 = hashlib.sha256(raw).hexdigest()
        content = raw.decode("utf-8")
        if content_sha256 != inventory[path_sha256]:
            raise BenchmarkEvidenceError("fresh_evidence_export_hash_mismatch")
        found.add(path_sha256)
        documents.append(
            {
                "path_sha256": path_sha256,
                "content_sha256": content_sha256,
                "content": content,
            }
        )
    if found != opened:
        raise BenchmarkEvidenceError("fresh_evidence_export_missing")
    return {
        "schema_version": "benchmark-fresh-opened-evidence-v1",
        "source": "validated_materialized_session",
        "documents": documents,
    }


def _iter_text(content) -> str:
    """Extrai SÓ os blocos de resposta (`type=="text"`/str) de um chunk.

    Blocos de reasoning (``type=="reasoning"``) são ignorados aqui, então o
    conteúdo-resposta e o raciocínio nunca se misturam (o reasoning sai pelo
    frame `reasoning`, não pelo `content`/processador de tags).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


def _extract_reasoning_delta(content) -> str:
    """Delta de reasoning de um chunk da Responses API. Reusa o núcleo do clássico.

    Import tardio: ``chat_workflow`` puxa um stack pesado (azure/websearch/DB) no
    import; carregá-lo aqui mantém o router de sessão importável sem esse stack.
    O núcleo aceita `content` direto, então não há objeto alocado por chunk.
    """
    from sei_ia.services.llm_models.chat_workflow import (
        extract_reasoning_delta_from_content,
    )

    return extract_reasoning_delta_from_content(content)


async def _sync_window_from_history(agent, config, resolved, traced) -> None:
    """Sincroniza a janela do checkpointer com o histórico fresco do SEI.

    A cada request SUBSTITUI as mensagens da thread pelos últimos turnos do JSONL
    (reescrito do SEI em `resolve`), para o agente sempre refletir o histórico atual
    do tópico, inclusive turnos gravados pelo frontend. Sem histórico no SEI, não
    mexe na thread (deixa um tópico novo acumular normalmente). `as_node="model"` é
    exigido pelo `aupdate_state`. Best-effort: falha é logada e não trava o stream.
    """
    try:
        from sei_ia.services.session_fs.history import seed_messages_from_jsonl

        seed = seed_messages_from_jsonl(
            resolved.paths.root / "historico_conversa.jsonl",
            resolved.paths.session_key,
            settings.SESSION_MAX_TURNS,
        )
        if not seed:
            return
        await agent.aupdate_state(
            config,
            {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *seed]},
            as_node="model",
        )
        if traced:
            _trace_logger.info("janela sincronizada com o SEI — %d msgs", len(seed))
    except Exception:  # noqa: BLE001
        logger.warning(
            "Falha ao sincronizar histórico; seguindo sem ele", exc_info=True
        )


async def _clear_window(agent, config, traced) -> None:
    """skip_memory: zera a janela para o agente considerar só o turno atual.

    Remove todo o histórico da thread NESTA iteração (REMOVE_ALL_MESSAGES). O histórico
    segue no SEI/JSONL e volta no próximo request normal (re-sincronizado). Best-effort:
    falha é logada e não trava o stream.
    """
    try:
        await agent.aupdate_state(
            config,
            {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES)]},
            as_node="model",
        )
        if traced:
            _trace_logger.info("histórico ignorado (skip_memory) — janela zerada")
    except Exception:  # noqa: BLE001
        logger.warning("Falha ao zerar janela (skip_memory); seguindo", exc_info=True)


async def _apply_history_policy(agent, config, resolved, skip_memory, traced) -> None:
    """Decide o que fazer com a janela do checkpointer antes do turno.

    ``skip_memory`` → zera (só o turno atual). Senão, com ``SESSION_SEED_HISTORY``,
    sincroniza com o histórico fresco do SEI. Sem nenhum, deixa a thread como está.
    """
    if skip_memory:
        # Nesta iteração não há histórico: zera a janela E remove o JSONL para o
        # agente não alcançá-lo via ls/grep. O próximo request normal o reconstrói.
        try:
            (resolved.paths.root / "historico_conversa.jsonl").unlink(missing_ok=True)
        except OSError:
            logger.warning("Falha ao remover JSONL (skip_memory)", exc_info=True)
        await _clear_window(agent, config, traced)
    elif settings.SESSION_SEED_HISTORY:
        await _sync_window_from_history(agent, config, resolved, traced)


@router.post(
    ENDPOINT_NAME,
    tags=["llm_lang"],
    summary="Endpoint Deep Agents com sessão escopada (streaming SSE)",
    responses=fast_api_responses,
)
async def session_stream(request: SessionStreamRequest, request_starllete: Request):  # noqa: C901, PLR0915  # NOSONAR
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    state_message_id = getattr(request_starllete.state, "id_request", None)
    message_id = state_message_id or request.id_request
    if message_id is None or message_id <= 0:
        raise RuntimeError("Não foi possível resolver um id_message inteiro positivo")

    async def stream_generator():  # noqa: C901, PLR0911, PLR0912, PLR0915  # NOSONAR
        upload_temp_files: set[str] = set()
        upload_removal_ids: set[int] = set()
        event_counts: Counter[str] = Counter()
        fetch_telemetry: dict[str, DocumentFetchTelemetry] = {}
        trace_stage = "session.accept_request"
        trace_mode: str | None = None
        trace_is_new: bool | None = None
        trace_has_unavailable = False
        trace_finished = False
        trace_reasoning_failover = False
        final_response_content: str | None = None
        web_research_state: dict[str, Any] = {}
        langfuse_trace_id = _trace_id_for_request(request_starllete)
        request_starllete.state.trace_id = langfuse_trace_id
        request_id = str(message_id)
        raw_body = getattr(request_starllete.state, "body", None)
        original_body = original_request_body_text(request, raw_body)
        langfuse_text_input = encode_langfuse_json_text(original_body)
        request_summary = build_session_request_summary(
            request,
            endpoint=ENDPOINT_NAME,
            request_id=request_id,
        )
        trace_metadata: dict[str, Any] = {
            "endpoint": ENDPOINT_NAME,
            "environment": settings.ENVIRONMENT,
            "version": str(settings.VERSION),
            "request_id": request_id,
            "input_format": "original_request_body_json_text",
            "redacted_fields": ["ip"],
        }
        root_context = _langfuse_span("session_stream", trace_id=langfuse_trace_id)
        root_span = root_context.__enter__()
        initial_tags = build_session_trace_tags(
            request, environment=settings.ENVIRONMENT
        )
        root_trace_kwargs: dict[str, Any] = {
            "name": "session_stream",
            "user_id": str(request.id_usuario),
            "version": str(settings.VERSION),
            "input": langfuse_text_input,
            "metadata": {
                **trace_metadata,
                "original_request": f"\\{original_body}",
                "original_request_source": (
                    "raw_body"
                    if isinstance(raw_body, bytes | str)
                    else "validated_model_fallback"
                ),
            },
            "tags": initial_tags,
        }
        if request.id_topico is not None:
            root_trace_kwargs["session_id"] = str(request.id_topico)
        _update_langfuse_observation(root_span, input=langfuse_text_input)
        _update_langfuse_trace(root_span, **root_trace_kwargs)

        def emit_frame(frame_type: str, **fields) -> str:
            event_counts[frame_type] += 1
            return _frame(frame_type, **fields)

        def emit_preparation_heartbeat(elapsed_s: float) -> str:
            event_counts["status"] += 1
            return _preparation_heartbeat_frame(elapsed_s)

        def record_error(
            status_code: int,
            detail: str,
            *,
            exception: BaseException | None = None,
            diagnostic: dict[str, Any] | None = None,
        ) -> str:
            nonlocal trace_finished
            event_counts["error"] += 1
            error_output = build_error_trace_output(
                stage=trace_stage,
                status_code=status_code,
                exception=exception,
                response_content=final_response_content,
            )
            error_tags = [
                *build_session_trace_tags(
                    request,
                    environment=settings.ENVIRONMENT,
                    result="error",
                    mode=trace_mode,
                    is_new=trace_is_new,
                    has_unavailable_documents=trace_has_unavailable,
                ),
                f"error:{status_code}",
                *(["reasoning_failover"] if trace_reasoning_failover else []),
            ]
            trace_metadata["last_stage"] = trace_stage
            with _langfuse_span("session.finalize_stream") as error_span:
                _update_langfuse_observation(
                    error_span,
                    input={"stage": trace_stage},
                    output={
                        **error_output,
                        "sse_event_counts": dict(event_counts),
                    },
                    metadata={"stage": "error_finalization"},
                    level="ERROR",
                    status_message=f"HTTP {status_code} em {trace_stage}",
                )
            _update_langfuse_trace(
                root_span,
                output=error_output,
                metadata=trace_metadata,
                tags=error_tags,
            )
            trace_finished = True
            return _error_frame(status_code, detail, diagnostic=diagnostic)

        try:
            with _langfuse_span("session.accept_request") as accept_span:
                _update_langfuse_observation(
                    accept_span,
                    input=request_summary,
                )
                if request.id_topico is None:
                    yield record_error(422, "id_topico é obrigatório neste endpoint.")
                    return
                benchmark_collect = (
                    request_starllete.headers.get("X-Experiment-Collect-Tools") == "1"
                )
                if benchmark_collect and not request.no_cache:
                    yield record_error(422, "benchmark exige no_cache=true")
                    return
                # Override (ChatRequest.model) só vale pro papel principal — os
                # outros profiles (explorador/classificador) ficam nos tiers fixos.
                model_override = getattr(request, "model", None)
                if model_override:
                    try:
                        await validate_model_override(model_override)
                    except ValueError as exc:
                        yield record_error(422, str(exc))
                        return
                model_configs = {
                    profile.lower(): get_model_config(
                        agent_tag=profile,
                        model_override=(
                            model_override
                            if profile == settings.SESSION_MAIN_MODEL
                            else None
                        ),
                    )
                    for profile in (
                        settings.SESSION_MAIN_MODEL,
                        settings.SESSION_EXPLORER_MODEL,
                        settings.SESSION_CLASSIFIER_MODEL,
                    )
                }
                reasoning_effort = getattr(request, "reasoning_effort", None)
                if reasoning_effort:
                    principal_model = model_configs[
                        settings.SESSION_MAIN_MODEL.lower()
                    ]["model"]
                    try:
                        await validate_reasoning_effort(
                            principal_model, reasoning_effort
                        )
                    except ValueError as exc:
                        yield record_error(422, str(exc))
                        return
                model_usage = SessionModelUsageHandler(model_configs)
                trace_metadata["config_models"] = model_usage.config_models
                _update_langfuse_observation(
                    accept_span,
                    output={"accepted": True, "benchmark_collect": benchmark_collect},
                    metadata={"stage": "request_validation"},
                )

            trace_stage = "session.prepare"
            with _langfuse_span("session.prepare") as prepare_span:
                yield emit_frame("status", data=" Preparando sessão")
                if request.arquivos_avulsos:
                    yield emit_frame("status", data=" Processando arquivos anexados")
                user_message = await _prepare_session_user_message(
                    request, upload_temp_files, upload_removal_ids
                )
                _t_coleta = time.perf_counter()
                specs = _extract_doc_specs(request)
                docs = [(proc, doc_id) for proc, doc_id, _, _ in specs]
                doc_ids = [doc_id for _, doc_id, _, _ in specs]
                ext_map = {doc_id: ext for _, doc_id, ext, _ in specs}
                refresh_document_ids = {
                    doc_id for _, doc_id, _, refresh in specs if refresh
                }
                procs = sorted({proc for proc, _, _, _ in specs})
                proc_metadata = _extract_proc_metadata(request)
                _update_langfuse_observation(
                    prepare_span,
                    input={
                        "uploads": len(request.arquivos_avulsos or []),
                        "requested_documents": len(docs),
                    },
                    output={
                        "process_ids": procs,
                        "document_ids": doc_ids,
                        "upload_temp_files": len(upload_temp_files),
                    },
                    metadata={"stage": "request_preparation"},
                )
            # ``trace=true`` liga um logger de debug com args/retornos brutos. No
            # benchmark, a telemetria v2 e o Langfuse substituem esse logger para que
            # nenhum caminho, pattern ou conteúdo apareça em stdout/arquivo.
            traced = (request.trace or settings.SESSION_TRACE) and not benchmark_collect
            preparation_heartbeats = 0
            evidence_preflight: dict[str, Any] | None = None
            pinned_snapshot = None
            if benchmark_collect and settings.SESSION_BENCHMARK_EVIDENCE_INDEX:
                async for event in _run_with_heartbeat(
                    asyncio.to_thread(
                        load_benchmark_evidence_snapshot,
                        settings.SESSION_BENCHMARK_EVIDENCE_INDEX,
                        [
                            (proc, doc_id, ext_map.get(doc_id) is True)
                            for proc, doc_id in docs
                        ],
                    ),
                    interval_s=(
                        settings.SESSION_PREPARATION_HEARTBEAT_INTERVAL_SECONDS
                    ),
                ):
                    if event.completed:
                        pinned_snapshot = event.result
                    else:
                        preparation_heartbeats += 1
                        yield emit_preparation_heartbeat(event.elapsed_s)
                if pinned_snapshot is None:
                    raise RuntimeError("preflight terminou sem snapshot de evidência")
                evidence_preflight = pinned_snapshot.diagnostic
            if benchmark_collect:
                fresh_proc_metadata = None
                async for event in _run_with_heartbeat(
                    _fetch_benchmark_process_metadata(procs),
                    interval_s=(
                        settings.SESSION_PREPARATION_HEARTBEAT_INTERVAL_SECONDS
                    ),
                ):
                    if event.completed:
                        fresh_proc_metadata = event.result
                    else:
                        preparation_heartbeats += 1
                        yield emit_preparation_heartbeat(event.elapsed_s)
                if fresh_proc_metadata is None:
                    raise RuntimeError("preparação processual terminou sem resultado")
                proc_metadata = fresh_proc_metadata

            async def fetch(doc_id: str) -> SessionDocumentOutcome:
                started = time.perf_counter()
                try:
                    outcome = await _fetch_session_document(
                        doc_id,
                        ext_map.get(doc_id),
                        no_cache=(request.no_cache or doc_id in refresh_document_ids),
                        pinned_snapshot=pinned_snapshot,
                    )
                except Exception:
                    fetch_telemetry[doc_id] = DocumentFetchTelemetry(
                        document_id=doc_id,
                        source="unknown",
                        duration_ms=round(
                            max(0.0, (time.perf_counter() - started) * 1000), 3
                        ),
                        status="unavailable",
                        reason="download_failed",
                    )
                    raise
                content = outcome.content or ""
                encoded = content.encode("utf-8")
                fetch_telemetry[doc_id] = DocumentFetchTelemetry(
                    document_id=doc_id,
                    source=outcome.source,
                    duration_ms=round(
                        max(0.0, (time.perf_counter() - started) * 1000), 3
                    ),
                    status=outcome.status.state,
                    reason=outcome.status.reason,
                    bytes=(
                        len(encoded) if outcome.status.state != "unavailable" else None
                    ),
                    content_sha256=hashlib.sha256(encoded).hexdigest()
                    if content and outcome.status.state != "unavailable"
                    else None,
                )
                return outcome

            async def fetch_history():
                # Import tardio: consulta_historico_topico_com_tokens conecta no banco.
                from sei_ia.data.database.sei_client import (
                    consulta_historico_topico_com_tokens,
                )

                return await asyncio.to_thread(
                    consulta_historico_topico_com_tokens, str(request.id_topico)
                )

            manager = await get_session_manager()
            checkpointer = await get_session_checkpointer()

            if traced:
                _trace_logger.info(
                    "🔽 coleta iniciada — processo(s) %s, %d documentos: %s",
                    procs,
                    len(docs),
                    doc_ids,
                )
            resolved = None
            materialization_output: dict[str, Any] = {}
            trace_stage = "session.materialize_documents"
            with _langfuse_span("session.materialize_documents") as materialize_span:
                with collect_ocr_usage() as ocr_usage_records:
                    if docs:
                        yield emit_frame("status", data=" Baixando documentos")
                    async for event in _run_with_heartbeat(
                        manager.resolve(
                            request.id_usuario,
                            request.id_topico,
                            docs=docs,
                            fetch_document=fetch,
                            fetch_history=(
                                fetch_history
                                if settings.SESSION_SEED_HISTORY
                                and not request.skip_memory
                                else None
                            ),
                            reset=request.no_cache,
                            proc_metadata=proc_metadata,
                            strict_materialization=benchmark_collect,
                            refresh_document_ids=refresh_document_ids,
                        ),
                        interval_s=(
                            settings.SESSION_PREPARATION_HEARTBEAT_INTERVAL_SECONDS
                        ),
                    ):
                        if event.completed:
                            resolved = event.result
                        else:
                            preparation_heartbeats += 1
                            yield emit_preparation_heartbeat(event.elapsed_s)
                if resolved is not None:
                    materialization_output = build_materialization_trace_output(
                        resolved, fetch_telemetry
                    )
                    _update_langfuse_observation(
                        materialize_span,
                        input={
                            "requested": [
                                {"process_id": process_id, "document_id": document_id}
                                for process_id, document_id in docs
                            ],
                            "reset": request.no_cache,
                        },
                        output=materialization_output,
                        metadata={"stage": "document_materialization"},
                    )
            if resolved is None:
                raise RuntimeError("preparação terminou sem sessão resolvida")
            if not resolved.is_new:
                materialized_count = len(resolved.materialization.materialized)
                yield emit_frame(
                    "status",
                    data=(
                        " Sessão atualizada"
                        if materialized_count
                        else " Sessão carregada"
                    ),
                )
            trace_is_new = resolved.is_new
            trace_has_unavailable = bool(resolved.materialization.unavailable)
            trace_metadata["materialization"] = {
                "requested": len(resolved.materialization.requested),
                "available": len(materialization_output["available"]),
                "registered": len(resolved.materialization.registered),
                "added": len(resolved.materialization.added),
                "refreshed": len(resolved.materialization.refreshed),
                "materialized": len(resolved.materialization.materialized),
                "reused": len(resolved.materialization.reused),
                "removed_from_manifest": len(
                    resolved.materialization.removed_from_manifest
                ),
                "unavailable": len(resolved.materialization.unavailable),
                "files_pruned": resolved.materialization.files_pruned,
            }
            if pinned_snapshot is not None:
                async for event in _run_with_heartbeat(
                    asyncio.to_thread(
                        pinned_snapshot.validate_materialized,
                        resolved.paths.root,
                    ),
                    interval_s=(
                        settings.SESSION_PREPARATION_HEARTBEAT_INTERVAL_SECONDS
                    ),
                ):
                    if event.completed:
                        evidence_preflight = {
                            **event.result,
                            "runtime_document_source": "sei_no_cache",
                            "snapshot_role": "validation_only",
                        }
                    else:
                        preparation_heartbeats += 1
                        yield emit_preparation_heartbeat(event.elapsed_s)
            preparation_duration_s = max(0.0, time.perf_counter() - _t_coleta)
            if traced:
                _dt = time.perf_counter() - _t_coleta
                _n = len(docs) or 1
                _trace_logger.info(
                    "✅ coleta concluída — %d/%d docs em %.2fs (média %.3fs/doc)",
                    len(resolved.meta.doc_ids),
                    len(docs),
                    _dt,
                    _dt / _n,
                )

            # Decisão de modo (fase 5): calculada UMA vez do sinal de tamanho já
            # acumulado no resolve; override por request só p/ experimentação, senão o
            # knob. Ver session_agent/mode.py.
            threshold = (
                request.inject_tokens_threshold
                if request.inject_tokens_threshold is not None
                else settings.SESSION_INJECT_TOKENS_THRESHOLD
            )
            trace_stage = "session.decide_mode"
            with _langfuse_span("session.decide_mode") as mode_span:
                mode_decision = decide_mode(
                    resolved.total_content_tokens,
                    threshold,
                    request.mode,
                )
                trace_mode = mode_decision.mode
                _update_langfuse_observation(
                    mode_span,
                    input={
                        "total_content_tokens": resolved.total_content_tokens,
                        "threshold": threshold,
                    },
                    output={
                        "mode": mode_decision.mode,
                        "total_content_tokens": mode_decision.total_content_tokens,
                        "threshold": mode_decision.threshold,
                        **(
                            {"mode_override": request.mode}
                            if request.mode is not None
                            else {}
                        ),
                    },
                    metadata={"stage": "mode_decision"},
                )
            if traced:
                _trace_logger.info(
                    "🧭 modo=%s (conteúdo=%d tok, threshold=%d)",
                    mode_decision.mode,
                    mode_decision.total_content_tokens,
                    mode_decision.threshold,
                )

            # Complexidade calibra a PROFUNDIDADE. No filesystem, orienta a exploração
            # de docs (fase 2). No injetado puro ela é inerte (compose_system_prompt
            # descarta a diretiva) e seria chamada mini inútil — pulamos (fase 7). MAS,
            # com WEBSEARCH ligada, ela volta com propósito: orienta a profundidade da
            # busca web (nº de buscas + páginas + diretiva) — easy=raso, high=explora
            # (fase 8, frente 3). Por isso classificamos quando filesystem OU web ativa.
            #
            # Com web ativa, o classify (profundidade) e o planejador mini de pontos
            # especulativos rodam em PARALELO. Ambos têm fallback interno (não
            # levantam), então o gather é seguro.
            use_websearch = bool(getattr(request, "use_websearch", False))
            web_active = use_websearch and settings.SESSION_WEB_TOOL == "web_research"
            langfuse_callback = (
                SessionLangfuseCallback() if settings.USE_LANGFUSE else None
            )
            preflight_callbacks = [model_usage]
            if langfuse_callback:
                preflight_callbacks.append(langfuse_callback)
            speculative_queries: list[str] = []
            if mode_decision.mode == "filesystem" or use_websearch:
                if web_active:
                    with _langfuse_span("session_web_preflight") as preflight_span:
                        complexity, speculative_queries = await asyncio.gather(
                            classify_complexity(
                                request.text,
                                len(doc_ids),
                                callbacks=preflight_callbacks,
                            ),
                            plan_speculative_web_queries(
                                request.text,
                                build_doc_hint(resolved),
                                max_queries=min(
                                    settings.SESSION_WEBRESEARCH_SPECULATIVE_MAX_QUERIES,
                                    settings.SESSION_WEBRESEARCH_MAX_CALLS,
                                ),
                                callbacks=preflight_callbacks,
                            ),
                        )
                        _update_langfuse_observation(
                            preflight_span,
                            input={
                                "user_request": request.text,
                                "documents": len(doc_ids),
                            },
                            output={
                                "complexity": complexity,
                                "speculative_queries": speculative_queries,
                            },
                            metadata={
                                "stage": "web_preflight",
                                "parallel": True,
                                "mini_tasks": [
                                    "classify_complexity",
                                    "plan_speculative_web_queries",
                                ],
                                "searches_started": len(speculative_queries),
                            },
                        )
                    if traced:
                        _trace_logger.info(
                            "🔮 buscas especulativas: queries=%r", speculative_queries
                        )
                else:
                    with _langfuse_span("session_complexity") as complexity_span:
                        complexity = await classify_complexity(
                            request.text,
                            len(doc_ids),
                            callbacks=preflight_callbacks,
                        )
                        _update_langfuse_observation(
                            complexity_span,
                            input={
                                "user_request": request.text,
                                "documents": len(doc_ids),
                            },
                            output={"complexity": complexity},
                            metadata={"stage": "complexity_classification"},
                        )
            else:
                complexity = "medium"
                yield emit_frame("status", data=" Modo: leitura direta dos documentos")

            # Modo injetado (fase 6): o bloco completo dos documentos vai no system
            # prompt e o agente sobe sem explorador. Montado dos arquivos que o
            # resolve acabou de materializar (locais e pequenos por construção do
            # threshold). A escrita no disco continua igual — a injeção é adicional.
            injected_context = (
                build_injected_context(resolved)
                if mode_decision.mode == "injected"
                else None
            )

            session_agent_kwargs: dict[str, Any] = {
                "checkpointer": checkpointer,
                "resolved": resolved,
                "complexity": complexity,
                "use_websearch": use_websearch,
                "max_turns": settings.SESSION_MAX_TURNS,
                "long_topic": resolved.history_turns > settings.SESSION_MAX_TURNS,
                "use_thinking": bool(getattr(request, "use_thinking", False)),
                "mode": mode_decision.mode,
                "injected_context": injected_context,
                "speculative_queries": speculative_queries,
                "web_question": request.text,
                "evidence_gate_callbacks": preflight_callbacks,
                "unavailable_document_ids": resolved.materialization.unavailable,
                "web_research_state": web_research_state,
                "model_override": model_override,
                "reasoning_effort": getattr(request, "reasoning_effort", None),
            }
            agent = build_session_agent(resolved.paths.root, **session_agent_kwargs)
            config = {
                "configurable": {"thread_id": resolved.paths.session_key},
                "metadata": {
                    "langfuse_session_id": str(request.id_topico),
                    "langfuse_user_id": str(request.id_usuario),
                },
            }
            # Status sempre-ligado (frame `status` por etapa). Trace é opcional (debug).
            callbacks = [SessionStatusHandler(), model_usage]
            benchmark_tools = None
            if benchmark_collect:
                document_entries = [
                    entry
                    for entry in resolved.meta.documentos.values()
                    if isinstance(entry, dict) and entry.get("arquivo")
                ]
                document_inventory = []
                for entry in document_entries:
                    raw = (resolved.paths.root / str(entry["arquivo"])).read_bytes()
                    document_inventory.append(
                        {
                            "path": str(entry["arquivo"]),
                            "content_sha256": hashlib.sha256(raw).hexdigest(),
                            "bytes": len(raw),
                            "tokens": int(entry.get("tokens", 0) or 0),
                        }
                    )
                benchmark_tools = BenchmarkToolHandler(
                    document_paths=[
                        str(entry["arquivo"]) for entry in document_entries
                    ],
                    document_inventory=document_inventory,
                )
            if benchmark_tools is not None:
                callbacks.append(benchmark_tools)
            if traced:
                callbacks.append(SessionTraceHandler())
            # Observabilidade Langfuse: o CallbackHandler captura a arvore inteira do
            # deepagents (agente principal, subagentes, deep_research) com token usage.
            # O mesmo callback já foi usado no pré-processamento web. Isso mantém
            # classify/planner mini e o agente principal no mesmo trace e evita
            # subcontabilizar o custo da busca web.
            if langfuse_callback:
                callbacks.append(langfuse_callback)
            config["callbacks"] = callbacks

            await _apply_history_policy(
                agent, config, resolved, request.skip_memory, traced
            )

            if request.use_thinking:
                yield emit_frame("status", data=" Pensando")

            # Processador de fontes: documentos SEI usam <doc_ID></doc_ID>, enquanto
            # arquivos enviados usam <upload_ID></upload_ID>. Os namespaces separados
            # evitam colisão quando os IDs técnicos coincidirem. O processador só recebe
            # uploads materializados neste turno; fontes de uploads indisponíveis são
            # descartadas sem consumir numeração.
            id_to_formatted_map = {
                doc_id: formatted_id
                for doc_id, entry in resolved.meta.documentos.items()
                if (
                    formatted_id := str(
                        entry.get("id_documento_formatado") or ""
                    ).strip()
                )
            }
            upload_id_to_filename_map = {
                str(upload.id_arquivo_avulso): upload.nome_arquivo_avulso
                for upload in request.arquivos_avulsos or []
                if upload.id_arquivo_avulso in upload_removal_ids
            }
            source_processor = StreamTagProcessorFinal(
                {
                    "id_to_formatted_map": id_to_formatted_map,
                    "upload_id_to_filename_map": upload_id_to_filename_map,
                    "rag_documents_count": len(resolved.meta.documentos),
                }
            )

            # Stream multi-modo: `messages` (tokens do LLM, 2-tupla (token, meta))
            # e `custom` (dicts `{"_status": ...}` do SessionStatusHandler). Com
            # lista, cada item do astream é `(mode, payload)`. O helper mantém o
            # `__anext__` pendente vivo quando o upstream demora, permitindo emitir
            # heartbeat sem cancelar a execução do agente.
            #
            # Reasoning só do agente PRINCIPAL: chunks de subagente teriam
            # checkpoint_ns com 2+ segmentos (separados por '|'); o principal tem
            # <=1 (helper `is_principal`, regra compartilhada com trace._caller).
            # Verificado em runtime
            # (2026-07-07, deepagents 0.6.10): NENHUM chunk de subagente chega a
            # este astream — o `task` roda o explorador via ainvoke dentro da
            # tool, fora do tap de messages do grafo pai. O gate fica como defesa
            # contra mudança de comportamento em bump do deepagents.
            current_status: str | None = None  # só para dedup de status
            saw_tool_status = False  # já houve etapa de tool? (para "Sintetizando")
            announced_synth = False
            response_parts: list[str] = []
            agent_input = {"messages": [user_message]}

            # O CallbackHandler anexa a árvore automática de deepagents a este span
            # sem substituir a entrada semântica do trace raiz.
            trace_stage = "session.agent"
            with _langfuse_span("session.agent") as span:
                _update_langfuse_observation(span, input=agent_input)
                trace_metadata.update(
                    {
                        "session_key": resolved.paths.session_key,
                        "is_new_session": resolved.is_new,
                        "complexity": complexity,
                        "mode_decision": {
                            "mode": mode_decision.mode,
                            "total_content_tokens": mode_decision.total_content_tokens,
                            "threshold": mode_decision.threshold,
                        },
                        "benchmark_evidence_preflight": evidence_preflight,
                    }
                )
                _update_langfuse_trace(
                    span,
                    metadata=trace_metadata,
                )
                # Failover do reasoning: se o provedor estoura ANTES
                # de qualquer frame `content`/`reasoning` (janela de reasoning
                # oculto), reconstrói o agente UMA vez com `reasoning_effort=
                # "none"` e refaz o turno. `_clear_window`+`_apply_history_policy`
                # zeram qualquer estado parcial que a 1ª tentativa tenha
                # commitado no checkpointer antes de reprocessar.
                failover_used = False
                while True:
                    try:
                        agent_stream = agent.astream(
                            agent_input,
                            config=config,
                            stream_mode=["messages", "custom"],
                        )
                        async for stream_event in _stream_events_with_heartbeat(
                            agent_stream,
                            interval_s=settings.SESSION_AGENT_HEARTBEAT_INTERVAL_SECONDS,
                        ):
                            if stream_event.heartbeat:
                                event_counts["status"] += 1
                                yield _agent_heartbeat_frame(stream_event.elapsed_s)
                                continue

                            mode, payload = stream_event.result
                            if mode == "custom":
                                if isinstance(payload, dict) and payload.get("_status"):
                                    status_value = payload["_status"]
                                    saw_tool_status = True
                                    if status_value != current_status:  # dedup
                                        current_status = status_value
                                        yield emit_frame("status", data=status_value)
                                continue

                            # mode == "messages": payload é (token, metadata)
                            chunk, meta = payload
                            if not isinstance(chunk, (AIMessageChunk, AIMessage)):
                                continue

                            meta = meta or {}
                            ns = (
                                meta.get("langgraph_checkpoint_ns")
                                or meta.get("checkpoint_ns")
                                or ""
                            )
                            # Principal = agente principal: profundidade de ns <= 1 E NÃO
                            # o nó de execução de ferramenta (`tools`). As LLM internas
                            # das tools (ex.: o deep_research classifica o modo e extrai
                            # entidades em JSON) rodam no nó `tools` com ns raso
                            # (`tools:<uuid>`), então passariam pelo teste de profundidade
                            # e vazariam seu JSON interno para reasoning/content. Só o
                            # principal (nó `model`) emite resposta; tool interna nunca.
                            is_principal = (
                                meta.get("langgraph_node") != "tools"
                                and len([s for s in ns.split("|") if s]) <= 1
                            )

                            content = getattr(chunk, "content", None)
                            # Reasoning só do principal; nunca vai pro processador de tags.
                            if is_principal and request.use_thinking:
                                reasoning_text = _extract_reasoning_delta(content)
                                if reasoning_text:
                                    yield emit_frame("reasoning", data=reasoning_text)

                            # Conteúdo-resposta (só blocos `text`/str do PRINCIPAL;
                            # reasoning fica de fora). Só o agente principal emite
                            # `content` — tokens de LLM internas de tools/subagentes
                            # (ex.: o `deep_research` streama seu JSON interno de
                            # modo/entidades) NÃO podem vazar para a resposta.
                            text = _iter_text(content) if is_principal else ""
                            if text:
                                if saw_tool_status and not announced_synth:
                                    announced_synth = True
                                    current_status = " Sintetizando resposta"
                                    yield emit_frame("status", data=current_status)
                                processed = source_processor.process_token(text)
                                if processed:
                                    response_parts.append(processed)
                                    yield emit_frame("content", data=processed)

                        tail = source_processor.flush()
                        if tail:
                            response_parts.append(tail)
                            yield emit_frame("content", data=tail)
                        break
                    except _REASONING_FAILOVER_ERRORS as exc:
                        streamed_anything = (
                            bool(response_parts)
                            or event_counts["content"]
                            or event_counts["reasoning"]
                        )
                        if (
                            failover_used
                            or streamed_anything
                            or benchmark_collect
                            or isinstance(exc, _REASONING_FAILOVER_EXCLUDE)
                        ):
                            raise
                        failover_used = True
                        trace_reasoning_failover = True
                        trace_metadata["reasoning_failover"] = True
                        logger.warning(
                            "session_stream: failover de reasoning (effort=none) após "
                            "%s do provedor [trace_id=%s]",
                            type(exc).__name__,
                            langfuse_trace_id,
                        )
                        yield emit_frame(
                            "status",
                            data=" Reprocessando sem raciocínio estendido",
                            stage="session_agent",
                            reasoning_failover=True,
                        )
                        agent = build_session_agent(
                            resolved.paths.root,
                            **{**session_agent_kwargs, "reasoning_effort": "none"},
                        )
                        source_processor = StreamTagProcessorFinal(
                            {
                                "id_to_formatted_map": id_to_formatted_map,
                                "upload_id_to_filename_map": upload_id_to_filename_map,
                                "rag_documents_count": len(resolved.meta.documentos),
                            }
                        )
                        current_status = None
                        saw_tool_status = False
                        announced_synth = False
                        await _clear_window(agent, config, traced)
                        await _apply_history_policy(
                            agent, config, resolved, request.skip_memory, traced
                        )

                final_response_content = "".join(response_parts)
                final_output = {"content": final_response_content}
                trace_metadata.update(
                    {
                        "usage_schema_version": "session-model-usage-v2",
                        "iteration_usage": model_usage.iteration_usage,
                        "model_usage": model_usage.model_usage,
                        "ocr_usage": aggregate_ocr_usage(ocr_usage_records),
                        "cache_percent_formula": (
                            "input_cache_read_tokens / input_total_tokens * 100"
                        ),
                    }
                )
                _update_langfuse_observation(
                    span,
                    output=final_output,
                )

            if web_research_state.get("searched"):
                resolved_websearch = _websearch_manifest(
                    resolved.meta.websearch,
                    web_research_state,
                    final_response_content,
                )
                manager.persist_websearch(resolved, resolved_websearch)
                trace_metadata["websearch"] = {
                    "searched": True,
                    "path": resolved_websearch["path"],
                    "latest_response_sources": resolved_websearch[
                        "latest_response_sources"
                    ],
                    "other_sources_count": len(resolved_websearch["other_sources"]),
                }

            trace_stage = "session.finalize_stream"
            indisponiveis = [d for d in doc_ids if d not in resolved.meta.doc_ids]
            # CONTRATO com o frontend: o frame `metadata` é o gatilho de finalização
            # da mensagem e o front lê as MESMAS chaves que o /llm_lang/stream emite
            # (ModelResponseWithMetadata.to_dict — id_message, usage, flags doc_*,
            # all_tokens_counter, intent...). Emitir shape diferente quebra o front na
            # finalização (bug visto em homologação: chunks ok, erro ao concluir).
            # Superset: contrato do clássico preenchido com o que o session tem +
            # campos próprios do session (chaves adicionais são ignoradas pelo front).
            _model_cfg = get_model_config(
                agent_tag=settings.SESSION_MAIN_MODEL,
                model_override=model_override,
            )
            metadata_data = {
                # --- chaves do contrato do clássico ---
                "id": f"chatcmpl-{_model_cfg['model_name']}",
                "id_message": message_id,
                "created": datetime.now().isoformat(),  # noqa: DTZ005
                # usage por modelo vive no trace (Langfuse); aqui não medimos por
                # request — zeros explícitos, não números inventados.
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                "use_websearch": bool(getattr(request, "use_websearch", False)),
                "use_thinking": bool(getattr(request, "use_thinking", False)),
                "doc_paged": False,
                "doc_summarized": False,
                "doc_rag": False,
                "doc_false_rag": False,
                "all_tokens_counter": mode_decision.total_content_tokens,
                "intent": None,
                "rag_method": None,
                "rag_documents_count": len(resolved.meta.doc_ids),
                "rag_chunks_count": None,
                # --- chaves próprias do session (observabilidade/harness) ---
                "session_key": resolved.paths.session_key,
                "is_new_session": resolved.is_new,
                "complexity": complexity,
                "no_cache": request.no_cache,
                "benchmark_no_cache_required": benchmark_collect,
                "benchmark_session_reset": (
                    benchmark_collect and request.no_cache and resolved.is_new
                ),
                "benchmark_process_source": (
                    "sei_no_cache" if benchmark_collect else "request_payload"
                ),
                "documentos": len(resolved.meta.doc_ids),
                "documentos_indisponiveis": indisponiveis,
                "preparation_duration_s": preparation_duration_s,
                "preparation_heartbeat_count": preparation_heartbeats,
                "benchmark_evidence_preflight": evidence_preflight,
            }
            if benchmark_collect:
                metadata_data["benchmark_ocr_usage"] = ocr_usage_records
            if benchmark_tools is not None:
                benchmark_summary = benchmark_tools.summary()
                metadata_data["benchmark_metrics"] = benchmark_summary
                if pinned_snapshot is not None:
                    metadata_data["benchmark_fresh_evidence"] = (
                        _benchmark_fresh_evidence_export(
                            resolved.paths.root, benchmark_summary
                        )
                    )

            # Só libera a remoção no SEI depois que o agente e a montagem da resposta
            # final concluíram. Em erro/cancelamento antes daqui, o upload-fonte fica
            # disponível para retry (respeitado o TTL externo do SEI).
            if request.arquivos_avulsos:
                await _remove_arquivos_avulsos_no_sei(
                    request.arquivos_avulsos,
                    eligible_ids=upload_removal_ids,
                )

            metadata_sent = False
            end_sent = False
            with _langfuse_span("session.finalize_stream") as final_span:
                metadata_sent = True
                yield emit_frame("metadata", data=metadata_data)
                end_sent = True
                yield emit_frame("end", data="Stream completed")
                response_content = final_output["content"]
                finalization_output = build_finalization_trace_output(
                    content=response_content,
                    event_counts=event_counts,
                    metadata_sent=metadata_sent,
                    end_sent=end_sent,
                )
                _update_langfuse_observation(
                    final_span,
                    input={
                        "response_chars": len(response_content),
                        "uploads_released": len(request.arquivos_avulsos or []),
                    },
                    output=finalization_output,
                    metadata={"stage": "stream_finalization"},
                )
                success_tags = build_session_trace_tags(
                    request,
                    environment=settings.ENVIRONMENT,
                    result="success",
                    mode=trace_mode,
                    is_new=trace_is_new,
                    has_unavailable_documents=trace_has_unavailable,
                )
                if trace_reasoning_failover:
                    success_tags = [*success_tags, "reasoning_failover"]
                trace_metadata["last_stage"] = trace_stage
                _update_langfuse_trace(
                    root_span,
                    output=finalization_output,
                    metadata=trace_metadata,
                    tags=success_tags,
                )
                trace_finished = True

        except (BenchmarkEvidenceError, SessionDocumentMaterializationError) as exc:
            logger.warning(
                f"Benchmark evidence preflight recusou o request "
                f"[trace_id={langfuse_trace_id}]"
            )
            yield record_error(
                409,
                str(exc),
                exception=exc,
                diagnostic=exc.diagnostic,
            )
        except (
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.BadRequestError,
            openai.InternalServerError,
            openai.APIConnectionError,
            httpx.TimeoutException,
            httpx.ConnectError,
        ) as exc:
            logger.exception(
                f"Erro de LLM no session_stream [trace_id={langfuse_trace_id}]"
            )
            status_code, detail = _map_exception(exc)
            yield record_error(status_code, detail, exception=exc)
        except HTTPException as exc:
            upload_temp_files.update(getattr(exc, "cleanup_paths", set()))
            logger.exception(
                f"Erro de upload no session_stream [trace_id={langfuse_trace_id}]"
            )
            status_code, detail = _map_exception(exc)
            yield record_error(status_code, detail, exception=exc)
        except ArquivoAvulsoProcessingError as exc:
            upload_temp_files.update(getattr(exc, "cleanup_paths", set()))
            logger.exception(
                f"Erro de upload no session_stream [trace_id={langfuse_trace_id}]"
            )
            status_code, detail = _map_exception(exc)
            yield record_error(status_code, detail, exception=exc)
        except asyncio.CancelledError:
            _update_langfuse_trace(
                root_span,
                output=with_response_summary(
                    {
                        "result": "cancelled",
                        "stage": trace_stage,
                        "status_code": 499,
                    },
                    final_response_content,
                ),
                metadata={**trace_metadata, "last_stage": trace_stage},
                tags=[
                    *build_session_trace_tags(
                        request,
                        environment=settings.ENVIRONMENT,
                        result="cancelled",
                        mode=trace_mode,
                        is_new=trace_is_new,
                        has_unavailable_documents=trace_has_unavailable,
                    ),
                    "error:499",
                ],
            )
            trace_finished = True
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                f"Erro não tratado no session_stream [trace_id={langfuse_trace_id}]"
            )
            status_code, detail = _map_exception(exc)
            yield record_error(status_code, detail, exception=exc)
        finally:
            if not trace_finished:
                _update_langfuse_trace(
                    root_span,
                    output=with_response_summary(
                        {"result": "interrupted", "stage": trace_stage},
                        final_response_content,
                    ),
                    metadata={**trace_metadata, "last_stage": trace_stage},
                    tags=build_session_trace_tags(
                        request,
                        environment=settings.ENVIRONMENT,
                        result="interrupted",
                        mode=trace_mode,
                        is_new=trace_is_new,
                        has_unavailable_documents=trace_has_unavailable,
                    ),
                )
            cleanup_arquivos_avulsos_temp_files(upload_temp_files)
            root_context.__exit__(None, None, None)
            _flush_langfuse()

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


def _websearch_manifest(
    previous: dict[str, Any], state: dict[str, Any], response: str
) -> dict[str, Any]:
    """Reconcileia referências web do turno com o histórico compacto da sessão."""
    if not state.get("searched"):
        return previous

    latest_sources = list(state.get("latest_sources") or [])
    used_sources = [
        source
        for source in latest_sources
        if (
            (source.get("url") and source["url"] in response)
            or (source.get("path") and source["path"] in response)
        )
    ]

    def unique(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        seen: set[str] = set()
        for source in sources:
            url = str(source.get("url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            result.append(
                {
                    "url": url,
                    "title": str(source.get("title") or ""),
                    "path": source.get("path"),
                }
            )
        return result

    used_sources = unique(used_sources)
    consulted = unique(
        [
            *(previous.get("latest_response_sources") or []),
            *(previous.get("other_sources") or []),
            *latest_sources,
        ]
    )
    used_urls = {source["url"] for source in used_sources}
    return {
        "searched": True,
        "path": "web/",
        "latest_response_sources": used_sources,
        "other_sources": [
            source for source in consulted if source["url"] not in used_urls
        ],
    }
