"""Orchestrator for fetching and extracting SEI document text.

Extension sets and decision tree are canonical copies from the assistant app:
- EXT_PERMITIDAS (allowlist): aplicacoes/assistente/sei_ia/data/etl/extract/doc_content.py:34-55
- EXT_AUDIO, EXT_HTML, EXT_PAGINADOS: aplicacoes/assistente/sei_ia/data/etl/extract/external.py:43-49
"""

from __future__ import annotations

import enum
import logging
from pathlib import Path
from typing import Optional

from sei_extraction.config import ExtractionConfig
from sei_extraction.exceptions import (
    EmptyDocumentError,
    MediaTypeNotAllowedError,
    PaginationNotSupportedError,
    UnsupportedFormatError,
)
from sei_extraction.extract import extract_document
from sei_extraction.ports import (
    AudioTranscriber,
    SeiContentSource,
    SeiFileDownloader,
    VisionOCRClient,
)
from sei_extraction.text import clean_text, html_to_markdown

logger = logging.getLogger(__name__)

# --- Extension sets (copied verbatim from the assistant; cite lines above) ---

# Formatos suportados pelo endpoint /v1/audio/transcriptions (Whisper/OpenAI):
# mp3, mp4, mpeg, mpga, m4a, wav, webm — limite de 25 MB por arquivo.
# Os demais (ogg, flac, aac, opus, wma) dependem do modelo/proxy local.
AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    ["mp3", "mp4", "wav", "ogg", "m4a", "webm", "flac", "aac", "opus", "wma"]
)

HTML_EXTENSIONS: frozenset[str] = frozenset(["html", "htm"])

# Paginable: extensions that accept pag_ini/pag_fim (pdf) or start_sheet/end_sheet (spreadsheets).
PAGINABLE_EXTENSIONS: frozenset[str] = frozenset(
    ["pdf", "ods", "xls", "xlsb", "xlsm", "xlsx"]
)

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    [
        "pdf",
        "html",
        "htm",
        "txt",
        "csv",
        "xml",
        "ods",
        "odt",
        "odp",
        "doc",
        "docx",
        "json",
        "ppt",
        "pptx",
        "rtf",
        "xls",
        "xlsb",
        "xlsm",
        "xlsx",
        *AUDIO_EXTENSIONS,
    ]
)


class DownloadPolicy(enum.Enum):
    """Caller-computed routing signal.

    TRUST_API  — use content_doc from the SEI API (Rota A; valid for HTML/internal docs).
    FORCE_DOWNLOAD — download the binary and parse locally (Rota B; required for externals/binaries).
    """

    TRUST_API = "trust_api"
    FORCE_DOWNLOAD = "force_download"


def fetch_document_text(
    id_documento: str,
    extension: str,
    policy: DownloadPolicy,
    source: SeiContentSource,
    downloader: SeiFileDownloader,
    config: ExtractionConfig,
    ocr_client: Optional[VisionOCRClient] = None,
    audio_transcriber: Optional[AudioTranscriber] = None,
    page_range: Optional[tuple[Optional[int], Optional[int]]] = None,
) -> str:
    """Return extracted text for a SEI document.

    Args:
        id_documento: SEI document identifier.
        extension: file extension without leading dot (e.g. "pdf", "html").
        policy: caller-computed routing policy.
        source: adapter that calls the SEI API and returns {"content_doc": ...}.
        downloader: adapter that downloads the binary and returns a local path.
        config: extraction configuration (OCR thresholds, sheet limits, etc.).
        ocr_client: required when config.ocr_enabled and the PDF has scanned pages.
        audio_transcriber: required for audio extensions; if None raises UnsupportedFormatError.
        page_range: (pag_ini, pag_fim) for PDF or (start_sheet, end_sheet) for spreadsheets.
            Only valid under FORCE_DOWNLOAD. Under TRUST_API any non-None range raises
            PaginationNotSupportedError.

    Returns:
        Cleaned plain text or Markdown string.

    Raises:
        MediaTypeNotAllowedError: extension not in ALLOWED_EXTENSIONS.
        UnsupportedFormatError: audio extension but no transcriber provided.
        EmptyDocumentError: TRUST_API route returned empty content_doc.
        PaginationNotSupportedError: page_range requested on TRUST_API, or extension
            is non-paginable under FORCE_DOWNLOAD.
    """
    ext = extension.lower().lstrip(".")

    if ext not in ALLOWED_EXTENSIONS:
        raise MediaTypeNotAllowedError(ext)

    if ext in AUDIO_EXTENSIONS:
        if audio_transcriber is None:
            raise UnsupportedFormatError(
                f"Áudio (.{ext}) requer um AudioTranscriber; nenhum foi fornecido."
            )
        path = downloader.download(id_documento, ext)
        try:
            return audio_transcriber.transcribe(path, ext)
        finally:
            try:
                Path(path).unlink()
            except Exception:
                pass

    if policy is DownloadPolicy.FORCE_DOWNLOAD:
        return _download_and_parse(
            id_documento, ext, page_range, downloader, config, ocr_client
        )

    # TRUST_API path — binary downloads are not used; pagination is unsupported here.
    if page_range and (page_range[0] or page_range[1]):
        raise PaginationNotSupportedError(
            f"Paginação só é suportada com FORCE_DOWNLOAD. "
            f"Documento {id_documento} solicitado com page_range={page_range} mas policy=TRUST_API."
        )

    raw = source.fetch_content_doc(id_documento).get("content_doc")
    if raw is None or not str(raw).strip():
        raise EmptyDocumentError(id_documento)

    return html_to_markdown(raw) if ext in HTML_EXTENSIONS else clean_text(raw)


def _download_and_parse(
    id_documento: str,
    ext: str,
    page_range: Optional[tuple[Optional[int], Optional[int]]],
    downloader: SeiFileDownloader,
    config: ExtractionConfig,
    ocr_client: Optional[VisionOCRClient],
) -> str:
    pag_ini, pag_fim = page_range if page_range else (None, None)

    if (pag_ini or pag_fim) and ext not in PAGINABLE_EXTENSIONS:
        raise PaginationNotSupportedError(
            f"Extensão .{ext} não suporta paginação. "
            f"Paginação disponível para: {', '.join(sorted(PAGINABLE_EXTENSIONS))}."
        )

    path = downloader.download(id_documento, ext)
    try:
        if ext in HTML_EXTENSIONS:
            return html_to_markdown(Path(path).read_text("utf-8", errors="replace"))
        return extract_document(
            path, ext, config, ocr_client, pag_ini=pag_ini, pag_fim=pag_fim
        )
    finally:
        try:
            Path(path).unlink()
        except Exception:
            pass
