"""Router /llm_lang/session_stream: registro da rota + helpers de frame/erro."""

import asyncio
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, create_autospec, patch, sentinel

import httpx
import openai
import pandas as pd
import pytest
from fastapi import HTTPException, Request
from langchain_core.messages import AIMessageChunk

from sei_ia.data.content_status import ContentStatus
from sei_ia.data.database.sei_client import SeiDBAPIError
from sei_ia.data.etl.extract.metadata import fetch_procedimentos_metadata_batch
from sei_ia.data.etl.extract.uploads import ArquivoAvulsoProcessingError
from sei_ia.routers.session import router as pkg_router
from sei_ia.routers.session.benchmark import (
    BENCHMARK_LIVE_PREFLIGHT_ENDPOINT,
    BENCHMARK_PREFLIGHT_ENDPOINT,
    session_benchmark_live_preflight,
    session_benchmark_preflight,
)
from sei_ia.routers.session.stream import (
    ENDPOINT_NAME,
    SessionStreamRequest,
    _agent_heartbeat_frame,
    _error_frame,
    _extract_doc_specs,
    _fetch_benchmark_process_metadata,
    _fetch_document,
    _fetch_session_document,
    _frame,
    _iter_text,
    _map_exception,
    _prepare_session_user_message,
    _stream_events_with_heartbeat,
    _trace_id_for_request,
    router as stream_router,
    session_stream,
)
from sei_ia.services.session_fs.benchmark_evidence import BenchmarkEvidenceError
from sei_ia.services.session_fs.manager import (
    SessionDocumentOutcome,
    SessionMaterialization,
)


def test_rota_registrada_e_reexportada():
    assert ENDPOINT_NAME == "/llm_lang/session_stream"
    assert pkg_router is not stream_router
    assert ENDPOINT_NAME in [r.path for r in pkg_router.routes]


@pytest.mark.parametrize(
    "supplied_trace_id",
    ["not-hex", "a" * 31, "A" * 32, "g" * 32],
)
def test_trace_id_invalido_e_substituido(monkeypatch, supplied_trace_id):
    import sei_ia.routers.session.stream as stream_module

    generated = "f" * 32
    monkeypatch.setattr(stream_module, "_new_trace_id", lambda: generated)
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-langfuse-trace-id", supplied_trace_id.encode("ascii"))],
        }
    )

    assert _trace_id_for_request(request) == generated


def test_trace_id_hexadecimal_minusculo_e_preservado(monkeypatch):
    import sei_ia.routers.session.stream as stream_module

    supplied = "0123456789abcdef0123456789abcdef"
    new_trace_id = MagicMock(return_value="f" * 32)
    monkeypatch.setattr(stream_module, "_new_trace_id", new_trace_id)
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-langfuse-trace-id", supplied.encode("ascii"))],
        }
    )

    assert _trace_id_for_request(request) == supplied
    new_trace_id.assert_not_called()


def test_documento_com_cache_n_e_marcado_para_refresh():
    request = SessionStreamRequest(
        id_usuario=1,
        id_topico=2,
        text="analise",
        id_procedimentos=[
            {
                "id_procedimento": "PROC-1",
                "id_documentos": [
                    {"id_documento": "DOC-1", "sin_armazena_cache": "N"},
                    {"id_documento": "DOC-2", "sin_armazena_cache": "S"},
                ],
            }
        ],
    )

    assert _extract_doc_specs(request) == [
        ("PROC-1", "DOC-1", None, True),
        ("PROC-1", "DOC-2", None, False),
    ]


def test_cliente_sei_usa_budget_de_retry_separado_do_llm():
    import sei_ia.data.database.sei_client as client_module

    assert (
        client_module.sei_client.config.max_retries
        == client_module.settings.SEI_API_MAX_RETRIES
    )


def test_preflight_benchmark_sem_corpus_expoe_apenas_configuracao_segura(monkeypatch):
    import sei_ia.routers.session.benchmark as benchmark_module

    monkeypatch.setattr(benchmark_module.settings, "MAX_RETRIES", 7)
    monkeypatch.setattr(benchmark_module.settings, "CTX_LEN_MINI_MODEL", 500000)
    monkeypatch.setattr(benchmark_module.settings, "CTX_LEN_NANO_MODEL", 500000)
    assert BENCHMARK_PREFLIGHT_ENDPOINT in [route.path for route in pkg_router.routes]
    assert session_benchmark_preflight() == {
        "status": "ready",
        "endpoint": ENDPOINT_NAME,
        "context_disclosure_threshold": 200000,
        "session_main_model_profile": "principal",
        "session_main_model": "standard",
        "session_main_model_context_window_tokens": 1000000,
        "session_main_model_client_retries": 7,
        "session_reasoning_effort_requested": "low",
        "session_classifier_model_profile": "classificador",
        "session_classifier_model": "mini",
        "session_classifier_model_context_window_tokens": 500000,
        "session_explorer_model_profile": "explorador",
        "session_explorer_model": "nano",
        "session_explorer_model_context_window_tokens": 500000,
        "session_ocr_model": "nano",
        "benchmark_no_cache_required": True,
        "benchmark_document_source": "sei_no_cache_with_pinned_validation",
        "benchmark_process_source": "sei_no_cache",
        "tool_telemetry_schema": "benchmark-tool-telemetry-v2",
        "preparation_heartbeat_interval_s": 30.0,
        "benchmark_evidence_pin_enabled": False,
        "benchmark_evidence_design": None,
    }


@pytest.mark.asyncio
async def test_live_preflight_uses_effective_container_client_and_returns_only_hashes(
    monkeypatch,
):
    import sei_ia.data.database.sei_client as client_module
    import sei_ia.routers.session.benchmark as benchmark_module

    query = AsyncMock(return_value=pd.DataFrame([{"id_procedimento": "proc-1"}]))
    monkeypatch.setattr(
        benchmark_module.settings,
        "SESSION_BENCHMARK_EVIDENCE_INDEX",
        "/pinned/index.json",
    )
    monkeypatch.setattr(
        benchmark_module.settings, "SEI_ADDRESS", "https://sei.example.test"
    )
    monkeypatch.setattr(
        benchmark_module.settings,
        "SEI_API_DB_ADDRESS",
        "https://sei.example.test/sei/controlador_ws.php",
    )
    monkeypatch.setattr(
        benchmark_module.settings, "SEI_API_DB_IDENTIFIER_SERVICE", "secret"
    )
    monkeypatch.setattr(
        client_module.sei_client, "md_ia_consulta_processo_async", query
    )

    result = await session_benchmark_live_preflight("proc-1")

    assert BENCHMARK_LIVE_PREFLIGHT_ENDPOINT in [
        route.path for route in pkg_router.routes
    ]
    assert result["status"] == "passed"
    assert result["live_query_performed"] is True
    assert result["response_type"] == "dataframe"
    assert result["response_nonempty"] is True
    assert result["process_matched"] is True
    assert result["public_api_scope_coherent"] is True
    assert result["credential_present"] is True
    assert result["duration_s"] >= 0
    assert all(
        "example" not in str(value) and "secret" not in str(value)
        for value in result.values()
    )
    query.assert_awaited_once_with("proc-1")


