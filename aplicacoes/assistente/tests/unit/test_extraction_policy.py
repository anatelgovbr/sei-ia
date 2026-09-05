"""Testes do roteamento de conteúdo orientado por `download_ext`.

O fallback temporário de escalação Rota A → Rota B foi removido: `download_ext`
é a única fonte de verdade para download. Quando `download_ext=False`/None, o
conteúdo vem só da Rota A (`content_doc`); se vier vazio, propaga 204 — sem
baixar o binário. Extensões de áudio são exceção: sempre baixam e transcrevem.

Cobre os dois entry points async de produção:
  * `doc_content._get_doc_content_internal` (fluxo grammar_checker).
  * `concatenate_documents.get_doc_from_id_async` (fluxo de chat).

Patch targets após P2b:
  - Routing delegado ao orquestrador `sei_extraction.fetch_document_text`.
  - IO passa pelos adapters em `sei_ia.data.etl.extract.sei_adapters`.
  - `get_type_doc_from_id` permanece em `doc_content` / `concatenate_documents`.
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from sei_ia.data.etl.concatenate_documents import get_doc_from_id_async
from sei_ia.data.etl.extract.doc_content import _get_doc_content_internal
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException204,
    HTTPException404,
)

DC = "sei_ia.data.etl.extract.doc_content"
CD = "sei_ia.data.etl.concatenate_documents"
ADAPTERS = "sei_ia.data.etl.extract.sei_adapters"

# A minimal API response for a present-but-empty document (has tipo_conteudo/extra_metadata).
_API_PRESENT_EMPTY = {"tipo_conteudo": "plain", "extra_metadata": {}, "content_doc": ""}


# A minimal API response for a found document with content.
def _api_response(content: str, extra: dict | None = None) -> dict:
    return {
        "tipo_conteudo": "plain",
        "extra_metadata": extra or {},
        "content_doc": content,
    }


class TestDocContentRouteAPure:
    """`_get_doc_content_internal`: Rota A pura, sem escalação para download."""

    @pytest.mark.asyncio
    @patch(f"{ADAPTERS}.SeiApiFileDownloader.download")
    @patch(f"{ADAPTERS}.SeiApiContentSource.fetch_content_doc")
    @patch(f"{DC}.get_type_doc_from_id")
    async def test_content_doc_returned_without_download(
        self, mock_type, mock_fetch, mock_download
    ):
        mock_type.return_value = (False, "pdf", "555", "proc-1")
        mock_fetch.return_value = {
            "content_doc": "conteudo extraído",
            "extra_metadata": {"meta": 1},
        }

        content, formatted = await _get_doc_content_internal("doc-1", None, False)

        assert content == "conteudo extraído"
        assert formatted == "555"
        mock_download.assert_not_called()

    @pytest.mark.asyncio
    @patch(f"{ADAPTERS}.SeiApiFileDownloader.download")
    @patch(f"{ADAPTERS}.SeiApiContentSource.fetch_content_doc")
    @patch(f"{DC}.get_type_doc_from_id")
    async def test_empty_content_doc_raises_204_no_download(
        self, mock_type, mock_fetch, mock_download
    ):
        mock_type.return_value = (False, "pdf", "556", "proc-1")
        mock_fetch.return_value = {"content_doc": "   \n\t ", "extra_metadata": {}}

        with pytest.raises(HTTPException204):
            await _get_doc_content_internal("doc-2", None, False)
        mock_download.assert_not_called()

    @pytest.mark.asyncio
    @patch(f"{ADAPTERS}.SeiApiContentSource.fetch_content_doc")
    @patch(f"{DC}.get_type_doc_from_id")
    async def test_route_a_404_propagates(self, mock_type, mock_fetch):
        from sei_extraction.exceptions import DocumentNotFoundError

        mock_type.return_value = (False, "pdf", "557", "proc-1")
        mock_fetch.side_effect = DocumentNotFoundError("documento inexistente")

        with pytest.raises(HTTPException404):
            await _get_doc_content_internal("doc-3", None, False)

    @pytest.mark.asyncio
    @patch(
        "sei_extraction.document_fetch.extract_document",
        return_value="texto via download",
    )
    @patch(f"{ADAPTERS}.SeiApiContentSource.fetch_content_doc")
    @patch(
        f"{ADAPTERS}.SeiApiFileDownloader.download", return_value="/tmp/fake_doc.pdf"
    )
    @patch(f"{DC}.get_type_doc_from_id")
    async def test_download_ext_true_uses_route_b(
        self, mock_type, mock_download, mock_fetch, mock_extract
    ):
        mock_type.return_value = (False, "pdf", "558", "proc-1")

        content, _ = await _get_doc_content_internal("doc-4", None, True)

        assert content == "texto via download"
        mock_download.assert_called_once()
        mock_fetch.assert_not_called()


class TestDocContentAudioBranch:
    """`_get_doc_content_internal`: áudio sempre transcreve, ignora download_ext."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("download_ext", [True, False, None])
    @patch(f"{ADAPTERS}.SeiApiAudioTranscriber.transcribe")
    @patch(f"{ADAPTERS}.SeiApiContentSource.fetch_content_doc")
    @patch(f"{ADAPTERS}.SeiApiFileDownloader.download", return_value="/tmp/audio.mp3")
    @patch(f"{DC}.get_type_doc_from_id")
    async def test_audio_transcribes_regardless_of_download_ext(
        self, mock_type, mock_download, mock_fetch, mock_transcribe, download_ext
    ):
        mock_type.return_value = (False, "mp3", "560", "proc-1")
        mock_transcribe.return_value = "transcrição do áudio"

        content, formatted = await _get_doc_content_internal(
            "doc-audio", None, download_ext
        )

        assert content == "transcrição do áudio"
        assert formatted == "560"
        mock_transcribe.assert_called_once_with("/tmp/audio.mp3", "mp3")
        mock_fetch.assert_not_called()


