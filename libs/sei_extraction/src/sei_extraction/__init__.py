"""sei_extraction: biblioteca compartilhada de extração de documentos SEI."""

from sei_extraction.config import ExtractionConfig
from sei_extraction.document_fetch import (
    ALLOWED_EXTENSIONS,
    AUDIO_EXTENSIONS,
    HTML_EXTENSIONS,
    PAGINABLE_EXTENSIONS,
    DownloadPolicy,
    fetch_document_text,
)
from sei_extraction.exceptions import (
    DocumentNotFoundError,
    EmptyDocumentError,
    ExtractionError,
    MediaTypeNotAllowedError,
    OCRExtractionError,
    OfficeExtractionError,
    PDFExtractionError,
    PaginationNotSupportedError,
    SpreadsheetExtractionError,
    UnsupportedFormatError,
)
from sei_extraction.extract import extract_document
from sei_extraction.ports import (
    AudioTranscriber,
    SeiContentSource,
    SeiFileDownloader,
    VisionOCRClient,
)
from sei_extraction.text import clean_text, get_file_extension, html_to_markdown

__all__ = [
    # text helpers (P1)
    "clean_text",
    "get_file_extension",
    "html_to_markdown",
    # extraction
    "extract_document",
    "ExtractionConfig",
    # orchestrator (P2a)
    "fetch_document_text",
    "DownloadPolicy",
    # extension sets
    "ALLOWED_EXTENSIONS",
    "AUDIO_EXTENSIONS",
    "HTML_EXTENSIONS",
    "PAGINABLE_EXTENSIONS",
    # ports
    "SeiContentSource",
    "SeiFileDownloader",
    "AudioTranscriber",
    "VisionOCRClient",
    # exceptions
    "ExtractionError",
    "DocumentNotFoundError",
    "UnsupportedFormatError",
    "PDFExtractionError",
    "OCRExtractionError",
    "SpreadsheetExtractionError",
    "OfficeExtractionError",
    "EmptyDocumentError",
    "PaginationNotSupportedError",
    "MediaTypeNotAllowedError",
]
