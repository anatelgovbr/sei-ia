"""Document reader module for extracting content from SEI documents."""

import asyncio
import logging

from sei_extraction.config import ExtractionConfig
from sei_extraction.document_fetch import DownloadPolicy, fetch_document_text
from sei_extraction.exceptions import (
    DocumentNotFoundError,
    EmptyDocumentError,
    ExtractionError,
    MediaTypeNotAllowedError,
    UnsupportedFormatError,
)
from sei_extraction.ocr.client import OpenAIVisionOCRClient

from jobs.db_models.sei_client import consulta_documentos
from jobs.document_extraction.sei_adapters import (
    SeiApiContentSource,
    SeiApiFileDownloader,
)
from jobs.envs import (
    LITELLM_PROXY_API_KEY,
    LITELLM_PROXY_URL,
    OCR_DPI,
    OCR_ENABLED,
    OCR_MAX_CONCURRENT_PAGES,
    OCR_MIN_TEXT_THRESHOLD,
    OCR_MODEL,
)

logger = logging.getLogger(__name__)

_extraction_config = ExtractionConfig(
    ocr_enabled=OCR_ENABLED,
    ocr_model=OCR_MODEL,
    ocr_min_text_threshold=OCR_MIN_TEXT_THRESHOLD,
    ocr_dpi=OCR_DPI,
    ocr_max_concurrent_pages=OCR_MAX_CONCURRENT_PAGES,
)
_ocr_client = OpenAIVisionOCRClient(
    base_url=LITELLM_PROXY_URL,
    api_key=LITELLM_PROXY_API_KEY or "not-needed",
)


async def get_document_content(id_documento: str) -> str:
    """Extrai o conteúdo de um documento SEI.

    Fluxo:
    1. Consulta metadados do documento no banco de dados
    2. Computa a política de rota a partir do content_type:
       - html/interno (content_type in ("html", "")) → TRUST_API
       - externo/binário → FORCE_DOWNLOAD
    3. Delega ao orquestrador ``sei_extraction.fetch_document_text``
    4. Retorna o texto extraído

    Args:
        id_documento: ID do documento no SEI.

    Returns:
        Conteúdo do documento extraído em texto/markdown.
        Retorna "" para documentos sem conteúdo (skip silencioso).

    Raises:
        RuntimeError: Documento não encontrado ou erro de extração irrecuperável.
    """
    logger.debug(f"Getting content for document {id_documento}")

    try:
        df_doc_info = consulta_documentos(id_documento)

        if df_doc_info.empty:
            logger.error(f"Document {id_documento} not found")
            msg = f"Document {id_documento} not found"
            raise RuntimeError(msg)

        doc_info = df_doc_info.iloc[0]
        content_type = doc_info.get("content_type", "html")
        # Internal docs report content_type "html" or "" — both mean HTML.
        doc_extension = content_type.lower() or "html"

        # Per-content-type policy: internal/HTML docs trust the API content_doc;
        # external/binary docs must download+extract.  A blanket TRUST_API would
        # silently drop external PDFs whose content_doc comes back empty.
        policy = (
            DownloadPolicy.TRUST_API
            if doc_extension == "html"
            else DownloadPolicy.FORCE_DOWNLOAD
        )

        logger.debug(
            f"Document {id_documento}: content_type={content_type!r}, policy={policy.value}"
        )

        source = SeiApiContentSource()
        downloader = SeiApiFileDownloader()

        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(
            None,
            lambda: fetch_document_text(
                id_documento=id_documento,
                extension=doc_extension,
                policy=policy,
                source=source,
                downloader=downloader,
                config=_extraction_config,
                ocr_client=_ocr_client,
                audio_transcriber=None,
                page_range=None,
            ),
        )
        return content

    except EmptyDocumentError:
        # Internal document with empty content_doc: skip silently.
        # embedding_service.generate_embeddings_for_documents treats "" as
        # "no content" → appends to no_content_ids, marks as vectorized to exit
        # the retry queue (embedding_service.py:264-271).
        logger.warning(f"Document {id_documento} has no content")
        return ""

    except DocumentNotFoundError as e:
        logger.error(f"Document {id_documento} not found: {e}")
        msg = f"Document {id_documento} not found"
        raise RuntimeError(msg) from e

    except (UnsupportedFormatError, MediaTypeNotAllowedError) as e:
        # Unsupported extension: return "" so the embedder loop skips this doc.
        logger.warning(f"Document {id_documento} has unsupported format: {e}")
        return ""

    except ExtractionError as e:
        logger.exception(f"Error getting content for document {id_documento}")
        msg = f"Failed to get document content: {e}"
        raise RuntimeError(msg) from e

    except RuntimeError:
        raise

    except Exception as e:
        logger.exception(f"Error getting content for document {id_documento}")
        msg = f"Failed to get document content: {e}"
        raise RuntimeError(msg) from e
