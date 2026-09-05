"""Ciclo de vida da sessão escopada (create/resume/sliding-TTL/expire/sweep)."""

import json

import pytest

from sei_ia.data.content_status import ContentStatus
from sei_ia.services.session_fs.manager import (
    SessionDocumentMaterializationError,
    SessionDocumentOutcome,
    SessionManager,
    SessionManifestError,
    _safe_filename,
)


class _FakeCheckpointer:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


class _FailingCheckpointer:
    async def adelete_thread(self, thread_id: str) -> None:
        raise RuntimeError(f"falha ao apagar {thread_id}")


async def _fetch(id_doc: str) -> tuple[str, str]:
    return f"conteudo de {id_doc}", f"DOC-{id_doc}"


def _docs(ids: list[str], proc: str = "P") -> list[tuple[str, str]]:
    return [(proc, i) for i in ids]


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

    async def fetch_document(document_id: str) -> tuple[str, str]:
        fetched.append(document_id)
        return await _fetch(document_id)

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
async def test_resume_preserva_numero_formatado_do_processo(manager):
    first = await manager.resolve(
        42,
        123,
        docs=_docs(["7"]),
        fetch_document=_fetch,
        proc_metadata={"P": {"id_protocolo_formatado": "00000.000000/0000-00"}},
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
        "id_protocolo_formatado": "00000.000000/0000-00"
    }
    assert second.meta.processos["P"]["metadata"] == {
        "id_protocolo_formatado": "00000.000000/0000-00"
    }


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
    async def fetch_parcial(id_doc: str) -> tuple[str, str]:
        if id_doc == "bad":
            raise RuntimeError("SEI fora do ar")
        return f"ok {id_doc}", f"DOC-{id_doc}"

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

    async def fetch_indisponivel(_id_doc: str) -> tuple[str, str]:
        raise RuntimeError("SEI indisponível")

    resolved = await manager.resolve(
        42,
        123,
        docs=_docs(["indisponivel"], proc="PROC-1"),
        fetch_document=fetch_indisponivel,
        proc_metadata={"PROC-1": {"id_protocolo_formatado": "00000.000000/0000-00"}},
        now=1000.0,
    )

    assert resolved.meta.doc_ids == ()
    assert resolved.meta.requested_doc_ids == ("indisponivel",)
    assert resolved.meta.processos["PROC-1"]["documentos"] == ["indisponivel"]
    assert resolved.meta.documentos["indisponivel"] == {
        "id_documento": "indisponivel",
        "id_documento_formatado": None,
        "id_procedimento": "PROC-1",
        "id_protocolo_formatado": None,
        "arquivo": None,
        "preview": "",
        "tokens": 0,
        "content_state": "unavailable",
        "content_reason": "download_failed",
    }
    assert resolved.materialization.registered == ("indisponivel",)
    assert resolved.materialization.added == ()
    assert resolved.materialization.materialized == ()
    assert resolved.materialization.unavailable == ("indisponivel",)
    assert _proc_files(resolved, "PROC-1") == []


@pytest.mark.asyncio
async def test_resume_sem_documentos_nao_reclassifica_indisponiveis(manager):
    async def fetch_parcial(id_doc: str) -> tuple[str, str]:
        if id_doc == "bad":
            raise RuntimeError("SEI indisponível")
        return await _fetch(id_doc)

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
    async def fetch_indisponivel(_id_doc: str) -> SessionDocumentOutcome:
        return SessionDocumentOutcome(
            content=None,
            formatted_document_number="15961770",
            formatted_process_number="00000.000000/0000-00",
            status=ContentStatus.unavailable("binary_not_found"),
            source="sei",
        )

    resolved = await manager.resolve(
        42,
        123,
        docs=_docs(["17859830"], proc="7214867"),
        fetch_document=fetch_indisponivel,
        now=1000.0,
    )

    assert resolved.meta.documentos["17859830"] == {
        "id_documento": "17859830",
        "id_documento_formatado": "15961770",
        "id_procedimento": "7214867",
        "id_protocolo_formatado": "00000.000000/0000-00",
        "arquivo": None,
        "preview": "",
        "tokens": 0,
        "content_state": "unavailable",
        "content_reason": "binary_not_found",
    }
    assert resolved.meta.processos["7214867"]["metadata"] == {
        "id_protocolo_formatado": "00000.000000/0000-00"
    }