@pytest.mark.asyncio
async def test_live_preflight_propagates_sanitized_401(monkeypatch):
    from sei_api import SeiApiError

    import sei_ia.data.database.sei_client as client_module
    import sei_ia.routers.session.benchmark as benchmark_module

    query = AsyncMock(side_effect=SeiApiError(401, "unauthorized"))
    monkeypatch.setattr(
        benchmark_module.settings,
        "SESSION_BENCHMARK_EVIDENCE_INDEX",
        "/pinned/index.json",
    )
    monkeypatch.setattr(
        benchmark_module.settings, "SEI_ADDRESS", "https://sei.example.test"
    )
    monkeypatch.setattr(
        benchmark_module.settings,
        "SEI_API_DB_ADDRESS",
        "https://sei.example.test/sei/controlador_ws.php",
    )
    monkeypatch.setattr(
        client_module.sei_client, "md_ia_consulta_processo_async", query
    )

    with pytest.raises(HTTPException, match="recusado") as exc_info:
        await session_benchmark_live_preflight("proc-1")

    assert exc_info.value.status_code == 401
    assert "unauthorized" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_live_preflight_rejects_empty_response(monkeypatch):
    import sei_ia.data.database.sei_client as client_module
    import sei_ia.routers.session.benchmark as benchmark_module

    query = AsyncMock(return_value=pd.DataFrame(columns=["id_procedimento"]))
    monkeypatch.setattr(
        benchmark_module.settings,
        "SESSION_BENCHMARK_EVIDENCE_INDEX",
        "/pinned/index.json",
    )
    monkeypatch.setattr(
        benchmark_module.settings, "SEI_ADDRESS", "https://sei.example.test"
    )
    monkeypatch.setattr(
        benchmark_module.settings,
        "SEI_API_DB_ADDRESS",
        "https://sei.example.test/sei/controlador_ws.php",
    )
    monkeypatch.setattr(
        client_module.sei_client, "md_ia_consulta_processo_async", query
    )

    with pytest.raises(HTTPException, match="vazia") as exc_info:
        await session_benchmark_live_preflight("proc-1")

    assert exc_info.value.status_code == 424


@pytest.mark.asyncio
async def test_live_preflight_rejects_crossed_hosts_before_sei_request(monkeypatch):
    import sei_ia.data.database.sei_client as client_module
    import sei_ia.routers.session.benchmark as benchmark_module

    query = AsyncMock()
    monkeypatch.setattr(
        benchmark_module.settings,
        "SESSION_BENCHMARK_EVIDENCE_INDEX",
        "/pinned/index.json",
    )
    monkeypatch.setattr(
        benchmark_module.settings, "SEI_ADDRESS", "https://prod.example.test"
    )
    monkeypatch.setattr(
        benchmark_module.settings,
        "SEI_API_DB_ADDRESS",
        "https://staging.example.test/sei/controlador_ws.php",
    )
    monkeypatch.setattr(
        client_module.sei_client, "md_ia_consulta_processo_async", query
    )

    with pytest.raises(HTTPException, match="divergente") as exc_info:
        await session_benchmark_live_preflight("proc-1")

    assert exc_info.value.status_code == 409
    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_slow_preparation_yields_sanitized_heartbeat_before_completion():
    import sei_ia.routers.session.stream as stream_module

    release = asyncio.Event()

    async def slow_preparation():
        await release.wait()
        return sentinel.resolved

    events = stream_module._run_with_heartbeat(slow_preparation(), interval_s=0.001)
    heartbeat = await anext(events)

    assert heartbeat.completed is False
    assert heartbeat.result is None
    assert heartbeat.elapsed_s >= 0
    frame = json.loads(
        stream_module._preparation_heartbeat_frame(heartbeat.elapsed_s)[6:-2]
    )
    assert frame["type"] == "status"
    assert frame["stage"] == "session_preparation"
    assert frame["heartbeat"] is True
    assert set(frame) == {
        "type",
        "timestamp",
        "data",
        "stage",
        "heartbeat",
        "elapsed_s",
    }

    release.set()
    completed = await anext(events)
    assert completed.completed is True
    assert completed.result is sentinel.resolved
    with pytest.raises(StopAsyncIteration):
        await anext(events)


@pytest.mark.asyncio
async def test_slow_agent_stream_yields_heartbeat_without_cancelling_next_event():
    release = asyncio.Event()

    async def slow_stream():
        await release.wait()
        yield ("messages", ("content", {}))

    events = _stream_events_with_heartbeat(slow_stream(), interval_s=0.001)
    heartbeat = await anext(events)

    assert heartbeat.heartbeat is True
    assert heartbeat.result is None
    assert heartbeat.elapsed_s >= 0

    release.set()
    stream_event = await anext(events)
    assert stream_event.heartbeat is False
    assert stream_event.result == ("messages", ("content", {}))

    with pytest.raises(StopAsyncIteration):
        await anext(events)


def test_agent_heartbeat_frame_is_sanitized():
    frame = json.loads(_agent_heartbeat_frame(1.234)[6:-2])

    assert frame["type"] == "status"
    assert frame["stage"] == "session_agent"
    assert frame["heartbeat"] is True
    assert frame["data"] == " Processando resposta"
    assert frame["elapsed_s"] == 1.234
    assert "path" not in frame
    assert "document" not in frame
    assert "prompt" not in frame


def test_session_request_flags_de_debug():
    base = SessionStreamRequest(id_usuario=1, id_topico=2, text="x")
    assert base.no_cache is False and base.trace is False  # defaults seguros
    assert base.mode is None
    dbg = SessionStreamRequest(
        id_usuario=1,
        id_topico=2,
        text="x",
        no_cache=True,
        trace=True,
        mode="filesystem",
    )
    assert dbg.no_cache is True and dbg.trace is True
    assert dbg.mode == "filesystem"


