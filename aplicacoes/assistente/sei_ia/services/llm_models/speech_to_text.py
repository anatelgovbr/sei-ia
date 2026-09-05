"""Módulo para transcrição de áudio via LiteLLM Proxy.

O alias público fixo ``speech-to-text`` pode apontar, no
``litellm_config.yaml`` do proxy, para dois tipos de backend bem diferentes:

- Whisper-like (ex: ``azure/whisper``): usa o endpoint
  ``/v1/audio/transcriptions`` (interface OpenAI Audio Transcriptions API).
- Gemini flash/flash-lite (ex: ``openai/seiia-ds-gemini-flash-lite``, via
  passthrough): esse endpoint não é suportado pelo LiteLLM para esse provider
  (erro "Unmapped provider passed in"). O caminho que funciona é
  ``/v1/chat/completions`` com o áudio como bloco multimodal
  (``type: input_audio``), o mesmo padrão já usado para imagem.

Qual dos dois é usado é decidido em runtime, sem exigir configuração do lado
da app: ``_resolve_stt_mode`` consulta ``GET /model/info`` no proxy para
descobrir o modelo real por trás do alias e cacheia o resultado com TTL. Assim,
uma troca de backend no ``litellm_config.yaml`` reflete em poucos minutos sem
reiniciar o assistente. Se a consulta falhar
(rede, ou rota bloqueada por permissão da virtual key em PD — caso esperado),
cai em ``"transcriptions"`` (Whisper), que é o comportamento atual, com
warning.

Uso:
    from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

    texto = await transcribe_audio_file("/tmp/audio_up123_abc.mp3", "mp3")
"""

import asyncio
import base64
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from openai import AsyncOpenAI

from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import LITELLM_STT_ALIAS, settings

setup_logging()
logger = logging.getLogger(__name__)

_WHISPER_MAX_BYTES = 25 * 1024 * 1024  # 25 MB — limite da API Whisper/OpenAI
_WHISPER_MAX_DURATION_SEC = (
    20 * 60
)  # 20 min por chunk — limite prático antes de timeout

_STT_MODEL_INFO_TIMEOUT_S = 2.0
_STT_MODE_TTL_S = 300.0  # 5 min — troca de backend no proxy reflete sem restart do app
_stt_mode_cache: dict[str, tuple[str, float]] = {}

_CHAT_AUDIO_PROMPT = (
    "Transcreva o áudio a seguir com precisão, exatamente como falado. "
    "Responda apenas com o texto transcrito, sem comentários adicionais."
)

# Documenta as extensões de entrada aceitas e seu MIME type. Na prática, todo
# áudio é sempre recomprimido para OGG antes de ir para a API (ver
# _resolve_audio_input), então em runtime só a entrada "ogg" deste mapa é
# consultada — as demais chaves ficam aqui como referência do que o ffmpeg
# aceita normalizar.
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


def _classify_stt_mode(backend_model: str | None) -> str:
    """Classifica o backend real (``litellm_params.model``) num modo de chamada.

    ``None`` ou qualquer valor não reconhecido cai em "transcriptions" — é o
    modo do Whisper, comportamento atual e o mais seguro como default.
    """
    if not backend_model:
        return "transcriptions"
    lowered = backend_model.lower()
    if "whisper" in lowered:
        return "transcriptions"
    if "gemini" in lowered or "flash" in lowered:
        return "chat_audio"
    return "transcriptions"


def _fetch_stt_backend_model(alias: str) -> str | None:
    """Busca ``litellm_params.model`` do alias no ``/model/info`` do proxy."""
    resp = httpx.get(
        f"{settings.LITELLM_PROXY_URL.rstrip('/')}/model/info",
        headers={
            "Authorization": f"Bearer {settings.LITELLM_PROXY_API_KEY or 'dummy-key'}"
        },
        timeout=_STT_MODEL_INFO_TIMEOUT_S,
    )
    resp.raise_for_status()
    for entry in resp.json().get("data", []):
        if entry.get("model_name") == alias:
            return entry.get("litellm_params", {}).get("model")
    return None


