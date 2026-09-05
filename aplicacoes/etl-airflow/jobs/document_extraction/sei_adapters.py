"""Adapters that wire the ETL's SEI API client to the lib's IO ports.

These two classes implement the protocols defined in ``sei_extraction.ports``
and bridge the async/sync SEI API client to the sync orchestrator
``sei_extraction.fetch_document_text``.

Async bridge rationale
----------------------
``fetch_document_text`` is synchronous (the lib has no async twin).  The ETL
calls it inside ``loop.run_in_executor``, which executes the callable in a
plain OS thread — there is no running event loop in that thread.
``asyncio.run(coro)`` is therefore safe: it creates a fresh event loop, runs
the coroutine to completion, and tears the loop down.  This mirrors the pattern
used in the assistant's sei_adapters.py (commit c0c3aa7).

No AudioTranscriber: the ETL has no audio processing path.
"""

from __future__ import annotations

import asyncio
import logging

from sei_api import SeiApiError
from sei_extraction.exceptions import DocumentNotFoundError, ExtractionError

from jobs.db_models.sei_client import sei_client

logger = logging.getLogger(__name__)

_STATUS_NOT_FOUND = 404


class SeiApiContentSource:
    """Implements ``sei_extraction.ports.SeiContentSource``.

    Wraps ``sei_client.md_ia_consulta_conteudo_documento_async``.

    Async bridge: ``asyncio.run()`` is called from a worker thread (no running
    loop) to execute the coroutine synchronously.

    The 404 discriminator lives here (adapter, not lib): a doc-not-found
    response carries only ``id_documento`` and ``content_doc=None`` — it lacks
    ``tipo_conteudo`` and ``extra_metadata``.  We raise ``DocumentNotFoundError``
    so the exception mapping in ``get_document_content`` can translate it to
    ``RuntimeError``.
    """

    def fetch_content_doc(self, id_documento: str) -> dict:
        """Return the SEI API response dict (must contain key ``content_doc``).

        SEI API errors (5xx/429/non-404) are translated to lib exceptions so the
        call-site mapping handles them, matching the downloader adapter.
        """
        try:
            api_response = asyncio.run(
                sei_client.md_ia_consulta_conteudo_documento_async(
                    id_documento=id_documento
                )
            )
        except SeiApiError as exc:
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

        return {
            "content_doc": api_response.get("content_doc"),
        }


class SeiApiFileDownloader:
    """Implements ``sei_extraction.ports.SeiFileDownloader``.

    Wraps ``sei_client.md_ia_download_arquivo_documento_externo`` (sync).
    Called directly from within the worker thread — no async bridge needed.
    """

    def download(
        self,
        id_documento: str,
        doc_extension: str,
        id_anexo: int | None = None,
    ) -> str:
        """Download the document binary and return the local file path.

        Translates SEI download errors into lib exceptions so the call-site
        mapping turns a 404 into RuntimeError and other failures into
        RuntimeError.
        """
        try:
            return sei_client.md_ia_download_arquivo_documento_externo(
                id_documento, doc_extension, id_anexo
            )
        except SeiApiError as exc:
            if getattr(exc, "status_code", None) == _STATUS_NOT_FOUND:
                raise DocumentNotFoundError(
                    f"Documento id {id_documento} não encontrado no repositório do SEI"
                ) from exc
            raise ExtractionError(
                f"Erro ao baixar o documento id {id_documento}: {exc}"
            ) from exc
