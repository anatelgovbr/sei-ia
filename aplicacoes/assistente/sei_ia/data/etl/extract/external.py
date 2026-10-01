"""Constantes de extensão e helper de exceção do fluxo de documentos.

A lógica de download e extração migrou para ``sei_extraction.fetch_document_text``.
Este módulo mantém apenas os conjuntos de extensão consumidos por ``uploads.py`` e
``metadata.py`` e o helper ``raise_http_exception``.
"""

import logging
from typing import NoReturn

from fastapi import HTTPException

logger = logging.getLogger(__name__)

EXT_PAGINADOS = ["pdf", "ods", "xls", "xlsb", "xlsm", "xlsx"]
EXT_HTML = ["html", "htm"]
EXT_DOCLING_SUPPORTED = ["docx", "pptx", "md", "asciidoc"]
EXT_PLAIN_TEXT = ["txt", "json", "csv", "xml"]
EXT_UNSTRUCTURED = ["rtf", "odt", "doc", "ppt"]
EXT_ODP = ["odp"]
EXT_AUDIO = ["mp3", "mp4", "wav", "ogg", "m4a", "webm", "flac", "aac", "opus", "wma"]


def raise_http_exception(exc_class: HTTPException, message: str) -> NoReturn:
    """Loga e lança uma exceção HTTP personalizada (workaround pylint TRY301)."""
    logger.exception(message)
    raise exc_class