@pytest.mark.asyncio
async def test_benchmark_rejects_no_cache_false_before_preparation(monkeypatch):
    import sei_ia.routers.session.stream as stream_module

    prepare = AsyncMock()
    manager = AsyncMock()
    monkeypatch.setattr(stream_module, "_prepare_session_user_message", prepare)
    monkeypatch.setattr(stream_module, "get_session_manager", manager)
    request = SessionStreamRequest(id_usuario=1, id_topico=2, text="x")
    starlette_request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": ENDPOINT_NAME,
            "headers": [(b"x-experiment-collect-tools", b"1")],
        }
    )
    starlette_request.state.id_request = 123456

    response = await session_stream(request, starlette_request)
    chunks = [
        chunk.decode() if isinstance(chunk, bytes) else chunk
        async for chunk in response.body_iterator
    ]
    frames = [json.loads(chunk[6:-2]) for chunk in chunks]

    assert frames == [
        {
            "type": "error",
            "timestamp": frames[0]["timestamp"],
            "status_code": 422,
            "detail": "benchmark exige no_cache=true",
        }
    ]
    prepare.assert_not_awaited()
    manager.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_cache_purges_all_redis_variants_and_fetches_fresh_from_sei():
    cache = AsyncMock()
    provenance = {
        "fresh_binary_sha256": "a" * 64,
        "id_protocolo_formatado": "PROC-1",
    }
    fetch = AsyncMock(return_value=("fresh do SEI", "DOC-1", provenance))
    with (
        patch("sei_ia.services.cache.get_cache", return_value=cache),
        patch(
            "sei_ia.data.etl.concatenate_documents.get_doc_from_id_async",
            new=fetch,
        ),
    ):
        result = await _fetch_document("doc-1", False, True)

    assert result.content == "fresh do SEI"
    assert result.formatted_document_number == "DOC-1"
    assert result.status.state == "available"
    assert result.source == "sei"
    assert result.provenance == provenance
    assert result.formatted_process_number == "PROC-1"
    cache.purge_document.assert_awaited_once_with("doc-1")
    cache.get_document.assert_not_awaited()
    fetch.assert_awaited_once_with("doc-1", download_ext=False)


@pytest.mark.asyncio
async def test_fetch_document_preserva_numero_formatado_do_documento_vazio():
    from sei_ia.services.exceptions.http_exceptions import HTTPException204

    empty_document = HTTPException204(
        formatted_document_number="16016297",
    )
    cache = AsyncMock()
    cache.get_document.return_value = None
    fetch = AsyncMock(side_effect=empty_document)

    with (
        patch("sei_ia.services.cache.get_cache", return_value=cache),
        patch(
            "sei_ia.data.etl.concatenate_documents.get_doc_from_id_async",
            new=fetch,
        ),
    ):
        result = await _fetch_document("doc-empty", False, False)

    assert result.content == ""
    assert result.formatted_document_number == "16016297"
    assert result.status.state == "empty"
    assert result.status.reason == "content_doc_empty"
    assert result.source == "sei"
    fetch.assert_awaited_once_with("doc-empty", download_ext=False)


@pytest.mark.asyncio
async def test_fetch_document_informa_origem_redis():
    cache = AsyncMock()
    cache.get_document.return_value = {
        "content": "cacheado",
        "id_documento_formatado": "DOC-1",
    }
    with patch("sei_ia.services.cache.get_cache", return_value=cache):
        result = await _fetch_document("doc-1", False, False)

    assert result.content == "cacheado"
    assert result.formatted_document_number == "DOC-1"
    assert result.status.state == "available"
    assert result.source == "redis"


@pytest.mark.asyncio
async def test_fetch_document_aceita_documento_sem_id_formatado():
    cache = AsyncMock()
    cache.get_document.return_value = None
    fetch = AsyncMock(return_value=("conteudo", None, {}))
    with (
        patch("sei_ia.services.cache.get_cache", return_value=cache),
        patch(
            "sei_ia.data.etl.concatenate_documents.get_doc_from_id_async",
            new=fetch,
        ),
    ):
        result = await _fetch_document("doc-1", False, False)
    assert result.formatted_document_number is None
    assert result.status.state == "available"


@pytest.mark.asyncio
async def test_fetch_document_classifica_binario_ausente_sem_expor_erro():
    missing_binary = HTTPException(status_code=404, detail="erro bruto não exposto")
    missing_binary.formatted_document_number = "16016297"
    missing_binary.content_reason = "binary_not_found"
    cache = AsyncMock()
    cache.get_document.return_value = None
    fetch = AsyncMock(side_effect=missing_binary)

    with (
        patch("sei_ia.services.cache.get_cache", return_value=cache),
        patch(
            "sei_ia.data.etl.concatenate_documents.get_doc_from_id_async",
            new=fetch,
        ),
    ):
        result = await _fetch_document("doc-1", True, False)

    assert result.content is None
    assert result.formatted_document_number == "16016297"
    assert result.status.state == "unavailable"
    assert result.status.reason == "binary_not_found"


@pytest.mark.asyncio
async def test_benchmark_fetches_process_metadata_fresh_from_sei():
    fetch = AsyncMock(return_value={"proc-1": "metadata fresh"})
    with patch(
        "sei_ia.data.etl.extract.metadata.fetch_procedimentos_metadata_batch",
        new=fetch,
    ):
        result = await _fetch_benchmark_process_metadata(["proc-1"])

    assert result == {
        "proc-1": {"description": "metadata fresh", "source": "sei_no_cache"}
    }
    fetch.assert_awaited_once_with(["proc-1"])


@pytest.mark.asyncio
async def test_benchmark_fails_closed_when_fresh_process_metadata_is_missing():
    fetch = AsyncMock(return_value={})
    with (
        patch(
            "sei_ia.data.etl.extract.metadata.fetch_procedimentos_metadata_batch",
            new=fetch,
        ),
        pytest.raises(BenchmarkEvidenceError, match="fresh_process_metadata_missing"),
    ):
        await _fetch_benchmark_process_metadata(["proc-1"])


@pytest.mark.asyncio
async def test_normal_process_metadata_batch_preserves_empty_fallback():
    error = SeiDBAPIError(status_code=502, detail="invalid upstream response")
    with patch(
        "sei_ia.data.etl.extract.metadata.sei_client.md_ia_consulta_processo_batch",
        new=AsyncMock(side_effect=error),
    ):
        result = await fetch_procedimentos_metadata_batch(["proc-1"])

    assert result == {}


