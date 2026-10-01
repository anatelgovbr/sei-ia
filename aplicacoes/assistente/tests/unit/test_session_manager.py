"""Ciclo de vida da sessão escopada (create/resume/sliding-TTL/expire/sweep)."""

import json

import pytest

from sei_ia.data.cache_policy import CachePolicy
from sei_ia.data.content_status import ContentStatus
from sei_ia.services.session_fs.manager import (
    SessionDocumentMaterializationError,
    SessionDocumentOutcome,
    SessionManager,
    SessionManifestError,
    _safe_filename,
)
from sei_ia.services.session_fs.types import SessionDocumentPlan, SessionDocumentSpec


class _FakeCheckpointer:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


class _FailingCheckpointer:
    async def adelete_thread(self, thread_id: str) -> None:
        raise RuntimeError(f"falha ao apagar {thread_id}")


def _outcome(
    plan: SessionDocumentPlan,
    content: str | None,
    formatted_document_number: str | None = None,
    *,
    status: ContentStatus | None = None,
    formatted_process_number: str | None = None,
    cache_policy: CachePolicy | None = None,
) -> SessionDocumentOutcome:
    return SessionDocumentOutcome(
        content=content,
        formatted_document_number=formatted_document_number,
        formatted_process_number=formatted_process_number,
        status=status or ContentStatus.available(),
        cache_policy=cache_policy or plan.cache_policy_on_failure or "S",
    )


