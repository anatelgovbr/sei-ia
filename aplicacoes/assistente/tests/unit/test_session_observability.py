"""Contrato sanitizado da observabilidade semântica do endpoint Session."""

import json
from collections import Counter

from sei_ia.configs.langfuse_config import (
    MAX_LANGFUSE_PAYLOAD_CHARS,
    truncate_large_fields,
)
from sei_ia.routers.session.observability import (
    DocumentFetchTelemetry,
    build_finalization_trace_output,
    build_materialization_trace_output,
    build_session_request_summary,
    encode_langfuse_json_text,
    original_request_body_text,
)
from sei_ia.routers.session.stream import SessionStreamRequest
from sei_ia.services.session_fs.manager import (
    ResolvedSession,
    SessionMaterialization,
)
from sei_ia.services.session_fs.types import SessionMeta, SessionPaths


def test_trace_input_preserva_body_como_string_sem_ip():
    request = SessionStreamRequest(
        id_usuario=1,
        id_topico=2,
        text="analise",
        id_procedimentos=[
            {
                "id_procedimento": "PROC-1",
                "id_documentos": [{"id_documento": "DOC-1"}],
            }
        ],
    )
    raw = (
        '{"id_usuario":1,"id_topico":2,"text":"analise",'
        '"ip":"192.0.2.10","trace":true,"no_cache":false}'
    )

    body = original_request_body_text(request, raw.encode())
    request_summary = build_session_request_summary(
        request,
        endpoint="/llm_lang/session_stream",
        request_id="REQ-1",
    )

    assert body != raw
    assert isinstance(body, str)
    assert json.loads(body)["text"] == "analise"
    assert "ip" not in json.loads(body)
    assert "trace" not in json.loads(body)
    assert "no_cache" not in json.loads(body)
    assert json.loads(encode_langfuse_json_text(body)) == body
    assert "trace" not in request_summary["flags"]
    assert "no_cache" not in request_summary["flags"]
    assert request_summary["processes"] == [
        {"process_id": "PROC-1", "document_ids": ["DOC-1"]}
    ]


def test_output_raiz_preserva_resposta_integral_do_agente():
    content = "R" * (MAX_LANGFUSE_PAYLOAD_CHARS + 1)

    output = build_finalization_trace_output(
        content=content,
        event_counts=Counter({"content": 10, "end": 1}),
        metadata_sent=True,
        end_sent=True,
    )
    masked = truncate_large_fields(output)

    assert output["response"]["output"] == content
    assert masked["response"]["output"] == content


def test_no_cache_so_aparece_quando_ativo():
    request = SessionStreamRequest(
        id_usuario=1,
        id_topico=2,
        text="benchmark",
        no_cache=True,
        trace=True,
    )
    raw = (
        '{"id_usuario":1,"id_topico":2,"text":"benchmark","no_cache":true,"trace":true}'
    )

    body = json.loads(original_request_body_text(request, raw))
    summary = build_session_request_summary(
        request,
        endpoint="/llm_lang/session_stream",
        request_id="REQ-2",
    )

    assert body["no_cache"] is True
    assert "trace" not in body
    assert summary["flags"]["no_cache"] is True
    assert "trace" not in summary["flags"]


def test_mode_override_eh_preservado_no_resumo_quando_informado():
    request = SessionStreamRequest(
        id_usuario=1,
        id_topico=2,
        text="teste",
        mode="filesystem",
    )

    summary = build_session_request_summary(
        request,
        endpoint="/llm_lang/session_stream",
        request_id="REQ-MODE",
    )

    assert summary["mode"] == "filesystem"


def test_numero_processo_aceita_description_textual():
    paths = SessionPaths.for_session("/tmp", "1_2")
    resolved = ResolvedSession(
        paths=paths,
        meta=SessionMeta(
            created_at=1.0,
            last_access=2.0,
            ttl_seconds=60,
            processos={
                "PROC-1": {
                    "metadata": {
                        "description": "Número do Processo: 00000.000000/0000-00"
                    }
                }
            },
            documentos={"DOC-1": {"id_documento_formatado": "16016297", "tokens": 1}},
        ),
        is_new=False,
        materialization=SessionMaterialization(requested=(("PROC-1", "DOC-1"),)),
    )

    output = build_materialization_trace_output(resolved, {})

    assert output["documents"][0]["process_number"] == "00000.000000/0000-00"


