"""Módulo para transcrição de áudio via LiteLLM Proxy.

Utiliza o endpoint /v1/audio/transcriptions do LiteLLM Proxy, que segue a
interface OpenAI Audio Transcriptions API.

Uso:
    from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

    texto = await transcribe_audio_file("/tmp/audio_up123_abc.mp3", "mp3")
"""

import logging
from pathlib import Path

from openai import AsyncOpenAI

from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings

setup_logging()
logger = logging.getLogger(__name__)


# Mapa de extensão → MIME type para a requisição multipart
_AUDIO_MIME_TYPES: dict[str, str] = {
    "mp3": "audio/mpeg",
    "mp4": "audio/mp4",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "m4a": "audio/mp4",
    "webm": "audio/webm",
    "flac": "audio/flac",
    "aac": "audio/aac",
    "opus": "audio/opus",
    "wma": "audio/x-ms-wma",
}


def _get_audio_mime_type(extensao: str) -> str:
    """Retorna o MIME type para a extensão de áudio fornecida."""
    ext = extensao.lower().strip(".")
    return _AUDIO_MIME_TYPES.get(ext, "application/octet-stream")


async def transcribe_audio_file(file_path: str, extensao: str) -> str:
    """Transcreve um arquivo de áudio usando o serviço speech-to-text do LiteLLM Proxy.

    O arquivo deve estar disponível em disco (ex: /tmp/) antes da chamada.
    A requisição é feita ao endpoint /v1/audio/transcriptions do LiteLLM Proxy,
    seguindo a interface OpenAI Audio Transcriptions API.

    Args:
        file_path: Caminho completo do arquivo de áudio em disco (ex: /tmp/audio_up123.mp3).
        extensao: Extensão do arquivo sem ponto (ex: "mp3", "wav", "ogg").

    Returns:
        Texto transcrito.

    Raises:
        Exception: Em caso de falha na comunicação com o LiteLLM Proxy.
    """
    client = AsyncOpenAI(
        api_key=settings.LITELLM_PROXY_API_KEY or "dummy-key",
        base_url=f"{settings.LITELLM_PROXY_URL}/v1",
        timeout=float(settings.TIMEOUT_API),
        max_retries=settings.MAX_RETRIES,
    )

    file_path_obj = Path(file_path)
    mime_type = _get_audio_mime_type(extensao)

    logger.info(
        f"Iniciando transcrição: '{file_path_obj.name}' "
        f"(mime={mime_type}) via {settings.LITELLM_PROXY_URL}"
    )

    with file_path_obj.open("rb") as f:
        file_content = f.read()

    transcript = await client.audio.transcriptions.create(
        model=settings.LITELLM_STT_MODEL_NAME,
        file=(file_path_obj.name, file_content, mime_type),
    )

    transcribed_text = transcript.text
    logger.info(
        f"Transcrição concluída: '{file_path_obj.name}' ({len(transcribed_text)} chars)"
    )
    return transcribed_text
