"""Ferramenta somente-leitura para navegar pelo manifesto da sessão.

A factory recebe um ``ResolvedSession`` já preparado e captura uma cópia profunda
do manifesto. A tool não relê o disco, não consulta Redis/SEI e nunca devolve o
conteúdo integral dos documentos; ela entrega apenas o catálogo necessário para o
agente escolher os paths que serão abertos por ``read_file`` ou delegados.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from langchain_core.tools import tool

TOOL_NAME = "read_session"

_UNAVAILABLE_STATES = {"indisponivel", "unavailable", "missing"}
_CONTENT_KEYS = {"content", "conteudo"}


def _snapshot_meta(resolved: Any) -> dict[str, Any]:
    """Converte e desacopla o manifesto recebido pela factory."""
    meta = getattr(resolved, "meta", resolved)
    to_dict = getattr(meta, "to_dict", None)
    if callable(to_dict):
        snapshot = to_dict()
    elif is_dataclass(meta):
        snapshot = asdict(meta)
    elif isinstance(meta, Mapping):
        snapshot = dict(meta)
    else:
        snapshot = {
            "processos": getattr(meta, "processos", []),
            "documentos": getattr(meta, "documentos", {}),
        }
    return copy.deepcopy(snapshot)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return {}


def _metadata(value: Any) -> Any:
    """Copia metadata sem permitir que conteúdo integral escape pela tool."""
    if isinstance(value, Mapping):
        return {
            str(key): _metadata(item)
            for key, item in value.items()
            if str(key).lower() not in _CONTENT_KEYS
        }
    if isinstance(value, list):
        return [_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [_metadata(item) for item in value]
    return copy.deepcopy(value)


def _process_records(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Lê a árvore ordenada do manifesto v1."""
    raw_processes = snapshot.get("processos") or []
    if not isinstance(raw_processes, list):
        raise TypeError("Manifesto da sessão v1 exige processos em lista")

    result: list[dict[str, Any]] = []
    for raw_process in raw_processes:
        process = _as_dict(raw_process)
        process_id = str(process.get("id_procedimento") or "")
        raw_documents = process.get("documentos") or []
        if not isinstance(raw_documents, list):
            raise TypeError(
                "Manifesto da sessão v1 exige documentos aninhados em lista"
            )

        documents: list[dict[str, Any]] = []
        for raw_document in raw_documents:
            document = _as_dict(raw_document)
            document_id = str(document.get("id_documento") or "")
            if not document_id:
                continue
            if not document.get("id_procedimento"):
                document["id_procedimento"] = process_id
            documents.append(_document_summary(document))

        result.append(
            {
                "id_procedimento": process_id,
                "metadata": _metadata(process.get("metadata") or {}),
                "documentos": documents,
            }
        )
    return result


def session_catalog(resolved: Any) -> list[dict[str, Any]]:
    """Retorna a mesma árvore ordenada usada pela tool e pelo modo injected."""
    return _process_records(_snapshot_meta(resolved))


def _document_summary(document: Mapping[str, Any]) -> dict[str, Any]:
    arquivo = document.get("arquivo")
    content_state = str(
        document.get("content_state")
        or ("available" if arquivo is not None else "unavailable")
    ).lower()
    estado = document.get("estado")
    if not estado:
        estado = {
            "available": "disponivel",
            "empty": "vazio",
            "unavailable": "indisponivel",
        }.get(content_state, "disponivel" if arquivo else "indisponivel")
    result: dict[str, Any] = {
        "id_documento": str(document.get("id_documento") or ""),
        "estado": str(estado),
        "content_state": content_state,
        "content_reason": document.get("content_reason"),
        "arquivo": arquivo,
        "metadata": _metadata(document.get("metadata") or {}),
        "preview": document.get("preview") or "",
        "tokens": int(document.get("tokens") or 0),
    }
    for key in (
        "id_documento_formatado",
        "id_protocolo_formatado",
        "download_ext",
        "sin_armazena_cache",
        "extracao",
        "cache",
    ):
        if key in document:
            result[key] = _metadata(document[key])
    return result