def test_numero_processo_ausente_vira_nulo_no_trace():
    paths = SessionPaths.for_session("/tmp", "1_2")
    resolved = ResolvedSession(
        paths=paths,
        meta=SessionMeta(
            created_at=1.0,
            last_access=2.0,
            ttl_seconds=60,
            processos={"PROC-1": {"metadata": {}}},
            documentos={"DOC-1": {"id_documento_formatado": "16016297"}},
        ),
        is_new=False,
        materialization=SessionMaterialization(requested=(("PROC-1", "DOC-1"),)),
    )

    output = build_materialization_trace_output(resolved, {})

    assert output["requested"][0]["process_number"] is None


def test_materialization_trace_registra_documento_vazio():
    paths = SessionPaths.for_session("/tmp", "1_2")
    resolved = ResolvedSession(
        paths=paths,
        meta=SessionMeta(
            created_at=1.0,
            last_access=2.0,
            ttl_seconds=60,
            doc_ids=("DOC-1",),
            processos={
                "PROC-1": {
                    "metadata": {"id_protocolo_formatado": "00000.000000/0000-00"}
                }
            },
            documentos={
                "DOC-1": {
                    "id_documento_formatado": "16016297",
                    "content_state": "empty",
                    "tokens": 0,
                }
            },
        ),
        is_new=True,
        materialization=SessionMaterialization(
            requested=(("PROC-1", "DOC-1"),),
            manifest_after=("DOC-1",),
            registered=("DOC-1",),
            added=("DOC-1",),
            materialized=("DOC-1",),
            empty=("DOC-1",),
        ),
    )
    fetches = {
        "DOC-1": DocumentFetchTelemetry(
            document_id="DOC-1",
            source="sei",
            duration_ms=3.5,
            status="empty",
            bytes=0,
        )
    }

    output = build_materialization_trace_output(resolved, fetches)

    assert output["empty"] == ["DOC-1"]
    assert output["available"] == []
    assert output["registered"] == ["DOC-1"]
    assert output["materialized"] == ["DOC-1"]
    assert output["unavailable"] == []
    assert output["source_counts"] == {"sei": 1}
    assert output["documents"] == [
        {
            "process_id": "PROC-1",
            "process_number": "00000.000000/0000-00",
            "document_id": "DOC-1",
            "document_number": "16016297",
            "status": "empty",
            "content_reason": None,
            "source": "sei",
            "duration_ms": 3.5,
            "bytes": 0,
            "tokens": 0,
            "content_sha256": None,
        }
    ]


def test_materialization_trace_nao_classifica_indisponivel_como_materializado():
    paths = SessionPaths.for_session("/tmp", "1_2")
    resolved = ResolvedSession(
        paths=paths,
        meta=SessionMeta(
            created_at=1.0,
            last_access=2.0,
            ttl_seconds=60,
            processos={"PROC-1": {"metadata": {}}},
            documentos={
                "DOC-1": {
                    "id_documento_formatado": "16016297",
                    "content_state": "unavailable",
                    "content_reason": "binary_not_found",
                }
            },
        ),
        is_new=False,
        materialization=SessionMaterialization(
            requested=(("PROC-1", "DOC-1"),),
            manifest_before=(),
            manifest_after=("DOC-1",),
            registered=("DOC-1",),
            unavailable=("DOC-1",),
        ),
    )

    output = build_materialization_trace_output(resolved, {})

    assert output["registered"] == ["DOC-1"]
    assert output["added"] == []
    assert output["materialized"] == []
    assert output["unavailable"] == ["DOC-1"]


def test_trace_input_remove_ip_nulo():
    request = SessionStreamRequest(id_usuario=1, id_topico=2, text="analise")
    raw = '{"id_usuario":1,"id_topico":2,"text":"analise","ip":null}'

    body = json.loads(original_request_body_text(request, raw))

    assert "ip" not in body


