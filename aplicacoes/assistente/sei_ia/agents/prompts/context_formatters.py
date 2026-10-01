"""Formatadores do contexto SEI para prompts."""

import re
from typing import Any


def _get_value(obj: Any, attr: str, default: Any = "") -> Any:
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _metadata_to_text(metadata: Any) -> str:
    if metadata is None:
        return ""
    if isinstance(metadata, str):
        return metadata.strip()
    if isinstance(metadata, dict):
        return "\n".join(
            f"{key}: {value}" for key, value in metadata.items() if value is not None
        ).strip()
    return str(metadata).strip()


def _strip_legacy_document_wrapper(content: str) -> str:
    """Remove delimitadores legados que eram salvos junto ao conteúdo."""
    text = (content or "").strip()
    text = re.sub(
        r"^-------\s*\n"
        r"# o conteúdo do documento.*?\n"
        r"está transcrito abaixo:\s*\n"
        r"\(delimitado por \[doc_[^\]]+---\] conteúdo \[\\doc_[^\]]+---\]\)\s*\n",
        "",
        text,
        flags=re.DOTALL,
    )
    open_tag = re.match(r"\[doc_[^\]]+---\]", text)
    if not open_tag:
        return text
    close_idx = text.rfind("[\\doc_")
    if close_idx <= open_tag.end():
        return text
    return text[open_tag.end() : close_idx].strip()


def _tag_id(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z_-]", "_", str(value or "sem_id"))


def format_document_context(doc: Any) -> str:
    """Formata um documento com metadados e conteúdo em tags explícitas."""
    doc_id = _get_value(doc, "id_documento", "")
    metadata = _metadata_to_text(_get_value(doc, "metadata", ""))
    content = _strip_legacy_document_wrapper(_get_value(doc, "content", "") or "")

    return (
        f"<doc_{_tag_id(doc_id)}>\n"
        "<metadados>\n"
        f"{metadata}\n"
        "</metadados>\n"
        "<conteudo>\n"
        f"{content}\n"
        "</conteudo>\n"
        f"</doc_{_tag_id(doc_id)}>"
    )


def format_procedure_context(proc: Any) -> str:
    """Formata um procedimento com metadados e documentos aninhados."""
    proc_id = _get_value(proc, "id_procedimento", "")
    metadata = _metadata_to_text(_get_value(proc, "metadata", ""))
    documents = _get_value(proc, "id_documentos", []) or []
    formatted_docs = "\n\n".join(
        format_document_context(doc)
        for doc in documents
        if _get_value(doc, "content", None)
    )

    return (
        f"<procedimento_{_tag_id(proc_id)}>\n"
        "<metadados>\n"
        f"{metadata}\n"
        "</metadados>\n"
        "<documentos>\n"
        f"{formatted_docs}\n"
        "</documentos>\n"
        f"</procedimento_{_tag_id(proc_id)}>"
    )


def format_procedures_context(procedures: list[Any] | None) -> str:
    """Formata uma lista de procedimentos para inclusão no last_prompt."""
    return "\n\n".join(
        format_procedure_context(proc) for proc in procedures or []
    ).strip()
