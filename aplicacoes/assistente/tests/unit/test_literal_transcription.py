"""Testes unitários do modo de transcrição literal.

Módulo testado: sei_ia/services/llm_models/speech_to_text.py
(transcribe_audio_file_literal e o limite de duração em
_split_audio_into_chunks).
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import omit

from sei_ia.services.llm_models.speech_to_text import (
    _LITERAL_MAX_DURATION_SEC,
    _LITERAL_TRANSCRIPTION_PROMPT,
    LiteralTranscriptionUnsupportedError,
    _split_audio_into_chunks,
    transcribe_audio_file_literal,
)

_MODULE = "sei_ia.services.llm_models.speech_to_text"


def _mock_client(texts: list[str]) -> MagicMock:
    transcripts = []
    for text in texts:
        t = MagicMock()
        t.text = text
        transcripts.append(t)
    client = MagicMock()
    client.audio.transcriptions.create = AsyncMock(side_effect=transcripts)
    return client


def _fake_resolve(chunk_paths: list[Path], extracted: Path):
    """Substitui _resolve_audio_input: popula prep sem chamar ffmpeg."""
    calls: list[dict] = []

    async def fake(file_path, ext, loop, prep, max_duration_sec=None):
        calls.append({"file_path": file_path, "max_duration_sec": max_duration_sec})
        extracted.write_bytes(b"ogg")
        prep.extracted_path = str(extracted)
        for c in chunk_paths:
            c.write_bytes(b"chunk")
        prep.chunk_paths = [str(c) for c in chunk_paths]

    return fake, calls


class TestTranscribeAudioFileLiteral:
    def test_chat_audio_e_recusado_antes_de_processar_o_audio(self, tmp_path):
        with (
            patch(f"{_MODULE}._resolve_stt_mode", return_value="chat_audio"),
            patch(f"{_MODULE}._resolve_audio_input") as mock_resolve,
            pytest.raises(LiteralTranscriptionUnsupportedError, match="chat"),
        ):
            asyncio.run(transcribe_audio_file_literal(str(tmp_path / "a.mp3"), "mp3"))

        mock_resolve.assert_not_called()

    def test_chunks_transcritos_com_parametros_literais_e_remontados(self, tmp_path):
        chunks = [tmp_path / "c0.ogg", tmp_path / "c1.ogg"]
        extracted = tmp_path / "a_audio_extraido.ogg"
        fake, calls = _fake_resolve(chunks, extracted)
        client = _mock_client(["  primeira parte ", "segunda parte"])

        with (
            patch(f"{_MODULE}._resolve_stt_mode", return_value="transcriptions"),
            patch(f"{_MODULE}._resolve_audio_input", side_effect=fake),
            patch(f"{_MODULE}.AsyncOpenAI", return_value=client),
        ):
            result = asyncio.run(
                transcribe_audio_file_literal(
                    str(tmp_path / "a.mp4"), "MP4", language="pt"
                )
            )

        assert calls[0]["max_duration_sec"] == _LITERAL_MAX_DURATION_SEC
        assert result == "primeira parte segunda parte"
        for call in client.audio.transcriptions.create.call_args_list:
            kwargs = call.kwargs
            assert kwargs["temperature"] == 0.0
            assert kwargs["prompt"] == _LITERAL_TRANSCRIPTION_PROMPT
            assert kwargs["language"] == "pt"
            assert kwargs["response_format"] == "json"
        # Temporários removidos
        assert not extracted.exists()
        assert not any(c.exists() for c in chunks)

    def test_audio_curto_usa_arquivo_normalizado_sem_language(self, tmp_path):
        extracted = tmp_path / "a_audio_extraido.ogg"
        fake, _ = _fake_resolve([], extracted)
        client = _mock_client(["texto"])

        with (
            patch(f"{_MODULE}._resolve_stt_mode", return_value="transcriptions"),
            patch(f"{_MODULE}._resolve_audio_input", side_effect=fake),
            patch(f"{_MODULE}.AsyncOpenAI", return_value=client),
        ):
            result = asyncio.run(
                transcribe_audio_file_literal(str(tmp_path / "a.mp3"), "mp3")
            )

        kwargs = client.audio.transcriptions.create.call_args.kwargs
        assert kwargs["file"][0] == extracted.name
        assert kwargs["language"] is omit
        assert result == "texto"
        assert not extracted.exists()

    def test_falha_na_api_propaga_e_limpa_temporarios(self, tmp_path):
        chunks = [tmp_path / "c0.ogg"]
        extracted = tmp_path / "a_audio_extraido.ogg"
        fake, _ = _fake_resolve(chunks, extracted)
        client = MagicMock()
        client.audio.transcriptions.create = AsyncMock(
            side_effect=RuntimeError("proxy fora")
        )

        with (
            patch(f"{_MODULE}._resolve_stt_mode", return_value="transcriptions"),
            patch(f"{_MODULE}._resolve_audio_input", side_effect=fake),
            patch(f"{_MODULE}.AsyncOpenAI", return_value=client),
            pytest.raises(RuntimeError, match="proxy fora"),
        ):
            asyncio.run(transcribe_audio_file_literal(str(tmp_path / "a.mp3"), "mp3"))

        assert not extracted.exists()
        assert not chunks[0].exists()


class TestSplitRespeitaLimiteDeDuracao:
    def test_limite_de_duracao_prevalece_sobre_o_de_tamanho(self, tmp_path):
        """Arquivo acima de max_bytes com chunks por tamanho longos demais deve
        ser cortado também pelo limite de duração."""
        audio = tmp_path / "audio.ogg"
        audio.write_bytes(b"x" * 1000)  # 1000 bytes em 100s → 10 bytes/s

        ffprobe_result = MagicMock(returncode=0, stdout=b"100.0\n", stderr=b"")
        silence_result = MagicMock(stderr=b"")
        split_calls: list[tuple[float, float]] = []

        def fake_run(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            if "silencedetect" in " ".join(cmd):
                return silence_result
            split_calls.append(
                (float(cmd[cmd.index("-ss") + 1]), float(cmd[cmd.index("-to") + 1]))
            )
            Path(cmd[-1]).write_bytes(b"chunk")
            return MagicMock(returncode=0, stderr=b"")

        with patch(f"{_MODULE}.subprocess.run", side_effect=fake_run):
            # Por tamanho (900 bytes) o alvo seria ~85s; por duração, ~19s.
            chunks = _split_audio_into_chunks(str(audio), 900, 20)

        assert len(chunks) == 6
        assert all(end - start <= 20 for start, end in split_calls)
