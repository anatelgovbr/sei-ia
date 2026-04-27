"""Cliente Redis assíncrono para cache de documentos."""

import asyncio
import gzip
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError

from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.pydantic_models import ItemDocument

from .cache_keys import CacheKeyGenerator, generate_cache_key

setup_logging()
logger = logging.getLogger(__name__)


class CacheStats:
    """Estatísticas do cache."""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.total_requests = 0

    @property
    def hit_ratio(self) -> float:
        """Calcula taxa de acerto do cache."""
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests

    def to_dict(self) -> dict:
        """Converte estatísticas para dicionário."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "errors": self.errors,
            "total_requests": self.total_requests,
            "hit_ratio": self.hit_ratio,
            "last_updated": datetime.now(UTC).isoformat(),
        }


class RedisCache:
    """Cliente Redis assíncrono para cache de documentos."""

    _pool: ConnectionPool | None = None  # Pool compartilhado entre instâncias
    _pool_lock: asyncio.Lock | None = None  # Lock para criação do pool (criado lazy)

    def __init__(self):
        self._client: redis.Redis | None = None
        self._stats = CacheStats()
        self._enabled = settings.CACHE_ENABLED

        # Circuit breaker simples
        self._error_count = 0
        self._max_errors = 5
        self._circuit_open = False
        self._last_error_time = None
        self._circuit_timeout = 60  # segundos

    @classmethod
    def _get_pool_lock(cls) -> asyncio.Lock:
        """Obtém o lock do pool, criando-o no event loop atual se necessário."""
        try:
            # Verificar se estamos em um event loop
            asyncio.get_running_loop()

            # Se não existe lock ou está vinculado a outro loop, criar novo
            if cls._pool_lock is None:
                cls._pool_lock = asyncio.Lock()
            else:
                # Testar se o lock ainda é válido
                try:
                    # Se conseguir testar, o lock está OK
                    cls._pool_lock.locked()
                except RuntimeError:
                    # Lock está vinculado a outro event loop, criar novo
                    cls._pool_lock = asyncio.Lock()

            return cls._pool_lock

        except RuntimeError:
            # Não estamos em um event loop assíncrono, usar None
            # Isso não deveria acontecer se usado corretamente
            raise RuntimeError(
                "_get_pool_lock deve ser chamado dentro de um contexto assíncrono"
            ) from None

    async def _create_connection_pool(self) -> ConnectionPool:
        """Cria pool de conexões Redis usando a URI configurada."""
        return redis.ConnectionPool.from_url(
            settings.REDIS_URI,
            max_connections=settings.CACHE_MAX_CONNECTIONS,
            socket_timeout=settings.CACHE_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.CACHE_CONNECTION_TIMEOUT,
            retry_on_timeout=settings.CACHE_RETRY_ON_TIMEOUT,
            decode_responses=False,  # Vamos lidar com bytes para compressão
        )

    async def _get_client(self) -> redis.Redis | None:
        """Obtém cliente Redis com lazy initialization e pool compartilhado."""
        if not self._enabled:
            return None

        if self._circuit_open:
            # Verificar se é hora de tentar reconectar
            if (
                self._last_error_time
                and (datetime.now() - self._last_error_time).seconds
                >= self._circuit_timeout
            ):
                logger.info("Tentando reabrir circuit breaker do cache Redis")
                self._circuit_open = False
                self._error_count = 0
            else:
                return None

        # Usar pool compartilhado entre todas as instâncias
        pool_lock = self._get_pool_lock()
        async with pool_lock:
            if RedisCache._pool is None:
                try:
                    RedisCache._pool = await self._create_connection_pool()
                    # Testar conexão com um cliente temporário
                    test_client = redis.Redis(connection_pool=RedisCache._pool)
                    await test_client.ping()
                    await test_client.aclose()
                    logger.info("Pool de conexões Redis criado com sucesso")
                except Exception as e:
                    logger.error(f"Erro ao criar pool Redis: {e}")
                    RedisCache._pool = None  # Garante retry na próxima tentativa
                    self._handle_error()
                    return None

        if self._client is None:
            try:
                self._client = redis.Redis(connection_pool=RedisCache._pool)
                logger.debug("Cliente Redis criado usando pool compartilhado")
            except Exception as e:
                logger.error(f"Erro ao criar cliente Redis: {e}")
                self._handle_error()
                return None

        return self._client

    def _handle_error(self):
        """Manipula erros e circuit breaker."""
        self._error_count += 1
        self._last_error_time = datetime.now()
        self._stats.errors += 1

        if self._error_count >= self._max_errors:
            logger.warning(f"Circuit breaker aberto após {self._error_count} erros")
            self._circuit_open = True

    def _serialize_data(self, data: dict[str, Any]) -> bytes:
        """Serializa dados para armazenamento."""
        json_data = json.dumps(data, default=str, ensure_ascii=False).encode("utf-8")

        if settings.CACHE_COMPRESS:
            return gzip.compress(json_data)
        return json_data

    def _deserialize_data(self, data: bytes) -> dict[str, Any]:
        """Deserializa dados do cache."""
        if settings.CACHE_COMPRESS:
            try:
                json_data = gzip.decompress(data)
            except gzip.BadGzipFile:
                # Fallback para dados não comprimidos
                json_data = data
        else:
            json_data = data

        return json.loads(json_data.decode("utf-8"))

    def _document_to_cache_data(self, document: ItemDocument) -> dict[str, Any]:
        """Converte ItemDocument para dados de cache."""
        return {
            "id_documento": document["id_documento"],
            "id_documento_formatado": document["id_documento_formatado"],
            "content": document["content"],
            "metadata": document["metadata"],
            "doc_tokens": document["doc_tokens"],
            "doc_paged": document.get("doc_paged", False),
            "pag_doc_init": document.get("pag_doc_init"),
            "pag_doc_end": document.get("pag_doc_end"),
            "download_ext": document.get("download_ext"),
            "id_anexos": document.get("id_anexos"),
            "sin_armazena_cache": document.get("sin_armazena_cache", "S"),
            "cached_at": datetime.now(UTC).isoformat(),
            "version": settings.CACHE_VERSION,
        }

    def _cache_data_to_document(self, cache_data: dict[str, Any]) -> ItemDocument:
        """Converte dados de cache para ItemDocument."""
        document: ItemDocument = {
            "id_documento": cache_data["id_documento"],
            "id_documento_formatado": cache_data["id_documento_formatado"],
            "content": cache_data["content"],
            "metadata": cache_data["metadata"],
            "doc_tokens": cache_data["doc_tokens"],
            "doc_paged": cache_data.get("doc_paged", False),
            "pag_doc_init": cache_data.get("pag_doc_init"),
            "pag_doc_end": cache_data.get("pag_doc_end"),
            "download_ext": cache_data.get("download_ext"),
            "id_anexos": cache_data.get("id_anexos"),
            "sin_armazena_cache": cache_data.get("sin_armazena_cache", "S"),
        }
        return document

    async def _acquire_lock(
        self, lock_key: str, timeout: int = 30, retry_delay: float = 0.1
    ) -> str | None:
        """
        Adquire um lock distribuído no Redis.

        Args:
            lock_key: Chave do lock
            timeout: Timeout em segundos para o lock
            retry_delay: Delay entre tentativas

        Returns:
            Token do lock se adquirido, None caso contrário
        """
        client = await self._get_client()
        if client is None:
            return None

        lock_token = str(uuid.uuid4())
        expiry_time = int(timeout)

        try:
            # Tentar adquirir o lock com SET NX EX
            acquired = await client.set(lock_key, lock_token, nx=True, ex=expiry_time)

            if acquired:
                return lock_token
            else:
                return None

        except RedisError as e:
            logger.error(f"Erro ao adquirir lock {lock_key}: {e}")
            return None

    async def _release_lock(self, lock_key: str, lock_token: str) -> bool:
        """
        Libera um lock distribuído no Redis.

        Args:
            lock_key: Chave do lock
            lock_token: Token do lock

        Returns:
            True se liberado com sucesso
        """
        client = await self._get_client()
        if client is None:
            return False

        # Script Lua para liberação atômica do lock
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        try:
            result = await client.eval(lua_script, 1, lock_key, lock_token)
            success = bool(result)
            if success:
                logger.debug(f"Lock liberado: {lock_key}")
            return success

        except RedisError as e:
            logger.error(f"Erro ao liberar lock {lock_key}: {e}")
            return False

    async def get_document(
        self,
        id_documento: str,
        pag_ini: int | None = None,
        pag_fim: int | None = None,
        download_ext: bool | None = None,
        id_anexos: list[str] | None = None,
    ) -> ItemDocument | None:
        """
        Recupera documento do cache com proteção contra condições de corrida.

        Args:
            id_documento: ID do documento
            pag_ini: Página inicial
            pag_fim: Página final
            download_ext: Flag de download externo
            id_anexos: Lista de IDs de anexos

        Returns:
            ItemDocument se encontrado, None caso contrário
        """
        if not self._enabled:
            return None

        client = await self._get_client()
        if client is None:
            return None

        key = generate_cache_key(
            id_documento, pag_ini, pag_fim, download_ext, id_anexos
        )
        self._stats.total_requests += 1

        try:
            cached_data = await client.get(key)
            if cached_data is None:
                self._stats.misses += 1
                logger.debug(f"Cache miss para documento {id_documento}")
                return None

            # Deserializar dados
            cache_dict = self._deserialize_data(cached_data)

            # Verificar versão do cache
            if cache_dict.get("version") != settings.CACHE_VERSION:
                logger.debug(f"Versão de cache inválida para documento {id_documento}")
                await self.delete_document(
                    id_documento, pag_ini, pag_fim, download_ext, id_anexos
                )
                self._stats.misses += 1
                return None

            self._stats.hits += 1
            logger.debug(f"Cache hit para documento {id_documento}")

            return self._cache_data_to_document(cache_dict)

        except (RedisError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Erro ao recuperar documento do cache: {e}")
            self._handle_error()
            self._stats.misses += 1
            return None

    async def set_document(
        self,
        document: ItemDocument,
        pag_ini: int | None = None,
        pag_fim: int | None = None,
        download_ext: bool | None = None,
        id_anexos: list[str] | None = None,
    ) -> bool:
        """
        Armazena documento no cache.

        Args:
            document: Documento a ser armazenado
            pag_ini: Página inicial
            pag_fim: Página final
            download_ext: Flag de download externo
            id_anexos: Lista de IDs de anexos

        Returns:
            bool: True se armazenado com sucesso
        """
        if not self._enabled:
            return False

        client = await self._get_client()
        if client is None:
            return False

        key = generate_cache_key(
            document["id_documento"], pag_ini, pag_fim, download_ext, id_anexos
        )

        try:
            cache_data = self._document_to_cache_data(document)
            serialized_data = self._serialize_data(cache_data)

            # Armazenar com TTL
            await client.setex(key, settings.CACHE_TTL_SECONDS, serialized_data)

            logger.debug(f"Documento {document['id_documento']} armazenado no cache")
            return True

        except (RedisError, TypeError, ValueError) as e:
            logger.error(f"Erro ao armazenar documento no cache: {e}")
            self._handle_error()
            return False

    async def delete_document(
        self,
        id_documento: str,
        pag_ini: int | None = None,
        pag_fim: int | None = None,
        download_ext: bool | None = None,
        id_anexos: list[str] | None = None,
    ) -> bool:
        """Remove documento do cache."""
        if not self._enabled:
            return False

        client = await self._get_client()
        if client is None:
            return False

        key = generate_cache_key(
            id_documento, pag_ini, pag_fim, download_ext, id_anexos
        )

        try:
            result = await client.delete(key)
            logger.debug(f"Documento {id_documento} removido do cache")
            return result > 0
        except RedisError as e:
            logger.error(f"Erro ao remover documento do cache: {e}")
            self._handle_error()
            return False

    async def _scan_iter_pattern(self, pattern: str, count: int = 100):
        """Itera sobre chaves Redis usando SCAN (não bloqueia Redis).

        Args:
            pattern: Pattern para filtrar chaves (ex: "seiia:v1:doc:123:*")
            count: Número de chaves por iteração do SCAN

        Yields:
            str: Chaves que correspondem ao pattern
        """
        client = await self._get_client()
        if client is None:
            return

        try:
            async for key in client.scan_iter(match=pattern, count=count):
                yield key
        except RedisError as e:
            logger.error(f"Erro ao iterar sobre chaves com pattern {pattern}: {e}")
            self._handle_error()

    async def clear_cache(self) -> bool:
        """Limpa todos os documentos do cache."""
        if not self._enabled:
            return False

        client = await self._get_client()
        if client is None:
            return False

        try:
            pattern = CacheKeyGenerator.get_key_pattern()
            keys = []

            async for key in client.scan_iter(match=pattern, count=100):
                keys.append(key)

                # Deletar em lotes para evitar timeout
                if len(keys) >= 1000:
                    if keys:
                        await client.delete(*keys)
                    keys = []

            # Deletar lote final
            if keys:
                await client.delete(*keys)

            logger.info("Cache de documentos limpo")
            return True

        except RedisError as e:
            logger.error(f"Erro ao limpar cache: {e}")
            self._handle_error()
            return False

    async def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do cache."""
        stats_dict = self._stats.to_dict()

        if not self._enabled:
            stats_dict["status"] = "disabled"
            return stats_dict

        client = await self._get_client()
        if client is None:
            stats_dict["status"] = "disconnected"
            return stats_dict

        try:
            # Informações do Redis
            info = await client.info()
            stats_dict.update(
                {
                    "status": "connected",
                    "redis_memory_used": info.get("used_memory_human"),
                    "redis_connected_clients": info.get("connected_clients"),
                    "redis_uptime": info.get("uptime_in_seconds"),
                    "circuit_open": self._circuit_open,
                }
            )

            # Contar chaves de documentos
            pattern = CacheKeyGenerator.get_key_pattern()
            key_count = 0
            async for _ in client.scan_iter(match=pattern, count=100):
                key_count += 1
            stats_dict["cached_documents"] = key_count

        except RedisError as e:
            logger.error(f"Erro ao obter estatísticas do Redis: {e}")
            stats_dict["status"] = "error"
            stats_dict["error"] = str(e)

        return stats_dict

    async def close(self):
        """Fecha conexões do Redis."""
        if self._client:
            await self._client.aclose()
            self._client = None
        # Pool é compartilhado, só fechar se for a última instância
        # Deixar o pool aberto durante a vida da aplicação
        logger.debug("Cliente Redis fechado (pool mantido para reutilização)")

    @classmethod
    async def reset_pool(cls):
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


async def reset_cache():
    """Reseta o cache global e pool de conexões (útil para testes)."""
    global _cache_instance
    if _cache_instance:
        await _cache_instance.close()
        _cache_instance = None
    await RedisCache.reset_pool()
    logger.debug("Cache global e pool resetados")


@asynccontextmanager
async def cache_context() -> AsyncGenerator[RedisCache, None]:
    """Context manager para usar o cache."""
    cache = get_cache()
    try:
        yield cache
    finally:
        # Context manager não fecha conexões para permitir reutilização
        # As conexões serão fechadas quando a aplicação for encerrada
        pass
