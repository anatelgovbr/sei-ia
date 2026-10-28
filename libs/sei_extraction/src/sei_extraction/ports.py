"""Dependency-injection protocols for sei_extraction."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class SeiContentSource(Protocol):
    """Returns document metadata dict with at least key "content_doc": str | None.

    The adapter — not the lib — handles the SEI 404 discriminator and raises
    DocumentNotFoundError when appropriate.
    """

    def fetch_content_doc(self, id_documento: str) -> dict: ...


@runtime_checkable
class SeiFileDownloader(Protocol):
    """Downloads a SEI document binary and returns a local file path."""

    def download(
        self,
        id_documento: str,
        doc_extension: str,
        id_anexo: Optional[int] = None,
    ) -> str: ...


@runtime_checkable
class AudioTranscriber(Protocol):
    """Transcribes an audio file and returns the transcript as plain text."""

    def transcribe(self, file_path: str, extension: str) -> str: ...


@runtime_checkable
class VisionOCRClient(Protocol):
    def extract_page(self, img_base64: str, model: str) -> str: ...