async def _fetch(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
    return _outcome(
        plan,
        f"conteudo de {plan.document_id}",
        f"DOC-{plan.document_id}",
    )


def _docs(
    ids: list[str],
    proc: str = "P",
    cache_policy: CachePolicy | None = "S",
    download_ext: bool | None = None,
    pag_doc_init: int | None = None,
    pag_doc_end: int | None = None,
) -> list[SessionDocumentSpec]:
    return [
        SessionDocumentSpec(
            process_id=proc,
            document_id=document_id,
            download_ext=download_ext,
            requested_cache_policy=cache_policy,
            pag_doc_init=pag_doc_init,
            pag_doc_end=pag_doc_end,
        )
        for document_id in ids
    ]


def _proc_files(res, proc: str = "P") -> list[str]:
    proc_dir = res.paths.root / f"proc_{proc}"
    return sorted(p.name for p in proc_dir.iterdir()) if proc_dir.exists() else []


@pytest.fixture
def manager(tmp_path):
    return SessionManager(
        sessions_root=tmp_path, ttl_seconds=60, checkpointer=_FakeCheckpointer()
    )


@pytest.mark.asyncio
async def test_cria_sessao_e_materializa_documentos(manager):
    res = await manager.resolve(
        42, 123, docs=_docs(["7", "9"]), fetch_document=_fetch, now=1000.0
    )
    assert res.is_new
    assert res.paths.root.name == "42_123"
    # documentos em proc_P/{id}.txt
    assert _proc_files(res) == ["7.txt", "9.txt"]
    assert (res.paths.root / "proc_P" / "7.txt").read_text() == "conteudo de 7"
    assert res.meta.doc_ids == ("7", "9")
    assert res.materialization.registered == ("7", "9")
    assert res.materialization.added == ("7", "9")
    assert res.materialization.materialized == ("7", "9")
    assert res.paths.workspace.is_dir()


@pytest.mark.asyncio
async def test_resume_dentro_do_ttl_nao_recria(manager):
    await manager.resolve(42, 123, docs=_docs(["7"]), fetch_document=_fetch, now=1000.0)
    res = await manager.resolve(
        42, 123, docs=_docs(["7"]), fetch_document=_fetch, now=1030.0
    )
    assert not res.is_new
    assert res.meta.last_access == 1030.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "manifest",
    [
        None,
        {
            "created_at": 1.0,
            "last_access": 2.0,
            "ttl_seconds": 60,
            "doc_ids": ["D1"],
            "processos": {"P": {"documentos": ["D1"]}},
            "documentos": {"D1": {"id_documento": "D1"}},
            "schema_version": 1,
        },
    ],
    ids=["sem_manifesto", "manifesto_plano"],
)
async def test_estado_persistido_sem_manifesto_v1_falha_fechado(
    manager, tmp_path, manifest
):
    session_root = tmp_path / "42_123"
    legacy_file = session_root / "proc_P" / "legacy.txt"
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_text("estado legado", encoding="utf-8")
    if manifest is not None:
        (session_root / "session.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    fetched: list[str] = []

    async def fetch_document(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        fetched.append(plan.document_id)
        return await _fetch(plan)

    with pytest.raises(SessionManifestError, match="no_cache=true"):
        await manager.resolve(
            42,
            123,
            docs=_docs(["D1"]),
            fetch_document=fetch_document,
            now=1000.0,
        )

    assert legacy_file.read_text(encoding="utf-8") == "estado legado"
    assert fetched == []
    assert manager._checkpointer.deleted == []


@pytest.mark.asyncio
async def test_manifesto_v1_sem_politica_e_revalidado_e_migrado(manager, tmp_path):
    session_root = tmp_path / "42_123"
    document_file = session_root / "proc_P" / "D1.txt"
    document_file.parent.mkdir(parents=True)
    document_file.write_text("conteudo antigo", encoding="utf-8")
    (session_root / "session.json").write_text(
        json.dumps(
            {
                "created_at": 1.0,
                "last_access": 1.0,
                "ttl_seconds": 60,
                "doc_ids": ["D1"],
                "requested_doc_ids": ["D1"],
                "processos": [
                    {
                        "id_procedimento": "P",
                        "metadata": {},
                        "documentos": [
                            {
                                "id_documento": "D1",
                                "id_procedimento": "P",
                                "arquivo": "proc_P/D1.txt",
                                "preview": "conteudo antigo",
                                "tokens": 2,
                                "content_state": "available",
                                "content_reason": None,
                            }
                        ],
                    }
                ],
                "websearch": {},
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    async def fetch_fresh(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        calls.append(plan.document_id)
        return _outcome(plan, "conteudo atual", cache_policy="S")

    resolved = await manager.resolve(
        42,
        123,
        docs=[],
        fetch_document=fetch_fresh,
        now=10.0,
    )

    assert calls == ["D1"]
    assert resolved.meta.schema_version == 2
    assert resolved.meta.documentos["D1"]["sin_armazena_cache"] == "S"
    assert document_file.read_text(encoding="utf-8") == "conteudo atual"


@pytest.mark.asyncio
async def test_resume_preserva_numero_formatado_do_processo(manager):
    first = await manager.resolve(
        42,
        123,
        docs=_docs(["7"]),
        fetch_document=_fetch,
        proc_metadata={"P": {"id_protocolo_formatado": "00000.000042/2026-01"}},
        now=1000.0,
    )
    second = await manager.resolve(
        42,
        123,
        docs=_docs(["7", "9"]),
        fetch_document=_fetch,
        proc_metadata={"P": {}},
        now=1010.0,
    )

    assert first.meta.processos["P"]["metadata"] == {
        "id_protocolo_formatado": "00000.000042/2026-01"
    }
    assert second.meta.processos["P"]["metadata"] == {
        "id_protocolo_formatado": "00000.000042/2026-01"
    }


@pytest.mark.asyncio
async def test_manifesto_preserva_metadata_documental_na_criacao_refresh_e_resume(
    manager,
):
    async def fetch_with(content: str, metadata: dict | None) -> SessionDocumentOutcome:
        return SessionDocumentOutcome(
            content=content,
            formatted_document_number="DOC-7",
            formatted_process_number="00000.000042/2026-01",
            status=ContentStatus.available(),
            source="sei",
            metadata=metadata,
        )

    first = await manager.resolve(
        42,
        123,
        docs=_docs(["7"]),
        fetch_document=lambda _plan: fetch_with(
            "versao 1", {"tipo": "oficio", "versao": 1}
        ),
        proc_metadata={"P": {"assunto": "metadata do processo"}},
        now=1000.0,
    )
    created_payload = json.loads(first.paths.meta_file.read_text(encoding="utf-8"))
    second = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], download_ext=True),
        fetch_document=lambda _plan: fetch_with(
            "versao 2", {"tipo": "despacho", "versao": 2}
        ),
        now=1010.0,
    )
    third = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], download_ext=False),
        fetch_document=lambda _plan: fetch_with("versao 3", None),
        now=1020.0,
    )

    async def fail_if_fetched(_plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        raise AssertionError("resume não deve rebuscar documento materializado")

    resumed = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], download_ext=False),
        fetch_document=fail_if_fetched,
        now=1030.0,
    )
    payload = json.loads(resumed.paths.meta_file.read_text(encoding="utf-8"))
    process = payload["processos"][0]
    document = process["documentos"][0]

    assert first.meta.documentos["7"]["metadata"] == {
        "tipo": "oficio",
        "versao": 1,
    }
    assert created_payload["processos"][0]["metadata"] == {
        "assunto": "metadata do processo",
        "id_protocolo_formatado": "00000.000042/2026-01",
    }
    assert created_payload["processos"][0]["documentos"][0]["metadata"] == {
        "tipo": "oficio",
        "versao": 1,
    }
    assert second.meta.documentos["7"]["metadata"] == {
        "tipo": "despacho",
        "versao": 2,
    }
    assert third.meta.documentos["7"]["metadata"] == {
        "tipo": "despacho",
        "versao": 2,
    }
    assert process["metadata"] == {
        "assunto": "metadata do processo",
        "id_protocolo_formatado": "00000.000042/2026-01",
    }
    assert document["metadata"] == {"tipo": "despacho", "versao": 2}
    assert (resumed.paths.root / document["arquivo"]).read_text() == "versao 3"


