"""Adapters that wire the assistant's SEI API clients to the lib's IO ports.

These three classes implement the protocols defined in ``sei_extraction.ports``
and bridge the async SEI API client to the sync orchestrator
``sei_extraction.fetch_document_text``.

Async bridge rationale
----------------------
``fetch_document_text`` is synchronous (the lib has no async twin).  Every call
site in the assistant runs it inside ``loop.run_in_executor``, which executes the
callable in a plain OS thread — there is no running event loop in that thread.
``asyncio.run(coro)`` is therefore safe: it creates a fresh event loop, runs the
coroutine to completion, and tears the loop down.  This mirrors the pattern already
used in ``concatenate_documents.py`` before P2b for ``download_and_parse_doc``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

from sei_extraction.exceptions import DocumentNotFoundError, ExtractionError

from sei_ia.data.database.sei_client import SeiDBAPIError, sei_client
from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

logger = logging.getLogger(__name__)

_STATUS_NOT_FOUND = 404
_HASH_CHUNK_SIZE = 1024 * 1024


class SeiApiContentSource:
    """Implements ``sei_extraction.ports.SeiContentSource``.

    Wraps ``sei_client.md_ia_consulta_conteudo_documento_async``.

    Async bridge: ``asyncio.run()`` is called from a worker thread (no running
    loop) to execute the coroutine synchronously.

    The 404 discriminator lives here (adapter, not lib): a doc-not-found response
    carries only ``id_documento`` and ``content_doc=None`` — it lacks
    ``tipo_conteudo`` and ``extra_metadata``.  We raise ``DocumentNotFoundError``
    so the lib exception-to-HTTP mapping at the call site can translate it to 404.

    ``extra_metadata`` is stored as an instance attribute after each call so that
    the call site (``get_doc_from_id_async``) can surface it as part of its
    3-tuple return without a second round-trip to the API.
    """

    def __init__(self) -> None:
        self.extra_metadata: dict = {}

    def fetch_content_doc(self, id_documento: str) -> dict:
        """Return the SEI API response dict (must contain key ``content_doc``).

        Side-effect: populates ``self.extra_metadata`` with the parsed
        ``extra_metadata`` field from the API response.

        SEI API errors (5xx/429/non-404) are translated to lib exceptions so the
        call-site mapping handles them, matching the downloader adapter.
        """
        try:
            api_response = asyncio.run(
                sei_client.md_ia_consulta_conteudo_documento_async(
                    id_documento=id_documento
                )
            )
        except SeiDBAPIError as exc:
            if getattr(exc, "status_code", None) == _STATUS_NOT_FOUND:
                raise DocumentNotFoundError(
                    f"Documento id {id_documento} não foi encontrado no SEI"
                ) from exc
            raise ExtractionError(
                f"Erro ao consultar conteúdo do documento id {id_documento}: {exc}"
            ) from exc
        if "tipo_conteudo" not in api_response and "extra_metadata" not in api_response:
            msg = f"Documento id {id_documento} não foi encontrado no SEI"
            logger.error(msg)
            raise DocumentNotFoundError(msg)

        raw_extra = api_response.get("extra_metadata") or {}
        self.extra_metadata = raw_extra if isinstance(raw_extra, dict) else {}

        return {
            "content_doc": api_response.get("content_doc"),
            "extra_metadata": self.extra_metadata,
        }


class SeiApiFileDownloader:
    """Implements ``sei_extraction.ports.SeiFileDownloader``.

    Wraps ``sei_client.md_ia_download_arquivo_documento_externo`` (sync).
    Called directly from within the worker thread — no async bridge needed.
    """

    def __init__(self) -> None:
        self.last_binary_sha256: str | None = None
        self.last_binary_bytes: int | None = None

    def download(
        self,
        id_documento: str,
        doc_extension: str,
        id_anexo: int | None = None,
    ) -> str:
        """Download the document binary and return the local file path.

        Translates SEI download errors into lib exceptions so the call-site
        mapping turns a 404 into HTTP 404 and other failures into HTTP 500.
        """
        try:
            path = sei_client.md_ia_download_arquivo_documento_externo(
                id_documento, doc_extension, id_anexo
            )
            digest = hashlib.sha256()
            byte_count = 0
            with Path(path).open("rb") as binary_file:
                while True:
                    chunk = binary_file.read(_HASH_CHUNK_SIZE)
                    if not chunk:
                        break
                    digest.update(chunk)
                    byte_count += len(chunk)
            self.last_binary_sha256 = digest.hexdigest()
            self.last_binary_bytes = byte_count
            return path
        except SeiDBAPIError as exc:
            if getattr(exc, "status_code", None) == _STATUS_NOT_FOUND:
                raise DocumentNotFoundError(
                    f"Documento id {id_documento} não encontrado no repositório do SEI"
                ) from exc
            raise ExtractionError(
                f"Erro ao baixar o documento id {id_documento}: {exc}"
            ) from exc


class SeiApiAudioTranscriber:
    """Implements ``sei_extraction.ports.AudioTranscriber``.

    Wraps ``transcribe_audio_file`` (async coroutine).  Same async→sync bridge as
    ``SeiApiContentSource``: called from a worker thread, so ``asyncio.run()`` is
    safe.
    """

    def transcribe(self, file_path: str, extension: str) -> str:
        """Transcribe the audio file and return the transcript text.

        Wraps transcription failures as ExtractionError so the call-site maps
        them to HTTP 500, matching the prior download_and_transcribe_audio.
        """
        try:
            return asyncio.run(transcribe_audio_file(file_path, extension))
        except Exception as exc:
            raise ExtractionError(
                f"Erro ao transcrever o áudio ({extension}): {exc}"
            ) from exc


def make_adapters() -> tuple[
    SeiApiContentSource, SeiApiFileDownloader, SeiApiAudioTranscriber
]:
    """Return a ready-to-use (source, downloader, transcriber) triple."""
    return SeiApiContentSource(), SeiApiFileDownloader(), SeiApiAudioTranscriber()