@pytest.mark.asyncio
async def test_pinned_benchmark_fetches_fresh_and_uses_snapshot_only_as_validator(
    monkeypatch,
):
    import sei_ia.routers.session.stream as stream_module

    provenance = {"fresh_binary_sha256": "a" * 64}
    fetch = AsyncMock(
        return_value=SessionDocumentOutcome(
            content="fresh do SEI",
            formatted_document_number="DOC-1",
            formatted_process_number=None,
            status=ContentStatus.available(),
            source="sei",
            provenance=provenance,
        )
    )
    snapshot = MagicMock()
    monkeypatch.setattr(stream_module, "_fetch_document", fetch)

    result = await _fetch_session_document(
        "doc-1", False, no_cache=True, pinned_snapshot=snapshot
    )

    assert result.content == "fresh do SEI"
    assert result.formatted_document_number == "DOC-1"
    assert result.source == "sei"
    fetch.assert_awaited_once_with("doc-1", False, True)
    snapshot.validate_fresh_document.assert_called_once_with(
        "doc-1", "fresh do SEI", provenance
    )
    snapshot.read_document.assert_not_called()


@pytest.mark.asyncio
async def test_pinned_benchmark_refuses_fetch_without_no_cache(monkeypatch):
    import sei_ia.routers.session.stream as stream_module

    fetch = AsyncMock()
    monkeypatch.setattr(stream_module, "_fetch_document", fetch)

    with pytest.raises(BenchmarkEvidenceError, match="benchmark_no_cache_required"):
        await _fetch_session_document(
            "doc-1", False, no_cache=False, pinned_snapshot=MagicMock()
        )

    fetch.assert_not_awaited()


def test_session_request_reaproveita_payload_real_de_upload():
    # Este teste valida apenas o parsing do contrato e não consulta o SEI. Em
    # E2E, o upload-fonte no SEI expira em 1h (independente do cache Redis): crie
    # um cenário novo e consuma-o logo depois; não use este ID como fixture externa.
    request = SessionStreamRequest.model_validate(
        {
            "text": "O que tem na imagem?",
            "id_usuario": 1,
            "system_prompt": '"Sou um Assistente de IA integrado ao SEI."',
            "use_thinking": False,
            "use_websearch": False,
            "skip_memory": False,
            "id_topico": 2,
            "id_procedimentos": [
                {
                    "id_procedimento": "100",
                    "id_documentos": [
                        {
                            "id_documento": "101",
                            "download_ext": False,
                            "precisa_ocr": False,
                        }
                    ],
                }
            ],
            "arquivos_avulsos": [
                {
                    "id_arquivo_avulso": 3,
                    "nome_arquivo_avulso": "imagem.png",
                    "extensao_arquivo_avulso": "png",
                }
            ],
        }
    )

    assert request.id_topico == 2
    assert request.arquivos_avulsos is not None
    assert request.arquivos_avulsos[0].id_arquivo_avulso == 3
    assert request.arquivos_avulsos[0].extensao_arquivo_avulso == "png"


@pytest.mark.asyncio
async def test_evidence_preflight_failure_emits_safe_error_before_any_llm(
    monkeypatch,
):
    import sei_ia.routers.session.stream as stream_module

    diagnostic_error = BenchmarkEvidenceError(
        "content_hash_mismatch", path="proc_safe/doc.txt"
    )
    preflight = MagicMock(side_effect=diagnostic_error)
    classify = AsyncMock()
    build_agent = MagicMock()
    manager = AsyncMock()
    monkeypatch.setattr(stream_module, "load_benchmark_evidence_snapshot", preflight)
    monkeypatch.setattr(stream_module, "classify_complexity", classify)
    monkeypatch.setattr(stream_module, "build_session_agent", build_agent)
    monkeypatch.setattr(stream_module, "get_session_manager", manager)
    monkeypatch.setattr(
        stream_module, "_prepare_session_user_message", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        stream_module.settings, "SESSION_BENCHMARK_EVIDENCE_INDEX", "/pinned/index.json"
    )
    monkeypatch.setattr(stream_module, "_flush_langfuse", lambda: None)

    request = SessionStreamRequest.model_validate(
        {
            "id_usuario": 1,
            "id_topico": 2,
            "text": "pergunta",
            "no_cache": True,
            "id_procedimentos": [
                {
                    "id_procedimento": "proc",
                    "id_documentos": [{"id_documento": "doc"}],
                }
            ],
        }
    )
    starlette_request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": ENDPOINT_NAME,
            "headers": [(b"x-experiment-collect-tools", b"1")],
        }
    )
    starlette_request.state.id_request = 123456

    response = await session_stream(request, starlette_request)
    chunks = [
        chunk.decode() if isinstance(chunk, bytes) else chunk
        async for chunk in response.body_iterator
    ]
    frames = [json.loads(chunk[6:-2]) for chunk in chunks]
    error = next(frame for frame in frames if frame["type"] == "error")

    assert error["status_code"] == 409
    assert error["diagnostic"] == diagnostic_error.diagnostic
    assert "proc_safe" not in json.dumps(error)
    preflight.assert_called_once()
    manager.assert_not_awaited()
    classify.assert_not_awaited()
    build_agent.assert_not_called()


@pytest.mark.asyncio
async def test_prepare_session_user_message_envia_imagem_multimodal():
    request = SessionStreamRequest(
        id_usuario=1,
        id_topico=2,
        text="o que tem na imagem?",
        arquivos_avulsos=[
            {
                "id_arquivo_avulso": 3,
                "nome_arquivo_avulso": "imagem.png",
                "extensao_arquivo_avulso": "png",
            }
        ],
    )

    async def fake_apply(_request, state, *, remove_from_sei, tolerant_uploads):
        assert remove_from_sei is False
        assert tolerant_uploads is True
        state["user_request"] += "\n\n<arquivos_avulsos>...</arquivos_avulsos>"
        state["image_attachments"] = [sentinel.image]
        return {"/tmp/upload.png"}

    temp_files: set[str] = set()
    with (
        patch(
            "sei_ia.routers.session.stream._apply_arquivos_avulsos_to_state",
            new=AsyncMock(side_effect=fake_apply),
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow._build_multimodal_human_message",
            return_value=sentinel.multimodal_message,
        ) as build_message,
    ):
        message = await _prepare_session_user_message(request, temp_files)

    assert message is sentinel.multimodal_message
    assert temp_files == {"/tmp/upload.png"}
    build_message.assert_called_once_with(
        "o que tem na imagem?\n\n<arquivos_avulsos>...</arquivos_avulsos>",
        [sentinel.image],
    )


