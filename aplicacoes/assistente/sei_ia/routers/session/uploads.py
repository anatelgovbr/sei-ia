"""Helpers para processamento, confirmação e cleanup de uploads (arquivos avulsos)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException as FastAPIHTTPException

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.database.sei_client import sei_client
from sei_ia.data.etl.extract.uploads import (
    AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION,
    IMAGE_ATTACHMENT_SYSTEM_INSTRUCTION,
    ArquivoAvulsoProcessingError,
    process_arquivos_avulsos,
    process_uploads_tolerant,
)
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.cache.topic_attachments import persist_topic_attachments
from sei_ia.services.counter import token_counter

setup_logging()
logger = logging.getLogger(__name__)


async def _remove_arquivos_avulsos_no_sei(
    arquivos_avulsos, *, eligible_ids: set[int] | None = None
) -> None:
    """Sinaliza ao SEI que os arquivos avulsos processados podem ser removidos.

    Esta função só deve ser chamada depois de ``process_arquivos_avulsos``
    concluir o lote inteiro. A API do SEI aceita um ID por chamada; por isso,
    não há remoção durante o processamento individual de cada upload.
    """
    loop = asyncio.get_running_loop()
    for arquivo_avulso in arquivos_avulsos:
        if (
            eligible_ids is not None
            and arquivo_avulso.id_arquivo_avulso not in eligible_ids
        ):
            continue
        try:
            await loop.run_in_executor(
                None,
                sei_client.md_ia_remove_arquivos_avulsos,
                [arquivo_avulso.id_arquivo_avulso],
            )
        except Exception:
            logger.warning(
                "Falha ao sinalizar remoção do arquivo avulso %s no SEI",
                arquivo_avulso.id_arquivo_avulso,
                exc_info=True,
            )
            continue
        logger.debug(
            "Arquivo avulso %s sinalizado para remoção no SEI",
            arquivo_avulso.id_arquivo_avulso,
        )


async def _apply_arquivos_avulsos_to_state(
    request,
    user_state: UserState,
    *,
    remove_from_sei: bool = True,
    tolerant_uploads: bool = False,
) -> set[str]:
    """Processa os arquivos avulsos do request e injeta no `user_state`.

    Retorna o conjunto de paths em /tmp/ que o caller deve apagar no `finally`
    do handler (incluindo paths já baixados quando um upload subsequente falhou).
    ``remove_from_sei=False`` permite que endpoints streaming só confirmem a
    remoção depois que o restante do request concluir com sucesso.

    Raises:
        FastAPIHTTPException(422): quando algum upload falha. Body inclui
            `{error, filename, extensao, message}` para o cliente identificar
            qual arquivo deu erro.
    """
    arquivos_avulsos = getattr(request, "arquivos_avulsos", None)
    if not arquivos_avulsos:
        return set()

    try:
        outcome = await (
            process_uploads_tolerant(arquivos_avulsos)
            if tolerant_uploads
            else process_arquivos_avulsos(arquivos_avulsos)
        )
    except ArquivoAvulsoProcessingError as exc:
        error = FastAPIHTTPException(
            status_code=422,
            detail={
                "error": "arquivo_avulso_failed",
                "legacy_error": "upload_failed",
                "filename": exc.filename,
                "extensao": exc.extensao,
                "message": exc.message,
            },
        )
        error.cleanup_paths = getattr(exc, "cleanup_paths", set())
        raise error from exc

    if outcome.text_block:
        user_state["user_request"] += f"\n\n{outcome.text_block}"
        user_state["all_tokens_counter"] += token_counter(outcome.text_block)
    if outcome.image_attachments:
        user_state["image_attachments"] = outcome.image_attachments
    user_state["upload_removal_ids"] = sorted(outcome.removal_ids)
    user_state["upload_outcomes"] = [
        {
            "id": attachment.id_arquivo_avulso,
            "name": attachment.nome_arquivo,
            "type": "image" if attachment.tipo == "imagem" else attachment.tipo,
            "state": attachment.content_state,
            "reason": attachment.content_reason,
        }
        for attachment in outcome.attachments
    ]
    has_audio = any(
        attachment.tipo == "audio" and attachment.content_state != "unavailable"
        for attachment in outcome.attachments
    )
    if has_audio:
        user_state["system_prompt"] = (
            user_state.get("system_prompt", "") + AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION
        )
    if outcome.image_attachments:
        user_state["system_prompt"] = (
            user_state.get("system_prompt", "") + IMAGE_ATTACHMENT_SYSTEM_INSTRUCTION
        )

    # Persiste anexos no Redis ANTES da remoção no SEI: se persistência
    # falhar (fail-open), o anexo ainda está no prompt corrente; se a
    # remoção falhar, o anexo já está disponível para consulta posterior.
    id_topico = user_state.get("id_topico")
    if id_topico is not None and outcome.attachments:
        try:
            await persist_topic_attachments(
                id_topico=int(id_topico),
                attachments=outcome.attachments,
            )
        except Exception:
            logger.warning(
                "Falha ao persistir anexos do tópico %s no Redis (fail-open)",
                id_topico,
                exc_info=True,
            )

    if remove_from_sei:
        # Só chegamos aqui depois de todos os uploads terem sido processados e, se
        # houver, persistidos. O cleanup de /tmp é independente e nunca significa
        # que o arquivo-fonte foi removido do SEI.
        await _remove_arquivos_avulsos_no_sei(
            arquivos_avulsos,
            eligible_ids=outcome.removal_ids,
        )

    return outcome.temp_files
