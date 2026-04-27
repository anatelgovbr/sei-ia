"""Testes para o cliente Redis de cache."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from sei_ia.data.pydantic_models import ItemDocument
from sei_ia.services.cache.redis_client import CacheStats, RedisCache, get_cache


class TestCacheStats:
    """Testes para estatísticas do cache."""

    def test_cache_stats_initial(self):
        """Testa estado inicial das estatísticas."""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.errors == 0
        assert stats.total_requests == 0
        assert stats.hit_ratio == 0.0

    def test_cache_stats_hit_ratio(self):
        """Testa cálculo da taxa de acerto."""
        stats = CacheStats()
        stats.hits = 7
        stats.misses = 3
        stats.total_requests = 10

        assert stats.hit_ratio == 0.7

    def test_cache_stats_to_dict(self):
        """Testa conversão para dicionário."""
        stats = CacheStats()
        stats.hits = 5
        stats.misses = 2

        stats_dict = stats.to_dict()
        assert stats_dict["hits"] == 5
        assert stats_dict["misses"] == 2
        assert "last_updated" in stats_dict


@pytest.fixture
def sample_document():
    """Fixture com documento de exemplo."""
    return ItemDocument(
        {
            "id_documento": "123456",
            "id_documento_formatado": "1234567",
            "content": "Conteúdo do documento de teste",
            "metadata": {"tipo": "teste"},
            "doc_tokens": 100,
            "doc_paged": False,
            "pag_doc_init": None,
            "pag_doc_end": None,
            "download_ext": False,
            "id_anexos": None,
        }
    )


class TestRedisCache:
    """Testes para o cliente Redis."""

    @pytest.fixture
    def cache(self):
        """Fixture com instância do cache."""
        return RedisCache()

    def test_cache_disabled(self, cache):
        """Testa comportamento quando cache está desabilitado."""
        with patch("sei_ia.configs.settings_config.settings.CACHE_ENABLED", False):
            cache._enabled = False
            client = asyncio.run(cache._get_client())
            assert client is None

    @pytest.mark.asyncio
    async def test_get_document_cache_disabled(self, cache):
        """Testa get_document com cache desabilitado."""
        cache._enabled = False
        result = await cache.get_document("123456")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_document_cache_disabled(self, cache, sample_document):
        """Testa set_document com cache desabilitado."""
        cache._enabled = False
        result = await cache.set_document(sample_document)
        assert result is False

    def test_document_serialization(self, cache, sample_document):
        """Testa serialização e deserialização de documentos."""
        # Converte documento para dados de cache
        cache_data = cache._document_to_cache_data(sample_document)

        assert cache_data["id_documento"] == "123456"
        assert cache_data["content"] == "Conteúdo do documento de teste"
        assert "cached_at" in cache_data
        assert "version" in cache_data

        # Converte dados de cache de volta para documento
        restored_doc = cache._cache_data_to_document(cache_data)

        assert restored_doc["id_documento"] == sample_document["id_documento"]
        assert restored_doc["content"] == sample_document["content"]
        assert restored_doc["doc_tokens"] == sample_document["doc_tokens"]

    @pytest.mark.asyncio
    async def test_circuit_breaker(self, cache):
        """Testa circuit breaker em caso de erros."""
        cache._error_count = 5
        cache._circuit_open = True

        client = await cache._get_client()
        assert client is None

    def test_handle_error(self, cache):
        """Testa manipulação de erros."""
        initial_error_count = cache._error_count
        initial_stats_errors = cache._stats.errors

        cache._handle_error()

        assert cache._error_count == initial_error_count + 1
        assert cache._stats.errors == initial_stats_errors + 1


class TestCacheIntegration:
    """Testes de integração com mock do Redis."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock do cliente Redis."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_client.get = AsyncMock()
        mock_client.setex = AsyncMock()
        mock_client.delete = AsyncMock()
        mock_client.scan_iter = AsyncMock()
        mock_client.info = AsyncMock(
            return_value={
                "used_memory_human": "1MB",
                "connected_clients": 1,
                "uptime_in_seconds": 3600,
            }
        )
        return mock_client

    @pytest.mark.asyncio
    async def test_get_document_cache_miss(self, mock_redis_client, sample_document):
        """Testa cache miss."""
        mock_redis_client.get.return_value = None

        with patch("redis.asyncio.Redis") as mock_redis:
            mock_redis.return_value = mock_redis_client

            cache = RedisCache()
            cache._client = mock_redis_client

            result = await cache.get_document("123456")
            assert result is None
            assert cache._stats.misses == 1
            assert cache._stats.total_requests == 1

    @pytest.mark.asyncio
    async def test_get_document_cache_hit(self, mock_redis_client, sample_document):
        """Testa cache hit."""
        # Preparar dados de cache
        cache = RedisCache()
        cache_data = cache._document_to_cache_data(sample_document)
        serialized_data = cache._serialize_data(cache_data)

        mock_redis_client.get.return_value = serialized_data

        with patch("redis.asyncio.Redis") as mock_redis:
            mock_redis.return_value = mock_redis_client

            cache._client = mock_redis_client

            result = await cache.get_document("123456")

            assert result is not None
            assert result["id_documento"] == "123456"
            assert result["content"] == "Conteúdo do documento de teste"
            assert cache._stats.hits == 1
            assert cache._stats.total_requests == 1

    @pytest.mark.asyncio
    async def test_set_document_success(self, mock_redis_client, sample_document):
        """Testa armazenamento bem-sucedido no cache."""
        mock_redis_client.setex.return_value = True

        with patch("redis.asyncio.Redis") as mock_redis:
            mock_redis.return_value = mock_redis_client

            cache = RedisCache()
            cache._client = mock_redis_client

            result = await cache.set_document(sample_document)

            assert result is True
            mock_redis_client.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_stats(self, mock_redis_client):
        """Testa obtenção de estatísticas."""
        mock_redis_client.scan_iter.return_value = AsyncMock()
        mock_redis_client.scan_iter.return_value.__aiter__.return_value = iter(
            [b"key1", b"key2"]
        )

        with patch("redis.asyncio.Redis") as mock_redis:
            mock_redis.return_value = mock_redis_client

            cache = RedisCache()
            cache._client = mock_redis_client
            cache._stats.hits = 10
            cache._stats.misses = 5
            cache._stats.total_requests = 15

            stats = await cache.get_stats()

            assert stats["hits"] == 10
            assert stats["misses"] == 5
            assert stats["status"] == "connected"
            assert "redis_memory_used" in stats


def test_get_cache_singleton():
    """Testa que get_cache retorna sempre a mesma instância."""
    cache1 = get_cache()
    cache2 = get_cache()

    assert cache1 is cache2
