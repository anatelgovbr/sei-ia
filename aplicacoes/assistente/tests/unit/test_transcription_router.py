"""Testes unitários para sei_ia/routers/transcription.py."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sei_ia.routers.transcription import ENDPOINT_NAME, router
from sei_ia.services.llm_models.speech_to_text import (
    LiteralTranscriptionUnsupportedError,
)

_MODULE = "sei_ia.routers.transcription"

_PAYLOAD = {
    "id_arquivo_avulso": 42,
    "nome_arquivo_avulso": "reuniao.mp4",
    "extensao_arquivo_avulso": "mp4",
}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def downloaded(tmp_path):
    path = tmp_path / "baixado.mp4"
    path.write_bytes(b"midia")
    return path


class TestTranscricaoEndpoint:
    def test_retorna_transcricao_e_remove_arquivo_no_sei(self, client, downloaded):
        with (
            patch(
                f"{_MODULE}.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(downloaded),
            ) as mock_download,
            patch(
                f"{_MODULE}.transcribe_audio_file_literal",
                new=AsyncMock(return_value="primeira parte segunda parte"),
            ) as mock_transcribe,
            patch(
                f"{_MODULE}._remove_arquivos_avulsos_no_sei", new=AsyncMock()
            ) as mock_remove,
        ):
            resp = client.post(ENDPOINT_NAME, json={**_PAYLOAD, "idioma": "pt"})

        assert resp.status_code == 200
        assert resp.json() == {"texto": "primeira parte segunda parte"}
        mock_download.assert_called_once_with(42, "mp4")
        mock_transcribe.assert_awaited_once_with(str(downloaded), "mp4", language="pt")
        assert mock_remove.await_args.args[0][0].id_arquivo_avulso == 42
        assert not downloaded.exists()

    def test_aceita_alias_legado_do_payload(self, client, downloaded):
        with (
            patch(
                f"{_MODULE}.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(downloaded),
            ),
            patch(
                f"{_MODULE}.transcribe_audio_file_literal",
                new=AsyncMock(return_value="primeira parte segunda parte"),
            ) as mock_transcribe,
            patch(f"{_MODULE}._remove_arquivos_avulsos_no_sei", new=AsyncMock()),
        ):
            resp = client.post(
                ENDPOINT_NAME,
                json={"id_upload": 7, "nome_original": "a.ogg", "extensao": ".OGG"},
            )

        assert resp.status_code == 200
        # idioma omitido assume "pt"
        mock_transcribe.assert_awaited_once_with(str(downloaded), "ogg", language="pt")

    def test_extensao_nao_suportada_retorna_415_sem_baixar(self, client):
        with patch(
            f"{_MODULE}.sei_client.md_ia_download_arquivo_avulso"
        ) as mock_download:
            resp = client.post(
                ENDPOINT_NAME, json={**_PAYLOAD, "extensao_arquivo_avulso": "pdf"}
            )

        assert resp.status_code == 415
        assert ".pdf" in resp.json()["detail"]
        mock_download.assert_not_called()

    def test_idioma_invalido_retorna_422(self, client):
        resp = client.post(ENDPOINT_NAME, json={**_PAYLOAD, "idioma": "português"})
        assert resp.status_code == 422

    def test_falha_no_download_retorna_502(self, client):
        with (
            patch(
                f"{_MODULE}.sei_client.md_ia_download_arquivo_avulso",
                side_effect=RuntimeError("SEI fora"),
            ),
            patch(
                f"{_MODULE}._remove_arquivos_avulsos_no_sei", new=AsyncMock()
            ) as mock_remove,
        ):
            resp = client.post(ENDPOINT_NAME, json=_PAYLOAD)

        assert resp.status_code == 502
        assert "42" in resp.json()["detail"]
        mock_remove.assert_not_awaited()

    def test_backend_de_chat_retorna_503_sem_remover_no_sei(self, client, downloaded):
        with (
            patch(
                f"{_MODULE}.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(downloaded),
            ),
            patch(
                f"{_MODULE}.transcribe_audio_file_literal",
                new=AsyncMock(
                    side_effect=LiteralTranscriptionUnsupportedError("modo chat_audio")
                ),
            ),
            patch(
                f"{_MODULE}._remove_arquivos_avulsos_no_sei", new=AsyncMock()
            ) as mock_remove,
        ):
            resp = client.post(ENDPOINT_NAME, json=_PAYLOAD)

        assert resp.status_code == 503
        assert "chat_audio" in resp.json()["detail"]
        mock_remove.assert_not_awaited()
        assert not downloaded.exists()

    def test_falha_na_transcricao_nao_remove_no_sei(self, client, downloaded):
        with (
            patch(
                f"{_MODULE}.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(downloaded),
            ),
            patch(
                f"{_MODULE}.transcribe_audio_file_literal",
                new=AsyncMock(side_effect=RuntimeError("ffmpeg falhou")),
            ),
            patch(
                f"{_MODULE}._remove_arquivos_avulsos_no_sei", new=AsyncMock()
            ) as mock_remove,
        ):
            resp = client.post(ENDPOINT_NAME, json=_PAYLOAD)

        assert resp.status_code == 500
        mock_remove.assert_not_awaited()
        assert not downloaded.exists()
