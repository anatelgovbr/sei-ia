"""Serialized PostgreSQL checkpointer setup for multi-turn sessions."""

from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import Final

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from sei_ia.configs.settings_config import settings

logger = logging.getLogger(__name__)

CHECKPOINTER_LOCK_NAMESPACE: Final = 0x534553
CHECKPOINTER_LOCK_RESOURCE: Final = 0x43485054
CHECKPOINTER_SETUP_TIMEOUT_SECONDS: Final = 60.0
CHECKPOINTER_LOCK_RETRY_SECONDS: Final = 0.1

_LOCK_PARAMS = (CHECKPOINTER_LOCK_NAMESPACE, CHECKPOINTER_LOCK_RESOURCE)
_TRY_LOCK_SQL = "SELECT pg_try_advisory_lock(%s, %s) AS acquired"
_UNLOCK_SQL = "SELECT pg_advisory_unlock(%s, %s) AS released"

_initialization_lock = asyncio.Lock()
_pool: AsyncConnectionPool | None = None
_saver: AsyncPostgresSaver | None = None


async def _acquire_setup_lock(
    connection: AsyncConnection,
    *,
    timeout_seconds: float = CHECKPOINTER_SETUP_TIMEOUT_SECONDS,
) -> None:
    """Try the session lock until acquired or the explicit deadline expires."""
    deadline = monotonic() + timeout_seconds
    while True:
        cursor = await connection.execute(_TRY_LOCK_SQL, _LOCK_PARAMS)
        row = await cursor.fetchone()
        if row is not None and row["acquired"]:
            return

        remaining = deadline - monotonic()
        if remaining <= 0:
            msg = (
                "Timeout ao aguardar o advisory lock de setup do checkpointer "
                f"após {timeout_seconds:.1f}s."
            )
            raise TimeoutError(msg)
        await asyncio.sleep(min(CHECKPOINTER_LOCK_RETRY_SECONDS, remaining))


async def _release_setup_lock(connection: AsyncConnection) -> None:
    cursor = await connection.execute(_UNLOCK_SQL, _LOCK_PARAMS)
    row = await cursor.fetchone()
    if row is None or not row["released"]:
        msg = "Falha ao liberar o advisory lock de setup do checkpointer."
        raise RuntimeError(msg)


async def _setup_checkpointer(
    pool: AsyncConnectionPool,
    schema: str,
) -> None:
    """Run schema and saver migrations on one dedicated pool connection."""
    async with pool.connection() as connection:
        await _acquire_setup_lock(connection)
        try:
            await connection.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
            )
            await AsyncPostgresSaver(connection).setup()
        finally:
            await _release_setup_lock(connection)


async def get_session_checkpointer() -> AsyncPostgresSaver:
    """Return the singleton saver after serialized, idempotent migrations."""
    global _pool, _saver
    if _saver is not None:
        return _saver

    async with _initialization_lock:
        if _saver is not None:
            return _saver

        schema = settings.SESSION_CHECKPOINTER_SCHEMA
        pool = AsyncConnectionPool(
            conninfo=settings.DB_SEIIA_CONNECTION_STRING,
            max_size=settings.DB_SEIIA_POOL_MAX_SIZE,
            open=False,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
                "options": f"-c search_path={schema}",
            },
        )
        try:
            await pool.open()
            await _setup_checkpointer(pool, schema)
            saver = AsyncPostgresSaver(pool)
        except BaseException:
            await pool.close()
            raise

        _pool = pool
        _saver = saver
        logger.info("Checkpointer Postgres da sessão pronto (schema=%s)", schema)
        return saver


async def close_session_checkpointer() -> None:
    """Close the singleton pool during application shutdown."""
    global _pool, _saver
    async with _initialization_lock:
        if _pool is not None:
            await _pool.close()
            logger.info("Pool do checkpointer da sessão fechado")
        _pool = None
        _saver = None