@pytest.mark.asyncio
async def test_janela_deslizante_mantem_viva(manager):
    await manager.resolve(42, 123, docs=_docs(["7"]), fetch_document=_fetch, now=1000.0)
    await manager.resolve(42, 123, docs=_docs(["7"]), fetch_document=_fetch, now=1030.0)
    res = await manager.resolve(
        42, 123, docs=_docs(["7"]), fetch_document=_fetch, now=1080.0
    )
    assert not res.is_new


@pytest.mark.asyncio
async def test_expira_recria_e_apaga_thread(manager):
    await manager.resolve(
        42, 123, docs=_docs(["7", "9"]), fetch_document=_fetch, now=1000.0
    )
    res = await manager.resolve(
        42, 123, docs=_docs(["7"]), fetch_document=_fetch, now=9999.0
    )
    assert res.is_new
    assert "42_123" in manager._checkpointer.deleted
    assert _proc_files(res) == ["7.txt"]


@pytest.mark.asyncio
async def test_expiracao_mantem_cleanup_best_effort_se_checkpointer_falhar(tmp_path):
    manager = SessionManager(
        sessions_root=tmp_path,
        ttl_seconds=60,
        checkpointer=_FakeCheckpointer(),
    )
    await manager.resolve(42, 123, docs=_docs(["7"]), fetch_document=_fetch, now=1000.0)
    manager._checkpointer = _FailingCheckpointer()

    res = await manager.resolve(
        42,
        123,
        docs=_docs(["7"]),
        fetch_document=_fetch,
        now=9999.0,
    )

    assert res.is_new
    assert _proc_files(res) == ["7.txt"]


@pytest.mark.asyncio
async def test_sweeper_remove_expiradas(manager):
    res = await manager.resolve(
        42, 123, docs=_docs(["7"]), fetch_document=_fetch, now=1000.0
    )
    removed = await manager.sweep_once(now=9999.0)
    assert removed == 1
    assert not res.paths.root.exists()
    assert "42_123" in manager._checkpointer.deleted


