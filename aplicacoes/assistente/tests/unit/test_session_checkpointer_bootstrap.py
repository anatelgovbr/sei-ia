"""Regressions for serialized session checkpointer setup."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from sei_ia.services.session_fs import checkpointer


class _Cursor:
    def __init__(self, row: dict[str, bool] | None = None) -> None:
        self._row = row

    async def fetchone(self) -> dict[str, bool] | None:
        return self._row


class _ConnectionContext:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


@pytest.fixture(autouse=True)
def _reset_checkpointer_state(monkeypatch) -> None:
    monkeypatch.setattr(checkpointer, "_pool", None)
    monkeypatch.setattr(checkpointer, "_saver", None)
    monkeypatch.setattr(
        checkpointer, "_initialization_lock", asyncio.Lock(), raising=False
    )


def test_checkpointer_lock_has_stable_distinct_keys() -> None:
    assert (
        checkpointer.CHECKPOINTER_LOCK_NAMESPACE,
        checkpointer.CHECKPOINTER_LOCK_RESOURCE,
    ) == (0x534553, 0x43485054)
    assert (
        checkpointer.CHECKPOINTER_LOCK_NAMESPACE,
        checkpointer.CHECKPOINTER_LOCK_RESOURCE,
    ) != (0x534549, 0x41535354)
    assert checkpointer.CHECKPOINTER_SETUP_TIMEOUT_SECONDS == 60.0
    assert checkpointer.CHECKPOINTER_LOCK_RETRY_SECONDS == 0.1


@pytest.mark.asyncio
async def test_lock_retries_in_python_before_succeeding(monkeypatch) -> None:
    connection = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _Cursor({"acquired": False}),
                _Cursor({"acquired": True}),
            ]
        )
    )
    sleep = AsyncMock()
    monkeypatch.setattr(checkpointer.asyncio, "sleep", sleep)

    await checkpointer._acquire_setup_lock(connection)

    sleep.assert_awaited_once_with(0.1)
    assert connection.execute.await_count == 2


@pytest.mark.asyncio
async def test_lock_timeout_is_explicit() -> None:
    connection = SimpleNamespace(
        execute=AsyncMock(return_value=_Cursor({"acquired": False}))
    )

    with pytest.raises(TimeoutError, match="checkpointer"):
        await checkpointer._acquire_setup_lock(connection, timeout_seconds=0.0)


@pytest.mark.asyncio
async def test_setup_keeps_one_connection_through_unlock(monkeypatch) -> None:
    events: list[str] = []

    async def execute(statement, params=None):  # noqa: ARG001
        position = len(events)
        if position == 0:
            events.append("lock")
            return _Cursor({"acquired": True})
        if position == 1:
            events.append("schema")
            return _Cursor()
        events.append("unlock")
        return _Cursor({"released": True})

    connection = SimpleNamespace(execute=AsyncMock(side_effect=execute))
    pool = SimpleNamespace(
        connection=MagicMock(return_value=_ConnectionContext(connection))
    )
    saver = SimpleNamespace(setup=AsyncMock(side_effect=lambda: events.append("setup")))
    saver_factory = MagicMock(return_value=saver)
    monkeypatch.setattr(checkpointer, "AsyncPostgresSaver", saver_factory)

    await checkpointer._setup_checkpointer(pool, "seiia_session")

    assert events == ["lock", "schema", "setup", "unlock"]
    pool.connection.assert_called_once_with()
    saver_factory.assert_called_once_with(connection)


@pytest.mark.asyncio
async def test_setup_unlocks_when_migration_fails(monkeypatch) -> None:
    connection = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _Cursor({"acquired": True}),
                _Cursor(),
                _Cursor({"released": True}),
            ]
        )
    )
    pool = SimpleNamespace(
        connection=MagicMock(return_value=_ConnectionContext(connection))
    )
    saver = SimpleNamespace(setup=AsyncMock(side_effect=RuntimeError("migration")))
    monkeypatch.setattr(
        checkpointer, "AsyncPostgresSaver", MagicMock(return_value=saver)
    )

    with pytest.raises(RuntimeError, match="migration"):
        await checkpointer._setup_checkpointer(pool, "seiia_session")

    assert connection.execute.await_count == 3


@pytest.mark.asyncio
async def test_singleton_pool_is_autocommit_and_reused(monkeypatch) -> None:
    pool = SimpleNamespace(open=AsyncMock(), close=AsyncMock())
    pool_factory = MagicMock(return_value=pool)
    setup = AsyncMock()
    saver = object()
    saver_factory = MagicMock(return_value=saver)
    monkeypatch.setattr(checkpointer, "AsyncConnectionPool", pool_factory)
    monkeypatch.setattr(checkpointer, "AsyncPostgresSaver", saver_factory)
    monkeypatch.setattr(checkpointer, "_setup_checkpointer", setup)

    first = await checkpointer.get_session_checkpointer()
    second = await checkpointer.get_session_checkpointer()

    assert first is saver
    assert second is saver
    pool_factory.assert_called_once()
    pool.open.assert_awaited_once_with()
    setup.assert_awaited_once_with(
        pool, checkpointer.settings.SESSION_CHECKPOINTER_SCHEMA
    )
    saver_factory.assert_called_once_with(pool)
    kwargs = pool_factory.call_args.kwargs["kwargs"]
    assert kwargs["autocommit"] is True


@pytest.mark.asyncio
async def test_setup_failure_closes_pool_and_keeps_singleton_empty(monkeypatch) -> None:
    pool = SimpleNamespace(open=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(
        checkpointer, "AsyncConnectionPool", MagicMock(return_value=pool)
    )
    monkeypatch.setattr(
        checkpointer,
        "_setup_checkpointer",
        AsyncMock(side_effect=RuntimeError("setup failed")),
        raising=False,
    )

    with pytest.raises(RuntimeError, match="setup failed"):
        await checkpointer.get_session_checkpointer()

    pool.close.assert_awaited_once_with()
    assert checkpointer._pool is None
    assert checkpointer._saver is None
