"""Testes unitários para o módulo speech_to_text.

Testa a função de transcrição de áudio via LiteLLM Proxy e o mapeamento
de extensões de áudio para MIME types.

Módulo testado: sei_ia/services/llm_models/speech_to_text.py
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SAMPLE_OGG_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "documents" / "sample.ogg"
)
VALID_OGG_BYTES = SAMPLE_OGG_PATH.read_bytes()


def _fake_transcode_to_ogg(input_path: str) -> str:
    """Substitui _transcode_to_ogg nos testes que não exercitam o ffmpeg de
    verdade: cria um OGG vazio ao lado do original, seguindo a mesma convenção
    de nome usada por _transcode_to_ogg (``<nome>_audio_extraido.ogg``)."""
    out_path = str(Path(input_path).with_suffix("")) + "_audio_extraido.ogg"
    Path(out_path).write_bytes(b"")
    return out_path


class _FakeAsyncSubprocess:
    def __init__(self, returncode=0, stdout=b"", stderr=b"", error=None):
        self.returncode = None
        self._final_returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._error = error
        self.killed = False
        self.waited = False

    async def communicate(self):
        if self._error:
            raise self._error
        self.returncode = self._final_returncode
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True

    async def wait(self):
        self.waited = True
        self.returncode = self._final_returncode
        return self.returncode


def _emulate_ffmpeg_y(cmd, default_bytes=VALID_OGG_BYTES):
    cmd_list = [
        str(x) for x in (cmd if isinstance(cmd, (list, tuple)) else str(cmd).split())
    ]
    if (
        cmd_list
        and "ffmpeg" in str(cmd_list[0])
        and str(cmd_list[-1]) not in ("-", "null")
    ):
        out_path = Path(str(cmd_list[-1]))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        in_path = next(
            (
                Path(cmd_list[i + 1])
                for i, a in enumerate(cmd_list)
                if a == "-i" and i + 1 < len(cmd_list)
            ),
            None,
        )
        out_path.write_bytes(
            in_path.read_bytes() if in_path and in_path.exists() else default_bytes
        )


async def _fake_create_subprocess_exec_default(*cmd, **kwargs):
    _emulate_ffmpeg_y(cmd)
    return _FakeAsyncSubprocess(returncode=0)


def _fake_subprocess_run_default(cmd, *args, **kwargs):
    _emulate_ffmpeg_y(cmd)
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")


@pytest.fixture(autouse=True)
def _default_audio_conversion(request):
    """Normalização de áudio para OGG antes da transcrição."""
    if "no_audio_conversion_patch" in request.keywords:
        yield
        return
    with (
        patch(
            "sei_ia.services.llm_models.speech_to_text._transcode_to_ogg",
            side_effect=_fake_transcode_to_ogg,
        ),
        patch(
            "sei_ia.services.llm_models.speech_to_text._get_audio_duration_sec",
            return_value=60.0,
        ),
        patch(
            "sei_ia.services.llm_models.speech_to_text.subprocess.run",
            side_effect=_fake_subprocess_run_default,
        ),
        patch(
            "sei_ia.services.llm_models.speech_to_text.asyncio.create_subprocess_exec",
            side_effect=_fake_create_subprocess_exec_default,
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _default_stt_mode_transcriptions(request):
    """Fixa o modo em "transcriptions" (Whisper) por padrão em todos os testes,
    já que ``_resolve_stt_mode`` consulta a rede (``/model/info`` do proxy).
    Testes do caminho "chat_audio" sobrescrevem localmente com um `with patch`
    aninhado (o patch mais interno prevalece). Testes que exercitam
    ``_resolve_stt_mode`` diretamente (TestResolveSttMode) pulam este fixture
    via marker, senão estariam testando o mock, não a função real."""
    if "no_stt_mode_patch" in request.keywords:
        yield
        return
    with patch(
        "sei_ia.services.llm_models.speech_to_text._resolve_stt_mode",
        return_value="transcriptions",
    ):
        yield


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

    def test_chama_create_com_alias_publico_fixo(self, tmp_path, monkeypatch):
        """A transcrição resolve e envia o alias, não o modelo físico."""
        from sei_ia.configs.settings_config import settings
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        monkeypatch.setattr(settings, "LITELLM_STT_MODEL", "provider/stt-physical")
        arquivo = tmp_path / "audio_up1_abc.mp3"
        arquivo.write_bytes(b"fake audio")
        mock_client = self._make_mock_client()

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._resolve_stt_mode",
                return_value="transcriptions",
            ) as resolve_mode,
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert resolve_mode.call_args.args == ("speech-to-text",)
        assert call_kwargs["model"] == "speech-to-text"

    def test_chama_create_com_nome_de_arquivo_correto(self, tmp_path):
        """O nome do arquivo passado ao serviço deve corresponder ao do OGG
        recomprimido em disco (mp3 nunca vai direto para a API)."""
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
        assert file_arg[0] == "depoimento_up42_xyz_audio_extraido.ogg"

    def test_envia_response_format_json_explicito(self, tmp_path):
        """O response_format vai explícito como "json": sem ele o LiteLLM injeta
        "verbose_json" (para calcular custo pela duração) e os backends
        gpt-transcribe rejeitam esse formato com HTTP 400."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "ata.mp3"
        arquivo.write_bytes(b"fake audio")
        mock_client = self._make_mock_client()

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["response_format"] == "json"

    @pytest.mark.parametrize("extensao", ["mp3", "wav", "aac", "opus", "wma"])
    def test_mime_type_enviado_e_sempre_ogg_apos_conversao(self, tmp_path, extensao):
        """Qualquer extensão de entrada deve chegar à API como 'audio/ogg',
        já que o arquivo é sempre recomprimido para OGG antes do envio."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / f"audio.{extensao}"
        arquivo.write_bytes(b"fake audio content")
        mock_client = self._make_mock_client()

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), extensao))

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["file"][2] == "audio/ogg"

    def test_conteudo_binario_do_arquivo_passado_ao_servico(self, tmp_path):
        """O conteúdo binário do áudio preparado deve ser enviado ao serviço."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        conteudo = b"conteudo binario real do audio ogg frame data"
        arquivo = tmp_path / "original.ogg"
        arquivo.write_bytes(conteudo)
        mock_client = self._make_mock_client()

        with patch(
            "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
            return_value=mock_client,
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "ogg"))

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