def _available(document: Mapping[str, Any]) -> bool:
    return (
        bool(document.get("arquivo"))
        and str(document.get("content_state") or "available").lower() == "available"
        and str(document.get("estado") or "disponivel").lower()
        not in _UNAVAILABLE_STATES
    )


def _summary(processes: list[dict[str, Any]]) -> dict[str, int]:
    documents = [
        document for process in processes for document in process["documentos"]
    ]
    available = sum(_available(document) for document in documents)
    return {
        "processes": len(processes),
        "documents": len(documents),
        "available": available,
        "unavailable": len(documents) - available,
        "total_tokens": sum(int(document["tokens"]) for document in documents),
    }


def _websearch_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Expõe apenas o estado útil da pesquisa web, sem o histórico de fontes."""
    websearch = snapshot.get("websearch") or {}
    if not isinstance(websearch, Mapping):
        websearch = {}
    sources = websearch.get("latest_response_sources") or []
    return {
        "searched": bool(websearch.get("searched", False)),
        "path": str(websearch.get("path") or "web/"),
        "latest_response_sources": _metadata(sources),
        "other_sources_count": len(websearch.get("other_sources") or []),
    }


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _not_found(message: str) -> str:
    return _dump({"status": "not_found", "message": message})


def make_read_session_tool(resolved: Any | None):
    """Cria ``read_session`` ligada a um snapshot imutável da sessão resolvida."""
    if resolved is None:
        return None
    snapshot = _snapshot_meta(resolved)
    processes = _process_records(snapshot)

    @tool(TOOL_NAME)
    def read_session(
        id_procedimento: str | None = None,
        id_documento: str | None = None,
    ) -> str:
        """Navega pelo catálogo documental da sessão sem abrir o conteúdo.

        Sem filtros retorna summary e todos os processos com documentos aninhados,
        metadata, preview, tokens, estado e arquivo. Use os paths retornados para
        ``read_file``. Um filtro de processo restringe a árvore; um filtro de
        documento retorna o documento e seu processo pai. Os campos
        ``id_procedimento``, ``id_documento`` e ``arquivo`` são referências
        internas para navegação: nunca os repita na resposta ao usuário; use os
        números visíveis do processo e do documento quando disponíveis.
        """
        process_filter = (id_procedimento or "").strip() or None
        document_filter = (id_documento or "").strip() or None

        if process_filter:
            selected_processes = [
                process
                for process in processes
                if process["id_procedimento"] == process_filter
            ]
            if not selected_processes:
                return _not_found(f"Processo não encontrado: {process_filter}")
        else:
            selected_processes = processes

        if document_filter:
            matches = [
                (process, document)
                for process in selected_processes
                for document in process["documentos"]
                if document["id_documento"] == document_filter
            ]
            if not matches:
                return _not_found(f"Documento não encontrado: {document_filter}")
            if len(matches) > 1:
                return _dump(
                    {
                        "status": "ambiguous",
                        "message": "O documento pertence a mais de um processo; informe id_procedimento.",
                        "matches": [
                            {
                                "id_procedimento": process["id_procedimento"],
                                "id_documento": document["id_documento"],
                            }
                            for process, document in matches
                        ],
                    }
                )
            process, document = matches[0]
            payload = {
                "status": "ok",
                "summary": _summary([process]),
                "websearch": _websearch_summary(snapshot),
                "processo": process,
                "documento": document,
            }
            return _dump(payload)

        payload = {
            "status": "ok",
            "summary": _summary(selected_processes),
            "websearch": _websearch_summary(snapshot),
            "processos": selected_processes,
        }
        return _dump(payload)

    return read_session


__all__ = ["TOOL_NAME", "make_read_session_tool", "session_catalog"]