def test_trace_input_remove_content_recursivo_dos_documentos():
    request = SessionStreamRequest(id_usuario=1, id_topico=2, text="analise")
    raw = json.dumps(
        {
            "id_usuario": 1,
            "id_topico": 2,
            "text": "analise",
            "content": "fora-do-documento",
            "id_procedimentos": [
                {
                    "id_procedimento": "PROC-1",
                    "id_documentos": [
                        {
                            "id_documento": "DOC-1",
                            "content": "segredo-sei",
                            "metadata": {
                                "content": "segredo-aninhado",
                                "safe": "preservado",
                            },
                        }
                    ],
                }
            ],
        }
    )

    body = json.loads(original_request_body_text(request, raw))
    document = body["id_procedimentos"][0]["id_documentos"][0]

    assert body["content"] == "fora-do-documento"
    assert "content" not in document
    assert "content" not in document["metadata"]
    assert document["metadata"]["safe"] == "preservado"


def test_trace_input_limita_body_sanitizado_sem_resumo_global():
    request = SessionStreamRequest(
        id_usuario=1,
        id_topico=2,
        text="P" * (MAX_LANGFUSE_PAYLOAD_CHARS + 1),
    )
    raw = request.model_dump_json(exclude_none=True)

    body = original_request_body_text(request, raw)
    root_input = encode_langfuse_json_text(body)
    metadata = {"original_request_body": f"\\{body}"}

    assert len(body.split("\n[truncado: ", 1)[0]) == MAX_LANGFUSE_PAYLOAD_CHARS
    assert body.endswith(" caracteres]")
    assert truncate_large_fields(root_input) == root_input
    assert truncate_large_fields(metadata) == metadata
    assert not isinstance(truncate_large_fields(root_input), dict)


def test_materialization_trace_nao_expoe_conteudo_preview_ou_path(tmp_path):
    paths = SessionPaths.for_session(tmp_path, "1_2")
    meta = SessionMeta(
        created_at=1.0,
        last_access=2.0,
        ttl_seconds=60,
        doc_ids=("DOC-1", "DOC-2"),
        processos={
            "PROC-1": {"metadata": {"id_protocolo_formatado": "00000.000000/0000-00"}}
        },
        documentos={
            "DOC-1": {
                "id_documento_formatado": "16016297",
                "tokens": 11,
                "preview": "SEGREDO DO DOCUMENTO",
                "arquivo": "proc_PROC-1/DOC-1.txt",
            },
            "DOC-2": {"id_documento_formatado": "16016298", "tokens": 22},
            "DOC-3": {"id_documento_formatado": "16016299"},
        },
    )
    resolved = ResolvedSession(
        paths=paths,
        meta=meta,
        is_new=False,
        total_content_tokens=33,
        materialization=SessionMaterialization(
            requested=(
                ("PROC-1", "DOC-1"),
                ("PROC-1", "DOC-2"),
                ("PROC-1", "DOC-3"),
            ),
            manifest_before=("DOC-1", "DOC-OLD"),
            manifest_after=("DOC-1", "DOC-2"),
            registered=("DOC-2",),
            added=("DOC-2",),
            materialized=("DOC-2",),
            reused=("DOC-1",),
            removed_from_manifest=("DOC-OLD",),
            unavailable=("DOC-3",),
            duration_ms=12.5,
        ),
    )
    fetches = {
        "DOC-2": DocumentFetchTelemetry(
            document_id="DOC-2",
            source="redis",
            duration_ms=3.5,
            status="available",
            bytes=123,
            content_sha256="a" * 64,
        ),
        "DOC-3": DocumentFetchTelemetry(
            document_id="DOC-3",
            source="unknown",
            duration_ms=9.0,
            status="unavailable",
        ),
    }

    output = build_materialization_trace_output(resolved, fetches)
    serialized = json.dumps(output, ensure_ascii=False)

    assert output["available"] == ["DOC-1", "DOC-2"]
    assert output["registered"] == ["DOC-2"]
    assert output["materialized"] == ["DOC-2"]
    assert output["source_counts"] == {"session_fs": 1, "redis": 1, "unknown": 1}
    assert output["removed_from_manifest"] == ["DOC-OLD"]
    assert output["files_pruned"] is False
    assert output["documents"][0]["process_number"] == "00000.000000/0000-00"
    assert output["documents"][0]["document_number"] == "16016297"
    assert output["requested"][0] == {
        "process_id": "PROC-1",
        "process_number": "00000.000000/0000-00",
        "document_id": "DOC-1",
        "document_number": "16016297",
    }
    assert "SEGREDO DO DOCUMENTO" not in serialized
    assert "preview" not in serialized
    assert "arquivo" not in serialized
    assert "proc_PROC-1/DOC-1.txt" not in serialized
