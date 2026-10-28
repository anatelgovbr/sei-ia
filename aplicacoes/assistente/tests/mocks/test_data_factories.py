"""
Factories e constantes centralizadas para criação de dados de teste.

Este módulo contém todas as constantes e funções factory para criar objetos
de teste de forma consistente e reutilizável.
"""

from datetime import datetime

# ==================== CONSTANTES ====================

# IDs dos documentos de teste
DOC_VOLATILE_ID = "99999001"
DOC_CACHEABLE_ID = "99999002"
DOC_VOLATILE_MULTI_ID = "99999003"

# Dimensão dos embeddings - obtida dinamicamente do settings
# O modelo text-embedding-3-small do Azure OpenAI tem dimensão 1536
EMBEDDING_DIMENSION = 1536

# Embeddings de teste - usando a dimensão configurada
DOC_VOLATILE_EMBEDDING = [0.1] * EMBEDDING_DIMENSION
DOC_CACHEABLE_EMBEDDING = [0.2] * EMBEDDING_DIMENSION
DOC_VOLATILE_MULTI_EMBEDDINGS = [
    [0.3] * EMBEDDING_DIMENSION,  # Chunk 0
    [0.4] * EMBEDDING_DIMENSION,  # Chunk 1
    [0.5] * EMBEDDING_DIMENSION,  # Chunk 2
]

# Constantes de posição
CHUNK_SIZE = 1000


# ==================== FACTORIES ====================


def create_volatile_document_data() -> dict:
    """
    Cria dados de teste para documento volátil (não cacheável).

    Returns:
        dict: Dados do documento com metadados e embedding
    """
    return {
        "id_documento": DOC_VOLATILE_ID,
        "id_documento_formatado": f"DOC-{DOC_VOLATILE_ID}",
        "content": "Conteúdo volátil",
        "doc_tokens": 100,
        "metadata": {"test": "volatile"},
        "doc_paged": False,
        "pag_doc_init": None,
        "pag_doc_end": None,
        "download_ext": None,
        "id_anexos": None,
        "sin_armazena_cache": "N",
        "embedding": DOC_VOLATILE_EMBEDDING,
        "chunk_id": 0,
        "start_position": 0,
        "end_position": CHUNK_SIZE,
    }


def create_cacheable_document_data() -> dict:
    """
    Cria dados de teste para documento cacheável.

    Returns:
        dict: Dados do documento com metadados e embedding
    """
    return {
        "id_documento": DOC_CACHEABLE_ID,
        "id_documento_formatado": f"DOC-{DOC_CACHEABLE_ID}",
        "content": "Conteúdo cacheável",
        "doc_tokens": 200,
        "metadata": {"test": "cacheable"},
        "doc_paged": False,
        "pag_doc_init": None,
        "pag_doc_end": None,
        "download_ext": None,
        "id_anexos": None,
        "sin_armazena_cache": "S",
        "embedding": DOC_CACHEABLE_EMBEDDING,
        "chunk_id": 0,
        "start_position": 0,
        "end_position": CHUNK_SIZE,
    }


def create_volatile_multi_chunk_document_data() -> dict:
    """
    Cria dados de teste para documento volátil com múltiplos chunks.

    Returns:
        dict: Dados do documento base (sem chunks individuais)
    """
    return {
        "id_documento": DOC_VOLATILE_MULTI_ID,
        "id_documento_formatado": f"DOC-{DOC_VOLATILE_MULTI_ID}",
        "content": "Conteúdo volátil multi-chunk",
        "doc_tokens": 300,
        "metadata": {"test": "volatile_multi"},
        "doc_paged": False,
        "pag_doc_init": None,
        "pag_doc_end": None,
        "download_ext": None,
        "id_anexos": None,
        "sin_armazena_cache": "N",
    }


def create_volatile_multi_chunk_embeddings() -> list[dict]:
    """
    Cria dados de embeddings para documento volátil com múltiplos chunks.

    Returns:
        list[dict]: Lista de dicts com dados de cada chunk
    """
    chunks = []
    for chunk_id, embedding in enumerate(DOC_VOLATILE_MULTI_EMBEDDINGS):
        chunks.append(
            {
                "chunk_id": chunk_id,
                "id_documento": DOC_VOLATILE_MULTI_ID,
                "embedding": embedding,
                "start_position": chunk_id * CHUNK_SIZE,
                "end_position": (chunk_id + 1) * CHUNK_SIZE,
                "created_at": datetime.now(),
            }
        )
    return chunks


def get_all_test_document_ids() -> list[str]:
    """
    Retorna lista de todos os IDs de documentos de teste.

    Returns:
        list[str]: Lista de IDs de documentos
    """
    return [DOC_VOLATILE_ID, DOC_CACHEABLE_ID, DOC_VOLATILE_MULTI_ID]
