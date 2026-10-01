"""Unit tests for ETL adapter IO wiring (jobs.document_extraction.sei_adapters).

Mirror of aplicacoes/assistente/tests/unit/test_sei_adapters.py adapted for the
ETL adapters: SeiApiError instead of SeiDBAPIError, no AudioTranscriber, no
extra_metadata on SeiApiContentSource.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sei_api import SeiApiError
from sei_extraction.exceptions import DocumentNotFoundError, ExtractionError

from jobs.document_extraction.sei_adapters import (
    SeiApiContentSource,
    SeiApiFileDownloader,
)

ADAPTERS = "jobs.document_extraction.sei_adapters"


class TestSeiApiFileDownloader:
    def test_returns_path_on_success(self):
        with patch(
            f"{ADAPTERS}.sei_client.md_ia_download_arquivo_documento_externo",
            return_value="/tmp/doc.pdf",
        ):
            assert SeiApiFileDownloader().download("doc-1", "pdf") == "/tmp/doc.pdf"

    def test_404_maps_to_document_not_found(self):
        with (
            patch(
                f"{ADAPTERS}.sei_client.md_ia_download_arquivo_documento_externo",
                side_effect=SeiApiError(404, "não encontrado"),
            ),
            pytest.raises(DocumentNotFoundError),
        ):
            SeiApiFileDownloader().download("doc-1", "pdf")

    def test_non_404_maps_to_extraction_error(self):
        with (
            patch(
                f"{ADAPTERS}.sei_client.md_ia_download_arquivo_documento_externo",
                side_effect=SeiApiError(500, "erro interno"),
            ),
            pytest.raises(ExtractionError),
        ):
            SeiApiFileDownloader().download("doc-1", "pdf")


class TestSeiApiContentSource:
    def test_returns_content_doc_on_success(self):
        resp = {
            "content_doc": "texto do doc",
            "tipo_conteudo": "html",
            "extra_metadata": {"k": 1},
        }
        with patch(
            f"{ADAPTERS}.sei_client.md_ia_consulta_conteudo_documento_async",
            new=AsyncMock(return_value=resp),
        ):
            source = SeiApiContentSource()
            out = source.fetch_content_doc("doc-1")
            assert out["content_doc"] == "texto do doc"
            assert "tipo_conteudo" not in out
            assert "extra_metadata" not in out

    def test_404_discriminator_raises_document_not_found(self):
        resp = {"id_documento": "doc-1", "content_doc": None}
        with (
            patch(
                f"{ADAPTERS}.sei_client.md_ia_consulta_conteudo_documento_async",
                new=AsyncMock(return_value=resp),
            ),
            pytest.raises(DocumentNotFoundError),
        ):
            SeiApiContentSource().fetch_content_doc("doc-1")

    def test_sei_api_error_404_raises_document_not_found(self):
        with (
            patch(
                f"{ADAPTERS}.sei_client.md_ia_consulta_conteudo_documento_async",
                new=AsyncMock(side_effect=SeiApiError(404, "not found")),
            ),
            pytest.raises(DocumentNotFoundError),
        ):
            SeiApiContentSource().fetch_content_doc("doc-1")

    def test_sei_api_error_5xx_raises_extraction_error(self):
        with (
            patch(
                f"{ADAPTERS}.sei_client.md_ia_consulta_conteudo_documento_async",
                new=AsyncMock(side_effect=SeiApiError(500, "server error")),
            ),
            pytest.raises(ExtractionError),
        ):
            SeiApiContentSource().fetch_content_doc("doc-1")