@pytest.mark.asyncio
async def test_materializacao_tolera_falha_de_um_doc(manager):
    async def fetch_parcial(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        id_doc = plan.document_id
        if id_doc == "bad":
            raise RuntimeError("SEI fora do ar")
        return _outcome(plan, f"ok {id_doc}", f"DOC-{id_doc}")

    res = await manager.resolve(
        42, 123, docs=_docs(["7", "bad", "9"]), fetch_document=fetch_parcial, now=1000.0
    )
    assert _proc_files(res) == ["7.txt", "9.txt"]
    assert res.meta.doc_ids == ("7", "9")  # 'bad' não entra no presente

    with pytest.raises(SessionDocumentMaterializationError) as caught:
        await manager.resolve(
            42,
            124,
            docs=_docs(["bad"]),
            fetch_document=fetch_parcial,
            now=1000.0,
            strict_materialization=True,
        )
    assert caught.value.diagnostic["category"] == "document_fetch_failed"
    assert caught.value.diagnostic["stage"] == "fetch_validate_before_write"
    assert "bad" not in str(caught.value.diagnostic)


@pytest.mark.asyncio
async def test_materializacao_preserva_documento_indisponivel_no_manifesto(manager):
    """Uma falha de conteúdo não pode apagar a identidade pedida pelo cliente."""

    async def fetch_indisponivel(_plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        raise RuntimeError("SEI indisponível")

    resolved = await manager.resolve(
        42,
        123,
        docs=_docs(["indisponivel"], proc="PROC-1"),
        fetch_document=fetch_indisponivel,
        proc_metadata={"PROC-1": {"id_protocolo_formatado": "00000.000001/2026-01"}},
        now=1000.0,
    )

    assert resolved.meta.doc_ids == ()
    assert resolved.meta.requested_doc_ids == ("indisponivel",)
    assert resolved.meta.processos["PROC-1"]["documentos"] == ["indisponivel"]
    doc_indisponivel = resolved.meta.documentos["indisponivel"]
    assert doc_indisponivel["id_documento"] == "indisponivel"
    assert doc_indisponivel["id_procedimento"] == "PROC-1"
    assert doc_indisponivel["content_state"] == "unavailable"
    assert doc_indisponivel["content_reason"] == "download_failed"
    assert doc_indisponivel["arquivo"] is None
    assert resolved.materialization.registered == ("indisponivel",)
    assert resolved.materialization.added == ()
    assert resolved.materialization.materialized == ()
    assert resolved.materialization.unavailable == ("indisponivel",)
    assert _proc_files(resolved, "PROC-1") == []


@pytest.mark.asyncio
async def test_resume_sem_documentos_nao_reclassifica_indisponiveis(manager):
    async def fetch_parcial(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        id_doc = plan.document_id
        if id_doc == "bad":
            raise RuntimeError("SEI indisponível")
        return await _fetch(plan)

    primeira = await manager.resolve(
        42,
        123,
        docs=_docs(["ok", "bad"]),
        fetch_document=fetch_parcial,
        now=1000.0,
    )
    segunda = await manager.resolve(
        42,
        123,
        docs=[],
        fetch_document=fetch_parcial,
        now=1010.0,
    )

    assert primeira.materialization.registered == ("ok", "bad")
    assert primeira.materialization.added == ("ok",)
    assert primeira.materialization.materialized == ("ok",)
    assert primeira.materialization.unavailable == ("bad",)
    assert segunda.materialization.requested == ()
    assert segunda.materialization.manifest_before == ("ok", "bad")
    assert segunda.materialization.manifest_after == ("ok", "bad")
    assert segunda.materialization.registered == ()
    assert segunda.materialization.added == ()
    assert segunda.materialization.materialized == ()
    assert segunda.materialization.reused == ()


@pytest.mark.asyncio
async def test_indisponivel_preserva_numeros_obtidos_antes_do_download(manager):
    async def fetch_indisponivel(
        plan: SessionDocumentPlan,
    ) -> SessionDocumentOutcome:
        return _outcome(
            plan,
            None,
            "15961770",
            formatted_process_number="53500.071566/2020-01",
            status=ContentStatus.unavailable("binary_not_found"),
        )

    resolved = await manager.resolve(
        42,
        123,
        docs=_docs(["17859830"], proc="7214867"),
        fetch_document=fetch_indisponivel,
        now=1000.0,
    )

    doc_entry = resolved.meta.documentos["17859830"]
    assert doc_entry["id_documento"] == "17859830"
    assert doc_entry["id_documento_formatado"] == "15961770"
    assert doc_entry["id_procedimento"] == "7214867"
    assert doc_entry["id_protocolo_formatado"] == "53500.071566/2020-01"
    assert doc_entry["content_state"] == "unavailable"
    assert doc_entry["content_reason"] == "binary_not_found"
    assert doc_entry["arquivo"] is None
    assert resolved.meta.processos["7214867"]["metadata"] == {
        "id_protocolo_formatado": "53500.071566/2020-01"
    }


@pytest.mark.asyncio
async def test_documento_vazio_preserva_manifesto_metadata_e_reuso(manager):
    calls: list[str] = []

    async def fetch_vazio(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        calls.append(plan.document_id)
        return _outcome(
            plan,
            "",
            "16016297",
            status=ContentStatus.empty("no_text_extracted"),
        )

    primeira = await manager.resolve(
        42,
        123,
        docs=_docs(["vazio"], proc="PROC-1"),
        fetch_document=fetch_vazio,
        proc_metadata={"PROC-1": {"id_protocolo_formatado": "00000.000001/2026-01"}},
        now=1000.0,
    )

    assert primeira.meta.doc_ids == ("vazio",)
    assert primeira.meta.processos["PROC-1"]["metadata"] == {
        "id_protocolo_formatado": "00000.000001/2026-01"
    }
    doc_vazio = primeira.meta.documentos["vazio"]
    assert doc_vazio["id_documento"] == "vazio"
    assert doc_vazio["id_documento_formatado"] == "16016297"
    assert doc_vazio["id_procedimento"] == "PROC-1"
    assert doc_vazio["arquivo"] == "proc_PROC-1/vazio.txt"
    assert doc_vazio["content_state"] == "empty"
    assert doc_vazio["content_reason"] == "no_text_extracted"
    assert (primeira.paths.root / "proc_PROC-1/vazio.txt").read_text() == ""
    assert primeira.materialization.empty == ("vazio",)

    segunda = await manager.resolve(
        42,
        123,
        docs=_docs(["vazio"], proc="PROC-1"),
        fetch_document=fetch_vazio,
        proc_metadata={"PROC-1": {"id_protocolo_formatado": "00000.000001/2026-01"}},
        now=1010.0,
    )

    assert calls == ["vazio"]
    assert segunda.materialization.reused == ("vazio",)
    assert segunda.materialization.empty == ("vazio",)


@pytest.mark.asyncio
async def test_convergencia_retoma_doc_que_falhou_transiente(manager):
    async def fetch_falha_9(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        id_doc = plan.document_id
        if id_doc == "9":
            raise RuntimeError("SEI transiente")
        return _outcome(plan, f"ok {id_doc}", f"DOC-{id_doc}")

    r1 = await manager.resolve(
        42, 123, docs=_docs(["7", "9"]), fetch_document=fetch_falha_9, now=1000.0
    )
    assert _proc_files(r1) == ["7.txt"]
    assert r1.meta.doc_ids == ("7",)

    # resume: '9' agora funciona → materializado; '7' já presente não rebusca
    r2 = await manager.resolve(
        42, 123, docs=_docs(["7", "9"]), fetch_document=_fetch, now=1010.0
    )
    assert not r2.is_new
    assert _proc_files(r2) == ["7.txt", "9.txt"]
    assert set(r2.meta.doc_ids) == {"7", "9"}


@pytest.mark.asyncio
async def test_resolve_expoe_resumo_efemero_da_materializacao(manager):
    primeira = await manager.resolve(
        42, 123, docs=_docs(["7", "9"]), fetch_document=_fetch, now=1000.0
    )

    async def fetch_parcial(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        id_doc = plan.document_id
        if id_doc == "bad":
            raise RuntimeError("SEI indisponível")
        return _outcome(plan, f"conteudo de {id_doc}", f"DOC-{id_doc}")

    segunda = await manager.resolve(
        42,
        123,
        docs=_docs(["7", "10", "bad"]),
        fetch_document=fetch_parcial,
        now=1010.0,
    )

    assert primeira.materialization.added == ("7", "9")
    assert primeira.materialization.registered == ("7", "9")
    assert primeira.materialization.materialized == ("7", "9")
    assert primeira.materialization.reused == ()
    assert segunda.materialization.requested == (
        ("P", "7"),
        ("P", "10"),
        ("P", "bad"),
    )
    assert segunda.materialization.manifest_before == ("7", "9")
    assert segunda.materialization.manifest_after == ("7", "9", "10", "bad")
    assert segunda.materialization.registered == ("10", "bad")
    assert segunda.materialization.added == ("10",)
    assert segunda.materialization.materialized == ("10",)
    assert segunda.materialization.reused == ("7",)
    assert segunda.materialization.removed_from_manifest == ()
    assert segunda.materialization.unavailable == ("bad",)
    assert segunda.materialization.files_pruned is False
    assert (segunda.paths.root / "proc_P" / "9.txt").exists()


@pytest.mark.asyncio
async def test_documento_sem_cache_e_rematerializado_em_cada_resolucao(manager):
    contents = iter(("versao 1", "versao 2"))
    calls = []

    async def fetch_fresh(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        calls.append(plan.document_id)
        return _outcome(plan, next(contents), f"DOC-{plan.document_id}")

    first = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="N"),
        fetch_document=fetch_fresh,
        now=1000.0,
    )
    second = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="N"),
        fetch_document=fetch_fresh,
        now=1010.0,
    )

    assert calls == ["7", "7"]
    assert first.materialization.added == ("7",)
    assert first.materialization.refreshed == ()
    assert first.materialization.materialized == ("7",)
    assert second.materialization.added == ()
    assert second.materialization.refreshed == ("7",)
    assert second.materialization.materialized == ("7",)
    assert second.materialization.reused == ()
    assert (second.paths.root / "proc_P" / "7.txt").read_text() == "versao 2"


@pytest.mark.asyncio
async def test_documento_sem_cache_omitido_e_rematerializado_na_iteracao_seguinte(
    manager,
):
    contents = iter(("versao 1", "versao 2"))
    calls = []

    async def fetch_fresh(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        calls.append(plan.document_id)
        return _outcome(plan, next(contents), f"DOC-{plan.document_id}")

    first = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="N"),
        fetch_document=fetch_fresh,
        now=1000.0,
    )
    second = await manager.resolve(
        42,
        123,
        docs=[],
        fetch_document=fetch_fresh,
        now=1010.0,
    )

    assert calls == ["7", "7"]
    assert first.meta.documentos["7"]["sin_armazena_cache"] == "N"
    assert second.materialization.refreshed == ("7",)
    assert (second.paths.root / "proc_P" / "7.txt").read_text() == "versao 2"


@pytest.mark.asyncio
async def test_documento_sem_flag_herda_n_e_e_rematerializado(manager):
    calls: list[str] = []

    async def fetch_fresh(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        calls.append(plan.document_id)
        return _outcome(plan, f"versao {len(calls)}", f"DOC-{plan.document_id}")

    await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="N"),
        fetch_document=fetch_fresh,
        now=1000.0,
    )
    second = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy=None),
        fetch_document=fetch_fresh,
        now=1010.0,
    )

    assert calls == ["7", "7"]
    assert second.meta.documentos["7"]["sin_armazena_cache"] == "N"
    assert second.materialization.scheduled == (("P", "7"),)


