"""Tests for fetch_document_text orchestrator (P2a).

Fakes implement the ports; no network or filesystem I/O beyond tmp_path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sei_extraction.config import ExtractionConfig
from sei_extraction.document_fetch import DownloadPolicy, fetch_document_text
from sei_extraction.exceptions import (
    EmptyDocumentError,
    MediaTypeNotAllowedError,
    PaginationNotSupportedError,
    UnsupportedFormatError,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeSource:
    def __init__(self, content_doc: str | None = "some text"):
        self._content = content_doc

    def fetch_content_doc(self, id_documento: str) -> dict:
        return {"content_doc": self._content}


class FakeDownloader:
    """Writes a tiny file in tmp_path and returns its path."""

    def __init__(self, tmp_path: Path, content: bytes = b"binary"):
        self._tmp = tmp_path
        self._content = content
        self.calls: list[tuple] = []

    def download(self, id_documento: str, doc_extension: str, id_anexo=None) -> str:
        self.calls.append((id_documento, doc_extension, id_anexo))
        p = self._tmp / f"{id_documento}.{doc_extension}"
        p.write_bytes(self._content)
        return str(p)


class FakeAudioTranscriber:
    def __init__(self, result: str = "transcript text"):
        self._result = result
        self.calls: list[tuple] = []

    def transcribe(self, file_path: str, extension: str) -> str:
        self.calls.append((file_path, extension))
        return self._result


_CONFIG = ExtractionConfig()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source() -> FakeSource:
    return FakeSource()


# ---------------------------------------------------------------------------
# 1. Allowlist rejection
# ---------------------------------------------------------------------------


def test_allowlist_rejection_raises_media_type_not_allowed():
    with pytest.raises(MediaTypeNotAllowedError):
        fetch_document_text(
            "123",
            "exe",
            DownloadPolicy.TRUST_API,
            FakeSource(),
            MagicMock(),
            _CONFIG,
        )


# ---------------------------------------------------------------------------
# 2. Audio branch: calls transcriber and unlinks temp file
# ---------------------------------------------------------------------------
# Whisper API aceita: mp3, mp4, mpeg, mpga, m4a, wav, webm.
# Limite da API: 25 MB por arquivo.


@pytest.mark.parametrize(
    "ext", ["mp3", "mp4", "wav", "m4a", "webm", "ogg", "flac", "aac", "opus", "wma"]
)
def test_audio_branch_calls_transcriber_and_unlinks(tmp_path: Path, ext: str):
    downloader = FakeDownloader(tmp_path, content=b"\x00audio")
    transcriber = FakeAudioTranscriber(result="hello world")

    result = fetch_document_text(
        "42",
        ext,
        DownloadPolicy.TRUST_API,  # policy is ignored for audio
        FakeSource(),
        downloader,
        _CONFIG,
        audio_transcriber=transcriber,
    )

    assert result == "hello world"
    assert len(transcriber.calls) == 1
    assert transcriber.calls[0][1] == ext
    downloaded_path = Path(transcriber.calls[0][0])
    assert not downloaded_path.exists()


@pytest.mark.parametrize("ext", ["mp3", "mp4"])
def test_audio_branch_no_transcriber_raises(ext: str):
    with pytest.raises(UnsupportedFormatError):
        fetch_document_text(
            "42",
            ext,
            DownloadPolicy.FORCE_DOWNLOAD,
            FakeSource(),
            MagicMock(),
            _CONFIG,
            audio_transcriber=None,
        )


# ---------------------------------------------------------------------------
# 3. FORCE_DOWNLOAD + html -> html_to_markdown
# ---------------------------------------------------------------------------


def test_force_download_html_returns_markdown(tmp_path: Path):
    html_bytes = b"<p>Hello <b>world</b></p>"
    downloader = FakeDownloader(tmp_path, content=html_bytes)

    result = fetch_document_text(
        "10",
        "html",
        DownloadPolicy.FORCE_DOWNLOAD,
        FakeSource(),
        downloader,
        _CONFIG,
    )

    # html_to_markdown should return a non-empty string; exact format is the converter's concern.
    assert isinstance(result, str)
    assert len(result) > 0
    # Temp file must be gone.
    assert not (tmp_path / "10.html").exists()


# ---------------------------------------------------------------------------
# 4. FORCE_DOWNLOAD + binary (txt) -> extract_document path
# ---------------------------------------------------------------------------


def test_force_download_plain_text_calls_extract_document(tmp_path: Path):
    downloader = FakeDownloader(tmp_path, content=b"plain text content")

    result = fetch_document_text(
        "20",
        "txt",
        DownloadPolicy.FORCE_DOWNLOAD,
        FakeSource(),
        downloader,
        _CONFIG,
    )

    assert "plain text content" in result
    assert not (tmp_path / "20.txt").exists()


# ---------------------------------------------------------------------------
# 5. TRUST_API + empty content_doc -> EmptyDocumentError
# ---------------------------------------------------------------------------


def test_trust_api_empty_content_doc_raises_empty_document_error():
    source = FakeSource(content_doc="")

    with pytest.raises(EmptyDocumentError):
        fetch_document_text(
            "30",
            "pdf",
            DownloadPolicy.TRUST_API,
            source,
            MagicMock(),
            _CONFIG,
        )


def test_trust_api_none_content_doc_raises_empty_document_error():
    source = FakeSource(content_doc=None)

    with pytest.raises(EmptyDocumentError):
        fetch_document_text(
            "31",
            "txt",
            DownloadPolicy.TRUST_API,
            source,
            MagicMock(),
            _CONFIG,
        )


# ---------------------------------------------------------------------------
# 6. TRUST_API + html -> html_to_markdown
# ---------------------------------------------------------------------------


def test_trust_api_html_returns_html_to_markdown():
    source = FakeSource(content_doc="<p>Hello</p>")

    result = fetch_document_text(
        "40",
        "html",
        DownloadPolicy.TRUST_API,
        source,
        MagicMock(),
        _CONFIG,
    )

    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# 7. TRUST_API + non-html -> clean_text
# ---------------------------------------------------------------------------


def test_trust_api_non_html_returns_clean_text():
    raw = "  hello   \n\n\n\n world  "
    source = FakeSource(content_doc=raw)

    result = fetch_document_text(
        "50",
        "txt",
        DownloadPolicy.TRUST_API,
        source,
        MagicMock(),
        _CONFIG,
    )

    # clean_text collapses whitespace and strips; should not start/end with spaces.
    assert result == result.strip()
    assert "hello" in result
    assert "world" in result


# ---------------------------------------------------------------------------
# 8. TRUST_API + page_range -> PaginationNotSupportedError
# ---------------------------------------------------------------------------


def test_trust_api_with_page_range_raises_pagination_not_supported():
    source = FakeSource(content_doc="<p>text</p>")

    with pytest.raises(PaginationNotSupportedError):
        fetch_document_text(
            "60",
            "pdf",
            DownloadPolicy.TRUST_API,
            source,
            MagicMock(),
            _CONFIG,
            page_range=(1, 5),
        )


# ---------------------------------------------------------------------------
# 9. FORCE_DOWNLOAD + non-paginable ext + page_range -> PaginationNotSupportedError
# ---------------------------------------------------------------------------


def test_force_download_non_paginable_ext_with_page_range_raises(tmp_path: Path):
    downloader = FakeDownloader(tmp_path, content=b"<p>doc</p>")

    with pytest.raises(PaginationNotSupportedError):
        fetch_document_text(
            "70",
            "docx",
            DownloadPolicy.FORCE_DOWNLOAD,
            FakeSource(),
            downloader,
            _CONFIG,
            page_range=(1, 3),
        )
