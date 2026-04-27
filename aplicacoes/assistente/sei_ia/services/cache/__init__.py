"""Módulo de cache para documentos processados.

Este módulo fornece funcionalidade de cache usando Redis para armazenar
documentos já processados, evitando reprocessamento desnecessário.
"""

from .cache_keys import CacheKeyGenerator, generate_cache_key
from .redis_client import RedisCache, get_cache

__all__ = ["RedisCache", "get_cache", "generate_cache_key", "CacheKeyGenerator"]