@pytest.mark.asyncio
async def test_documento_n_omitido_continua_agendado_com_outro_documento(manager):
    calls: list[str] = []

    async def fetch_fresh(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        calls.append(plan.document_id)
        return _outcome(plan, f"conteudo {plan.document_id}")

    await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="N"),
        fetch_document=fetch_fresh,
        now=1000.0,
    )
    second = await manager.resolve(
        42,
        123,
        docs=_docs(["9"], proc="OUTRO", cache_policy="S"),
        fetch_document=fetch_fresh,
        now=1010.0,
    )

    assert calls.count("7") == 2
    assert calls.count("9") == 1
    assert second.materialization.requested == (("OUTRO", "9"),)
    assert set(second.materialization.scheduled) == {("OUTRO", "9"), ("P", "7")}


@pytest.mark.asyncio
async def test_transicao_n_para_s_exige_fetch_fresh_antes_do_reuso(manager):
    policies = iter(("N", "S"))
    calls: list[str] = []

    async def fetch_fresh(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        calls.append(plan.document_id)
        return _outcome(
            plan,
            f"versao {len(calls)}",
            cache_policy=next(policies),
        )

    await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="N"),
        fetch_document=fetch_fresh,
        now=1000.0,
    )
    second = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="S"),
        fetch_document=fetch_fresh,
        now=1010.0,
    )
    third = await manager.resolve(
        42,
        123,
        docs=[],
        fetch_document=fetch_fresh,
        now=1020.0,
    )

    assert calls == ["7", "7"]
    assert second.meta.documentos["7"]["sin_armazena_cache"] == "S"
    assert third.materialization.scheduled == ()


