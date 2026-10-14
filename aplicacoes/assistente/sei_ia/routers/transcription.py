"""Endpoint de transcrição literal de arquivos avulsos de áudio/vídeo."""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from sei_extraction import AUDIO_EXTENSIONS

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.database.sei_client import sei_client
from sei_ia.data.pydantic_models import TranscricaoRequest, TranscricaoResponse
from sei_ia.routers.session.uploads import _remove_arquivos_avulsos_no_sei
from sei_ia.services.llm_models.speech_to_text import (
    LiteralTranscriptionUnsupportedError,
    transcribe_audio_file_literal,
)

setup_logging()

logger = logging.getLogger(__name__)

router = APIRouter()

ENDPOINT_NAME = "/transcription"


@router.post(
    ENDPOINT_NAME,
    tags=["transcription"],
    summary="Transcreve literalmente um arquivo avulso de áudio/vídeo",
    response_description="Texto transcrito",
    status_code=status.HTTP_200_OK,
)
async def transcribe_arquivo_avulso(request: TranscricaoRequest) -> TranscricaoResponse:
    """## Transcrição literal.

    Baixa o arquivo avulso do SEI (mesmo fluxo de upload do chat), transcreve
    via alias `speech-to-text` em modo literal e devolve o texto integral, sem
    passar por agente nem LLM conversacional. Após sucesso, sinaliza ao SEI que
    o arquivo avulso pode ser removido.

    - **415**: extensão não é de áudio/vídeo suportado.
    - **502**: falha ao baixar o arquivo do SEI.
    - **503**: o alias STT aponta para um backend de chat multimodal.
    """
    ext = request.extensao_arquivo_avulso.lower().strip(".")
    if ext not in AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Extensão '.{ext}' não suportada para transcrição. "
                f"Aceitas: {', '.join(sorted(AUDIO_EXTENSIONS))}."
            ),
        )

    loop = asyncio.get_running_loop()
    try:
        file_path = await loop.run_in_executor(
            None,
            sei_client.md_ia_download_arquivo_avulso,
            request.id_arquivo_avulso,
            ext,
        )
    except Exception as err:
        logger.exception(
            "Falha ao baixar arquivo avulso %s do SEI", request.id_arquivo_avulso
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Não foi possível baixar o arquivo avulso "
                f"{request.id_arquivo_avulso} do SEI."
            ),
        ) from err

    try:
        texto = await transcribe_audio_file_literal(
            file_path, ext, language=request.idioma
        )
    except LiteralTranscriptionUnsupportedError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(err)
        ) from err
    finally:
        Path(file_path).unlink(missing_ok=True)

    await _remove_arquivos_avulsos_no_sei([request])
    return TranscricaoResponse(texto=texto)
