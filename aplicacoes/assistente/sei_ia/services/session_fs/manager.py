"""Ciclo de vida da sessão escopada: create/resume, materialização, TTL, sweeper.

O estado da sessão é o próprio diretório. ``session.json`` (manifesto v1) guarda
``last_access`` (move a janela deslizante do TTL) e o índice de processos/documentos
com previews, que o agente lê no começo do turno. Não há Redis aqui: ler um JSON pequeno por
request é barato e o sweeper recupera sessões abandonadas. Deletar é convergente
(idempotente): apaga o diretório e a thread do checkpointer, não importa o estado
anterior. ``resolve`` também materializa o JSONL do histórico completo do tópico
(``historico_conversa.jsonl``) quando um fetcher é injetado.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import shutil
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from sei_ia.data.content_status import ContentStatus

if TYPE_CHECKING:
    import pandas as pd

from sei_ia.services.counter import token_counter
from sei_ia.services.session_fs.reference_numbers import extract_process_number
from sei_ia.services.session_fs.types import (
    SessionMeta,
    SessionPaths,
    build_session_key,
)

logger = logging.getLogger(__name__)

DocumentSource = Literal["session_fs", "redis", "sei", "unknown"]


@dataclass(frozen=True)
class SessionDocumentOutcome:
    """Resultado sanitizado de uma busca SEI para o manifesto da sessão."""

    content: str | None
    formatted_document_number: str | None
    formatted_process_number: str | None
    status: ContentStatus
    source: DocumentSource = "unknown"
    provenance: Mapping[str, object] = field(default_factory=dict)


# A tupla é mantida apenas para os fakes unitários já existentes; o router da
# sessão sempre fornece ``SessionDocumentOutcome`` para não perder o estado.
FetchDocument = Callable[[str], Awaitable[SessionDocumentOutcome | tuple[str, str]]]

# fetch_history() -> DataFrame com colunas pergunta/resposta/dth_cadastro/total_tokens.
# Injetado pelo router (wraps consulta_historico_topico_com_tokens via asyncio.to_thread),
# para o manager continuar testável offline.
FetchHistory = Callable[[], Awaitable["pd.DataFrame"]]

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")

# Carência para o sweeper: uma pasta SEM `session.json` só é varrida se estiver
# parada há mais que isto. Cobre a janela mínima entre criar a pasta e gravar o
# meta (claim) e qualquer materialização longa; abaixo disso é sessão nascendo,
# não lixo abandonado.
_SWEEP_GRACE_SECONDS = 120.0


def _safe_filename(name: str) -> str:
    cleaned = _UNSAFE_FILENAME.sub("_", name).strip("._") or "documento"
    return cleaned[:128]


def _count_jsonl_lines(path: Path) -> int:
    """Conta linhas não-vazias de um JSONL; 0 se ausente ou ilegível."""
    try:
        if not path.exists():
            return 0
        return sum(
            1
            for linha in path.read_text(encoding="utf-8").splitlines()
            if linha.strip()
        )
    except Exception:
        return 0


@dataclass(frozen=True)
class SessionMaterialization:
    """Resumo efêmero da reconciliação documental feita por ``resolve``.

    O resumo não entra no ``session.json`` e não contém conteúdo, preview ou path.
    ``registered`` descreve a entrada de IDs no inventário lógico, mesmo quando
    o conteúdo ficou indisponível. ``added``, ``refreshed`` e ``materialized``
    descrevem somente arquivos escritos com sucesso nesta resolução; conteúdo
    vazio conta como arquivo materializado e permanece separado em ``empty``.
    ``removed_from_manifest`` descreve somente a troca do inventário lógico: o
    manager atual não apaga do disco arquivos que saíram do payload.
    """

    requested: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    manifest_before: tuple[str, ...] = field(default_factory=tuple)
    manifest_after: tuple[str, ...] = field(default_factory=tuple)
    registered: tuple[str, ...] = field(default_factory=tuple)
    added: tuple[str, ...] = field(default_factory=tuple)
    refreshed: tuple[str, ...] = field(default_factory=tuple)
    materialized: tuple[str, ...] = field(default_factory=tuple)
    reused: tuple[str, ...] = field(default_factory=tuple)
    empty: tuple[str, ...] = field(default_factory=tuple)
    removed_from_manifest: tuple[str, ...] = field(default_factory=tuple)
    unavailable: tuple[str, ...] = field(default_factory=tuple)
    duration_ms: float = 0.0
    files_pruned: bool = False


@dataclass(frozen=True)
class ResolvedSession:
    paths: SessionPaths
    meta: SessionMeta
    is_new: bool
    history_turns: int = field(default=0)
    # Tokens totais do conteúdo materializado (sinal de tamanho p/ a decisão de modo,
    # fase 5). Somado das entradas do manifesto (persistido por doc no session.json),
    # então sobrevive a resume sem reler o disco. Ver session_agent/mode.py.
    total_content_tokens: int = field(default=0)
    materialization: SessionMaterialization = field(
        default_factory=SessionMaterialization
    )


class SessionDocumentMaterializationError(RuntimeError):
    """Falha sanitizada por documento usada pelo modo benchmark fail-fast."""

    def __init__(
        self,
        document_id: str,
        cause: Exception | None = None,
        *,
        category: str | None = None,
    ) -> None:
        cause_diagnostic = getattr(cause, "diagnostic", None)
        category = category or (
            cause_diagnostic.get("category")
            if isinstance(cause_diagnostic, dict)
            else "document_fetch_failed"
        )
        descriptor = {
            "category": category,
            "stage": "fetch_validate_before_write",
            "cause_type": type(cause).__name__ if cause is not None else None,
        }
        self.diagnostic = {
            "schema_version": "benchmark-document-materialization-error-v1",
            "category": category,
            "stage": "fetch_validate_before_write",
            "document_id_sha256": hashlib.sha256(document_id.encode()).hexdigest(),
            "cause_type": descriptor["cause_type"],
            "cause_fingerprint": (
                cause_diagnostic.get("fingerprint")
                if isinstance(cause_diagnostic, dict)
                else None
            ),
            "fingerprint": hashlib.sha256(
                json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "raw_persisted": False,
        }
        super().__init__(f"session document materialization failed: {category}")


class SessionManifestError(RuntimeError):
    """Estado persistido incompatível com o manifesto v1 da sessão."""


class SessionManager:
    """Dono do diretório raiz das sessões e da thread do checkpointer."""

    def __init__(
        self,
        *,
        sessions_root: str | Path,
        ttl_seconds: int,
        checkpointer,
        max_fetch_concurrency: int = 8,
        preview_chars: int = 1500,
    ) -> None:
        self._root = Path(sessions_root)
        self._ttl = ttl_seconds
        self._checkpointer = checkpointer
        self._max_fetch_concurrency = max(1, max_fetch_concurrency)
        self._preview_chars = max(0, preview_chars)

    def _paths(self, session_key: str) -> SessionPaths:
        return SessionPaths.for_session(self._root, session_key)

    @staticmethod
    def _read_meta(paths: SessionPaths) -> SessionMeta | None:
        try:
            raw = paths.meta_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            return SessionMeta.from_json(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise SessionManifestError(
                f"Manifesto da sessão {paths.session_key} inválido ou incompatível "
                "com v1; use no_cache=true para recriá-la"
            ) from exc

    @staticmethod
    def _write_meta(paths: SessionPaths, meta: SessionMeta) -> None:
        paths.meta_file.write_text(meta.to_json(), encoding="utf-8")

    async def resolve(
        self,
        id_usuario: int,
        id_topico: int,
        *,
        docs: list[tuple[str, str]],
        fetch_document: FetchDocument,
        fetch_history: FetchHistory | None = None,
        now: float | None = None,
        reset: bool = False,
        proc_metadata: dict[str, dict] | None = None,
        strict_materialization: bool = False,
        refresh_document_ids: set[str] | None = None,
    ) -> ResolvedSession:
        """Cria a sessão ou retoma a existente, garantindo os documentos no disco.

        Janela deslizante: toda resolução renova ``last_access``. Sessão expirada
        é apagada e recriada limpa. A materialização é convergente: a cada
        resolução garante no disco os documentos pedidos que ainda faltam, então
        falha transiente do SEI é retomada no request seguinte. Com ``reset=True``
        a sessão é zerada antes (dir + thread), forçando download fresco e
        histórico limpo — útil para debug. IDs em ``refresh_document_ids`` são
        rebuscados e sobrescritos mesmo quando o arquivo local já existe.
        """
        now = time.time() if now is None else now
        key = build_session_key(id_usuario, id_topico)
        paths = self._paths(key)

        if reset:
            await self.delete(key, fail_closed=True)

        existing = self._read_meta(paths)
        if existing is None and paths.root.exists():
            raise SessionManifestError(
                f"Manifesto da sessão {key} ausente; use no_cache=true para recriá-la"
            )
        if existing is not None and existing.is_expired(now):
            await self.delete(key)
            existing = None

        is_new = existing is None
        created_at = existing.created_at if existing else now
        paths.workspace.mkdir(parents=True, exist_ok=True)

        # Claim a sessão ANTES de materializar: grava o meta (last_access=now)
        # sincronamente, sem await entre o mkdir e esta escrita. A materialização
        # leva segundos; sem o claim a pasta fica sem `session.json` nesse
        # intervalo e o sweeper concorrente (mesmo loop / outros workers) a
        # varre por achar meta=None, apagando documentos no meio do download.
        # Como o event loop só troca em await, escrever aqui fecha a janela.
        # Preserva o manifesto anterior (processos/documentos) para não zerá-lo
        # no meio da materialização — só a escrita pós-materialização o atualiza.
        self._write_meta(
            paths,
            SessionMeta(
                created_at=created_at,
                last_access=now,
                ttl_seconds=self._ttl,
                doc_ids=existing.doc_ids if existing else (),
                requested_doc_ids=existing.requested_doc_ids if existing else (),
                processos=existing.processos if existing else {},
                documentos=existing.documentos if existing else {},
                websearch=existing.websearch if existing else {},
            ),
        )

        materialization_started = time.perf_counter()
        present = await self._ensure_documents(
            paths,
            docs,
            fetch_document,
            existing_documentos=existing.documentos if existing else {},
            strict_materialization=strict_materialization,
            refresh_document_ids=refresh_document_ids,
        )
        materialization_duration_ms = max(
            0.0, (time.perf_counter() - materialization_started) * 1000
        )
        documentos, processos = self._build_manifest(present, existing, proc_metadata)
        meta = SessionMeta(
            created_at=created_at,
            last_access=now,
            ttl_seconds=self._ttl,
            doc_ids=tuple(
                doc_id for doc_id, entry in documentos.items() if entry.get("arquivo")
            ),
            requested_doc_ids=tuple(
                dict.fromkeys(
                    [
                        *(existing.requested_doc_ids if existing else ()),
                        *(d for _, d in docs),
                    ]
                )
            ),
            processos=processos,
            documentos=documentos,
            websearch=existing.websearch if existing else {},
        )
        self._write_meta(paths, meta)
        if is_new:
            logger.info(
                "Sessão %s criada (%d/%d documentos)", key, len(present), len(docs)
            )
        history_turns = (
            await self._ensure_history(paths, fetch_history)
            if fetch_history is not None
            else 0
        )
        # Sinal de tamanho (fase 5): soma os tokens por doc do manifesto. Docs frescos
        # trazem `tokens` recém-contados; cache-hits reaproveitam o valor persistido no
        # session.json. Sessões v1/antigas sem o campo somam 0 nos docs faltantes
        # (degrada p/ subcontagem no resume; `no_cache`/expiração recontam do zero).
        total_content_tokens = sum(
            int(entry.get("tokens", 0) or 0) for entry in documentos.values()
        )
        requested_doc_ids = tuple(dict.fromkeys(doc_id for _, doc_id in docs))
        # Compara o inventário lógico com o inventário lógico. ``doc_ids`` só
        # contém arquivos existentes e, portanto, não pode ser usado como o
        # lado anterior da diferença: documentos indisponíveis reapareceriam
        # como ``added`` em todo resume, inclusive quando ``docs`` está vazio.
        manifest_before = tuple(
            dict.fromkeys(existing.requested_doc_ids if existing else ())
        )
        manifest_after = tuple(dict.fromkeys(meta.requested_doc_ids))
        before_set = set(manifest_before)
        after_set = set(manifest_after)
        registered = tuple(
            doc_id for doc_id in manifest_after if doc_id not in before_set
        )
        materialized_ids = tuple(
            dict.fromkeys(
                doc_id
                for _, doc_id, fresh_entry in present
                if fresh_entry is not None and fresh_entry.get("arquivo")
            )
        )
        added = tuple(doc_id for doc_id in materialized_ids if doc_id not in before_set)
        refreshed = tuple(doc_id for doc_id in materialized_ids if doc_id in before_set)
        reused = tuple(
            dict.fromkeys(
                doc_id for _, doc_id, fresh_entry in present if fresh_entry is None
            )
        )
        empty = tuple(
            doc_id
            for doc_id in manifest_after
            if documentos.get(doc_id, {}).get("content_state") == "empty"
        )
        materialization = SessionMaterialization(
            requested=tuple(docs),
            manifest_before=manifest_before,
            manifest_after=manifest_after,
            registered=registered,
            added=added,
            refreshed=refreshed,
            materialized=materialized_ids,
            reused=reused,
            empty=empty,
            removed_from_manifest=tuple(
                doc_id for doc_id in manifest_before if doc_id not in after_set
            ),
            unavailable=tuple(
                doc_id
                for doc_id in requested_doc_ids
                if documentos.get(doc_id, {}).get("content_state") == "unavailable"
            ),
            duration_ms=round(materialization_duration_ms, 3),
        )
        return ResolvedSession(
            paths=paths,
            meta=meta,
            is_new=is_new,
            history_turns=history_turns,
            total_content_tokens=total_content_tokens,
            materialization=materialization,
        )

    async def _ensure_history(
        self, paths: SessionPaths, fetch_history: FetchHistory
    ) -> int:
        """Materializa ``historico_conversa.jsonl`` com o histórico completo do tópico.

        Rebusca SEMPRE do SEI (fonte da verdade) e reescreve o arquivo, para refletir
        turnos gravados pelo frontend desde a última materialização — o cache não pode
        ficar defasado. Em falha de busca ou gravação, preserva o JSONL anterior se
        houver. Degradação graciosa: nunca propaga exceção.
        """
        jsonl = paths.root / "historico_conversa.jsonl"
        try:
            df = await fetch_history()
        except Exception:
            logger.warning(
                "Falha ao buscar histórico do tópico %s; mantém JSONL anterior",
                paths.session_key,
                exc_info=True,
            )
            return _count_jsonl_lines(jsonl)

        if df.empty:
            return _count_jsonl_lines(jsonl)

        try:
            df = df.sort_values("dth_cadastro")
            linhas = []
            for _, row in df.iterrows():
                dth = row["dth_cadastro"]
                dth_str = dth.isoformat() if hasattr(dth, "isoformat") else str(dth)
                linhas.append(
                    json.dumps(
                        {
                            "pergunta": row["pergunta"],
                            "resposta": row["resposta"],
                            "dth_cadastro": dth_str,
                            "total_tokens": int(row["total_tokens"]),
                        },
                        ensure_ascii=False,
                    )
                )

            jsonl.write_text("\n".join(linhas) + "\n", encoding="utf-8")
            return len(linhas)
        except Exception:
            logger.warning(
                "Falha ao gravar histórico em %s; mantém JSONL anterior",
                paths.session_key,
                exc_info=True,
            )
            return _count_jsonl_lines(jsonl)

    async def _ensure_documents(
        self,
        paths: SessionPaths,
        docs: list[tuple[str, str]],
        fetch_document: FetchDocument,
        *,
        existing_documentos: dict[str, dict],
        strict_materialization: bool,
        refresh_document_ids: set[str] | None,
    ) -> list[tuple[str, str, dict | None]]:
        """Garante no disco cada doc pedido e rebusca os marcados para refresh.

        Cada doc é ``(id_procedimento, id_documento)`` e vai para
        ``proc_{numero}/{id_documento}.txt``. Busca em paralelo os ausentes e os
        IDs de ``refresh_document_ids``, limitada por um semáforo. Todo documento
        pedido ganha uma entrada no manifesto: conteúdo vazio é ``empty`` e uma
        falha de leitura é ``unavailable``. Devolve, por documento pedido, a tupla
        ``(proc, doc_id, fresh_entry | None)``: ``fresh_entry`` é o dict de
        manifesto do doc recém-buscado (com ``id_documento_formatado`` e
        ``preview``); ``None`` marca um doc já no disco (não rebuscado), cuja
        entry o ``resolve`` reaproveita do manifesto anterior.
        """
        sem = asyncio.Semaphore(self._max_fetch_concurrency)
        refresh_document_ids = refresh_document_ids or set()

        async def ensure_one(proc: str, doc_id: str) -> tuple[str, str, dict | None]:
            proc_dir = paths.root / f"proc_{_safe_filename(proc)}"
            target = proc_dir / f"{_safe_filename(doc_id)}.txt"
            arquivo = f"proc_{_safe_filename(proc)}/{_safe_filename(doc_id)}.txt"

            def discard_stale_refresh() -> None:
                if doc_id in refresh_document_ids:
                    target.unlink(missing_ok=True)

            previous_entry = existing_documentos.get(doc_id, {})
            previous_state = (
                previous_entry.get("content_state")
                if isinstance(previous_entry, dict)
                else None
            )
            if (
                doc_id not in refresh_document_ids
                and target.exists()
                and previous_state in {"available", "empty"}
            ):
                return (proc, doc_id, None)  # já presente: resolve reaproveita
            async with sem:
                try:
                    raw_outcome = await fetch_document(doc_id)
                except Exception as exc:
                    discard_stale_refresh()
                    logger.warning(
                        "Falha ao materializar documento %s (proc %s) na sessão %s",
                        doc_id,
                        proc,
                        paths.session_key,
                        exc_info=True,
                    )
                    if strict_materialization:
                        raise SessionDocumentMaterializationError(doc_id, exc) from exc
                    return (
                        proc,
                        doc_id,
                        self._unavailable_entry(
                            proc,
                            doc_id,
                            ContentStatus.unavailable("download_failed"),
                        ),
                    )
            outcome = self._normalize_document_outcome(raw_outcome)
            if outcome.status.state == "unavailable":
                discard_stale_refresh()
                if strict_materialization:
                    raise SessionDocumentMaterializationError(
                        doc_id, category=str(outcome.status.reason)
                    )
                return (
                    proc,
                    doc_id,
                    self._unavailable_entry(proc, doc_id, outcome.status, outcome),
                )
            content = outcome.content
            if content is None:
                discard_stale_refresh()
                if strict_materialization:
                    raise SessionDocumentMaterializationError(doc_id)
                return (
                    proc,
                    doc_id,
                    self._unavailable_entry(
                        proc,
                        doc_id,
                        ContentStatus.unavailable("extraction_failed"),
                        outcome,
                    ),
                )
            proc_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            formatted_id = outcome.formatted_document_number
            fresh_entry = {
                "id_documento": doc_id,
                "id_documento_formatado": formatted_id,
                "id_procedimento": proc,
                "id_protocolo_formatado": outcome.formatted_process_number,
                "arquivo": arquivo,
                "preview": content[: self._preview_chars],
                # tokens do conteúdo, contados UMA vez sobre o texto já em mãos (sem
                # releitura de disco) e persistidos no manifesto: o resume soma daqui.
                "tokens": token_counter(content),
                "content_state": outcome.status.state,
                "content_reason": outcome.status.reason,
            }
            return (proc, doc_id, fresh_entry)

        tasks = [asyncio.create_task(ensure_one(p, d)) for p, d in docs]
        try:
            results = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return results

    @staticmethod
    def _normalize_document_outcome(
        raw: SessionDocumentOutcome | tuple[str, str],
    ) -> SessionDocumentOutcome:
        if isinstance(raw, SessionDocumentOutcome):
            return raw
        content, formatted_document_number = raw
        if content is None:
            return SessionDocumentOutcome(
                content=None,
                formatted_document_number=None,
                formatted_process_number=None,
                status=ContentStatus.unavailable("extraction_failed"),
            )
        return SessionDocumentOutcome(
            content=content,
            formatted_document_number=str(formatted_document_number or "").strip()
            or None,
            formatted_process_number=None,
            status=(
                ContentStatus.empty("no_text_extracted")
                if content == ""
                else ContentStatus.available()
            ),
        )

    @staticmethod
    def _unavailable_entry(
        proc: str,
        doc_id: str,
        status: ContentStatus,
        outcome: SessionDocumentOutcome | None = None,
    ) -> dict:
        return {
            "id_documento": doc_id,
            "id_documento_formatado": (
                outcome.formatted_document_number if outcome is not None else None
            ),
            "id_procedimento": proc,
            "id_protocolo_formatado": (
                outcome.formatted_process_number if outcome is not None else None
            ),
            "arquivo": None,
            "preview": "",
            "tokens": 0,
            "content_state": status.state,
            "content_reason": status.reason,
        }

    @staticmethod
    def _build_manifest(
        present: list[tuple[str, str, dict | None]],
        existing: SessionMeta | None,
        proc_metadata: dict[str, dict] | None = None,
    ) -> tuple[dict, dict]:
        """Monta ``documentos`` e ``processos`` do manifesto a partir dos pedidos.

        Para cada doc presente usa a entry fresca (recém-buscada) quando há; senão
        reaproveita a entry do manifesto anterior (doc já no disco, não rebuscado).
        Cada ``processos[id]`` ganha ``metadata`` com o dict que o frontend mandou
        (``proc_metadata``); quando a continuidade não o repete, preserva o
        metadata já persistido da sessão. Sem nenhum dos dois, fica ``{}``;
        números formatados são opcionais nas projeções de prompt e telemetria.
        """
        prev_docs = existing.documentos if existing else {}
        prev_processes = existing.processos if existing else {}
        proc_metadata = proc_metadata or {}
        # A sessão é acumulativa. Começamos pela árvore persistida para que um
        # turno sem documentos (multiturn) ou com apenas documentos novos nunca
        # descarte processos, arquivos ou estados já resolvidos.
        documentos: dict = {
            document_id: dict(entry)
            for document_id, entry in prev_docs.items()
            if isinstance(entry, dict)
        }
        processos: dict = {}
        for process_id, raw_process in prev_processes.items():
            if not isinstance(raw_process, dict):
                continue
            process = dict(raw_process)
            process["id_procedimento"] = str(
                process.get("id_procedimento") or process_id
            )
            process["documentos"] = list(process.get("documentos") or ())
            processos[str(process_id)] = process

        for proc, doc_id, fresh_entry in present:
            entry = fresh_entry if fresh_entry is not None else prev_docs.get(doc_id)
            if entry is not None:
                documentos[doc_id] = dict(entry)
            if proc not in processos:
                processos[proc] = {
                    "id_procedimento": proc,
                    "documentos": [],
                    "metadata": {},
                }
            bucket = processos[proc]
            supplied_metadata = proc_metadata.get(proc) or {}
            previous_metadata = bucket.get("metadata") or {}
            if supplied_metadata:
                bucket["metadata"] = dict(supplied_metadata)
            elif not isinstance(previous_metadata, dict):
                bucket["metadata"] = {}
            if entry is not None:
                formatted_process_number = str(
                    entry.get("id_protocolo_formatado") or ""
                ).strip()
                metadata = bucket.get("metadata") or {}
                if formatted_process_number and not extract_process_number(metadata):
                    bucket["metadata"] = {
                        **metadata,
                        "id_protocolo_formatado": formatted_process_number,
                    }
            if doc_id not in bucket["documentos"]:
                bucket["documentos"].append(doc_id)
        return documentos, processos

    def persist_websearch(
        self, resolved: ResolvedSession, websearch: dict[str, Any]
    ) -> None:
        """Atualiza somente a seção websearch do manifesto já materializado."""
        current = self._read_meta(resolved.paths) or resolved.meta
        self._write_meta(
            paths=resolved.paths, meta=replace(current, websearch=websearch)
        )

    async def delete(self, session_key: str, *, fail_closed: bool = False) -> None:
        """Apaga a sessão, propagando falhas quando a operação é obrigatória."""
        paths = self._paths(session_key)
        if paths.root.exists():
            shutil.rmtree(paths.root, ignore_errors=not fail_closed)
        try:
            await self._checkpointer.adelete_thread(session_key)
        except Exception:
            if fail_closed:
                raise
            logger.warning(
                "Falha ao apagar thread %s do checkpointer", session_key, exc_info=True
            )

    async def sweep_once(self, *, now: float | None = None) -> int:
        """Apaga sessões expiradas e lixo sem manifesto. Retorna quantas."""
        now = time.time() if now is None else now
        if not self._root.exists():
            return 0
        removed = 0
        for child in self._root.iterdir():
            if not child.is_dir():
                continue
            try:
                meta = self._read_meta(self._paths(child.name))
            except SessionManifestError:
                logger.warning(
                    "Sessão %s tem manifesto incompatível; preservada para recuperação explícita",
                    child.name,
                )
                continue
            if meta is None:
                # Sem meta: só lixo se parado há mais que a carência. Uma sessão
                # nascendo (claim + materialização) tem mtime recente — não reapar.
                try:
                    if now - child.stat().st_mtime < _SWEEP_GRACE_SECONDS:
                        continue
                except OSError:
                    continue
                await self.delete(child.name)
                removed += 1
            elif meta.is_expired(now):
                await self.delete(child.name)
                removed += 1
        if removed:
            logger.info("Sweeper removeu %d sessão(ões) expirada(s)", removed)
        return removed
