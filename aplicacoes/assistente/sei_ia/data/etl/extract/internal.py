"""Módulo de extração de documentos internos."""

import logging

from sei_ia.data.database.sei_db_handlers import SEIDBHandler
from sei_ia.data.etl.text_preprocess import html_to_markdown
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException204,
    HTTPException404,
    HTTPException409,
)

logger = logging.getLogger(__name__)


async def get_doc_int_from_id(id_documento: str) -> tuple[str, dict]:
    """Obtém conteúdo de documentos internos de forma assíncrona.

    Args:
        id_documento: ID do documento

    Returns:
        Tuple com conteúdo do documento em markdown e metadados extras da API
    """
    df_docs = await SEIDBHandler.get_internal_docs_from_process(
        id_documentos=id_documento
    )
    l_df = len(df_docs)
    if l_df == 0:
        msg = f"Documento interno id {id_documento} não encontrado no BD do SEI"
        logger.error(msg)
        raise HTTPException404(detail="O documento não foi encontrado no SEI!")
    if l_df == 1:
        doc_content = df_docs["content_doc"][0]
        if doc_content is None or not doc_content.strip():
            msg = f"Documento interno id {id_documento} está sem conteúdo"
            logger.error(msg)
            raise HTTPException204(
                detail=f"Documento {id_documento} foi encontrado, mas está sem conteúdo!"
            )

        if isinstance(df_docs["content_doc"][0], str):
            extra_metadata = (
                df_docs["extra_metadata"][0]
                if "extra_metadata" in df_docs.columns
                else {}
            )
            if not isinstance(extra_metadata, dict):
                extra_metadata = {}
            markdown_content = html_to_markdown(doc_content)
            return markdown_content, extra_metadata
        raise HTTPException404
    logger.error(f"Encontrado mais de um documento com o id {id_documento}!")
    raise HTTPException409
