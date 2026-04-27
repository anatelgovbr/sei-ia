"""Cliente Redis para invalidação de cache de documentos no Jobs.

Este módulo fornece funcionalidade para invalidar cache de documentos
armazenados no Redis compartilhado com o Assistente.
"""

import asyncio
import logging

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError

from jobs.envs import CACHE_ENABLED, CACHE_KEY_PREFIX, REDIS_URI

logger = logging.getLogger(__name__)


class RedisCache:
    """Cliente Redis para invalidação de cache de documentos."""

    _pool: ConnectionPool | None = None
    _pool_lock: asyncio.Lock | None = None

    def __init__(self) -> None:
        self._client: redis.Redis | None = None
        self._enabled = CACHE_ENABLED

    @classmethod
    def _get_pool_lock(cls) -> asyncio.Lock:
        """Obtém o lock do pool, criando-o no event loop atual se necessário."""
        try:
            asyncio.get_running_loop()

            if cls._pool_lock is None:
                cls._pool_lock = asyncio.Lock()
            else:
                try:
                    cls._pool_lock.locked()
                except RuntimeError:
                    cls._pool_lock = asyncio.Lock()

            return cls._pool_lock

        except RuntimeError as e:
            raise RuntimeError(
                "_get_pool_lock deve ser chamado dentro de um contexto assíncrono"
            ) from e

    async def _create_connection_pool(self) -> ConnectionPool:
        """Cria pool de conexões Redis usando a URI configurada."""
        return redis.ConnectionPool.from_url(
            REDIS_URI,
            max_connections=50,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            decode_responses=False,
        )

    async def _get_client(self) -> redis.Redis | None:
        """Obtém cliente Redis com lazy initialization e pool compartilhado."""
        if not self._enabled:
            logger.warning("Cache Redis está desabilitado")
            return None

        pool_lock = self._get_pool_lock()
        async with pool_lock:
            if RedisCache._pool is None:
                try:
                    RedisCache._pool = await self._create_connection_pool()
                    test_client = redis.Redis(connection_pool=RedisCache._pool)
                    await test_client.ping()
                    await test_client.aclose()
                    logger.info("Pool de conexões Redis criado com sucesso")
                except Exception as e:
                    logger.exception(f"Erro ao criar pool Redis: {e}")
                    return None

        if self._client is None:
            try:
                self._client = redis.Redis(connection_pool=RedisCache._pool)
                logger.debug("Cliente Redis criado usando pool compartilhado")
            except Exception as e:
                logger.exception(f"Erro ao criar cliente Redis: {e}")
                return None

        return self._client

    async def invalidate_documents(self, doc_ids: list[str]) -> int:
        """Invalida cache de documentos usando padrão de chave.

        Args:
            doc_ids: Lista de IDs de documentos a invalidar

        Returns:
            Número total de chaves deletadas
        """
        if not self._enabled:
            logger.warning("Cache desabilitado, nenhuma chave invalidada")
            return 0

        client = await self._get_client()
        if client is None:
            logger.error("Cliente Redis não disponível, nenhuma chave invalidada")
            return 0

        total_deleted = 0

        try:
            for doc_id in doc_ids:
                # Padrão de chave: seiia:doc:{id_documento}*
                pattern = f"{CACHE_KEY_PREFIX}{doc_id}*"
                keys_to_delete = []

                # Escanear chaves que correspondem ao padrão
                async for key in client.scan_iter(match=pattern, count=100):
                    keys_to_delete.append(key)

                # Deletar chaves encontradas
                if keys_to_delete:
                    deleted = await client.delete(*keys_to_delete)
                    total_deleted += deleted
                    logger.info(
                        f"Documento {doc_id}: {deleted} chaves de cache invalidadas"
                    )
                else:
                    logger.debug(
                        f"Documento {doc_id}: nenhuma chave de cache encontrada"
                    )

            logger.info(f"Total de chaves invalidadas: {total_deleted}")
            return total_deleted

        except RedisError as e:
            logger.exception(f"Erro ao invalidar cache de documentos: {e}")
            return total_deleted

    async def close(self) -> None:
        """Fecha conexões do Redis."""
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.debug("Cliente Redis fechado")

    @classmethod
    async def reset_pool(cls) -> None:
        """Reseta o pool de conexões (útil para testes)."""
        if cls._pool:
            await cls._pool.aclose()
            cls._pool = None
            logger.debug("Pool de conexões Redis resetado")


# Instância global do cache
_cache_instance: RedisCache | None = None


def get_cache() -> RedisCache:
    """Obtém instância singleton do cache."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = RedisCache()
    return _cache_instance


async def invalidate_document_cache(doc_ids: list[str]) -> int:
    """Função auxiliar para invalidar cache de documentos.

    Args:
        doc_ids: Lista de IDs de documentos

    Returns:
        Número de chaves deletadas
    """
    cache = get_cache()
    return await cache.invalidate_documents(doc_ids)