@pytest.mark.asyncio
async def test_prepare_session_user_message_preserva_cleanup_se_multimodal_falhar():
    request = SessionStreamRequest(
        id_usuario=1,
        id_topico=2,
        text="descreva",
        arquivos_avulsos=[
            {
                "id_arquivo_avulso": 10,
                "nome_arquivo_avulso": "imagem.png",
                "extensao_arquivo_avulso": "png",
            }
        ],
    )

    async def fake_apply(_request, state, *, remove_from_sei, tolerant_uploads):
        assert remove_from_sei is False
        assert tolerant_uploads is True
        state["image_attachments"] = [sentinel.image]
        return {"/tmp/imagem.png"}

    temp_files: set[str] = set()
    with (
        patch(
            "sei_ia.routers.session.stream._apply_arquivos_avulsos_to_state",
            new=AsyncMock(side_effect=fake_apply),
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow._build_multimodal_human_message",
            side_effect=ArquivoAvulsoProcessingError(
                "imagem.png", "png", "falha de leitura"
            ),
        ),
        pytest.raises(ArquivoAvulsoProcessingError),
    ):
        await _prepare_session_user_message(request, temp_files)

    assert temp_files == {"/tmp/imagem.png"}


def _patch_session_langfuse(monkeypatch, stream_module, *, enabled):
    span = MagicMock()
    span_names = []
    updates = []
    callback = MagicMock()
    callback_factory = MagicMock(return_value=callback)

    def fake_span(name, *_args, **_kwargs):
        span_names.append(name)
        return nullcontext(span)

    def capture_update(_span, **kwargs):
        updates.append(kwargs)

    monkeypatch.setattr(stream_module, "_langfuse_span", fake_span)
    monkeypatch.setattr(stream_module, "_update_langfuse_trace", capture_update)
    monkeypatch.setattr(stream_module, "_new_trace_id", lambda: None)
    monkeypatch.setattr(stream_module, "_flush_langfuse", lambda: None)
    monkeypatch.setattr(stream_module, "SessionLangfuseCallback", callback_factory)
    monkeypatch.setattr(stream_module.settings, "USE_LANGFUSE", enabled)
    return SimpleNamespace(
        span=span,
        span_names=span_names,
        updates=updates,
        callback=callback,
        callback_factory=callback_factory,
    )


async def _run_session_stream_with_fake_agent(  # noqa: PLR0915
    # Harness de teste que monta o generator inteiro do session_stream com
    # dublês — cresce a cada novo parâmetro/validação do endpoint (ex.:
    # model_override, reasoning_effort); dividir em partes menores não
    # compensa o ganho de legibilidade de manter o setup num só lugar.
    monkeypatch,
    tmp_path,
    *,
    fail: bool,
    trace: bool = False,
    benchmark_collect: bool = False,
    cancel_during_remove: bool = False,
    agent_delay: float = 0.0,
    unavailable_document_ids: tuple[str, ...] = (),
    use_langfuse: bool = False,
    response_text: str = "resposta",
    processed_upload_ids: tuple[int, ...] = (10,),
    model_override: str | None = None,
    reasoning_effort: str | None = None,
    validate_reasoning_effort_side_effect=None,
    validate_model_override_side_effect=None,
    agent_error: BaseException | None = None,
    agent_error_times: int = 1,
):
    import sei_ia.routers.session.stream as stream_module

    events: list[str] = []
    observed: dict = {}
    get_model_config_calls: list[dict] = []
    validate_reasoning_effort_mock = AsyncMock(
        side_effect=validate_reasoning_effort_side_effect
    )
    validate_model_override_mock = AsyncMock(
        side_effect=validate_model_override_side_effect
    )
    resolved = SimpleNamespace(
        paths=SimpleNamespace(root=tmp_path, session_key="1_2"),
        meta=SimpleNamespace(doc_ids=(), documentos={}),
        is_new=True,
        history_turns=0,
        total_content_tokens=0,
        materialization=SessionMaterialization(unavailable=unavailable_document_ids),
    )
    manager = SimpleNamespace(resolve=AsyncMock(return_value=resolved))

    astream_calls = {"n": 0}

    class FakeAgent:
        async def astream(self, agent_input, **_kwargs):
            astream_calls["n"] += 1
            observed["agent_input"] = agent_input
            observed["astream_kwargs"] = _kwargs
            observed["astream_calls"] = astream_calls["n"]
            events.append("agent_start")
            if fail:
                raise RuntimeError("falha simulada do agente")
            if agent_error is not None and astream_calls["n"] <= agent_error_times:
                raise agent_error
            if agent_delay:
                await asyncio.sleep(agent_delay)
            events.append("agent_done")
            yield ("messages", (AIMessageChunk(content=response_text), {}))

        async def aupdate_state(self, *_args, **_kwargs):
            events.append("clear_window")

    async def fake_prepare(_request, temp_files, removal_ids):
        temp_files.add("/tmp/upload.png")
        removal_ids.update(processed_upload_ids)
        return sentinel.user_message

    async def fake_remove(_arquivos_avulsos, *, eligible_ids=None):
        events.append("remove")
        assert eligible_ids == set(processed_upload_ids)
        if cancel_during_remove:
            raise asyncio.CancelledError

    remove_mock = AsyncMock(side_effect=fake_remove)
    cleanup_mock = MagicMock()
    monkeypatch.setattr(stream_module, "_prepare_session_user_message", fake_prepare)
    monkeypatch.setattr(
        stream_module, "get_session_manager", AsyncMock(return_value=manager)
    )
    monkeypatch.setattr(
        stream_module,
        "get_session_checkpointer",
        AsyncMock(return_value=sentinel.checkpointer),
    )
    monkeypatch.setattr(
        stream_module,
        "decide_mode",
        lambda *_args: SimpleNamespace(
            mode="filesystem", total_content_tokens=0, threshold=100
        ),
    )
    monkeypatch.setattr(
        stream_module, "classify_complexity", AsyncMock(return_value="easy")
    )

    def fake_build_session_agent(*_args, **kwargs):
        observed["agent_kwargs"] = kwargs
        observed.setdefault("agent_kwargs_calls", []).append(kwargs)
        return FakeAgent()

    monkeypatch.setattr(
        stream_module,
        "build_session_agent",
        create_autospec(
            stream_module.build_session_agent, side_effect=fake_build_session_agent
        ),
    )
    monkeypatch.setattr(stream_module, "_apply_history_policy", AsyncMock())

    def fake_get_model_config(**kwargs):
        get_model_config_calls.append(kwargs)
        return {
            "model": "fake",
            "model_name": "fake",
            "max_ctx_len": 1000,
        }

    monkeypatch.setattr(stream_module, "get_model_config", fake_get_model_config)
    monkeypatch.setattr(
        stream_module, "validate_reasoning_effort", validate_reasoning_effort_mock
    )
    monkeypatch.setattr(
        stream_module, "validate_model_override", validate_model_override_mock
    )
    monkeypatch.setattr(stream_module, "_remove_arquivos_avulsos_no_sei", remove_mock)
    monkeypatch.setattr(
        stream_module, "cleanup_arquivos_avulsos_temp_files", cleanup_mock
    )
    langfuse = _patch_session_langfuse(monkeypatch, stream_module, enabled=use_langfuse)
    monkeypatch.setattr(stream_module.settings, "SESSION_SEED_HISTORY", False)
    monkeypatch.setattr(stream_module.settings, "SESSION_TRACE", False)

    request = SessionStreamRequest(
        id_usuario=1,
        id_topico=2,
        ip="192.0.2.10",
        text="descreva a imagem",
        trace=trace,
        no_cache=benchmark_collect,
        model=model_override,
        reasoning_effort=reasoning_effort,
        arquivos_avulsos=[
            {
                "id_arquivo_avulso": 10,
                "nome_arquivo_avulso": "imagem.png",
                "extensao_arquivo_avulso": "png",
            }
        ],
    )
    headers = [(b"x-experiment-collect-tools", b"1")] if benchmark_collect else []
    starlette_request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": ENDPOINT_NAME,
            "headers": headers,
        }
    )
    original_request_body = request.model_dump_json(exclude_none=True)
    starlette_request.state.body = original_request_body.encode("utf-8")
    starlette_request.state.id_request = 987654
    response = await session_stream(request, starlette_request)
    chunks = []
    try:
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    except asyncio.CancelledError:
        if not cancel_during_remove:
            raise
        observed["cancelled"] = True

    return {
        "body": "".join(chunks),
        "cleanup_mock": cleanup_mock,
        "events": events,
        "observed": observed,
        "langfuse_updates": langfuse.updates,
        "langfuse_span": langfuse.span,
        "langfuse_span_names": langfuse.span_names,
        "langfuse_callback": langfuse.callback,
        "langfuse_callback_factory": langfuse.callback_factory,
        "remove_mock": remove_mock,
        "original_request_body": original_request_body,
        "request": request,
        "get_model_config_calls": get_model_config_calls,
        "validate_reasoning_effort_mock": validate_reasoning_effort_mock,
        "validate_model_override_mock": validate_model_override_mock,
    }


