"""Módulo de cache Redis para invalidação de documentos.

Este módulo fornece funcionalidade de invalidação de cache usando Redis
para remover documentos cancelados do cache compartilhado com o Assistente.
"""

from .redis_client import RedisCache, get_cache, invalidate_document_cache

__all__ = ["RedisCache", "get_cache", "invalidate_document_cache"]
