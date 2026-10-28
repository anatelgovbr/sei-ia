"""extract_document: top-level dispatcher by file extension."""

from __future__ import annotations

import logging
from typing import Optional

from sei_extraction.config import ExtractionConfig
from sei_extraction.exceptions import UnsupportedFormatError
from sei_extraction.ports import VisionOCRClient

logger = logging.getLogger(__name__)

_EXT_PDF = {"pdf"}
_EXT_SPREADSHEET = {"ods", "xls", "xlsb", "xlsm", "xlsx"}
_EXT_HTML = {"html", "htm"}
_EXT_DOCLING = {"docx", "pptx", "md", "asciidoc"}
_EXT_PLAIN_TEXT = {"txt", "json", "csv", "xml"}
_EXT_UNSTRUCTURED = {"rtf", "odt", "doc", "ppt"}
_EXT_ODP = {"odp"}


def extract_document(
    file_path: str,
    extension: str,
    config: ExtractionConfig,
    ocr_client: Optional[VisionOCRClient] = None,
    pag_ini: Optional[int] = None,
    pag_fim: Optional[int] = None,
) -> str:
    ext = extension.lower().lstrip(".")

    if ext in _EXT_PDF:
        from sei_extraction.parsers.pdf import extract_pdf

        return extract_pdf(
            file_path, config, ocr_client, pag_ini=pag_ini, pag_fim=pag_fim
        )

    if ext in _EXT_SPREADSHEET:
        from sei_extraction.parsers.spreadsheet import extract_spreadsheet

        # Spreadsheet paginates by sheet index; pag_ini/pag_fim map to start_sheet/end_sheet.
        return extract_spreadsheet(
            file_path, config, start_sheet=pag_ini, end_sheet=pag_fim
        )

    if ext in _EXT_HTML:
        from sei_extraction.parsers.office import extract_html

        return extract_html(file_path)

    if ext in _EXT_DOCLING:
        from sei_extraction.parsers.office import extract_with_docling

        return extract_with_docling(file_path)

    if ext in _EXT_PLAIN_TEXT:
        from sei_extraction.parsers.office import extract_plain_text

        result = extract_plain_text(file_path)
        return result

    if ext in _EXT_UNSTRUCTURED:
        from sei_extraction.parsers.office import extract_with_unstructured

        return extract_with_unstructured(file_path)

    if ext in _EXT_ODP:
        from sei_extraction.parsers.office import extract_odp

        return extract_odp(file_path)

    raise UnsupportedFormatError(f"Formato não suportado: {ext!r}")
