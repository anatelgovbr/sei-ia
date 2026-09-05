"""Montagem do bloco de documentos do MODO INJETADO (fase 6).

Lê os arquivos já materializados pelo `SessionManager` (locais e, por construção do
threshold, pequenos) e formata com o MESMO `format_procedures_context` do endpoint
clássico (importado, não copiado) — mesmos marcadores `<doc_{id}>`, logo o mesmo
contrato de citação `<doc_ID></doc_ID>` nos dois modos.

Ordem DETERMINÍSTICA: o bloco usa a mesma árvore persistida e exposta por
``read_session``, preservando a ordem do payload entre turnos para não quebrar o
prompt caching.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from sei_ia.agents.prompts.context_formatters import format_procedures_context
from sei_ia.agents.session_agent.read_session import session_catalog
from sei_ia.services.session_fs.manager import ResolvedSession
from sei_ia.services.session_fs.reference_numbers import extract_process_number

logger = logging.getLogger(__name__)


def _document_metadata_text(metadata: object) -> str:
    if not isinstance(metadata, Mapping):
        return ""
    return "".join(
        f"\n{key}: {value}" for key, value in metadata.items() if value is not None
    )


def build_injected_context(resolved: ResolvedSession) -> str:
    """Bloco `<documentos_da_sessao>` com o conteúdo integral dos documentos.

    Fonte: manifesto (`resolved.meta`) + arquivos da sessão. Documento listado no
    manifesto cujo arquivo suma do disco é PULADO com warning — não inventamos
    conteúdo; o agente ainda pode acusar a ausência via filesystem.
    """
    procedures = []
    for bucket in session_catalog(resolved):
        proc_id = bucket["id_procedimento"]
        process_number = (
            extract_process_number(bucket.get("metadata", {})) or "não disponível"
        )
        docs = []
        for entry in bucket.get("documentos", []):
            doc_id = entry["id_documento"]
            content_state = entry.get("content_state", "available")
            if content_state not in {"available", "empty", "unavailable"}:
                raise ValueError(
                    f"Documento {doc_id} com content_state inválido na sessão"
                )
            formatted_id = str(entry.get("id_documento_formatado") or "").strip()
            if content_state == "unavailable":
                content_status = "Estado do conteúdo: indisponível nesta solicitação; não infira fatos."
                content_for_context = (
                    "[Conteúdo do documento indisponível nesta solicitação. "
                    "Não infira fatos.]"
                )
            elif content_state == "empty":
                content_status = (
                    "Estado do conteúdo: documento existente, sem conteúdo textual."
                )
                content_for_context = (
                    "[Documento existente, mas sem conteúdo textual no SEI.]"
                )
            else:
                path = resolved.paths.root / str(entry.get("arquivo") or "")
                try:
                    content_for_context = path.read_text(encoding="utf-8")
                except OSError:
                    logger.warning(
                        "Modo injetado: arquivo %s do doc %s ausente na sessão %s; pulado",
                        entry.get("arquivo"),
                        doc_id,
                        resolved.paths.session_key,
                    )
                    continue
                content_status = "Estado do conteúdo: disponível."
            docs.append(
                {
                    "id_documento": doc_id,
                    "metadata": (
                        "Referências internas (somente para navegação; não repetir ao usuário):\n"
                        f"id_documento: {doc_id}\n"
                        f"id_procedimento: {proc_id}\n"
                        "Referências visíveis para a resposta:\n"
                        f"Documento SEI nº: {formatted_id or 'não disponível'}\n"
                        f"Processo/protocolo: {process_number}\n"
                        f"{content_status}"
                        f"{_document_metadata_text(entry.get('metadata'))}"
                    ),
                    "content": content_for_context,
                }
            )
        procedures.append(
            {
                "id_procedimento": proc_id,
                "metadata": bucket.get("metadata", {}),
                "id_documentos": docs,
            }
        )

    corpo = format_procedures_context(procedures)
    return f"<documentos_da_sessao>\n{corpo}\n</documentos_da_sessao>"
