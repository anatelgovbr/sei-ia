"""Data shapes da sessão Deep Agents.

Tudo aqui é puro (sem I/O de rede). A `session_key` é a chave canônica usada em
três lugares ao mesmo tempo: nome do diretório do FilesystemBackend, `thread_id`
do checkpointer e sufixo da chave Redis de TTL.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SESSION_SCHEMA_VERSION = 1

# Manifesto da sessão. VISÍVEL ao agente (sem ponto): ele lê este arquivo no
# começo do turno para conhecer processos/documentos e os previews sem abrir tudo.
_META_FILENAME = "session.json"
_WORKSPACE_DIRNAME = "workspace"


def build_session_key(id_usuario: int, id_topico: int) -> str:
    """Chave canônica da sessão (também é o `thread_id` do checkpointer).

    Só inteiros entram, então o resultado fica sempre no charset seguro para
    diretório, `thread_id` e chave Redis.
    """
    return f"{id_usuario}_{id_topico}"


@dataclass(frozen=True)
class SessionPaths:
    """Caminhos derivados de uma sessão. `root` é o boundary do FilesystemBackend.

    Os documentos ficam em subpastas por processo (``proc_{numero}/{doc}.txt``),
    montadas pelo manager a partir de `root`.
    """

    session_key: str
    root: Path
    workspace: Path
    meta_file: Path

    @classmethod
    def for_session(cls, sessions_root: str | Path, session_key: str) -> SessionPaths:
        root = Path(sessions_root) / session_key
        return cls(
            session_key=session_key,
            root=root,
            workspace=root / _WORKSPACE_DIRNAME,
            meta_file=root / _META_FILENAME,
        )


@dataclass(frozen=True)
class SessionMeta:
    """Manifesto persistido em ``{root}/session.json`` (v1).

    `last_access` move a janela deslizante do TTL. `doc_ids` registra somente
    documentos materializados em arquivo; `requested_doc_ids` preserva todo o
    inventário lógico, inclusive conteúdo temporariamente indisponível.

    O manager mantém ``processos`` e ``documentos`` como índices internos por ID.
    ``to_json`` projeta esses índices como uma lista ordenada de processos, cada um
    com seus documentos completos e ordenados; ``from_json`` recompõe os índices a
    partir exclusivamente dessa árvore v1. Cada documento pode carregar número
    formatado, path, preview, tokens, ``content_state`` e ``content_reason``.
    Metadados e números ausentes permanecem ausentes; não são inferidos. A seção
    ``websearch`` registra o estado cumulativo e as referências do último turno;
    o histórico detalhado de fontes fica fora do payload compacto da ``read_session``.
    """

    created_at: float
    last_access: float
    ttl_seconds: int
    doc_ids: tuple[str, ...] = field(default_factory=tuple)
    requested_doc_ids: tuple[str, ...] = field(default_factory=tuple)
    processos: dict = field(default_factory=dict)
    documentos: dict = field(default_factory=dict)
    websearch: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SESSION_SCHEMA_VERSION

    def is_expired(self, now: float) -> bool:
        return (now - self.last_access) > self.ttl_seconds

    def to_dict(self) -> dict:
        """Serializa o manifesto como processos com documentos aninhados.

        Os mapas ``processos``/``documentos`` continuam sendo os índices internos
        usados pelo manager. No arquivo entregue ao agente, cada documento fica
        junto do processo pai para preservar ordem e reduzir navegação cruzada.
        """
        processos = []
        for process_id, raw_process in self.processos.items():
            process = dict(raw_process or {})
            document_ids = process.pop("documentos", ()) or ()
            documents = []
            for raw_document_id in document_ids:
                document_id = str(raw_document_id)
                entry = self.documentos.get(document_id)
                if entry is None:
                    continue
                documents.append(dict(entry))
            processos.append(
                {
                    "id_procedimento": str(process.pop("id_procedimento", process_id)),
                    **process,
                    "documentos": documents,
                }
            )
        return {
            "created_at": self.created_at,
            "last_access": self.last_access,
            "ttl_seconds": self.ttl_seconds,
            "doc_ids": list(self.doc_ids),
            "requested_doc_ids": list(self.requested_doc_ids),
            "processos": processos,
            "websearch": self.websearch,
            "schema_version": SESSION_SCHEMA_VERSION,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> SessionMeta:
        data = json.loads(raw)
        if not isinstance(data, dict):
            # O manager trata ValueError como manifesto inválido e recria a sessão.
            raise ValueError(  # noqa: TRY004
                "Manifesto da sessão v1 deve ser um objeto JSON"
            )
        if data.get("schema_version") != SESSION_SCHEMA_VERSION:
            raise ValueError("Versão de manifesto de sessão não suportada")
        if "documentos" in data:
            raise ValueError(
                "Manifesto da sessão v1 não possui índice plano de documentos"
            )

        raw_processes = data.get("processos")
        if not isinstance(raw_processes, list):
            raise ValueError(  # noqa: TRY004
                "Manifesto da sessão v1 exige processos aninhados em lista"
            )

        process_index: dict[str, dict] = {}
        document_index: dict[str, dict] = {}
        for raw_process in raw_processes:
            if not isinstance(raw_process, dict):
                raise ValueError(  # noqa: TRY004
                    "Processo inválido no manifesto da sessão v1"
                )
            process = dict(raw_process)
            process_id = str(process.get("id_procedimento") or "")
            if not process_id:
                raise ValueError(
                    "Processo sem id_procedimento no manifesto da sessão v1"
                )
            raw_documents = process.pop("documentos", None)
            if not isinstance(raw_documents, list):
                raise ValueError(  # noqa: TRY004
                    "Manifesto da sessão v1 exige documentos aninhados em cada processo"
                )
            document_ids = []
            for raw_document in raw_documents:
                if not isinstance(raw_document, dict):
                    raise ValueError(  # noqa: TRY004
                        "Documento inválido no manifesto da sessão v1"
                    )
                document = dict(raw_document)
                document_id = str(document.get("id_documento") or "")
                if not document_id:
                    raise ValueError(
                        "Documento sem id_documento no manifesto da sessão v1"
                    )
                document.setdefault("id_procedimento", process_id)
                document_index[document_id] = document
                document_ids.append(document_id)
            process_index[process_id] = {
                **process,
                "id_procedimento": process_id,
                "documentos": document_ids,
            }
        data["processos"] = process_index
        data["documentos"] = document_index
        data["doc_ids"] = tuple(data.get("doc_ids", ()))
        data["requested_doc_ids"] = tuple(
            data.get("requested_doc_ids", data["doc_ids"])
        )
        data["websearch"] = dict(data.get("websearch") or {})
        return cls(**data)
