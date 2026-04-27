"""Router para endpoints de geração de embeddings."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jobs.api_rest.services.embedding_service import generate_embeddings_for_documents

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


class GenerateEmbeddingsRequest(BaseModel):
    """Modelo de request para geração de embeddings."""

    id_documentos: list[str]


class EmbeddingInfo(BaseModel):
    """Informação sobre um embedding gerado."""

    id_documento: str
    chunks_count: int


class GenerateEmbeddingsResponse(BaseModel):
    """Modelo de response para geração de embeddings."""

    status: str  # "processed" ou "already_exists"
    processed_count: int
    skipped_count: int
    embeddings: list[EmbeddingInfo]


@router.post("/generate", response_model=GenerateEmbeddingsResponse)
async def generate_embeddings(
    request: GenerateEmbeddingsRequest,
) -> GenerateEmbeddingsResponse:
    """Gera embeddings para uma lista de documentos.

    Se os embeddings já existirem no banco de dados, retorna status "already_exists".
    Caso contrário, busca os documentos via API do SEI, gera chunks, cria embeddings
    e salva no banco de dados PostgreSQL compartilhado com o Assistente.

    Args:
        request: Request contendo lista de IDs de documentos

    Returns:
        Response com status e informações dos embeddings gerados

    Raises:
        HTTPException: Em caso de erro no processamento
    """
    try:
        logger.info(
            f"Recebida requisição para gerar embeddings de {len(request.id_documentos)} documentos"
        )

        result = await generate_embeddings_for_documents(request.id_documentos)

        logger.info(
            f"Processamento concluído: {result['status']}, "
            f"processados={result['processed_count']}, "
            f"já existentes={result['skipped_count']}"
        )

        return GenerateEmbeddingsResponse(**result)

    except Exception as e:
        logger.error(f"Erro ao gerar embeddings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