@pytest.mark.asyncio
async def test_falha_de_conteudo_na_transicao_para_s_preserva_n(manager):
    await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="N"),
        fetch_document=_fetch,
        now=1000.0,
    )

    async def fetch_unavailable(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        return _outcome(
            plan,
            None,
            status=ContentStatus.unavailable("download_failed"),
            cache_policy="S",
        )

    second = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="S"),
        fetch_document=fetch_unavailable,
        now=1010.0,
    )

    assert second.meta.documentos["7"]["sin_armazena_cache"] == "N"
    assert second.meta.documentos["7"]["content_state"] == "unavailable"
    assert not (second.paths.root / "proc_P" / "7.txt").exists()


@pytest.mark.asyncio
async def test_alteracao_download_ext_forca_rematerializacao(manager):
    calls: list[bool | None] = []

    async def fetch_fresh(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        calls.append(plan.download_ext)
        return _outcome(plan, f"download_ext={plan.download_ext}")

    await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="S", download_ext=False),
        fetch_document=fetch_fresh,
        now=1000.0,
    )
    second = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="S", download_ext=True),
        fetch_document=fetch_fresh,
        now=1010.0,
    )

    assert calls == [False, True]
    assert second.meta.documentos["7"]["download_ext"] is True


@pytest.mark.asyncio
async def test_transicoes_paginacao_e_reuso(manager):
    """Transições whole -> 10:11 -> outro range -> whole forçam rematerialização; range idêntico reusa."""
    plans_called: list[tuple[int | None, int | None]] = []

    async def fetch_tracked(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        plans_called.append((plan.pag_doc_init, plan.pag_doc_end))
        return _outcome(
            plan,
            f"conteudo {plan.document_id} pag {plan.pag_doc_init}-{plan.pag_doc_end}",
            f"DOC-{plan.document_id}",
        )

    # 1. Whole document (None, None)
    res1 = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="S", download_ext=True),
        fetch_document=fetch_tracked,
        now=1000.0,
    )
    assert plans_called == [(None, None)]
    assert res1.meta.documentos["7"]["pag_doc_init"] is None
    assert res1.meta.documentos["7"]["pag_doc_end"] is None
    file_p = res1.paths.root / "proc_P" / "7.txt"
    assert file_p.read_text(encoding="utf-8") == "conteudo 7 pag None-None"

    # 2. Transição whole -> 10:11 (força refresh)
    res2 = await manager.resolve(
        42,
        123,
        docs=_docs(
            ["7"],
            cache_policy="S",
            download_ext=True,
            pag_doc_init=10,
            pag_doc_end=11,
        ),
        fetch_document=fetch_tracked,
        now=1010.0,
    )
    assert plans_called == [(None, None), (10, 11)]
    assert res2.meta.documentos["7"]["pag_doc_init"] == 10
    assert res2.meta.documentos["7"]["pag_doc_end"] == 11
    assert file_p.read_text(encoding="utf-8") == "conteudo 7 pag 10-11"

    # 3. Range idêntico 10:11 (reusa sem novo fetch)
    res3 = await manager.resolve(
        42,
        123,
        docs=_docs(
            ["7"],
            cache_policy="S",
            download_ext=True,
            pag_doc_init=10,
            pag_doc_end=11,
        ),
        fetch_document=fetch_tracked,
        now=1020.0,
    )
    assert len(plans_called) == 2
    assert res3.materialization.reused == ("7",)

    # 4. Transição para outro range 10:15 (força refresh)
    res4 = await manager.resolve(
        42,
        123,
        docs=_docs(
            ["7"],
            cache_policy="S",
            download_ext=True,
            pag_doc_init=10,
            pag_doc_end=15,
        ),
        fetch_document=fetch_tracked,
        now=1030.0,
    )
    assert plans_called == [(None, None), (10, 11), (10, 15)]
    assert res4.meta.documentos["7"]["pag_doc_init"] == 10
    assert res4.meta.documentos["7"]["pag_doc_end"] == 15
    assert file_p.read_text(encoding="utf-8") == "conteudo 7 pag 10-15"

    # 5. Transição range -> whole (None, None) (força refresh)
    res5 = await manager.resolve(
        42,
        123,
        docs=_docs(
            ["7"],
            cache_policy="S",
            download_ext=True,
            pag_doc_init=None,
            pag_doc_end=None,
        ),
        fetch_document=fetch_tracked,
        now=1040.0,
    )
    assert plans_called == [(None, None), (10, 11), (10, 15), (None, None)]
    assert res5.meta.documentos["7"]["pag_doc_init"] is None
    assert res5.meta.documentos["7"]["pag_doc_end"] is None
    assert file_p.read_text(encoding="utf-8") == "conteudo 7 pag None-None"