@pytest.mark.asyncio
async def test_documento_vazio_preserva_manifesto_metadata_e_reuso(manager):
    calls: list[str] = []

    async def fetch_vazio(id_doc: str) -> tuple[str, str]:
        calls.append(id_doc)
        return "", "16016297"

    primeira = await manager.resolve(
        42,
        123,
        docs=_docs(["vazio"], proc="PROC-1"),
        fetch_document=fetch_vazio,
        proc_metadata={"PROC-1": {"id_protocolo_formatado": "00000.000000/0000-00"}},
        now=1000.0,
    )

    assert primeira.meta.doc_ids == ("vazio",)
    assert primeira.meta.processos["PROC-1"]["metadata"] == {
        "id_protocolo_formatado": "00000.000000/0000-00"
    }
    assert primeira.meta.documentos["vazio"] == {
        "id_documento": "vazio",
        "id_documento_formatado": "16016297",
        "id_procedimento": "PROC-1",
        "id_protocolo_formatado": None,
        "arquivo": "proc_PROC-1/vazio.txt",
        "preview": "",
        "tokens": 0,
        "content_state": "empty",
        "content_reason": "no_text_extracted",
    }
    assert (primeira.paths.root / "proc_PROC-1/vazio.txt").read_text() == ""
    assert primeira.materialization.empty == ("vazio",)

    segunda = await manager.resolve(
        42,
        123,
        docs=_docs(["vazio"], proc="PROC-1"),
        fetch_document=fetch_vazio,
        proc_metadata={"PROC-1": {"id_protocolo_formatado": "00000.000000/0000-00"}},
        now=1010.0,
    )

    assert calls == ["vazio"]
    assert segunda.materialization.reused == ("vazio",)
    assert segunda.materialization.empty == ("vazio",)


@pytest.mark.asyncio
async def test_convergencia_retoma_doc_que_falhou_transiente(manager):
    async def fetch_falha_9(id_doc: str) -> tuple[str, str]:
        if id_doc == "9":
            raise RuntimeError("SEI transiente")
        return f"ok {id_doc}", f"DOC-{id_doc}"

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

    async def fetch_parcial(id_doc: str) -> tuple[str, str]:
        if id_doc == "bad":
            raise RuntimeError("SEI indisponível")
        return f"conteudo de {id_doc}", f"DOC-{id_doc}"

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

    async def fetch_fresh(id_doc: str) -> tuple[str, str]:
        calls.append(id_doc)
        return next(contents), f"DOC-{id_doc}"

    first = await manager.resolve(
        42,
        123,
        docs=_docs(["7"]),
        fetch_document=fetch_fresh,
        refresh_document_ids={"7"},
        now=1000.0,
    )
    second = await manager.resolve(
        42,
        123,
        docs=_docs(["7"]),
        fetch_document=fetch_fresh,
        refresh_document_ids={"7"},
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
async def test_falha_no_refresh_remove_arquivo_e_manifesto_anteriores(manager):
    first = await manager.resolve(
        42,
        123,
        docs=_docs(["7"]),
        fetch_document=_fetch,
        refresh_document_ids={"7"},
        now=1000.0,
    )

    async def fail_refresh(_id_doc: str) -> tuple[str, str]:
        raise RuntimeError("SEI indisponível")

    second = await manager.resolve(
        42,
        123,
        docs=_docs(["7"]),
        fetch_document=fail_refresh,
        refresh_document_ids={"7"},
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
    docs = [("1000000", "7"), ("1000000", "9"), ("9000000", "5")]
    res = await manager.resolve(42, 123, docs=docs, fetch_document=_fetch, now=1000.0)
    assert sorted(p.name for p in res.paths.root.glob("proc_*")) == [
        "proc_1000000",
        "proc_9000000",
    ]
    assert (res.paths.root / "proc_1000000" / "7.txt").exists()
    assert (res.paths.root / "proc_9000000" / "5.txt").exists()
    assert set(res.meta.doc_ids) == {"7", "9", "5"}


@pytest.mark.asyncio
async def test_materializacao_paralela_respeita_semaforo(tmp_path):
    import asyncio

    active = 0
    peak = 0

    async def fetch_lento(id_doc: str) -> tuple[str, str]:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return f"c{id_doc}", f"DOC-{id_doc}"

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

    async def fetch_with_late_writer(id_doc: str) -> tuple[str, str]:
        if id_doc == "late":
            late_started.set()
            await release_late.wait()
            return "escrita tardia", "DOC-late"
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

    async def fetch_e_dispara_sweep(id_doc: str) -> tuple[str, str]:
        if not disparou:
            disparou.append(1)
            # sweep no MEIO da materialização, com o mesmo relógio lógico
            await manager.sweep_once(now=1000.0)
        return f"conteudo de {id_doc}", f"DOC-{id_doc}"

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
