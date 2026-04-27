"""
Módulo de mocks e dados de teste centralizados.

Este pacote contém constantes, factories e utilitários para criação
de dados de teste de forma consistente em todo o projeto.
"""

from tests.mocks.test_data_factories import (
    CHUNK_SIZE,
    DOC_CACHEABLE_EMBEDDING,
    DOC_CACHEABLE_ID,
    DOC_VOLATILE_EMBEDDING,
    DOC_VOLATILE_ID,
    DOC_VOLATILE_MULTI_EMBEDDINGS,
    DOC_VOLATILE_MULTI_ID,
    EMBEDDING_DIMENSION,
    create_cacheable_document_data,
    create_volatile_document_data,
    create_volatile_multi_chunk_document_data,
    create_volatile_multi_chunk_embeddings,
    get_all_test_document_ids,
)

__all__ = [
    # Constantes
    "DOC_VOLATILE_ID",
    "DOC_CACHEABLE_ID",
    "DOC_VOLATILE_MULTI_ID",
    "EMBEDDING_DIMENSION",
    "DOC_VOLATILE_EMBEDDING",
    "DOC_CACHEABLE_EMBEDDING",
    "DOC_VOLATILE_MULTI_EMBEDDINGS",
    "CHUNK_SIZE",
    # Factories
    "create_volatile_document_data",
    "create_cacheable_document_data",
    "create_volatile_multi_chunk_document_data",
    "create_volatile_multi_chunk_embeddings",
    "get_all_test_document_ids",
]