class TestConcatenateRouteAPure:
    """`get_doc_from_id_async`: mesma semântica de Rota A pura + áudio."""

    @pytest.mark.asyncio
    @patch(f"{ADAPTERS}.SeiApiFileDownloader.download")
    @patch(
        f"{ADAPTERS}.sei_client.md_ia_consulta_conteudo_documento_async",
        new_callable=AsyncMock,
    )
    @patch(f"{CD}.get_type_doc_from_id")
    async def test_content_doc_returned_without_download(
        self, mock_type, mock_api, mock_download
    ):
        """TRUST_API path: extra_metadata flows through the real adapter."""
        mock_type.return_value = (False, "pdf", "555", "proc-1")
        mock_api.return_value = _api_response("conteudo extraído", {"meta": 1})

        content, formatted, extra = await get_doc_from_id_async("doc-1", None, False)

        assert content == "conteudo extraído"
        assert formatted == "555"
        assert extra == {"meta": 1, "id_protocolo_formatado": "proc-1"}
        mock_download.assert_not_called()

    @pytest.mark.asyncio
    @patch(f"{ADAPTERS}.SeiApiFileDownloader.download")
    @patch(f"{ADAPTERS}.SeiApiContentSource.fetch_content_doc")
    @patch(f"{CD}.get_type_doc_from_id")
    async def test_empty_content_doc_raises_204_no_download(
        self, mock_type, mock_fetch, mock_download
    ):
        mock_type.return_value = (False, "pdf", "556", "proc-1")
        mock_fetch.return_value = {"content_doc": "", "extra_metadata": {}}

        with pytest.raises(HTTPException204) as caught:
            await get_doc_from_id_async("doc-2", None, False)
        assert caught.value.formatted_document_number == "556"
        assert caught.value.formatted_process_number == "proc-1"
        mock_download.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("download_ext", [True, False, None])
    @patch(f"{ADAPTERS}.SeiApiAudioTranscriber.transcribe")
    @patch(f"{ADAPTERS}.SeiApiFileDownloader.download", return_value="/tmp/audio.wav")
    @patch(f"{ADAPTERS}.SeiApiContentSource.fetch_content_doc")
    @patch(f"{CD}.get_type_doc_from_id")
    async def test_audio_transcribes_regardless_of_download_ext(
        self, mock_type, mock_fetch, mock_download, mock_transcribe, download_ext
    ):
        mock_type.return_value = (False, "wav", "561", "proc-1")
        mock_transcribe.return_value = "transcrição"

        content, formatted, extra = await get_doc_from_id_async(
            "doc-audio", None, download_ext
        )

        assert content == "transcrição"
        assert formatted == "561"
        assert extra == {"id_protocolo_formatado": "proc-1"}
        mock_transcribe.assert_called_once_with("/tmp/audio.wav", "wav")
        mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    @patch(f"{ADAPTERS}.SeiApiAudioTranscriber.transcribe")
    @patch(f"{ADAPTERS}.SeiApiFileDownloader.download", return_value="/tmp/audio.mp3")
    @patch(f"{CD}.get_type_doc_from_id")
    async def test_audio_via_cached_metadata_skips_type_lookup(
        self, mock_type, mock_download, mock_transcribe
    ):
        """O batch passa metadata cacheada: a extensão de áudio vem dali, sem
        consultar `get_type_doc_from_id`."""
        mock_transcribe.return_value = "transcrição via cache"
        cached = {
            "metadata": {"formato_arquivo": "mp3", "id_documento_formatado": "999"}
        }

        content, formatted, extra = await get_doc_from_id_async(
            "doc-cache", None, False, cached
        )

        assert content == "transcrição via cache"
        assert formatted == "999"
        assert extra == {}
        mock_transcribe.assert_called_once_with("/tmp/audio.mp3", "mp3")
        mock_type.assert_not_called()


