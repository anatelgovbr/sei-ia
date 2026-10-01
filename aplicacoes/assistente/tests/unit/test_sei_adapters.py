"""Testes dos adapters de IO do assistente para os ports da sei_extraction.

Cobrem a tradução de erros que antes vivia em external.py: 404 do SEI vira
DocumentNotFoundError, demais falhas viram ExtractionError, de modo que o
mapeamento exception→HTTP no doc_content.py funcione no caminho de download.
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from sei_extraction.exceptions import DocumentNotFoundError, ExtractionError

from sei_ia.data.database.sei_client import SeiDBAPIError
from sei_ia.data.etl.extract.sei_adapters import (
    SeiApiAudioTranscriber,
    SeiApiContentSource,
    SeiApiFileDownloader,
)

ADAPTERS = "sei_ia.data.etl.extract.sei_adapters"


class TestSeiApiFileDownloader:
    def test_returns_path_and_records_binary_identity_on_success(self, tmp_path):
        path = tmp_path / "doc.pdf"
        path.write_bytes(b"pdf fresh")
        with patch(
            f"{ADAPTERS}.sei_client.md_ia_download_arquivo_documento_externo",
            return_value=str(path),
        ):
            downloader = SeiApiFileDownloader()
            assert downloader.download("doc-1", "pdf") == str(path)

        assert downloader.last_binary_bytes == 9
        assert downloader.last_binary_sha256 == hashlib.sha256(b"pdf fresh").hexdigest()

    def test_404_maps_to_document_not_found(self):
        with (
            patch(
                f"{ADAPTERS}.sei_client.md_ia_download_arquivo_documento_externo",
                side_effect=SeiDBAPIError(404, "não encontrado"),
            ),
            pytest.raises(DocumentNotFoundError),
        ):
            SeiApiFileDownloader().download("doc-1", "pdf")

    def test_other_status_maps_to_extraction_error(self):
        with (
            patch(
                f"{ADAPTERS}.sei_client.md_ia_download_arquivo_documento_externo",
                side_effect=SeiDBAPIError(500, "erro interno"),
            ),
            pytest.raises(ExtractionError),
        ):
            SeiApiFileDownloader().download("doc-1", "pdf")


class TestSeiApiAudioTranscriber:
    def test_returns_transcript_on_success(self):
        with patch(
            f"{ADAPTERS}.transcribe_audio_file", new=AsyncMock(return_value="texto")
        ):
            assert SeiApiAudioTranscriber().transcribe("/tmp/a.mp3", "mp3") == "texto"

    def test_failure_maps_to_extraction_error(self):
        with (
            patch(
                f"{ADAPTERS}.transcribe_audio_file",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            pytest.raises(ExtractionError),
        ):
            SeiApiAudioTranscriber().transcribe("/tmp/a.mp3", "mp3")


class TestSeiApiContentSource:
    def test_returns_content_doc_and_stores_extra_metadata(self):
        resp = {
            "content_doc": "olá",
            "tipo_conteudo": "html",
            "extra_metadata": {"k": 1},
        }
        with patch(
            f"{ADAPTERS}.sei_client.md_ia_consulta_conteudo_documento_async",
            new=AsyncMock(return_value=resp),
        ):
            source = SeiApiContentSource()
            out = source.fetch_content_doc("doc-1")
            assert out["content_doc"] == "olá"
            assert source.extra_metadata == {"k": 1}

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