def _resolve_stt_mode(alias: str) -> str:
    """Modo de chamada STT do alias: "transcriptions" (Whisper) ou "chat_audio"
    (Gemini flash/flash-lite via chat multimodal).

    Resolvido via ``/model/info`` do proxy e cacheado por alias com TTL de
    ``_STT_MODE_TTL_S`` — troca de backend no ``litellm_config.yaml`` (sem
    reiniciar o assistente) reflete em poucos minutos, não só no próximo
    restart do processo. Nunca levanta exceção: falha de rede/permissão cai em
    "transcriptions" com warning — rota bloqueada por permissão da virtual key
    é o caso esperado em PD.
    """
    cached = _stt_mode_cache.get(alias)
    if cached is not None and (time.monotonic() - cached[1]) < _STT_MODE_TTL_S:
        return cached[0]

    backend_model: str | None = None
    fetch_failed = False
    try:
        backend_model = _fetch_stt_backend_model(alias)
    except Exception:  # noqa: BLE001
        fetch_failed = True
        logger.warning(
            "Consulta a /model/info falhou para '%s' (rota bloqueada em PD é o "
            "caso esperado)",
            alias,
            exc_info=True,
        )

    if fetch_failed and cached is not None:
        # Mantém o último modo conhecido (stale) em vez de derrubar pro default
        # em toda falha transitória de rede após o TTL expirar.
        logger.warning(
            "Reaproveitando modo STT anterior (stale) de '%s': %s",
            alias,
            cached[0],
        )
        _stt_mode_cache[alias] = (cached[0], time.monotonic())
        return cached[0]

    mode = _classify_stt_mode(backend_model)
    if backend_model is None:
        logger.warning(
            "Backend de '%s' indisponível via /model/info; usando modo default "
            "'transcriptions' (Whisper)",
            alias,
        )
    else:
        logger.info(
            "Modo STT de '%s' resolvido via /model/info: backend=%s -> modo=%s",
            alias,
            backend_model,
            mode,
        )

    _stt_mode_cache[alias] = (mode, time.monotonic())
    return mode


async def _transcribe_via_whisper(
    client: AsyncOpenAI, model: str, filename: str, content: bytes, mime: str
) -> str:
    """Transcreve via /v1/audio/transcriptions (Whisper-like)."""
    transcript = await client.audio.transcriptions.create(
        model=model,
        file=(filename, content, mime),
        extra_body={"tags": ["agents:audio_transcription"]},
    )
    return transcript.text


async def _transcribe_via_chat_audio(
    client: AsyncOpenAI, model: str, content: bytes, extensao: str
) -> str:
    """Transcreve via /v1/chat/completions, áudio como bloco multimodal
    (``type: input_audio``) — caminho para Gemini flash/flash-lite, que não
    tem suporte a /v1/audio/transcriptions no LiteLLM."""
    audio_b64 = base64.b64encode(content).decode("utf-8")
    resp = await client.chat.completions.create(
        model=model,
        temperature=0.0,
        extra_body={"tags": ["agents:audio_transcription"]},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _CHAT_AUDIO_PROMPT},
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_b64, "format": extensao},
                    },
                ],
            }
        ],
    )
    return resp.choices[0].message.content or ""


async def _transcribe_one(
    mode: str,
    client: AsyncOpenAI,
    model: str,
    filename: str,
    content: bytes,
    mime: str,
    extensao: str,
) -> str:
    """Despacha a transcrição de um único arquivo/chunk para o modo resolvido."""
    if mode == "chat_audio":
        return await _transcribe_via_chat_audio(client, model, content, extensao)
    return await _transcribe_via_whisper(client, model, filename, content, mime)


