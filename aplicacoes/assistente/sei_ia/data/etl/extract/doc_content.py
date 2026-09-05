"""Roteador de leitura de documento orientado pelo payload do ChatRequest.

A flag `download_ext` do payload é o único sinal de rota. `download_ext=True`
vira `DownloadPolicy.FORCE_DOWNLOAD` (Rota B, download + parser local);
`download_ext=False`/`None` vira `DownloadPolicy.TRUST_API` (Rota A, content_doc).
Não há escalação automática entre as rotas.

A árvore de decisão mora em ``sei_extraction.fetch_document_text``. Este módulo
resolve metadata, computa o ``DownloadPolicy``, monta os adapters de IO e mapeia
exceptions da lib em HTTPException.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException
from requests.exceptions import Timeout
from sei_extraction import (
    DownloadPolicy,
    fetch_document_text,
)
from sei_extraction.exceptions import (
    DocumentNotFoundError,
    EmptyDocumentError,
    ExtractionError,
    MediaTypeNotAllowedError,
    PaginationNotSupportedError,
    UnsupportedFormatError,
)

from sei_ia.configs.settings_config import settings
from sei_ia.data.database.sei_client import extraction_config, ocr_client, sei_client
from sei_ia.data.etl.extract.metadata import get_type_doc_from_id
from sei_ia.data.etl.extract.sei_adapters import make_adapters
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException204,
    HTTPException404,
    HTTPException406,
    HTTPException411DocumentTimeout,
    HTTPException412SeiApiTimeout,
    HTTPException415,
    HTTPException500,
)

logger = logging.getLogger(__name__)


def map_lib_exc_to_http(
    exc: ExtractionError,
    id_documento: str,
    num_doc_formatado: str | None,
    *,
    num_proc_formatado: str | None = None,
    download_ext: bool | None = None,
) -> HTTPException:
    """Translate a lib domain exception into the assistant's HTTPException.

    Mapping table (per plan):
      DocumentNotFoundError      → HTTPException404
      EmptyDocumentError         → HTTPException204
      PaginationNotSupportedError→ HTTPException406
      MediaTypeNotAllowedError   → HTTPException415  (subclass of UnsupportedFormatError)
      UnsupportedFormatError     → HTTPException406  (e.g. audio w/o transcriber)
      other ExtractionError      → HTTPException500
    """
    label = num_doc_formatado or id_documento
    if isinstance(exc, DocumentNotFoundError):
        mapped = HTTPException404(
            detail=f"O documento {label} não foi encontrado no SEI!"
        )
        reason = (
            "binary_not_found"
            if download_ext is True and num_doc_formatado
            else "source_not_found"
        )
    elif isinstance(exc, EmptyDocumentError):
        mapped = HTTPException204(
            detail=(
                f"Documento {label} sem conteúdo "
                f"(content_doc vazio; download_ext=false)."
            ),
            formatted_document_number=(
                str(num_doc_formatado).strip() if num_doc_formatado else None
            ),
        )
        reason = "content_doc_empty"
    elif isinstance(exc, PaginationNotSupportedError):
        mapped = HTTPException406(detail=str(exc))
        reason = "unsupported_format"
    elif isinstance(exc, MediaTypeNotAllowedError):
        mapped = HTTPException415(
            detail=f"ID DOC: {id_documento} (nº: {label}). Tipo de midia nao suportado."
        )
        reason = "unsupported_format"
    elif isinstance(exc, UnsupportedFormatError):
        mapped = HTTPException406(detail=str(exc))
        reason = "unsupported_format"
    else:
        # Remaining ExtractionError subclasses → 500
        mapped = HTTPException500(
            detail=f"Erro ao extrair o conteúdo do documento id {id_documento}!"
        )
        reason = "extraction_failed"
    mapped.formatted_document_number = (
        str(num_doc_formatado).strip() if num_doc_formatado else None
    )
    mapped.formatted_process_number = (
        str(num_proc_formatado).strip() if num_proc_formatado else None
    )
    mapped.content_reason = reason
    return mapped


async def _get_doc_content_internal(
    id_documento: str, docs_paged: list | None = None, download_ext: bool | None = None
) -> tuple[str, str]:
    """Decide a fonte de conteúdo do documento delegando ao orquestrador da lib.

    Regra:
      * Extensão de áudio → sempre baixa o binário e transcreve (não há Rota A
        para áudio); `download_ext`/paginação são ignorados.
      * `download_ext=True` → ``DownloadPolicy.FORCE_DOWNLOAD`` (Rota B).
      * `download_ext=False`/None → ``DownloadPolicy.TRUST_API`` (Rota A).
    """
    (
        _is_internal_unused,
        doc_extension,
        num_doc_formatado,
        _protocolo_formatado,
    ) = await get_type_doc_from_id(id_documento)

    policy = (
        DownloadPolicy.FORCE_DOWNLOAD
        if download_ext is True
        else DownloadPolicy.TRUST_API
    )

    pag_ini: int | None = None
    pag_fim: int | None = None
    for doc in docs_paged or []:
        if doc[0] == num_doc_formatado:
            pag_ini = doc[1]
            pag_fim = doc[2]
            break
    page_range: tuple[int | None, int | None] | None = (
        (pag_ini, pag_fim) if (pag_ini is not None or pag_fim is not None) else None
    )

    source, downloader, transcriber = make_adapters()

    loop = asyncio.get_running_loop()
    try:
        content = await loop.run_in_executor(
            None,
            lambda: fetch_document_text(
                id_documento=id_documento,
                extension=doc_extension,
                policy=policy,
                source=source,
                downloader=downloader,
                config=extraction_config,
                ocr_client=ocr_client,
                audio_transcriber=transcriber,
                page_range=page_range,
            ),
        )
    except ExtractionError as exc:
        http_exc = map_lib_exc_to_http(exc, id_documento, num_doc_formatado)
        logger.warning(
            f"Documento {id_documento} (nº {num_doc_formatado}): {type(exc).__name__}"
        )
        raise http_exc from exc

    return content, num_doc_formatado


async def get_doc_from_id(
    id_documento: str, docs_paged: list | None = None, download_ext: bool | None = None
) -> tuple[str, str]:
    """Recupera o conteúdo de um documento orientado pelo payload.

    Args:
        id_documento: identificador único do documento.
        docs_paged: lista (num_doc_formatado, pag_ini, pag_fim) — só aplicável
            quando `download_ext=True`.
        download_ext: flag do payload. `True` baixa via API do SEI + parser
            local; caso contrário usa `content_doc` da API.

    Returns:
        Tuple (conteúdo do documento, número do documento formatado).
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
    result = await sei_client.md_ia_consulta_conteudo_documento_async(
        id_documento=id_documento
    )
    if not result or not result.get("content_doc"):
        return False

    content = result.get("content_doc")
    return bool(content and str(content).strip())
