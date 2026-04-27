"""Módulo de extracao de documentos internos e externos."""

import asyncio
import logging

from requests.exceptions import Timeout

from sei_ia.configs.settings_config import settings
from sei_ia.data.database.sei_db_handlers import SEIDBHandler
from sei_ia.data.etl.extract.external import get_doc_ext_from_id
from sei_ia.data.etl.extract.internal import get_doc_int_from_id
from sei_ia.data.etl.extract.metadata import get_type_doc_from_id
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException204,
    HTTPException406,
    HTTPException411DocumentTimeout,
    HTTPException412SeiApiTimeout,
    HTTPException415,
)

logger = logging.getLogger(__name__)

EXT_PERMITIDAS = [
    "pdf",
    "html",
    "htm",
    "txt",
    "csv",
    "xml",
    "ods",
    "odt",
    "odp",
    "doc",
    "docx",
    "json",
    "ppt",
    "pptx",
    "rtf",
    "xls",
    "xlsb",
    "xlsm",
    "xlsx",
]


async def _get_doc_content_internal(
    id_documento: str, docs_paged: list | None = None, download_ext: bool | None = None
) -> tuple[str, str]:
    """Função interna para recuperar conteúdo do documento de forma assíncrona."""
    (internal, doc_extension, num_doc_formatado, _) = await get_type_doc_from_id(
        id_documento
    )  # protocolo_formatado

    if not internal and doc_extension not in EXT_PERMITIDAS:
        msg = f"ID DOC: {id_documento} (nº: {num_doc_formatado}). Tipo de midia nao suportado."
        logger.warning(msg)
        raise HTTPException415(detail=msg)

    pag_ini = None
    pag_fim = None
    for doc in docs_paged or []:
        if doc[0] == num_doc_formatado:
            pag_ini = doc[1]
            pag_fim = doc[2]
            break

    if download_ext is True and not internal:
        return (
            get_doc_ext_from_id(
                id_documento, pag_ini, pag_fim, doc_extension, force_download=True
            ),
            num_doc_formatado,
        )

    if internal:
        if pag_ini or pag_fim:
            logger.warning(
                f"O documento id {id_documento} (nº {num_doc_formatado}) é interno!"
            )
            msg = f"Não posso definir um intervalo de páginas para o documento nº {num_doc_formatado}!"
            raise HTTPException406(detail=msg)
        try:
            return (await get_doc_int_from_id(id_documento), num_doc_formatado)
        except HTTPException204:
            return (get_doc_ext_from_id(id_documento), num_doc_formatado)

    return (
        get_doc_ext_from_id(id_documento, pag_ini, pag_fim, doc_extension),
        num_doc_formatado,
    )


async def get_doc_from_id(
    id_documento: str, docs_paged: list | None = None, download_ext: bool | None = None
) -> tuple[str, str]:
    """Recupera o conteúdo de um documento com base em seu identificador de forma assíncrona.

    Args:
        id_documento: O identificador único do documento a ser recuperado
        docs_paged: lista de número de documentos e respectivas paginações
        download_ext: Flag para indicar se deve fazer download do arquivo externo

    Returns:
        Tupla com (conteúdo do documento, número do documento formatado)
    """
    max_retries = 1
    retry_count = 0

    while retry_count < max_retries:
        try:
            return await asyncio.wait_for(
                _get_doc_content_internal(id_documento, docs_paged, download_ext),
                timeout=settings.TIMEOUT_GET_DOC,
            )
        except TimeoutError as exc:
            retry_count += 1
            if retry_count >= max_retries:
                logger.exception(
                    f"Timeout durante o processamento do documento {id_documento} após {max_retries} tentativas"
                )
                raise HTTPException411DocumentTimeout(document_id=id_documento) from exc
            else:
                logger.warning(
                    f"Timeout durante o processamento do documento {id_documento} - tentativa {retry_count}/{max_retries}"
                )
                await asyncio.sleep(
                    settings.BACKOFF_INITIAL_WAIT
                    * (settings.RETRY_BACKOFF_FACTOR ** (retry_count - 1))
                )
        except HTTPException412SeiApiTimeout:
            raise
        except Timeout as exc:
            retry_count += 1
            if retry_count >= max_retries:
                logger.exception(
                    f"Timeout da API SEI ao consultar documento {id_documento} após {max_retries} tentativas"
                )
                raise HTTPException412SeiApiTimeout(document_id=id_documento) from exc
            else:
                logger.warning(
                    f"Timeout da API SEI ao consultar documento {id_documento} - tentativa {retry_count}/{max_retries}"
                )
                await asyncio.sleep(
                    settings.BACKOFF_INITIAL_WAIT
                    * (settings.RETRY_BACKOFF_FACTOR ** (retry_count - 1))
                )

    raise HTTPException411DocumentTimeout(document_id=id_documento)


async def check_exist_content(id_documento: str) -> bool:
    """Verifica se um documento com o ID fornecido existe e possui conteúdo de forma assíncrona.

    Args:
        id_documento: O identificador único do documento a ser verificado

    Returns:
        True se o documento existe e possui conteúdo, False caso contrário
    """
    result = await SEIDBHandler.md_ia_consulta_conteudo_documento_async(
        id_documento=id_documento
    )
    if not result or not result.get("content_doc"):
        return False

    content = result.get("content_doc")
    return bool(content and str(content).strip())
