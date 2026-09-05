"""sei_extraction exception hierarchy. No fastapi/airflow imports."""

from __future__ import annotations


class ExtractionError(Exception):
    pass


class DocumentNotFoundError(ExtractionError):
    pass


class UnsupportedFormatError(ExtractionError):
    pass


class PDFExtractionError(ExtractionError):
    pass


class OCRExtractionError(ExtractionError):
    pass


class SpreadsheetExtractionError(ExtractionError):
    pass


class OfficeExtractionError(ExtractionError):
    pass


class EmptyDocumentError(ExtractionError):
    """content_doc came back empty after fetch (TRUST_API route)."""

    pass


class PaginationNotSupportedError(ExtractionError):
    """Pages were requested for a route or extension that cannot paginate."""

    pass


class MediaTypeNotAllowedError(UnsupportedFormatError):
    """Extension is not in the ALLOWED_EXTENSIONS allowlist (maps to HTTP 415)."""

    pass
