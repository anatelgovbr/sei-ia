"""Extração dos números visíveis do SEI sem depender do roteador HTTP."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _process_number_from_text(value: str) -> str | None:
    for line in value.splitlines():
        if ":" not in line:
            continue
        key, candidate = (part.strip() for part in line.split(":", 1))
        if key.casefold() in {"número do processo", "numero do processo"} and candidate:
            return candidate
    return None


def extract_process_number(metadata: Any) -> str | None:
    """Extrai somente um identificador formatado de processo.

    O ID interno nunca é usado como fallback. ``description`` é aceito porque é
    o formato textual retornado pela consulta de metadados do SEI.
    """
    if isinstance(metadata, Mapping):
        for key in (
            "id_processo_formatado",
            "id_procedimento_formatado",
            "id_protocolo_formatado",
        ):
            value = metadata.get(key)
            if value not in (None, ""):
                return str(value).strip()
        description = metadata.get("description")
        if isinstance(description, str):
            return _process_number_from_text(description)
    elif isinstance(metadata, str):
        return _process_number_from_text(metadata)
    return None