@pytest.mark.asyncio
async def test_session_stream_remove_upload_somente_depois_do_agente(
    monkeypatch, tmp_path
):
    result = await _run_session_stream_with_fake_agent(
        monkeypatch, tmp_path, fail=False
    )

    assert result["events"] == ["agent_start", "agent_done", "remove"]
    assert result["observed"]["agent_input"] == {"messages": [sentinel.user_message]}
    result["remove_mock"].assert_awaited_once_with(
        result["request"].arquivos_avulsos,
        eligible_ids={10},
    )
    result["cleanup_mock"].assert_called_once_with({"/tmp/upload.png"})
    assert '"type": "metadata"' in result["body"]
    assert '"type": "end"' in result["body"]
    assert '"type": "error"' not in result["body"]
    span_updates = result["langfuse_span"].update.call_args_list
    assert call(input={"messages": ["sentinel.user_message"]}) in span_updates
    assert call(output={"content": "resposta"}) in span_updates
    assert any(
        update.kwargs.get("metadata", {}).get("stage") == "complexity_classification"
        for update in span_updates
    )
    assert any(
        update.get("output", {}).get("result") == "success"
        for update in result["langfuse_updates"]
    )


@pytest.mark.asyncio
async def test_session_stream_renderiza_upload_disponivel_pelo_nome(
    monkeypatch, tmp_path
):
    """O mapa do endpoint inclui somente o upload que foi processado com sucesso."""
    result = await _run_session_stream_with_fake_agent(
        monkeypatch,
        tmp_path,
        fail=False,
        response_text="Use <upload_10></upload_10>",
    )

    assert 'title=\\"imagem.png\\"' in result["body"]
    assert "Documento SEI" not in result["body"]
    assert "upload_10" not in result["body"]


@pytest.mark.asyncio
async def test_session_stream_descarta_citacao_de_upload_indisponivel(
    monkeypatch, tmp_path
):
    """Upload não materializado não entra no mapa de fontes do endpoint."""
    result = await _run_session_stream_with_fake_agent(
        monkeypatch,
        tmp_path,
        fail=False,
        response_text="Use <upload_10></upload_10>",
        processed_upload_ids=(),
    )

    assert "AssistenteSEIIAfonteResposta" not in result["body"]
    assert "upload_10" not in result["body"]


@pytest.mark.asyncio
async def test_session_stream_emite_heartbeat_durante_agente_silencioso(
    monkeypatch, tmp_path
):
    import sei_ia.routers.session.stream as stream_module

    monkeypatch.setattr(
        stream_module.settings, "SESSION_AGENT_HEARTBEAT_INTERVAL_SECONDS", 0.001
    )
    result = await _run_session_stream_with_fake_agent(
        monkeypatch,
        tmp_path,
        fail=False,
        agent_delay=0.01,
    )

    frames = [
        json.loads(line.removeprefix("data: "))
        for line in result["body"].splitlines()
        if line.startswith("data: ")
    ]
    heartbeat_index = next(
        index
        for index, frame in enumerate(frames)
        if frame["type"] == "status"
        and frame.get("stage") == "session_agent"
        and frame.get("heartbeat") is True
    )
    content_index = next(
        index for index, frame in enumerate(frames) if frame["type"] == "content"
    )

    assert heartbeat_index < content_index
    heartbeat = frames[heartbeat_index]
    assert heartbeat["data"] == " Processando resposta"
    assert "path" not in heartbeat
    assert "document" not in heartbeat
    assert "prompt" not in heartbeat


@pytest.mark.asyncio
async def test_session_stream_metadata_usa_id_request_do_middleware(
    monkeypatch, tmp_path
):
    result = await _run_session_stream_with_fake_agent(
        monkeypatch, tmp_path, fail=False
    )

    frames = [
        json.loads(line.removeprefix("data: "))
        for line in result["body"].splitlines()
        if line.startswith("data: ")
    ]
    metadata = next(frame for frame in frames if frame["type"] == "metadata")

    assert result["request"].id_request is None
    assert metadata["data"]["id_message"] == 987654
    assert isinstance(metadata["data"]["id_message"], int)


@pytest.mark.asyncio
async def test_session_stream_delega_contexto_ao_deepagents(monkeypatch, tmp_path):
    result = await _run_session_stream_with_fake_agent(
        monkeypatch, tmp_path, fail=False
    )

    assert "remaining_context_tokens" not in result["observed"]["agent_kwargs"]


