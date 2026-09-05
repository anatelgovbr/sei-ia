"""Tests for jobs/services/cache/redis_client.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import RedisError

from jobs.services.cache.redis_client import (
    RedisCache,
    get_cache,
    invalidate_document_cache,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_pool():
    RedisCache._pool = None
    RedisCache._pool_lock = None
    yield
    RedisCache._pool = None
    RedisCache._pool_lock = None


class TestGetClientDisabled:
    async def test_returns_none_when_cache_disabled(self):
        cache = RedisCache()
        cache._enabled = False
        assert await cache._get_client() is None


class TestGetClientEnabled:
    async def test_creates_pool_and_client_on_first_call(self):
        cache = RedisCache()
        cache._enabled = True

        fake_pool = MagicMock()
        fake_test_client = AsyncMock()
        fake_client = AsyncMock()

        with patch.object(
            RedisCache, "_create_connection_pool", return_value=fake_pool
        ), patch(
            "jobs.services.cache.redis_client.redis.Redis",
            side_effect=[fake_test_client, fake_client],
        ):
            client = await cache._get_client()

        assert client is fake_client
        fake_test_client.ping.assert_awaited_once()
        fake_test_client.aclose.assert_awaited_once()

    async def test_reuses_existing_pool(self):
        RedisCache._pool = MagicMock()
        cache = RedisCache()
        cache._enabled = True

        with patch(
            "jobs.services.cache.redis_client.redis.Redis",
            return_value=AsyncMock(),
        ) as mock_redis:
            client = await cache._get_client()

        assert client is mock_redis.return_value

    async def test_returns_none_when_pool_creation_fails(self):
        cache = RedisCache()
        cache._enabled = True

        with patch.object(
            RedisCache, "_create_connection_pool", side_effect=RuntimeError("boom")
        ):
            client = await cache._get_client()

        assert client is None

    async def test_returns_none_when_client_creation_fails(self):
        RedisCache._pool = MagicMock()
        cache = RedisCache()
        cache._enabled = True

        with patch(
            "jobs.services.cache.redis_client.redis.Redis",
            side_effect=RuntimeError("boom"),
        ):
            client = await cache._get_client()

        assert client is None


class TestGetPoolLock:
    async def test_creates_lock_within_event_loop(self):
        lock = RedisCache._get_pool_lock()
        assert lock is not None

    def test_raises_outside_event_loop(self):
        with pytest.raises(RuntimeError):
            RedisCache._get_pool_lock()


class TestInvalidateDocuments:
    async def test_returns_zero_when_disabled(self):
        cache = RedisCache()
        cache._enabled = False
        assert await cache.invalidate_documents(["1"]) == 0

    async def test_returns_zero_when_client_unavailable(self):
        cache = RedisCache()
        cache._enabled = True
        with patch.object(cache, "_get_client", return_value=None):
            assert await cache.invalidate_documents(["1"]) == 0

    async def test_deletes_matching_keys(self):
        cache = RedisCache()
        cache._enabled = True

        async def fake_scan_iter(match, count):
            for key in [b"seiia:doc:1:a", b"seiia:doc:1:b"]:
                yield key

        fake_client = MagicMock()
        fake_client.scan_iter = fake_scan_iter
        fake_client.delete = AsyncMock(return_value=2)

        with patch.object(cache, "_get_client", return_value=fake_client):
            total = await cache.invalidate_documents(["1"])

        assert total == 2
        fake_client.delete.assert_awaited_once()

    async def test_no_keys_found_for_document(self):
        cache = RedisCache()
        cache._enabled = True

        async def fake_scan_iter(match, count):
            return
            yield  # pragma: no cover - makes this an async generator

        fake_client = MagicMock()
        fake_client.scan_iter = fake_scan_iter
        fake_client.delete = AsyncMock()

        with patch.object(cache, "_get_client", return_value=fake_client):
            total = await cache.invalidate_documents(["1"])

        assert total == 0
        fake_client.delete.assert_not_awaited()

    async def test_redis_error_returns_partial_total(self):
        cache = RedisCache()
        cache._enabled = True

        fake_client = MagicMock()

        async def raise_scan_iter(match, count):
            raise RedisError("boom")
            yield  # pragma: no cover

        fake_client.scan_iter = raise_scan_iter

        with patch.object(cache, "_get_client", return_value=fake_client):
            total = await cache.invalidate_documents(["1"])

        assert total == 0


class TestClose:
    async def test_closes_client_when_present(self):
        cache = RedisCache()
        cache._client = AsyncMock()
        client = cache._client

        await cache.close()

        client.aclose.assert_awaited_once()
        assert cache._client is None

    async def test_noop_when_no_client(self):
        cache = RedisCache()
        await cache.close()
        assert cache._client is None


class TestResetPool:
    async def test_resets_existing_pool(self):
        pool = AsyncMock()
        RedisCache._pool = pool

        await RedisCache.reset_pool()

        pool.aclose.assert_awaited_once()
        assert RedisCache._pool is None

    async def test_noop_when_no_pool(self):
        RedisCache._pool = None
        await RedisCache.reset_pool()
        assert RedisCache._pool is None


class TestGetCacheSingleton:
    def test_returns_same_instance(self):
        import jobs.services.cache.redis_client as redis_client_module

        redis_client_module._cache_instance = None
        first = get_cache()
        second = get_cache()
        assert first is second
        redis_client_module._cache_instance = None


class TestInvalidateDocumentCache:
    async def test_delegates_to_singleton_cache(self):
        fake_cache = MagicMock()
        fake_cache.invalidate_documents = AsyncMock(return_value=3)

        with patch(
            "jobs.services.cache.redis_client.get_cache", return_value=fake_cache
        ):
            result = await invalidate_document_cache(["1", "2"])

        assert result == 3
        fake_cache.invalidate_documents.assert_awaited_once_with(["1", "2"])