class TestTranscribeAudioFileSizeCheck:
    """Testes para a verificação de tamanho e recompressão de áudio para OGG."""

    def _make_mock_client(self, texto_transcrito: str = "Texto transcrito."):
        mock_transcript = MagicMock()
        mock_transcript.text = texto_transcrito
        mock_transcriptions = MagicMock()
        mock_transcriptions.create = AsyncMock(return_value=mock_transcript)
        mock_audio = MagicMock()
        mock_audio.transcriptions = mock_transcriptions
        mock_client = MagicMock()
        mock_client.audio = mock_audio
        return mock_client

    def test_mp4_abaixo_do_limite_ainda_assim_extrai_audio(self, tmp_path):
        """MP4 menor que 25 MB deve, mesmo assim, ser convertido para OGG via
        ffmpeg antes de ir para a API — a mídia original nunca é enviada
        diretamente ao modelo, independente do tamanho."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "pequeno.mp4"
        arquivo.write_bytes(b"fake mp4 content")
        arquivo_ogg = tmp_path / "pequeno_audio_extraido.ogg"
        arquivo_ogg.write_bytes(b"")
        mock_client = self._make_mock_client("Texto.")

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._transcode_to_ogg",
                return_value=str(arquivo_ogg),
            ) as mock_extract,
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "mp4"))

        mock_extract.assert_called_once_with(str(arquivo))

    def test_ogg_abaixo_do_limite_remuxa_sem_recodificar(self, tmp_path):
        """OGG não chama _transcode_to_ogg (recompressão com recodificação),
        mas é remuxado via stream-copy antes do envio."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "pequeno.ogg"
        arquivo.write_bytes(b"fake ogg content")
        mock_client = self._make_mock_client("Texto.")

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._transcode_to_ogg"
            ) as mock_extract,
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "ogg"))

        mock_extract.assert_not_called()

    def test_mp4_acima_do_limite_extrai_audio_e_transcreve(self, tmp_path):
        """MP4 maior que 25 MB deve extrair áudio via ffmpeg e transcrever o OGG."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo_mp4 = tmp_path / "grande.mp4"
        arquivo_mp4.write_bytes(b"x")
        arquivo_ogg = tmp_path / "grande_audio_extraido.ogg"
        arquivo_ogg.write_bytes(b"")  # 0 bytes — não dispara o check de tamanho
        mock_client = self._make_mock_client("Transcrição do vídeo grande.")

        with (
            patch("sei_ia.services.llm_models.speech_to_text._WHISPER_MAX_BYTES", 0),
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._transcode_to_ogg",
                return_value=str(arquivo_ogg),
            ) as mock_extract,
            patch(
                "sei_ia.services.llm_models.speech_to_text._get_audio_duration_sec",
                return_value=60.0,  # 1 min — não dispara o check de duração
            ),
        ):
            resultado = asyncio.run(transcribe_audio_file(str(arquivo_mp4), "mp4"))

        mock_extract.assert_called_once_with(str(arquivo_mp4))
        assert resultado == "Transcrição do vídeo grande."

    def test_mp4_audio_extraido_acima_do_limite_divide_em_chunks(self, tmp_path):
        """Se o OGG extraído > 25 MB, deve dividir em chunks e transcrever cada um."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo_mp4 = tmp_path / "enorme.mp4"
        arquivo_mp4.write_bytes(b"x")
        arquivo_ogg = tmp_path / "enorme_audio_extraido.ogg"
        arquivo_ogg.write_bytes(b"still big audio")

        chunk1 = tmp_path / "enorme_audio_extraido_chunk000.ogg"
        chunk2 = tmp_path / "enorme_audio_extraido_chunk001.ogg"
        chunk1.write_bytes(b"")
        chunk2.write_bytes(b"")

        t_a = MagicMock()
        t_a.text = "parte um"
        t_b = MagicMock()
        t_b.text = "parte dois"
        mock_transcriptions = MagicMock()
        mock_transcriptions.create = AsyncMock(side_effect=[t_a, t_b])
        mock_audio = MagicMock()
        mock_audio.transcriptions = mock_transcriptions
        mock_client = MagicMock()
        mock_client.audio = mock_audio

        with (
            patch("sei_ia.services.llm_models.speech_to_text._WHISPER_MAX_BYTES", 0),
            patch(
                "sei_ia.services.llm_models.speech_to_text._transcode_to_ogg",
                return_value=str(arquivo_ogg),
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._split_audio_into_chunks",
                return_value=[str(chunk1), str(chunk2)],
            ) as mock_split,
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
        ):
            resultado = asyncio.run(transcribe_audio_file(str(arquivo_mp4), "mp4"))

        mock_split.assert_called_once_with(str(arquivo_ogg), 0)
        assert resultado == "parte um parte dois"

    def test_chunks_remontados_na_ordem_correta(self, tmp_path):
        """A remontagem deve preservar a ordem dos chunks mesmo com parallelismo."""
        from sei_ia.services.llm_models.speech_to_text import _transcribe_chunks

        chunk0 = tmp_path / "audio_chunk000.ogg"
        chunk1 = tmp_path / "audio_chunk001.ogg"
        chunk2 = tmp_path / "audio_chunk002.ogg"
        for c in [chunk0, chunk1, chunk2]:
            c.write_bytes(b"")

        respostas = ["primeiro", "segundo", "terceiro"]
        transcripts = [MagicMock(text=t) for t in respostas]
        mock_transcriptions = MagicMock()
        mock_transcriptions.create = AsyncMock(side_effect=transcripts)
        mock_audio = MagicMock()
        mock_audio.transcriptions = mock_transcriptions
        mock_client = MagicMock()
        mock_client.audio = mock_audio

        resultado = asyncio.run(
            _transcribe_chunks(
                [str(chunk0), str(chunk1), str(chunk2)], mock_client, "whisper-1"
            )
        )

        assert resultado == "primeiro segundo terceiro"

    def test_mp4_audio_com_duracao_longa_divide_em_chunks(self, tmp_path):
        """OGG extraído < 25 MB mas com duração > 20 min deve disparar chunking."""
        from sei_ia.services.llm_models.speech_to_text import (
            _WHISPER_MAX_DURATION_SEC,
            transcribe_audio_file,
        )

        arquivo_mp4 = tmp_path / "longo.mp4"
        arquivo_mp4.write_bytes(b"x")
        arquivo_ogg = tmp_path / "longo_audio_extraido.ogg"
        arquivo_ogg.write_bytes(b"")  # 0 bytes — abaixo do limite de tamanho

        chunk1 = tmp_path / "longo_audio_extraido_chunk000.ogg"
        chunk2 = tmp_path / "longo_audio_extraido_chunk001.ogg"
        chunk1.write_bytes(b"")
        chunk2.write_bytes(b"")

        t_a = MagicMock()
        t_a.text = "primeira parte"
        t_b = MagicMock()
        t_b.text = "segunda parte"
        mock_transcriptions = MagicMock()
        mock_transcriptions.create = AsyncMock(side_effect=[t_a, t_b])
        mock_audio = MagicMock()
        mock_audio.transcriptions = mock_transcriptions
        mock_client = MagicMock()
        mock_client.audio = mock_audio

        with (
            patch("sei_ia.services.llm_models.speech_to_text._WHISPER_MAX_BYTES", 0),
            patch(
                "sei_ia.services.llm_models.speech_to_text._transcode_to_ogg",
                return_value=str(arquivo_ogg),
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._get_audio_duration_sec",
                return_value=_WHISPER_MAX_DURATION_SEC + 1,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._split_audio_into_chunks",
                return_value=[str(chunk1), str(chunk2)],
            ) as mock_split,
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
        ):
            resultado = asyncio.run(transcribe_audio_file(str(arquivo_mp4), "mp4"))

        mock_split.assert_called_once_with(
            str(arquivo_ogg), 0, _WHISPER_MAX_DURATION_SEC
        )
        assert resultado == "primeira parte segunda parte"

    def test_mp3_acima_do_limite_recomprime_para_ogg_e_transcreve(self, tmp_path):
        """MP3 maior que 25 MB deve ser recomprimido para OGG via ffmpeg, como o MP4."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo_mp3 = tmp_path / "longo.mp3"
        arquivo_mp3.write_bytes(b"x")
        arquivo_ogg = tmp_path / "longo_audio_extraido.ogg"
        arquivo_ogg.write_bytes(b"")  # 0 bytes — não dispara o check de tamanho
        mock_client = self._make_mock_client("Transcrição do áudio longo.")

        with (
            patch("sei_ia.services.llm_models.speech_to_text._WHISPER_MAX_BYTES", 0),
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._transcode_to_ogg",
                return_value=str(arquivo_ogg),
            ) as mock_transcode,
            patch(
                "sei_ia.services.llm_models.speech_to_text._get_audio_duration_sec",
                return_value=60.0,  # 1 min — não dispara o check de duração
            ),
        ):
            resultado = asyncio.run(transcribe_audio_file(str(arquivo_mp3), "mp3"))

        mock_transcode.assert_called_once_with(str(arquivo_mp3))
        assert resultado == "Transcrição do áudio longo."

    def test_ogg_acima_do_limite_remuxa_sem_recodificar_e_divide_em_chunks(
        self, tmp_path
    ):
        """OGG maior que 25 MB não chama _transcode_to_ogg (sem recodificação),
        mas é remuxado e o áudio preparado é dividido em chunks."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo_ogg = tmp_path / "longo.ogg"
        arquivo_ogg.write_bytes(b"still big audio")

        chunk1 = tmp_path / "longo_chunk000.ogg"
        chunk2 = tmp_path / "longo_chunk001.ogg"
        chunk1.write_bytes(b"")
        chunk2.write_bytes(b"")

        t_a = MagicMock()
        t_a.text = "parte um"
        t_b = MagicMock()
        t_b.text = "parte dois"
        mock_transcriptions = MagicMock()
        mock_transcriptions.create = AsyncMock(side_effect=[t_a, t_b])
        mock_audio = MagicMock()
        mock_audio.transcriptions = mock_transcriptions
        mock_client = MagicMock()
        mock_client.audio = mock_audio

        with (
            patch("sei_ia.services.llm_models.speech_to_text._WHISPER_MAX_BYTES", 0),
            patch(
                "sei_ia.services.llm_models.speech_to_text._transcode_to_ogg"
            ) as mock_transcode,
            patch(
                "sei_ia.services.llm_models.speech_to_text._split_audio_into_chunks",
                return_value=[str(chunk1), str(chunk2)],
            ) as mock_split,
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
        ):
            resultado = asyncio.run(transcribe_audio_file(str(arquivo_ogg), "ogg"))

        mock_transcode.assert_not_called()
        assert mock_split.call_count == 1
        assert resultado == "parte um parte dois"

    def test_arquivo_extraido_deletado_apos_transcricao(self, tmp_path):
        """Arquivo OGG extraído deve ser deletado do disco após a transcrição."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo_mp4 = tmp_path / "video.mp4"
        arquivo_mp4.write_bytes(b"x")
        arquivo_ogg = tmp_path / "video_audio_extraido.ogg"
        arquivo_ogg.write_bytes(b"")  # 0 bytes — não dispara o check de tamanho
        mock_client = self._make_mock_client("Texto.")

        with (
            patch("sei_ia.services.llm_models.speech_to_text._WHISPER_MAX_BYTES", 0),
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._transcode_to_ogg",
                return_value=str(arquivo_ogg),
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._get_audio_duration_sec",
                return_value=60.0,  # 1 min — não dispara o check de duração
            ),
        ):
            asyncio.run(transcribe_audio_file(str(arquivo_mp4), "mp4"))

        assert not arquivo_ogg.exists(), (
            "OGG extraído deve ser removido após transcrição"
        )

    def test_arquivo_extraido_deletado_mesmo_quando_api_falha(self, tmp_path):
        """Arquivo OGG extraído deve ser deletado mesmo quando a API lança erro."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo_mp4 = tmp_path / "video_erro.mp4"
        arquivo_mp4.write_bytes(b"x")
        arquivo_ogg = tmp_path / "video_erro_audio_extraido.ogg"
        arquivo_ogg.write_bytes(b"")  # 0 bytes — não dispara o check de tamanho

        mock_transcriptions = MagicMock()
        mock_transcriptions.create = AsyncMock(side_effect=Exception("API error"))
        mock_audio = MagicMock()
        mock_audio.transcriptions = mock_transcriptions
        mock_client = MagicMock()
        mock_client.audio = mock_audio

        with (
            patch("sei_ia.services.llm_models.speech_to_text._WHISPER_MAX_BYTES", 0),
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._transcode_to_ogg",
                return_value=str(arquivo_ogg),
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._get_audio_duration_sec",
                return_value=60.0,  # 1 min — não dispara o check de duração
            ),
            pytest.raises(Exception, match="API error"),
        ):
            asyncio.run(transcribe_audio_file(str(arquivo_mp4), "mp4"))

        assert not arquivo_ogg.exists()