@pytest.mark.asyncio
async def test_session_stream_propaga_model_override_do_request_so_para_principal(
    monkeypatch, tmp_path
):
    override = "openai/seiia-ds-gemini-pro"
    result = await _run_session_stream_with_fake_agent(
        monkeypatch, tmp_path, fail=False, model_override=override
    )

    # Validado contra o catálogo ao vivo do proxy antes de ser usado.
    result["validate_model_override_mock"].assert_awaited_once_with(override)

    # build_session_agent recebe o override do request (ChatRequest.model).
    assert result["observed"]["agent_kwargs"]["model_override"] == override

    # get_model_config: só a chamada do papel principal (SESSION_MAIN_MODEL)
    # recebe o override; explorador/classificador continuam sem.
    calls_by_tag = {}
    for kwargs in result["get_model_config_calls"]:
        calls_by_tag.setdefault(kwargs.get("agent_tag"), []).append(kwargs)

    for kwargs in calls_by_tag.get("principal", []):
        assert kwargs.get("model_override") == override
    for tag in ("explorador", "classificador"):
        for kwargs in calls_by_tag.get(tag, []):
            assert kwargs.get("model_override") is None


@pytest.mark.asyncio
async def test_session_stream_propaga_reasoning_effort_valido(monkeypatch, tmp_path):
    result = await _run_session_stream_with_fake_agent(
        monkeypatch, tmp_path, fail=False, reasoning_effort="high"
    )

    # Validado contra o modelo físico resolvido pro papel principal (o "model"
    # que get_model_config devolve, já com override aplicado se houver).
    result["validate_reasoning_effort_mock"].assert_awaited_once_with("fake", "high")
    assert result["observed"]["agent_kwargs"]["reasoning_effort"] == "high"
    assert "agent_start" in result["events"]


@pytest.mark.asyncio
async def test_session_stream_failover_reasoning_apos_erro_do_provedor(
    monkeypatch, tmp_path
):
    """Erro do provedor antes do 1º byte → reconstrói o agente com
    `reasoning_effort="none"`, zera a janela e reprocessa; o turno conclui."""
    result = await _run_session_stream_with_fake_agent(
        monkeypatch,
        tmp_path,
        fail=False,
        agent_error=openai.APIConnectionError(
            message="boom", request=httpx.Request("POST", "http://proxy/responses")
        ),
    )

    body = result["body"]
    assert '"type": "error"' not in body
    assert '"type": "end"' in body
    assert '"reasoning_failover": true' in body  # frame de status do failover
    # 2 builds: o 1º sem forçar effort, o 2º com "none".
    builds = result["observed"]["agent_kwargs_calls"]
    assert len(builds) == 2
    assert builds[0]["reasoning_effort"] is None
    assert builds[1]["reasoning_effort"] == "none"
    assert builds[1] == {**builds[0], "reasoning_effort": "none"}
    assert all("remaining_context_tokens" not in kwargs for kwargs in builds)
    # Janela do checkpointer foi zerada antes do reprocessamento.
    assert result["events"].count("agent_start") == 2
    assert "clear_window" in result["events"]
    # Tag no trace Langfuse.
    assert any(
        "reasoning_failover" in (update.get("tags") or [])
        for update in result["langfuse_updates"]
    )


@pytest.mark.asyncio
async def test_session_stream_sem_failover_em_erro_4xx_deterministico(
    monkeypatch, tmp_path
):
    request_obj = httpx.Request("POST", "http://proxy/responses")
    result = await _run_session_stream_with_fake_agent(
        monkeypatch,
        tmp_path,
        fail=False,
        agent_error=openai.BadRequestError(
            "conteúdo rejeitado",
            response=httpx.Response(400, request=request_obj),
            body=None,
        ),
    )

    assert '"status_code": 400' in result["body"]
    assert len(result["observed"]["agent_kwargs_calls"]) == 1
    assert "clear_window" not in result["events"]


@pytest.mark.asyncio
async def test_session_stream_failover_reasoning_so_uma_vez(monkeypatch, tmp_path):
    """Se a 2ª tentativa (já sem reasoning) também estoura, o erro propaga —
    não há 3ª tentativa."""
    result = await _run_session_stream_with_fake_agent(
        monkeypatch,
        tmp_path,
        fail=False,
        agent_error=openai.APIConnectionError(
            message="boom", request=httpx.Request("POST", "http://proxy/responses")
        ),
        agent_error_times=2,
    )

    assert '"status_code": 503' in result["body"]
    assert len(result["observed"]["agent_kwargs_calls"]) == 2
    assert result["events"].count("agent_start") == 2


@pytest.mark.asyncio
async def test_session_stream_reasoning_effort_invalido_nao_chama_o_agente(
    monkeypatch, tmp_path
):
    result = await _run_session_stream_with_fake_agent(
        monkeypatch,
        tmp_path,
        fail=False,
        reasoning_effort="high",
        validate_reasoning_effort_side_effect=ValueError(
            "reasoning_effort='high' não é suportado"
        ),
    )

    # Rejeitado antes de montar/chamar o agente — erro 422 no frame SSE.
    assert "agent_start" not in result["events"]
    assert "agent_kwargs" not in result["observed"]
    assert '"status_code": 422' in result["body"]
    assert "não é suportado" in result["body"]


@pytest.mark.asyncio
async def test_session_stream_model_override_invalido_nao_chama_o_agente(
    monkeypatch, tmp_path
):
    result = await _run_session_stream_with_fake_agent(
        monkeypatch,
        tmp_path,
        fail=False,
        model_override="modelo-arbitrario",
        validate_model_override_side_effect=ValueError(
            "model='modelo-arbitrario' não está liberado"
        ),
    )

    # Rejeitado antes de montar/chamar o agente — erro 422 no frame SSE.
    assert "agent_start" not in result["events"]
    assert "agent_kwargs" not in result["observed"]
    assert '"status_code": 422' in result["body"]
    assert "não está liberado" in result["body"]