def _transcode_to_ogg(input_path: str) -> str:
    """Recomprime um arquivo de áudio (ou extrai a trilha de um vídeo) para Opus/OGG
    16 kHz mono via ffmpeg. Funciona para qualquer extensão de entrada suportada
    (mp3, mp4, wav, m4a, webm, flac, aac, wma) — o ffmpeg detecta o formato pelo
    conteúdo, não pela extensão, e ``-vn`` é inofensivo em entradas sem vídeo.

    Returns the path to the transcoded OGG file (caller is responsible for deletion).
    Raises RuntimeError if ffmpeg fails.
    """
    out_path = str(Path(input_path).with_suffix("")) + "_audio_extraido.ogg"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vn",
        "-acodec",
        "libopus",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-b:a",
        "32k",
        out_path,
    ]
    result = subprocess.run(  # noqa: S603 S607  # NOSONAR
        cmd, capture_output=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg falhou ao recomprimir áudio de '{Path(input_path).name}': "
            f"{result.stderr.decode(errors='replace')}"
        )
    return out_path


def _get_audio_duration_sec(input_path: str) -> float:
    """Retorna a duração em segundos do arquivo de áudio via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        input_path,
    ]
    result = subprocess.run(  # noqa: S603 S607  # NOSONAR
        cmd, capture_output=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe falhou ao obter duração de '{Path(input_path).name}': "
            f"{result.stderr.decode(errors='replace')}"
        )
    return float(result.stdout.decode().strip())


def _detect_silence_points(input_path: str) -> list[float]:
    """Retorna pontos médios (segundos) dos períodos de silêncio detectados no áudio."""
    cmd = [
        "ffmpeg",
        "-i",
        input_path,
        "-af",
        "silencedetect=noise=-30dB:duration=0.3",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(  # noqa: S603 S607  # NOSONAR
        cmd, capture_output=True, timeout=300
    )
    text = result.stderr.decode(errors="replace")
    starts = [
        float(m.group(1)) for m in re.finditer(r"silence_start: (\d+\.?\d*)", text)
    ]
    ends = [float(m.group(1)) for m in re.finditer(r"silence_end: (\d+\.?\d*)", text)]
    return [(s + e) / 2 for s, e in zip(starts, ends, strict=True)]


def _split_audio_into_chunks(
    input_path: str,
    max_bytes: int,
    target_chunk_duration_sec: float | None = None,
) -> list[str]:
    """Divide áudio em chunks cortando em pontos de silêncio.

    target_chunk_duration_sec: quando informado, usa esse valor como duração alvo por
    chunk (útil quando o gatilho foi duração, não tamanho). Caso omitido, calcula a
    duração alvo a partir de max_bytes e da taxa bytes/s do arquivo.

    Returns list of chunk paths (caller is responsible for deletion).
    Raises RuntimeError if ffprobe or ffmpeg fails.
    """
    path = Path(input_path)
    total_size = path.stat().st_size
    total_duration = _get_audio_duration_sec(input_path)

    if target_chunk_duration_sec is not None:
        target_duration = target_chunk_duration_sec * 0.95
    else:
        # Duração alvo por chunk com margem de 5% para não ultrapassar max_bytes
        size_per_sec = total_size / total_duration
        target_duration = (max_bytes / size_per_sec) * 0.95

    silence_points = _detect_silence_points(input_path)
    logger.debug(
        f"Pontos de silêncio detectados em '{path.name}': {len(silence_points)}"
    )

    chunks: list[str] = []
    start = 0.0
    idx = 0
    base = str(path.with_suffix(""))
    suffix = path.suffix

    while start < total_duration - 0.1:
        target_end = min(start + target_duration, total_duration)

        if target_end < total_duration:
            candidates = [p for p in silence_points if start < p <= target_end]
            # Usa o silêncio mais próximo antes do limite; cai no corte exato se não houver
            end = candidates[-1] if candidates else target_end
        else:
            end = total_duration

        out_path = f"{base}_chunk{idx:03d}{suffix}"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-ss",
            str(start),
            "-to",
            str(end),
            "-c",
            "copy",
            out_path,
        ]
        result = subprocess.run(  # noqa: S603 S607  # NOSONAR
            cmd, capture_output=True, timeout=300
        )
        if result.returncode != 0:
            for c in chunks:
                Path(c).unlink(missing_ok=True)
            raise RuntimeError(
                f"ffmpeg falhou ao criar chunk {idx} de '{path.name}': "
                f"{result.stderr.decode(errors='replace')}"
            )
        chunk_size_mb = Path(out_path).stat().st_size / (1024 * 1024)
        logger.info(
            f"Chunk {idx}: {start:.1f}s-{end:.1f}s -> '{Path(out_path).name}' "
            f"({chunk_size_mb:.1f} MB)"
        )
        chunks.append(out_path)
        start = end
        idx += 1

    return chunks


async def _transcribe_chunks(
    chunks: list[str], client: AsyncOpenAI, model: str, mode: str = "transcriptions"
) -> str:
    """Transcreve chunks em paralelo (máx. 2 simultâneos) e remonta na ordem original."""
    semaphore = asyncio.Semaphore(2)

    async def _transcrever(idx: int, chunk_path: str) -> tuple[int, str]:
        async with semaphore:
            ext = Path(chunk_path).suffix.lstrip(".")
            mime = _get_audio_mime_type(ext)
            with Path(chunk_path).open("rb") as f:  # NOSONAR
                content = f.read()
            logger.info(
                f"Transcrevendo chunk {idx + 1}/{len(chunks)}: '{Path(chunk_path).name}'"
            )
            texto = await _transcribe_one(
                mode, client, model, Path(chunk_path).name, content, mime, ext
            )
            return (idx, texto)

    resultados = await asyncio.gather(
        *[_transcrever(i, c) for i, c in enumerate(chunks)]
    )
    return " ".join(texto for _, texto in sorted(resultados, key=lambda x: x[0]))


@dataclass
class _AudioPrep:
    """Resultado da preparação do áudio: chunks (se dividido) e caminho recomprimido (se houve)."""

    chunk_paths: list[str] = field(default_factory=list)
    extracted_path: str | None = None


async def _resolve_audio_input(
    file_path: str,
    ext: str,
    loop: asyncio.AbstractEventLoop,
    prep: _AudioPrep,
) -> None:
    """Recomprime para OGG e/ou divide em chunks se o áudio ultrapassar os limites da API.

    A recompressão via ffmpeg roda sempre que a extensão de entrada não é OGG,
    independente do tamanho do arquivo: nem todo formato aceito no upload
    (aac, opus, wma, ...) tem suporte confiável de extração pelo
    Whisper/Gemini, então a mídia original nunca é enviada direto ao modelo —
    é sempre normalizada para um único formato conhecido primeiro.

    Popula ``prep`` incrementalmente (em vez de retornar só ao final) para que o
    caminho recomprimido fique visível ao chamador mesmo se a divisão em chunks
    falhar depois — necessário para a limpeza no ``finally`` de
    ``transcribe_audio_file``.
    """
    if ext == "ogg":
        working_path = file_path
    else:
        logger.info(
            f"Extraindo/convertendo áudio de '{Path(file_path).name}' ({ext}) "
            "para Opus/OGG via ffmpeg..."
        )
        prep.extracted_path = await loop.run_in_executor(
            None, _transcode_to_ogg, file_path
        )
        working_path = prep.extracted_path

    working_size = Path(working_path).stat().st_size
    if working_size > _WHISPER_MAX_BYTES:
        working_mb = working_size / (1024 * 1024)
        logger.warning(
            f"Áudio '{Path(working_path).name}' tem {working_mb:.1f} MB "
            f"(> 25 MB). Dividindo em chunks por pontos de silêncio..."
        )
        prep.chunk_paths = await loop.run_in_executor(
            None, _split_audio_into_chunks, working_path, _WHISPER_MAX_BYTES
        )
        return

    working_duration = await loop.run_in_executor(
        None, _get_audio_duration_sec, working_path
    )
    if working_duration <= _WHISPER_MAX_DURATION_SEC:
        return

    working_min = working_duration / 60
    max_min = _WHISPER_MAX_DURATION_SEC / 60
    logger.warning(
        f"Áudio '{Path(working_path).name}' tem "
        f"{working_min:.1f} min (> {max_min:.0f} min). "
        f"Dividindo em chunks por pontos de silêncio..."
    )
    prep.chunk_paths = await loop.run_in_executor(
        None,
        _split_audio_into_chunks,
        working_path,
        _WHISPER_MAX_BYTES,
        _WHISPER_MAX_DURATION_SEC,
    )


async def transcribe_audio_file(file_path: str, extensao: str) -> str:
    """Transcreve um arquivo de áudio usando o serviço speech-to-text do LiteLLM Proxy.

    O áudio é sempre recomprimido para Opus/OGG via ffmpeg antes de enviar à API
    (arquivos já em OGG pulam essa etapa) — a mídia na extensão original nunca é
    enviada diretamente ao modelo, mesmo abaixo de 25 MB, pois formatos como aac,
    opus e wma não têm suporte confiável de extração pelo Whisper/Gemini. Se o
    OGG resultante ainda ultrapassar 25 MB ou 20 min de duração, divide em chunks
    cortando em pontos de silêncio e transcreve em paralelo.

    Args:
        file_path: Caminho completo do arquivo de áudio em disco (ex: /tmp/audio_up123.mp3).
        extensao: Extensão do arquivo sem ponto (ex: "mp3", "wav", "mp4").

    Returns:
        Texto transcrito.

    Raises:
        RuntimeError: Se a recompressão via ffmpeg ou a divisão em chunks falhar.
        Exception: Em caso de falha na comunicação com o LiteLLM Proxy.
    """
    ext = extensao.lower().strip(".")
    prep = _AudioPrep()

    try:
        loop = asyncio.get_event_loop()
        await _resolve_audio_input(file_path, ext, loop, prep)

        client = AsyncOpenAI(
            api_key=settings.LITELLM_PROXY_API_KEY or "dummy-key",
            base_url=f"{settings.LITELLM_PROXY_URL}/v1",
            timeout=float(settings.TIMEOUT_API),
            max_retries=settings.MAX_RETRIES,
        )
        mode = await loop.run_in_executor(None, _resolve_stt_mode, LITELLM_STT_ALIAS)

        if prep.chunk_paths:
            logger.info(
                f"Transcrevendo {len(prep.chunk_paths)} chunks de '{Path(file_path).name}'..."
            )
            transcribed_text = await _transcribe_chunks(
                prep.chunk_paths, client, LITELLM_STT_ALIAS, mode
            )
            logger.info(
                f"Transcrição concluída: '{Path(file_path).name}' "
                f"({len(transcribed_text)} chars, {len(prep.chunk_paths)} chunks)"
            )
            return transcribed_text

        actual_path = prep.extracted_path if prep.extracted_path else file_path
        actual_ext = "ogg" if prep.extracted_path else ext

        file_path_obj = Path(actual_path)
        mime_type = _get_audio_mime_type(actual_ext)

        logger.info(
            f"Iniciando transcrição: '{file_path_obj.name}' "
            f"(mime={mime_type}, modo={mode}) via {settings.LITELLM_PROXY_URL}"
        )

        with file_path_obj.open("rb") as f:  # NOSONAR
            file_content = f.read()

        transcribed_text = await _transcribe_one(
            mode,
            client,
            LITELLM_STT_ALIAS,
            file_path_obj.name,
            file_content,
            mime_type,
            actual_ext,
        )
        logger.info(
            f"Transcrição concluída: '{Path(file_path).name}' ({len(transcribed_text)} chars)"
        )
        return transcribed_text

    finally:
        if prep.extracted_path:
            Path(prep.extracted_path).unlink(missing_ok=True)
        for chunk in prep.chunk_paths:
            Path(chunk).unlink(missing_ok=True)