@pytest.mark.asyncio
async def test_refresh_implicito_herda_paginacao_do_manifesto(manager):
    """Documento volátil omitido da próxima chamada herda pag_doc_init/pag_doc_end no refresh implícito."""
    plans_called: list[SessionDocumentPlan] = []

    async def fetch_tracked(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        plans_called.append(plan)
        return _outcome(
            plan,
            f"conteudo {plan.document_id}",
            f"DOC-{plan.document_id}",
        )

    # 1º turno: documento 7 tem cache_policy='N' e pag_doc_init=10, pag_doc_end=11
    await manager.resolve(
        42,
        123,
        docs=_docs(
            ["7"],
            cache_policy="N",
            download_ext=True,
            pag_doc_init=10,
            pag_doc_end=11,
        ),
        fetch_document=fetch_tracked,
        now=1000.0,
    )
    assert len(plans_called) == 1
    assert plans_called[0].pag_doc_init == 10
    assert plans_called[0].pag_doc_end == 11
    assert plans_called[0].implicit_from_manifest is False

    # 2º turno: omite documento 7 do payload, envia documento 9
    second = await manager.resolve(
        42,
        123,
        docs=_docs(["9"], cache_policy="S", download_ext=False),
        fetch_document=fetch_tracked,
        now=1010.0,
    )
    doc7_plans = [p for p in plans_called if p.document_id == "7"]
    assert len(doc7_plans) == 2
    implicit_plan = doc7_plans[1]
    assert implicit_plan.implicit_from_manifest is True
    assert implicit_plan.force_refresh is True
    assert implicit_plan.pag_doc_init == 10
    assert implicit_plan.pag_doc_end == 11
    assert second.meta.documentos["7"]["pag_doc_init"] == 10
    assert second.meta.documentos["7"]["pag_doc_end"] == 11


@pytest.mark.asyncio
async def test_manifesto_persiste_paginacao_em_documento_indisponivel(manager):
    async def fetch_fail(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        return SessionDocumentOutcome(
            content=None,
            status=ContentStatus.unavailable("download_failed"),
            cache_policy=plan.cache_policy_on_failure,
        )

    res = await manager.resolve(
        42,
        123,
        docs=_docs(
            ["7"],
            cache_policy="S",
            download_ext=True,
            pag_doc_init=10,
            pag_doc_end=11,
        ),
        fetch_document=fetch_fail,
        now=1000.0,
    )
    assert res.meta.documentos["7"]["content_state"] == "unavailable"
    assert res.meta.documentos["7"]["pag_doc_init"] == 10
    assert res.meta.documentos["7"]["pag_doc_end"] == 11


@pytest.mark.asyncio
async def test_falha_no_refresh_remove_arquivo_e_manifesto_anteriores(manager):
    first = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy="N"),
        fetch_document=_fetch,
        now=1000.0,
    )

    async def fail_refresh(_plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        raise RuntimeError("SEI indisponível")

    second = await manager.resolve(
        42,
        123,
        docs=_docs(["7"], cache_policy=None),
        fetch_document=fail_refresh,
        now=1010.0,
    )

    target = first.paths.root / "proc_P" / "7.txt"
    assert second.materialization.registered == ()
    assert second.materialization.added == ()
    assert second.materialization.refreshed == ()
    assert second.materialization.materialized == ()
    assert second.materialization.unavailable == ("7",)
    assert second.materialization.manifest_after == ("7",)
    assert second.meta.doc_ids == ()
    assert not target.exists()


@pytest.mark.asyncio
async def test_materializa_por_processo(manager):
    # docs de dois processos vão para pastas separadas
    docs = _docs(["7", "9"], proc="8116731") + _docs(["5"], proc="9000000")
    res = await manager.resolve(42, 123, docs=docs, fetch_document=_fetch, now=1000.0)
    assert sorted(p.name for p in res.paths.root.glob("proc_*")) == [
        "proc_8116731",
        "proc_9000000",
    ]
    assert (res.paths.root / "proc_8116731" / "7.txt").exists()
    assert (res.paths.root / "proc_9000000" / "5.txt").exists()
    assert set(res.meta.doc_ids) == {"7", "9", "5"}


@pytest.mark.asyncio
async def test_materializacao_paralela_respeita_semaforo(tmp_path):
    import asyncio

    active = 0
    peak = 0

    async def fetch_lento(plan: SessionDocumentPlan) -> SessionDocumentOutcome:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return _outcome(plan, f"c{plan.document_id}", f"DOC-{plan.document_id}")

    mgr = SessionManager(
        sessions_root=tmp_path,
        ttl_seconds=60,
        checkpointer=_FakeCheckpointer(),
        max_fetch_concurrency=3,
    )
    res = await mgr.resolve(
        1,
        2,
        docs=_docs([str(i) for i in range(10)]),
        fetch_document=fetch_lento,
        now=1.0,
    )
    assert len(res.meta.doc_ids) == 10
    assert peak > 1, "materialização deveria ser paralela"
    assert peak <= 3, "deveria respeitar o limite do semáforo"


@pytest.mark.asyncio
async def test_strict_materialization_aguarda_irmas_antes_de_propagar_falha(
    manager,
):
    import asyncio

    late_started = asyncio.Event()
    release_late = asyncio.Event()

    async def fetch_with_late_writer(
        plan: SessionDocumentPlan,
    ) -> SessionDocumentOutcome:
        id_doc = plan.document_id
        if id_doc == "late":
            late_started.set()
            await release_late.wait()
            return _outcome(plan, "escrita tardia", "DOC-late")
        await late_started.wait()
        raise RuntimeError("causa original")

    with pytest.raises(SessionDocumentMaterializationError) as caught:
        await manager.resolve(
            42,
            123,
            docs=_docs(["late", "bad"]),
            fetch_document=fetch_with_late_writer,
            now=1000.0,
            strict_materialization=True,
        )

    assert isinstance(caught.value.__cause__, RuntimeError)
    assert str(caught.value.__cause__) == "causa original"

    fresh = await manager.resolve(
        42,
        123,
        docs=_docs(["fresh"]),
        fetch_document=_fetch,
        now=1010.0,
        reset=True,
    )
    release_late.set()
    await asyncio.sleep(0)

    assert _proc_files(fresh) == ["fresh.txt"]


@pytest.mark.asyncio
async def test_sweeper_concorrente_nao_destroi_sessao_em_materializacao(manager):
    """Regressão: um sweep disparado durante o download não pode apagar a sessão.

    Antes do claim a pasta ficava sem ``.session.json`` enquanto materializava;
    um sweep concorrente a varria por achar meta=None e só sobreviviam os docs
    escritos depois (no real, 1 de 25). O claim grava o meta antes de baixar.
    """
    disparou = []

    async def fetch_e_dispara_sweep(
        plan: SessionDocumentPlan,
    ) -> SessionDocumentOutcome:
        if not disparou:
            disparou.append(1)
            # sweep no MEIO da materialização, com o mesmo relógio lógico
            await manager.sweep_once(now=1000.0)
        return _outcome(
            plan,
            f"conteudo de {plan.document_id}",
            f"DOC-{plan.document_id}",
        )

    res = await manager.resolve(
        42,
        123,
        docs=_docs(["7", "9", "11"]),
        fetch_document=fetch_e_dispara_sweep,
        now=1000.0,
    )
    assert _proc_files(res) == ["11.txt", "7.txt", "9.txt"]
    assert set(res.meta.doc_ids) == {"7", "9", "11"}
    assert res.paths.meta_file.exists()


@pytest.mark.asyncio
async def test_reset_zera_sessao(manager):
    await manager.resolve(
        42, 123, docs=_docs(["7", "9"]), fetch_document=_fetch, now=1000.0
    )
    resume = await manager.resolve(
        42, 123, docs=_docs(["7"]), fetch_document=_fetch, now=1010.0
    )
    assert not resume.is_new  # resume normal não recria

    nova = await manager.resolve(
        42, 123, docs=_docs(["7"]), fetch_document=_fetch, now=1020.0, reset=True
    )
    assert nova.is_new  # reset zera e recria
    assert "42_123" in manager._checkpointer.deleted  # thread apagada


@pytest.mark.asyncio
async def test_reset_falha_fechado_se_checkpointer_nao_apagar_thread(tmp_path):
    manager = SessionManager(
        sessions_root=tmp_path,
        ttl_seconds=60,
        checkpointer=_FakeCheckpointer(),
    )
    await manager.resolve(42, 123, docs=_docs(["7"]), fetch_document=_fetch, now=1000.0)
    manager._checkpointer = _FailingCheckpointer()

    with pytest.raises(RuntimeError, match="falha ao apagar 42_123"):
        await manager.resolve(
            42,
            123,
            docs=_docs(["7"]),
            fetch_document=_fetch,
            now=1010.0,
            reset=True,
        )

    assert not (tmp_path / "42_123").exists()


def test_safe_filename_remove_caracteres_perigosos():
    assert _safe_filename("../../etc/passwd") == "etc_passwd"
    assert _safe_filename("DOC 123/v2") == "DOC_123_v2"
    assert _safe_filename("") == "documento"
