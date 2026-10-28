"""Serialized runtime database bootstrap for the Assistente application."""

from typing import Final

from sqlalchemy import Connection, MetaData, text

from sei_ia.configs.settings_config import settings
from sei_ia.data.database.async_db_connection import AsyncDbConnector
from sei_ia.data.database.table_manager import TableManager

BOOTSTRAP_LOCK_NAMESPACE: Final = 0x534549
BOOTSTRAP_LOCK_RESOURCE: Final = 0x41535354

_LOCK_SQL = text("SELECT pg_advisory_xact_lock(:namespace, :resource)")
_LOCK_PARAMS = {
    "namespace": BOOTSTRAP_LOCK_NAMESPACE,
    "resource": BOOTSTRAP_LOCK_RESOURCE,
}


def _register_database_models() -> None:
    """Register every ORM model before metadata.create_all runs."""
    from sei_ia.data.database.db_models.embedding import EmbeddingsTable
    from sei_ia.data.database.db_models.feedback import Feedback

    _ = EmbeddingsTable, Feedback


def _initialize_database_objects(
    connection: Connection,
    metadata: MetaData,
) -> None:
    """Create every runtime database object on the caller transaction."""
    schema = connection.dialect.identifier_preparer.quote(
        settings.DB_SEIIA_ASSISTENTE_SCHEMA
    )
    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    metadata.create_all(connection, checkfirst=True)
    TableManager(connection).initialize_all_tables()
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS public.gateway_status (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                rate_limit_reached JSONB NOT NULL DEFAULT '{}'::JSONB,
                last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO public.gateway_status DEFAULT VALUES
            ON CONFLICT (id) DO NOTHING
            """
        )
    )


async def initialize_runtime_database(
    db: AsyncDbConnector,
    metadata: MetaData,
) -> None:
    """Run all Assistente DDL under one transaction advisory lock."""
    _register_database_models()
    if db.async_engine is None:
        msg = "AsyncEngine não está disponível para o bootstrap do banco."
        raise RuntimeError(msg)

    async with db.async_engine.begin() as connection:
        await connection.execute(_LOCK_SQL, _LOCK_PARAMS)
        await connection.run_sync(
            lambda sync_connection: _initialize_database_objects(
                sync_connection, metadata
            )
        )


def initialize_runtime_database_sync(
    db: AsyncDbConnector,
    metadata: MetaData,
) -> None:
    """Run the same bootstrap for standalone synchronous RAG scripts."""
    _register_database_models()
    with db.engine.begin() as connection:
        connection.execute(_LOCK_SQL, _LOCK_PARAMS)
        _initialize_database_objects(connection, metadata)
