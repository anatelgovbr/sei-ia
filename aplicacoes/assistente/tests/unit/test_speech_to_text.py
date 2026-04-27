"""Testes unitários para o módulo speech_to_text.

Testa a função de transcrição de áudio via LiteLLM Proxy e o mapeamento
de extensões de áudio para MIME types.

Módulo testado: sei_ia/services/llm_models/speech_to_text.py
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetAudioMimeType:
    """Testes para a função _get_audio_mime_type."""

    @pytest.mark.parametrize(
        "extensao,mime_esperado",
        [
            ("mp3", "audio/mpeg"),
            ("mp4", "audio/mp4"),
            ("wav", "audio/wav"),
            ("ogg", "audio/ogg"),
            ("m4a", "audio/mp4"),
            ("webm", "audio/webm"),
            ("flac", "audio/flac"),
            ("aac", "audio/aac"),
            ("opus", "audio/opus"),
            ("wma", "audio/x-ms-wma"),
        ],
    )
    def test_todos_formatos_suportados_retornam_mime_correto(
        self, extensao, mime_esperado
    ):
        """Cada extensão de áudio suportada deve retornar seu MIME type correto."""
        from sei_ia.services.llm_models.speech_to_text import _get_audio_mime_type

        assert _get_audio_mime_type(extensao) == mime_esperado

    def test_extensao_desconhecida_retorna_octet_stream(self):
        """Extensão desconhecida deve retornar 'application/octet-stream'."""
        from sei_ia.services.llm_models.speech_to_text import _get_audio_mime_type

        assert _get_audio_mime_type("xyz") == "application/octet-stream"

    def test_extensao_vazia_retorna_octet_stream(self):
        """Extensão vazia deve retornar 'application/octet-stream'."""
        from sei_ia.services.llm_models.speech_to_text import _get_audio_mime_type

        assert _get_audio_mime_type("") == "application/octet-stream"

    def test_extensao_em_maiusculas_e_normalizada(self):
        """Extensão em maiúsculas deve ser normalizada e retornar o MIME correto."""
        from sei_ia.services.llm_models.speech_to_text import _get_audio_mime_type

        assert _get_audio_mime_type("MP3") == "audio/mpeg"
        assert _get_audio_mime_type("WAV") == "audio/wav"
        assert _get_audio_mime_type("OGG") == "audio/ogg"

    def test_extensao_com_ponto_inicial_removido(self):
        """Extensão com ponto inicial (ex: '.mp3') deve ser aceita normalmente."""
        from sei_ia.services.llm_models.speech_to_text import _get_audio_mime_type

        assert _get_audio_mime_type(".mp3") == "audio/mpeg"
        assert _get_audio_mime_type(".wav") == "audio/wav"


class TestTranscribeAudioFile:
    """Testes para a função transcribe_audio_file."""

    def _make_mock_client(self, texto_transcrito: str = "Texto transcrito."):
        """Cria um mock do AsyncOpenAI configurado para retornar texto transcrito."""
        mock_transcript = MagicMock()
        mock_transcript.text = texto_transcrito

        mock_transcriptions = MagicMock()
        mock_transcriptions.create = AsyncMock(return_value=mock_transcript)

        mock_audio = MagicMock()
        mock_audio.transcriptions = mock_transcriptions

        mock_client = MagicMock()
        mock_client.audio = mock_audio

        return mock_client

    def test_retorna_texto_transcrito(self, tmp_path):
        """Deve retornar o texto transcrito pelo serviço."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "reuniao.mp3"
        arquivo.write_bytes(b"fake mp3 content")
        mock_client = self._make_mock_client("Texto da reunião transcrito.")

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ):
            resultado = asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

        assert resultado == "Texto da reunião transcrito."

    def test_chama_create_com_modelo_correto(self, tmp_path):
        """Deve usar a constante SPEECH_TO_TEXT_MODEL na chamada ao serviço."""
        from sei_ia.services.llm_models.speech_to_text import (
            SPEECH_TO_TEXT_MODEL,
            transcribe_audio_file,
        )

        arquivo = tmp_path / "audio_up1_abc.mp3"
        arquivo.write_bytes(b"fake audio")
        mock_client = self._make_mock_client()

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["model"] == SPEECH_TO_TEXT_MODEL

    def test_chama_create_com_nome_de_arquivo_correto(self, tmp_path):
        """O nome do arquivo passado ao serviço deve corresponder ao nome em disco."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "depoimento_up42_xyz.mp3"
        arquivo.write_bytes(b"fake audio")
        mock_client = self._make_mock_client()

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        file_arg = call_kwargs["file"]
        assert file_arg[0] == "depoimento_up42_xyz.mp3"

    def test_chama_create_com_mime_type_correto_para_mp3(self, tmp_path):
        """Deve usar MIME type 'audio/mpeg' para arquivos MP3."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "audio.mp3"
        arquivo.write_bytes(b"fake mp3")
        mock_client = self._make_mock_client()

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["file"][2] == "audio/mpeg"

    def test_chama_create_com_mime_type_correto_para_wav(self, tmp_path):
        """Deve usar MIME type 'audio/wav' para arquivos WAV."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "gravacao.wav"
        arquivo.write_bytes(b"RIFF fake wav")
        mock_client = self._make_mock_client()

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "wav"))

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["file"][2] == "audio/wav"

    def test_conteudo_binario_do_arquivo_passado_ao_servico(self, tmp_path):
        """O conteúdo binário lido do arquivo deve ser enviado ao serviço."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        conteudo = b"conteudo binario real do audio mp3 frame data"
        arquivo = tmp_path / "original.mp3"
        arquivo.write_bytes(conteudo)
        mock_client = self._make_mock_client()

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["file"][1] == conteudo

    def test_excecao_propagada_quando_servico_falha(self, tmp_path):
        """Deve propagar exceção quando o serviço de transcrição lança erro."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "falho.mp3"
        arquivo.write_bytes(b"fake")

        mock_transcriptions = MagicMock()
        mock_transcriptions.create = AsyncMock(
            side_effect=Exception("Serviço de transcrição indisponível")
        )
        mock_audio = MagicMock()
        mock_audio.transcriptions = mock_transcriptions
        mock_client = MagicMock()
        mock_client.audio = mock_audio

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            pytest.raises(Exception, match="Serviço de transcrição indisponível"),
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

    def test_cliente_openai_configurado_com_base_url_litellm(self, tmp_path):
        """O AsyncOpenAI deve ser configurado com a base_url do LiteLLM Proxy."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "cfg_test.mp3"
        arquivo.write_bytes(b"fake")
        mock_client = self._make_mock_client()

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ) as mock_openai_cls:
            asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

        call_kwargs = mock_openai_cls.call_args.kwargs
        assert "base_url" in call_kwargs
        assert "/v1" in call_kwargs["base_url"]

    def test_cliente_openai_recebe_api_key(self, tmp_path):
        """O AsyncOpenAI deve receber uma api_key na configuração."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "cfg_test2.mp3"
        arquivo.write_bytes(b"fake")
        mock_client = self._make_mock_client()

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ) as mock_openai_cls:
            asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

        call_kwargs = mock_openai_cls.call_args.kwargs
        assert "api_key" in call_kwargs

    @pytest.mark.parametrize(
        "extensao",
        ["mp3", "mp4", "wav", "ogg", "m4a", "webm", "flac", "aac", "opus", "wma"],
    )
    def test_todas_extensoes_de_audio_sao_transcritas(self, tmp_path, extensao):
        """Deve transcrever arquivos de qualquer extensão de áudio suportada."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / f"audio.{extensao}"
        arquivo.write_bytes(b"fake audio content")
        texto_esperado = f"Transcrição do arquivo {extensao}."
        mock_client = self._make_mock_client(texto_esperado)

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ):
            resultado = asyncio.run(transcribe_audio_file(str(arquivo), extensao))

        assert resultado == texto_esperado

    def test_transcricao_retorna_string_vazia_quando_servico_retorna_vazio(
        self, tmp_path
    ):
        """Deve retornar string vazia quando o serviço transcreve silêncio."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "silencio.mp3"
        arquivo.write_bytes(b"fake silence")
        mock_client = self._make_mock_client("")

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ):
            resultado = asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

        assert resultado == ""