@pytest.mark.asyncio
async def test_session_stream_trace_cobre_fluxo_semantico_e_body_textual(
    monkeypatch, tmp_path
):
    import sei_ia.routers.session.stream as stream_module

    result = await _run_session_stream_with_fake_agent(
        monkeypatch, tmp_path, fail=False
    )

    assert result["langfuse_span_names"] == [
        "session_stream",
        "session.accept_request",
        "session.prepare",
        "session.materialize_documents",
        "session.decide_mode",
        "session_complexity",
        "session.agent",
        "session.finalize_stream",
    ]
    root_update = next(
        update
        for update in result["langfuse_updates"]
        if update.get("name") == "session_stream"
    )
    langfuse_body = json.loads(root_update["input"])
    assert langfuse_body != result["original_request_body"]
    assert isinstance(root_update["input"], str)
    assert json.loads(langfuse_body)["text"] == "descreva a imagem"
    assert "ip" not in json.loads(langfuse_body)
    assert "trace" not in json.loads(langfuse_body)
    assert "no_cache" not in json.loads(langfuse_body)
    assert json.loads(result["original_request_body"])["ip"] == "192.0.2.10"
    assert root_update["metadata"]["input_format"] == "original_request_body_json_text"
    assert root_update["metadata"]["redacted_fields"] == ["ip"]
    metadata_body = root_update["metadata"]["original_request"]
    assert metadata_body.startswith("\\{")
    assert json.loads(metadata_body[1:])["text"] == "descreva a imagem"
    assert (
        sum(
            "original_request" in update.get("metadata", {})
            for update in result["langfuse_updates"]
        )
        == 1
    )
    assert root_update["session_id"] == "2"
    assert root_update["user_id"] == "1"
    assert root_update["version"] == str(stream_module.settings.VERSION)
    assert result["observed"]["astream_kwargs"]["config"]["metadata"] == {
        "langfuse_session_id": "2",
        "langfuse_user_id": "1",
    }


@pytest.mark.asyncio
async def test_session_stream_usa_callback_langfuse_com_redacao(monkeypatch, tmp_path):
    result = await _run_session_stream_with_fake_agent(
        monkeypatch,
        tmp_path,
        fail=False,
        use_langfuse=True,
    )

    result["langfuse_callback_factory"].assert_called_once_with()
    callbacks = result["observed"]["astream_kwargs"]["config"]["callbacks"]
    assert result["langfuse_callback"] in callbacks


@pytest.mark.asyncio
async def test_session_stream_registra_erro_no_trace(monkeypatch, tmp_path):
    result = await _run_session_stream_with_fake_agent(monkeypatch, tmp_path, fail=True)

    error_update = next(
        update
        for update in result["langfuse_updates"]
        if isinstance(update.get("output"), dict)
        and update["output"].get("result") == "error"
    )
    assert error_update["output"]["stage"] == "session.agent"
    assert error_update["output"]["status_code"] == 500
    assert "error:500" in error_update["tags"]
    assert "result:error" in error_update["tags"]


@pytest.mark.asyncio
async def test_falha_de_remocao_nao_altera_resposta_do_agente(monkeypatch, tmp_path):
    result = await _run_session_stream_with_fake_agent(
        monkeypatch,
        tmp_path,
        fail=False,
    )

    assert result["events"] == ["agent_start", "agent_done", "remove"]
    assert '"type": "metadata"' in result["body"]
    assert '"type": "end"' in result["body"]
    assert '"type": "error"' not in result["body"]


@pytest.mark.asyncio
async def test_cancelamento_tardio_preserva_output_e_contexto_indisponivel(
    monkeypatch, tmp_path
):
    result = await _run_session_stream_with_fake_agent(
        monkeypatch,
        tmp_path,
        fail=False,
        cancel_during_remove=True,
        unavailable_document_ids=("DOC-7",),
    )

    cancelled_update = next(
        update
        for update in result["langfuse_updates"]
        if update.get("output", {}).get("result") == "cancelled"
    )
    assert result["observed"]["cancelled"] is True
    assert cancelled_update["output"]["response"]["output"] == "resposta"
    assert cancelled_update["output"]["response"]["chars"] == len("resposta")
    assert result["observed"]["agent_kwargs"]["unavailable_document_ids"] == ("DOC-7",)


@pytest.mark.asyncio
async def test_benchmark_collect_suppresses_raw_debug_trace(monkeypatch, tmp_path):
    import sei_ia.routers.session.stream as stream_module

    debug_handler = MagicMock()
    monkeypatch.setattr(stream_module, "SessionTraceHandler", debug_handler)
    (tmp_path / "doc.txt").write_text("resposta fresh protegida")

    result = await _run_session_stream_with_fake_agent(
        monkeypatch,
        tmp_path,
        fail=False,
        trace=True,
        benchmark_collect=True,
    )

    debug_handler.assert_not_called()
    assert '"schema_version": "benchmark-tool-telemetry-v2"' in result["body"]
    assert '"benchmark_session_reset": true' in result["body"]
    assert '"benchmark_process_source": "sei_no_cache"' in result["body"]
    assert '"benchmark_fresh_evidence"' not in result["body"]
    assert "resposta fresh protegida" not in result["body"]


@pytest.mark.asyncio
async def test_session_stream_nao_remove_upload_quando_agente_falha(
    monkeypatch, tmp_path
):
    result = await _run_session_stream_with_fake_agent(monkeypatch, tmp_path, fail=True)

    assert result["events"] == ["agent_start"]
    result["remove_mock"].assert_not_awaited()
    result["cleanup_mock"].assert_called_once_with({"/tmp/upload.png"})
    assert '"type": "error"' in result["body"]
    assert '"status_code": 500' in result["body"]
    assert '"type": "metadata"' not in result["body"]


def test_frame_contract_sse():
    frame = _frame("content", data="oi")
    assert frame.startswith("data: ") and frame.endswith("\n\n")
    payload = json.loads(frame[6:-2])
    assert payload == {
        "type": "content",
        "data": "oi",
        "timestamp": payload["timestamp"],
    }
    assert isinstance(payload["timestamp"], float)


def test_error_frame():
    payload = json.loads(_error_frame(422, "faltou id_topico")[6:-2])
    assert payload["type"] == "error"
    assert payload["status_code"] == 422
    assert payload["detail"] == "faltou id_topico"


def test_iter_text_str_e_blocos():
    assert _iter_text("abc") == "abc"
    assert (
        _iter_text(
            [
                {"type": "text", "text": "a"},
                {"type": "tool_use"},
                {"type": "text", "text": "b"},
            ]
        )
        == "ab"
    )
    assert _iter_text(None) == ""
    assert _iter_text(123) == ""


def test_map_exception_status_codes():
    assert (
        _map_exception(openai.RateLimitError.__new__(openai.RateLimitError))[0] == 429
    )
    assert (
        _map_exception(openai.APITimeoutError.__new__(openai.APITimeoutError))[0] == 408
    )
    assert (
        _map_exception(openai.BadRequestError.__new__(openai.BadRequestError))[0] == 400
    )
    assert (
        _map_exception(openai.InternalServerError.__new__(openai.InternalServerError))[
            0
        ]
        == 502
    )
    assert _map_exception(httpx.ConnectError("x"))[0] == 503
    assert _map_exception(RuntimeError("boom"))[0] == 500
