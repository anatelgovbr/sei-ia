"""Validação compartilhada na borda dos provedores de embeddings."""

from typing import Any

from sei_ia.services.exceptions.embedding_exceptions import (
    EmptyEmbeddingInputException,
)


def first_document_id(request_json: dict[str, Any]) -> str | None:
    """Obtém apenas o primeiro ID, sem propagar listas completas em erros."""
    document_ids = request_json.get("doc_ids")
    if not isinstance(document_ids, list) or not document_ids:
        return None
    return str(document_ids[0])


def ensure_embedding_input(
    texts: object,
    document_id: str | None = None,
) -> None:
    """Bloqueia entradas vazias ou malformadas antes de qualquer chamada de rede."""
    if isinstance(texts, str):
        is_invalid = not texts.strip()
    elif isinstance(texts, list):
        is_invalid = not texts or any(
            not isinstance(text, str) or not text.strip() for text in texts
        )
    else:
        is_invalid = True

    if is_invalid:
        raise EmptyEmbeddingInputException(document_id)