def _make_remux_runner(out_bytes=VALID_OGG_BYTES, returncode=0, error=None):
    """Auxiliar para testes: runner fake de remux ffmpeg assíncrono e lista de arquivos gerados."""
    created, invocations, processes = [], [], []

    async def runner(*cmd, **kwargs):
        cmd_list = [str(x) for x in cmd]
        invocations.append({"cmd": cmd_list, "kwargs": kwargs})
        out_path = Path(cmd_list[-1])
        created.append(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        has_copy = "-c:a" in cmd_list and cmd_list[cmd_list.index("-c:a") + 1] == "copy"
        has_map = "-map" in cmd_list and cmd_list[cmd_list.index("-map") + 1] == "0:a:0"
        has_vn = "-vn" in cmd_list
        has_ogg = "-f" in cmd_list and cmd_list[cmd_list.index("-f") + 1] == "ogg"
        has_in = "-i" in cmd_list and cmd_list.index("-i") + 1 < len(cmd_list)
        separate_io = has_in and cmd_list[cmd_list.index("-i") + 1] != cmd_list[-1]

        if not (has_copy and has_map and has_vn and has_ogg and separate_io):
            raise RuntimeError(
                f"ffmpeg invocado sem flags estritas de remux: {cmd_list}"
            )

        out_path.write_bytes(out_bytes)
        proc = _FakeAsyncSubprocess(
            returncode=returncode,
            stderr=b"err" if returncode else b"",
            error=error,
        )
        processes.append(proc)
        return proc

    runner.created = created
    runner.invocations = invocations
    runner.processes = processes
    return runner, created


def _make_mock_client(text="Texto transcrito.", chunks=None):
    """Cria mock do cliente LiteLLM/OpenAI para transcription ou chunking."""
    mock_audio = MagicMock()
    if chunks:
        mock_audio.transcriptions.create = AsyncMock(
            side_effect=[MagicMock(text=t) for t in chunks]
        )
    else:
        mock_audio.transcriptions.create = AsyncMock(return_value=MagicMock(text=text))
    return MagicMock(audio=mock_audio)


class TestTranscribeAudioFileOggRemux:
    """Testes de remux de arquivos OGG sem recodificação antes do envio ao LiteLLM."""

    def test_transcribe_ogg_remuxes_before_sending_to_service(self, tmp_path):
        """OGG de entrada deve ser remuxado antes do envio com metadados corretos."""
        from sei_ia.services.llm_models.speech_to_text import (
            LITELLM_STT_ALIAS,
            transcribe_audio_file,
        )

        input_file = tmp_path / "depoimento.ogg"
        input_file.write_bytes(b"CONTAMINATED_OGG_HEADER")
        runner, created = _make_remux_runner()
        mock_client = _make_mock_client("Transcrito.")

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text.asyncio.create_subprocess_exec",
                side_effect=runner,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text.asyncio.wait_for",
                wraps=asyncio.wait_for,
            ) as spy_wait_for,
        ):
            resultado = asyncio.run(transcribe_audio_file(str(input_file), "ogg"))

        assert resultado == "Transcrito."
        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        name, content, mime = call_kwargs["file"]
        assert (
            content == VALID_OGG_BYTES
            and mime == "audio/ogg"
            and name.endswith(".ogg")
            and name != input_file.name
        )
        assert (
            call_kwargs["response_format"] == "json"
            and call_kwargs["model"] == LITELLM_STT_ALIAS
        )
        assert (
            input_file.read_bytes() == b"CONTAMINATED_OGG_HEADER"
            and created
            and not created[0].exists()
        )
        cmd = runner.invocations[0]["cmd"]
        assert (
            "-vn" in cmd
            and cmd[cmd.index("-map") + 1] == "0:a:0"
            and cmd[cmd.index("-c:a") + 1] == "copy"
            and cmd[cmd.index("-f") + 1] == "ogg"
        )
        assert cmd[cmd.index("-i") + 1] == str(input_file) and cmd[-1] != str(
            input_file
        )
        spy_wait_for.assert_called_once()
        assert spy_wait_for.call_args.kwargs.get("timeout") == 300

    def test_transcribe_ogg_deletes_temp_file_on_api_error(self, tmp_path):
        """Arquivo temporário remuxado deve ser deletado se a API falhar."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        input_file = tmp_path / "audio_erro.ogg"
        input_file.write_bytes(b"ORIGINAL_OGG")
        runner, created = _make_remux_runner()
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create = AsyncMock(
            side_effect=RuntimeError("API error")
        )

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text.asyncio.create_subprocess_exec",
                side_effect=runner,
            ),
            pytest.raises(RuntimeError, match="API error"),
        ):
            asyncio.run(transcribe_audio_file(str(input_file), "ogg"))

        assert (
            input_file.read_bytes() == b"ORIGINAL_OGG"
            and created
            and not created[0].exists()
        )

    def test_transcribe_ogg_ffmpeg_failure_propagates_error_and_cleans_up(
        self, tmp_path
    ):
        """Falha do ffmpeg no remux deve propagar erro, abortar chamada de API e limpar temporário."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        input_file = tmp_path / "audio_falho.ogg"
        input_file.write_bytes(b"ORIGINAL_OGG")
        runner, created = _make_remux_runner(out_bytes=b"partial", returncode=1)
        mock_client = _make_mock_client()

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text.asyncio.create_subprocess_exec",
                side_effect=runner,
            ),
            pytest.raises(RuntimeError, match="ffmpeg falhou ao remuxar"),
        ):
            asyncio.run(transcribe_audio_file(str(input_file), "ogg"))

        mock_client.audio.transcriptions.create.assert_not_called()
        assert (
            input_file.read_bytes() == b"ORIGINAL_OGG"
            and created
            and not created[0].exists()
        )

    def test_transcribe_ogg_ffmpeg_timeout_propagates_and_cleans_up(self, tmp_path):
        """Timeout do ffmpeg no remux deve propagar erro, abortar chamada de API e limpar temporário."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        input_file = tmp_path / "audio_timeout.ogg"
        input_file.write_bytes(b"ORIGINAL_OGG")
        runner, created = _make_remux_runner(
            out_bytes=b"partial",
            error=TimeoutError(),
        )
        mock_client = _make_mock_client()

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text.asyncio.create_subprocess_exec",
                side_effect=runner,
            ),
            pytest.raises(subprocess.TimeoutExpired) as exc_info,
        ):
            asyncio.run(transcribe_audio_file(str(input_file), "ogg"))

        mock_client.audio.transcriptions.create.assert_not_called()
        assert (
            input_file.read_bytes() == b"ORIGINAL_OGG"
            and created
            and not created[0].exists()
        )
        assert exc_info.value.timeout == 300
        assert (
            runner.processes
            and runner.processes[0].killed
            and runner.processes[0].waited
        )

    def test_transcribe_ogg_large_file_remuxes_before_chunking(self, tmp_path):
        """OGG > 25 MB deve ser remuxado antes do chunking, e chunks recebem o caminho remuxado."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo_ogg = tmp_path / "longo.ogg"
        arquivo_ogg.write_bytes(b"ORIGINAL_LARGE_OGG")
        chunk1, chunk2 = tmp_path / "c1.ogg", tmp_path / "c2.ogg"
        chunk1.write_bytes(b""), chunk2.write_bytes(b"")

        runner, created = _make_remux_runner(out_bytes=b"x" * 100)
        mock_client = _make_mock_client(chunks=["parte um", "parte dois"])

        with (
            patch("sei_ia.services.llm_models.speech_to_text._WHISPER_MAX_BYTES", 0),
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text.asyncio.create_subprocess_exec",
                side_effect=runner,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._split_audio_into_chunks",
                return_value=[str(chunk1), str(chunk2)],
            ) as mock_split,
            patch(
                "sei_ia.services.llm_models.speech_to_text._get_audio_duration_sec",
                return_value=60.0,
            ),
        ):
            resultado = asyncio.run(transcribe_audio_file(str(arquivo_ogg), "ogg"))

        assert resultado == "parte um parte dois"
        assert (
            created
            and mock_split.call_args[0][0] == str(created[0])
            and not created[0].exists()
        )
        assert arquivo_ogg.read_bytes() == b"ORIGINAL_LARGE_OGG"

    def test_transcribe_ogg_chat_audio_mode_sends_remuxed_bytes(self, tmp_path):
        """No modo chat_audio, o áudio remuxado deve ser enviado em base64 e limpo."""
        import base64

        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        input_file = tmp_path / "chat.ogg"
        input_file.write_bytes(b"CONTAMINATED_CHAT_OGG")
        runner, created = _make_remux_runner()

        mock_resp = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Texto Gemini."))]
        )
        mock_client = MagicMock(
            chat=MagicMock(
                completions=MagicMock(create=AsyncMock(return_value=mock_resp))
            )
        )

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._resolve_stt_mode",
                return_value="chat_audio",
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text.asyncio.create_subprocess_exec",
                side_effect=runner,
            ),
        ):
            resultado = asyncio.run(transcribe_audio_file(str(input_file), "ogg"))

        assert resultado == "Texto Gemini."
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        block = next(
            b
            for b in call_kwargs["messages"][0]["content"]
            if b.get("type") == "input_audio"
        )
        assert base64.b64decode(block["input_audio"]["data"]) == VALID_OGG_BYTES
        assert block["input_audio"]["format"] == "ogg"
        assert (
            input_file.read_bytes() == b"CONTAMINATED_CHAT_OGG"
            and created
            and not created[0].exists()
        )

    @pytest.mark.no_audio_conversion_patch
    def test_transcribe_ogg_cancellation_during_ffmpeg_cleans_up_without_orphan(
        self, tmp_path, monkeypatch
    ):
        """Cancelamento de transcribe_audio_file durante remux via ffmpeg não deve
        deixar arquivo temporário órfão recriado pelo worker em execução."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        input_file = tmp_path / "audio_cancel.ogg"
        input_file.write_bytes(b"ORIGINAL_OGG")

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        fake_ffmpeg = bin_dir / "ffmpeg"

        started_file = tmp_path / "started"
        release_file = tmp_path / "release"
        done_file = tmp_path / "done"
        out_record = tmp_path / "out_path"

        fake_ffmpeg.write_text(f"""#!{sys.executable}