class TestAudioIntegrationThroughHelper:
    """Integração entry point → adapters reais, mockando apenas o download do SEI
    e o serviço de transcrição subjacentes."""

    @pytest.mark.asyncio
    @patch(f"{ADAPTERS}.transcribe_audio_file", new_callable=AsyncMock)
    @patch(f"{ADAPTERS}.sei_client.md_ia_download_arquivo_documento_externo")
    @patch(f"{CD}.get_type_doc_from_id")
    async def test_get_doc_from_id_async_audio_end_to_end(
        self, mock_type, mock_download, mock_transcribe, tmp_path
    ):
        mock_type.return_value = (False, "mp3", "777", "proc-1")
        audio_bytes = b"fake mp3"
        audio = tmp_path / "doc.mp3"
        audio.write_bytes(audio_bytes)
        mock_download.return_value = str(audio)
        mock_transcribe.return_value = "transcrição integrada"

        content, formatted, extra = await get_doc_from_id_async("doc-int", None, False)

        assert content == "transcrição integrada"
        assert formatted == "777"
        assert set(extra) == {
            "fresh_binary_bytes",
            "fresh_binary_sha256",
            "fresh_extraction_pipeline_sha256",
            "id_protocolo_formatado",
        }
        assert extra["id_protocolo_formatado"] == "proc-1"
        assert extra["fresh_binary_bytes"] == len(audio_bytes)
        assert extra["fresh_binary_sha256"] == hashlib.sha256(audio_bytes).hexdigest()
        pipeline_sha256 = extra["fresh_extraction_pipeline_sha256"]
        assert len(pipeline_sha256) == 64
        assert set(pipeline_sha256) <= set("0123456789abcdef")
        mock_download.assert_called_once_with("doc-int", "mp3", None)
        mock_transcribe.assert_called_once_with(str(audio), "mp3")
        assert not audio.exists()  # adapter limpou o temp