import sys
import time
from pathlib import Path

args = sys.argv[1:]
has_copy = "-c:a" in args and args[args.index("-c:a") + 1] == "copy"
has_map = "-map" in args and args[args.index("-map") + 1] == "0:a:0"
has_vn = "-vn" in args
has_ogg = "-f" in args and args[args.index("-f") + 1] == "ogg"
has_in = "-i" in args and args.index("-i") + 1 < len(args)
separate_io = has_in and args[args.index("-i") + 1] != args[-1]

if not (has_copy and has_map and has_vn and has_ogg and separate_io):
    sys.stderr.write("Invalid remux args: " + repr(args) + "\\n")
    sys.exit(2)

out_target = args[-1]
Path({str(out_record)!r}).write_text(out_target)
Path({str(started_file)!r}).write_text("1")

release = Path({str(release_file)!r})
start = time.time()
while not release.exists() and (time.time() - start) < 5.0:
    time.sleep(0.01)

out_path = Path(out_target)
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_bytes(b"FAKE_OUTPUT")
Path({str(done_file)!r}).write_text("1")
""")
        fake_ffmpeg.chmod(0o755)

        monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
        mock_client = _make_mock_client("Transcrito.")

        recorded_out = None
        try:
            with (
                patch(
                    "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                    return_value=mock_client,
                ),
                patch(
                    "sei_ia.services.llm_models.speech_to_text._get_audio_duration_sec",
                    return_value=60.0,
                ),
            ):

                async def _run_and_cancel():
                    nonlocal recorded_out
                    task = asyncio.create_task(
                        transcribe_audio_file(str(input_file), "ogg")
                    )
                    for _ in range(100):
                        if started_file.exists():
                            break
                        await asyncio.sleep(0.02)

                    assert started_file.exists(), "ffmpeg fake não iniciou a tempo"
                    recorded_out = Path(out_record.read_text().strip())

                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task

                    release_file.write_text("1")
                    for _ in range(30):
                        if done_file.exists() or recorded_out.exists():
                            break
                        await asyncio.sleep(0.01)

                asyncio.run(_run_and_cancel())

            assert input_file.read_bytes() == b"ORIGINAL_OGG"
            mock_client.audio.transcriptions.create.assert_not_called()
            assert recorded_out is not None
            assert not recorded_out.exists(), (
                f"Arquivo temporário {recorded_out} ficou órfão após cancelamento"
            )
        finally:
            if recorded_out and recorded_out.exists():
                recorded_out.unlink(missing_ok=True)

    @pytest.mark.no_audio_conversion_patch
    def test_transcribe_ogg_cancellation_during_temp_creation_cleans_up_without_orphan(
        self, tmp_path
    ):
        """Cancelamento de transcribe_audio_file durante criação de temp OGG no worker
        não deve deixar arquivo temporário órfão."""
        import tempfile
        import threading

        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        input_file = tmp_path / "audio_cancel_temp.ogg"
        input_file.write_bytes(b"ORIGINAL_OGG")

        created_file: Path | None = None
        resume_worker = threading.Event()

        mock_subprocess_exec = AsyncMock()
        mock_client = MagicMock()

        try:
            loop: asyncio.AbstractEventLoop | None = None
            worker_started: asyncio.Event | None = None
            worker_done: asyncio.Event | None = None

            def fake_create_temp_ogg_path() -> str:
                nonlocal created_file
                assert (
                    loop is not None
                    and worker_started is not None
                    and worker_done is not None
                )
                loop.call_soon_threadsafe(worker_started.set)
                if not resume_worker.wait(timeout=5.0):
                    raise TimeoutError("Worker timed out waiting for resume_worker")
                with tempfile.NamedTemporaryFile(
                    suffix=".ogg", dir=str(tmp_path), delete=False
                ) as tmp_file:
                    created_file = Path(tmp_file.name)
                    loop.call_soon_threadsafe(worker_done.set)
                    return tmp_file.name

            with (
                patch(
                    "sei_ia.services.llm_models.speech_to_text._create_temp_ogg_path",
                    side_effect=fake_create_temp_ogg_path,
                ),
                patch(
                    "sei_ia.services.llm_models.speech_to_text.asyncio.create_subprocess_exec",
                    mock_subprocess_exec,
                ),
                patch(
                    "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                    return_value=mock_client,
                ),
            ):

                async def _run_and_cancel():
                    nonlocal loop, worker_started, worker_done
                    loop = asyncio.get_running_loop()
                    worker_started = asyncio.Event()
                    worker_done = asyncio.Event()

                    task = asyncio.create_task(
                        transcribe_audio_file(str(input_file), "ogg")
                    )
                    await asyncio.wait_for(worker_started.wait(), timeout=5)

                    task.cancel()
                    resume_worker.set()

                    with pytest.raises(asyncio.CancelledError):
                        await task

                    await asyncio.wait_for(worker_done.wait(), timeout=5)

                asyncio.run(_run_and_cancel())

            assert input_file.read_bytes() == b"ORIGINAL_OGG"
            mock_subprocess_exec.assert_not_called()
            mock_client.audio.transcriptions.create.assert_not_called()
            assert created_file is not None
            assert not created_file.exists(), (
                f"Arquivo temporário {created_file} ficou órfão após cancelamento"
            )
        finally:
            resume_worker.set()
            if created_file and created_file.exists():
                created_file.unlink(missing_ok=True)


class TestDetectSilencePoints:
    """Testes para _detect_silence_points."""

    def test_retorna_pontos_medios_dos_silencias(self):
        """Deve retornar a média entre silence_start e silence_end."""
        from unittest.mock import MagicMock

        from sei_ia.services.llm_models.speech_to_text import _detect_silence_points

        ffmpeg_output = (
            b"[silencedetect] silence_start: 10.0\n"
            b"[silencedetect] silence_end: 12.0 | silence_duration: 2.0\n"
            b"[silencedetect] silence_start: 50.0\n"
            b"[silencedetect] silence_end: 51.0 | silence_duration: 1.0\n"
        )
        mock_result = MagicMock()
        mock_result.stderr = ffmpeg_output

        with patch(
            "sei_ia.services.llm_models.speech_to_text.subprocess.run",
            return_value=mock_result,
        ):
            pontos = _detect_silence_points("/tmp/audio.ogg")

        assert pontos == [11.0, 50.5]

    def test_retorna_lista_vazia_quando_sem_silencio(self):
        """Deve retornar lista vazia quando não há silêncio detectado."""
        from unittest.mock import MagicMock

        from sei_ia.services.llm_models.speech_to_text import _detect_silence_points

        mock_result = MagicMock()
        mock_result.stderr = b"sem silencio aqui"

        with patch(
            "sei_ia.services.llm_models.speech_to_text.subprocess.run",
            return_value=mock_result,
        ):
            pontos = _detect_silence_points("/tmp/audio.ogg")

        assert pontos == []


@pytest.mark.no_audio_conversion_patch
class TestSplitAudioIntoChunks:
    """Testes para _split_audio_into_chunks."""

    def test_cria_um_chunk_quando_audio_cabe_em_um_bloco(self, tmp_path):
        """Áudio que cabe em um chunk deve gerar exatamente 1 arquivo."""
        from unittest.mock import MagicMock

        from sei_ia.services.llm_models.speech_to_text import _split_audio_into_chunks

        audio = tmp_path / "audio.ogg"
        audio.write_bytes(b"x" * 100)

        chunk0 = tmp_path / "audio_chunk000.ogg"

        silence_result = MagicMock()
        silence_result.stderr = b""

        ffprobe_result = MagicMock()
        ffprobe_result.returncode = 0
        ffprobe_result.stdout = b"60.0\n"
        ffprobe_result.stderr = b""

        def fake_run(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            if "silencedetect" in " ".join(cmd):
                return silence_result
            chunk0.write_bytes(b"chunk data")
            m = MagicMock()
            m.returncode = 0
            m.stderr = b""
            return m

        with patch(
            "sei_ia.services.llm_models.speech_to_text.subprocess.run",
            side_effect=fake_run,
        ):
            chunks = _split_audio_into_chunks(str(audio), 10_000)

        assert len(chunks) == 1
        assert chunks[0] == str(chunk0)

    def test_usa_ponto_de_silencio_como_corte(self, tmp_path):
        """O corte deve ocorrer no ponto de silêncio mais próximo antes do limite."""
        from unittest.mock import MagicMock

        from sei_ia.services.llm_models.speech_to_text import _split_audio_into_chunks

        audio = tmp_path / "audio.ogg"
        audio.write_bytes(b"x" * 1000)  # 1000 bytes → 2 chunks com max_bytes=600

        chunk0 = tmp_path / "audio_chunk000.ogg"
        chunk1 = tmp_path / "audio_chunk001.ogg"  # noqa: F841

        ffprobe_result = MagicMock()
        ffprobe_result.returncode = 0
        ffprobe_result.stdout = b"100.0\n"  # 100s; 10 bytes/s; target≈57s
        ffprobe_result.stderr = b""

        silence_result = MagicMock()
        silence_result.stderr = (
            b"silence_start: 49.0\nsilence_end: 51.0 | silence_duration: 2.0\n"
        )

        from pathlib import Path as _Path

        split_calls: list = []

        def fake_run(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            if "silencedetect" in " ".join(cmd):
                return silence_result
            ss_idx = cmd.index("-ss")
            to_idx = cmd.index("-to")
            split_calls.append((float(cmd[ss_idx + 1]), float(cmd[to_idx + 1])))
            _Path(cmd[-1]).write_bytes(b"chunk")
            m = MagicMock()
            m.returncode = 0
            m.stderr = b""
            return m

        with patch(
            "sei_ia.services.llm_models.speech_to_text.subprocess.run",
            side_effect=fake_run,
        ):
            chunks = _split_audio_into_chunks(str(audio), 600)

        assert split_calls[0][1] == 50.0  # corte no ponto de silêncio, não em 57s
        assert len(chunks) == 2

    def test_limpa_chunks_anteriores_se_ffmpeg_falhar(self, tmp_path):
        """Chunks já criados devem ser deletados se um split posterior falhar."""
        from unittest.mock import MagicMock

        from sei_ia.services.llm_models.speech_to_text import _split_audio_into_chunks

        audio = tmp_path / "audio.ogg"
        audio.write_bytes(b"x" * 1000)

        chunk0 = tmp_path / "audio_chunk000.ogg"

        ffprobe_result = MagicMock()
        ffprobe_result.returncode = 0
        ffprobe_result.stdout = b"100.0\n"
        ffprobe_result.stderr = b""

        silence_result = MagicMock()
        silence_result.stderr = b""

        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            if "silencedetect" in " ".join(cmd):
                return silence_result
            call_count += 1
            if call_count == 1:
                chunk0.write_bytes(b"chunk")
                m = MagicMock()
                m.returncode = 0
                m.stderr = b""
                return m
            m = MagicMock()
            m.returncode = 1
            m.stderr = b"erro fatal"
            return m

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text.subprocess.run",
                side_effect=fake_run,
            ),
            pytest.raises(RuntimeError, match="ffmpeg falhou"),
        ):
            _split_audio_into_chunks(str(audio), 600)

        assert not chunk0.exists()


class TestClassifySttMode:
    """Testes para _classify_stt_mode: mapeia o backend real (litellm_params.model)
    para o modo de chamada ("transcriptions" ou "chat_audio")."""

    def test_whisper_retorna_transcriptions(self):
        from sei_ia.services.llm_models.speech_to_text import _classify_stt_mode

        assert _classify_stt_mode("azure/whisper") == "transcriptions"
        assert _classify_stt_mode("openai/whisper-1") == "transcriptions"

    def test_gemini_flash_retorna_chat_audio(self):
        from sei_ia.services.llm_models.speech_to_text import _classify_stt_mode

        assert _classify_stt_mode("openai/seiia-ds-gemini-flash-lite") == "chat_audio"
        assert _classify_stt_mode("openai/seiia-ds-gemini-flash") == "chat_audio"
        assert _classify_stt_mode("vertex_ai/gemini-2.5-flash") == "chat_audio"

    def test_none_retorna_transcriptions(self):
        from sei_ia.services.llm_models.speech_to_text import _classify_stt_mode

        assert _classify_stt_mode(None) == "transcriptions"

    def test_string_vazia_retorna_transcriptions(self):
        from sei_ia.services.llm_models.speech_to_text import _classify_stt_mode

        assert _classify_stt_mode("") == "transcriptions"

    def test_modelo_desconhecido_retorna_transcriptions(self):
        """Modelo não reconhecido (nem whisper, nem gemini/flash) cai no
        default mais seguro: transcriptions (comportamento atual)."""
        from sei_ia.services.llm_models.speech_to_text import _classify_stt_mode

        assert _classify_stt_mode("openai/seiia-ds-chirp") == "transcriptions"


@pytest.mark.no_stt_mode_patch
class TestResolveSttMode:
    """Testes para _resolve_stt_mode: resolução via /model/info, cache por
    alias no processo, e fallback seguro quando a consulta falha."""

    def setup_method(self):
        from sei_ia.services.llm_models import speech_to_text

        speech_to_text._stt_mode_cache.clear()

    def teardown_method(self):
        from sei_ia.services.llm_models import speech_to_text

        speech_to_text._stt_mode_cache.clear()

    def test_usa_classificacao_do_backend_resolvido(self):
        from sei_ia.services.llm_models.speech_to_text import _resolve_stt_mode

        with patch(
            "sei_ia.services.llm_models.speech_to_text._fetch_stt_backend_model",
            return_value="openai/seiia-ds-gemini-flash-lite",
        ):
            assert _resolve_stt_mode("speech-to-text") == "chat_audio"

    def test_backend_whisper_resolve_para_transcriptions(self):
        from sei_ia.services.llm_models.speech_to_text import _resolve_stt_mode

        with patch(
            "sei_ia.services.llm_models.speech_to_text._fetch_stt_backend_model",
            return_value="azure/whisper",
        ):
            assert _resolve_stt_mode("speech-to-text") == "transcriptions"

    def test_cacheia_resultado_por_alias_uma_unica_consulta(self):
        from sei_ia.services.llm_models.speech_to_text import _resolve_stt_mode

        with patch(
            "sei_ia.services.llm_models.speech_to_text._fetch_stt_backend_model",
            return_value="azure/whisper",
        ) as mock_fetch:
            _resolve_stt_mode("speech-to-text")
            _resolve_stt_mode("speech-to-text")
            _resolve_stt_mode("speech-to-text")

        mock_fetch.assert_called_once()

    def test_falha_na_consulta_cai_em_transcriptions_sem_levantar(self):
        """Rota bloqueada por permissão da virtual key (caso esperado em PD) não
        deve propagar exceção — apenas cair no modo Whisper com warning."""
        from sei_ia.services.llm_models.speech_to_text import _resolve_stt_mode

        with patch(
            "sei_ia.services.llm_models.speech_to_text._fetch_stt_backend_model",
            side_effect=Exception("403 Forbidden"),
        ):
            assert _resolve_stt_mode("speech-to-text") == "transcriptions"

    def test_backend_nao_encontrado_cai_em_transcriptions(self):
        from sei_ia.services.llm_models.speech_to_text import _resolve_stt_mode

        with patch(
            "sei_ia.services.llm_models.speech_to_text._fetch_stt_backend_model",
            return_value=None,
        ):
            assert _resolve_stt_mode("speech-to-text") == "transcriptions"

    def test_aliases_diferentes_sao_cacheados_independentemente(self):
        from sei_ia.services.llm_models.speech_to_text import _resolve_stt_mode

        with patch(
            "sei_ia.services.llm_models.speech_to_text._fetch_stt_backend_model",
            side_effect=lambda alias: {
                "speech-to-text": "azure/whisper",
                "speech-to-text-v2": "openai/seiia-ds-gemini-flash-lite",
            }[alias],
        ):
            assert _resolve_stt_mode("speech-to-text") == "transcriptions"
            assert _resolve_stt_mode("speech-to-text-v2") == "chat_audio"

    def test_ttl_expirado_reconsulta_e_reflete_backend_novo(self):
        """Troca de backend no proxy (sem restart do assistente) deve refletir
        depois que o TTL do cache expira — é o ponto central da transparência."""
        from sei_ia.services.llm_models import speech_to_text
        from sei_ia.services.llm_models.speech_to_text import _resolve_stt_mode

        with patch(
            "sei_ia.services.llm_models.speech_to_text._fetch_stt_backend_model",
            return_value="azure/whisper",
        ):
            assert _resolve_stt_mode("speech-to-text") == "transcriptions"

        # Simula TTL expirado sem esperar de verdade: recua o timestamp cacheado.
        mode, _ts = speech_to_text._stt_mode_cache["speech-to-text"]
        speech_to_text._stt_mode_cache["speech-to-text"] = (
            mode,
            speech_to_text.time.monotonic() - speech_to_text._STT_MODE_TTL_S - 1,
        )

        with patch(
            "sei_ia.services.llm_models.speech_to_text._fetch_stt_backend_model",
            return_value="openai/seiia-ds-gemini-flash-lite",
        ) as mock_fetch:
            assert _resolve_stt_mode("speech-to-text") == "chat_audio"

        mock_fetch.assert_called_once()

    def test_ttl_nao_expirado_nao_reconsulta(self):
        from sei_ia.services.llm_models.speech_to_text import _resolve_stt_mode

        with patch(
            "sei_ia.services.llm_models.speech_to_text._fetch_stt_backend_model",
            return_value="azure/whisper",
        ):
            _resolve_stt_mode("speech-to-text")

        with patch(
            "sei_ia.services.llm_models.speech_to_text._fetch_stt_backend_model",
            return_value="openai/seiia-ds-gemini-flash-lite",
        ) as mock_fetch:
            # Ainda dentro do TTL: deve retornar o valor cacheado, não reconsultar.
            assert _resolve_stt_mode("speech-to-text") == "transcriptions"

        mock_fetch.assert_not_called()

    def test_falha_apos_ttl_expirado_reaproveita_modo_anterior_stale(self):
        """Falha transitória de rede depois do TTL expirar não deve derrubar um
        modo já resolvido de volta pro default — mantém o último conhecido."""
        from sei_ia.services.llm_models import speech_to_text
        from sei_ia.services.llm_models.speech_to_text import _resolve_stt_mode

        with patch(
            "sei_ia.services.llm_models.speech_to_text._fetch_stt_backend_model",
            return_value="openai/seiia-ds-gemini-flash-lite",
        ):
            assert _resolve_stt_mode("speech-to-text") == "chat_audio"

        mode, _ts = speech_to_text._stt_mode_cache["speech-to-text"]
        speech_to_text._stt_mode_cache["speech-to-text"] = (
            mode,
            speech_to_text.time.monotonic() - speech_to_text._STT_MODE_TTL_S - 1,
        )

        with patch(
            "sei_ia.services.llm_models.speech_to_text._fetch_stt_backend_model",
            side_effect=Exception("timeout de rede"),
        ):
            # Não cai em "transcriptions" (default) — reaproveita "chat_audio".
            assert _resolve_stt_mode("speech-to-text") == "chat_audio"


class TestFetchSttBackendModel:
    """Testes para _fetch_stt_backend_model: parsing da resposta de /model/info."""

    def _mock_response(self, payload, status_ok=True):
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        if not status_ok:
            mock_resp.raise_for_status.side_effect = Exception("HTTP error")
        return mock_resp

    def test_extrai_model_do_alias_correspondente(self):
        from sei_ia.services.llm_models.speech_to_text import _fetch_stt_backend_model

        payload = {
            "data": [
                {"model_name": "standard", "litellm_params": {"model": "openai/x"}},
                {
                    "model_name": "speech-to-text",
                    "litellm_params": {"model": "azure/whisper"},
                },
            ]
        }
        with patch(
            "sei_ia.services.llm_models.speech_to_text.httpx.get",
            return_value=self._mock_response(payload),
        ):
            assert _fetch_stt_backend_model("speech-to-text") == "azure/whisper"

    def test_alias_nao_encontrado_retorna_none(self):
        from sei_ia.services.llm_models.speech_to_text import _fetch_stt_backend_model

        payload = {"data": [{"model_name": "standard", "litellm_params": {}}]}
        with patch(
            "sei_ia.services.llm_models.speech_to_text.httpx.get",
            return_value=self._mock_response(payload),
        ):
            assert _fetch_stt_backend_model("speech-to-text") is None

    def test_erro_http_propaga_excecao(self):
        """Deve propagar (não engolir) — quem engole é _resolve_stt_mode."""
        from sei_ia.services.llm_models.speech_to_text import _fetch_stt_backend_model

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text.httpx.get",
                return_value=self._mock_response({}, status_ok=False),
            ),
            pytest.raises(Exception, match="HTTP error"),
        ):
            _fetch_stt_backend_model("speech-to-text")


class TestTranscribeAudioFileChatAudioMode:
    """Testes para o caminho chat_audio (Gemini flash/flash-lite via
    /v1/chat/completions multimodal), usado quando _resolve_stt_mode
    identifica um backend que não suporta /v1/audio/transcriptions."""

    def _make_mock_client(self, texto_transcrito: str = "Texto via chat."):
        mock_message = MagicMock()
        mock_message.content = texto_transcrito
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_completions = MagicMock()
        mock_completions.create = AsyncMock(return_value=mock_response)
        mock_chat = MagicMock()
        mock_chat.completions = mock_completions

        mock_client = MagicMock()
        mock_client.chat = mock_chat
        return mock_client

    def test_usa_chat_completions_quando_modo_chat_audio(self, tmp_path):
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "audio.mp3"
        arquivo.write_bytes(b"fake mp3 content")
        mock_client = self._make_mock_client("Transcrição via Gemini.")

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text._resolve_stt_mode",
                return_value="chat_audio",
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
        ):
            resultado = asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

        assert resultado == "Transcrição via Gemini."
        mock_client.chat.completions.create.assert_called_once()

    def test_envia_audio_como_bloco_input_audio_base64(self, tmp_path):
        """O áudio preparado deve ser enviado como bloco input_audio codificado em base64."""
        import base64

        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        conteudo = b"conteudo binario real do audio"
        arquivo = tmp_path / "audio.ogg"
        arquivo.write_bytes(conteudo)
        mock_client = self._make_mock_client()

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text._resolve_stt_mode",
                return_value="chat_audio",
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "ogg"))

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        content_blocks = call_kwargs["messages"][0]["content"]
        audio_block = next(b for b in content_blocks if b["type"] == "input_audio")
        assert audio_block["input_audio"]["data"] == base64.b64encode(conteudo).decode(
            "utf-8"
        )
        assert audio_block["input_audio"]["format"] == "ogg"

    def test_modelo_usado_e_o_alias_publico_fixo(self, tmp_path):
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "audio.mp3"
        arquivo.write_bytes(b"fake")
        mock_client = self._make_mock_client()

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text._resolve_stt_mode",
                return_value="chat_audio",
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "speech-to-text"

    def test_excecao_propagada_quando_chat_completions_falha(self, tmp_path):
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo = tmp_path / "falho.mp3"
        arquivo.write_bytes(b"fake")

        mock_completions = MagicMock()
        mock_completions.create = AsyncMock(
            side_effect=Exception("Gemini indisponível")
        )
        mock_chat = MagicMock()
        mock_chat.completions = mock_completions
        mock_client = MagicMock()
        mock_client.chat = mock_chat

        with (
            patch(
                "sei_ia.services.llm_models.speech_to_text._resolve_stt_mode",
                return_value="chat_audio",
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            pytest.raises(Exception, match="Gemini indisponível"),
        ):
            asyncio.run(transcribe_audio_file(str(arquivo), "mp3"))

    def test_chunks_usam_chat_completions_em_modo_chat_audio(self, tmp_path):
        """Arquivo grande, dividido em chunks, também deve usar o caminho
        chat_audio para cada chunk quando o modo resolvido é chat_audio."""
        from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

        arquivo_mp3 = tmp_path / "longo.mp3"
        arquivo_mp3.write_bytes(b"x")
        arquivo_ogg = tmp_path / "longo_audio_extraido.ogg"
        arquivo_ogg.write_bytes(b"still big audio")

        chunk1 = tmp_path / "longo_audio_extraido_chunk000.ogg"
        chunk2 = tmp_path / "longo_audio_extraido_chunk001.ogg"
        chunk1.write_bytes(b"")
        chunk2.write_bytes(b"")

        def make_response(texto):
            msg = MagicMock()
            msg.content = texto
            choice = MagicMock()
            choice.message = msg
            resp = MagicMock()
            resp.choices = [choice]
            return resp

        mock_completions = MagicMock()
        mock_completions.create = AsyncMock(
            side_effect=[make_response("parte um"), make_response("parte dois")]
        )
        mock_chat = MagicMock()
        mock_chat.completions = mock_completions
        mock_client = MagicMock()
        mock_client.chat = mock_chat

        with (
            patch("sei_ia.services.llm_models.speech_to_text._WHISPER_MAX_BYTES", 0),
            patch(
                "sei_ia.services.llm_models.speech_to_text._resolve_stt_mode",
                return_value="chat_audio",
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text.AsyncOpenAI",
                return_value=mock_client,
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._transcode_to_ogg",
                return_value=str(arquivo_ogg),
            ),
            patch(
                "sei_ia.services.llm_models.speech_to_text._split_audio_into_chunks",
                return_value=[str(chunk1), str(chunk2)],
            ),
        ):
            resultado = asyncio.run(transcribe_audio_file(str(arquivo_mp3), "mp3"))

        assert resultado == "parte um parte dois"
        assert mock_client.chat.completions.create.call_count == 2
