"""Real PostgreSQL/pgvector regression tests for concurrent database bootstrap."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
import pytest
from psycopg import sql

RUNTIME_SCHEMA = "sei_llm"
CHECKPOINTER_SCHEMA = "seiia_session"
EMBEDDING_DIMENSION = 7
EMBEDDINGS_TABLE = "bootstrap_integration_model_24_4"
RUNTIME_LOCK = (0x534549, 0x41535354)
CHECKPOINTER_LOCK = (0x534553, 0x43485054)
CHECKPOINTER_TABLES = {
    "checkpoint_blobs",
    "checkpoint_migrations",
    "checkpoint_writes",
    "checkpoints",
}


def _database_url() -> str:
    url = os.getenv("ASSISTENTE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("ASSISTENTE_TEST_DATABASE_URL is required for the real DB test")
    if os.getenv("ASSISTENTE_TEST_DATABASE_DISPOSABLE") != "1":
        pytest.fail(
            "Refusing to use a database without ASSISTENTE_TEST_DATABASE_DISPOSABLE=1"
        )
    return url


def _assert_clean_database(url: str) -> None:
    with psycopg.connect(url) as connection:
        target_schemas = connection.execute(
            "SELECT count(*) FROM pg_namespace WHERE nspname IN (%s, %s)",
            (RUNTIME_SCHEMA, CHECKPOINTER_SCHEMA),
        ).fetchone()
        gateway_objects = connection.execute(
            """
            SELECT count(*)
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public'
              AND relation.relname = 'gateway_status'
            """,
        ).fetchone()
    assert target_schemas == (0,), "the integration database schemas are not clean"
    assert gateway_objects == (0,), "the integration database gateway is not clean"


def _worker_environment(url: str) -> dict[str, str]:
    parsed = urlsplit(url)
    environment = os.environ.copy()
    environment.update(
        {
            "DB_SEIIA_HOST": parsed.hostname or "localhost",
            "DB_SEIIA_PORT": str(parsed.port or 5432),
            "DB_SEIIA_USER": parsed.username or "",
            "DB_SEIIA_PWD": parsed.password or "",
            "DB_SEIIA_ASSISTENTE": parsed.path.removeprefix("/"),
            "DB_SEIIA_ASSISTENTE_SCHEMA": RUNTIME_SCHEMA,
            "ASSISTENTE_SESSION_CHECKPOINTER_SCHEMA": CHECKPOINTER_SCHEMA,
            "ASSISTENTE_EMBEDDING_DIMENSION": str(EMBEDDING_DIMENSION),
            "ASSISTENTE_MAX_LENGTH_CHUNK_SIZE": "24",
            "ASSISTENTE_CHUNK_OVERLAP": "4",
            "LITELLM_EMBEDDING_MODEL": "bootstrap/integration-model",
            "SEI_API_DB_ADDRESS": "http://integration.invalid",
            "SEI_API_DB_IDENTIFIER_SERVICE": "integration-test",
        }
    )
    return environment


def _run_parallel_runtime_bootstraps(url: str) -> None:
    test_file = Path(__file__).resolve()
    environment = _worker_environment(url)
    processes = [
        subprocess.Popen(  # noqa: S603
            [sys.executable, str(test_file), "runtime", url],
            cwd=test_file.parents[2],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]

    _communicate_processes(processes)


def _assert_runtime_objects(url: str) -> None:
    with psycopg.connect(url) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                """,
                (RUNTIME_SCHEMA,),
            )
        }
        assert tables == {"feedback", EMBEDDINGS_TABLE}

        gateway_rows = connection.execute(
            "SELECT count(*) FROM public.gateway_status"
        ).fetchone()
        assert gateway_rows == (1,)

        embedding_type = connection.execute(
            """
            SELECT format_type(attribute.atttypid, attribute.atttypmod)
            FROM pg_attribute AS attribute
            JOIN pg_class AS relation ON relation.oid = attribute.attrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = %s
              AND relation.relname = %s
              AND attribute.attname = 'embedding'
            """,
            (RUNTIME_SCHEMA, EMBEDDINGS_TABLE),
        ).fetchone()
        assert embedding_type == (f"vector({EMBEDDING_DIMENSION})",)

        indexes = {
            row[0]
            for row in connection.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = %s AND tablename = %s
                """,
                (RUNTIME_SCHEMA, EMBEDDINGS_TABLE),
            )
        }
        assert indexes == {
            f"{EMBEDDINGS_TABLE}_pkey",
            f"idx_{EMBEDDINGS_TABLE}_id_documento",
            f"idx_{EMBEDDINGS_TABLE}_embedding",
        }

        invalid_indexes = connection.execute(
            """
            SELECT count(*)
            FROM pg_index AS index_state
            JOIN pg_class AS index_relation
              ON index_relation.oid = index_state.indexrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = index_relation.relnamespace
            WHERE namespace.nspname IN (%s, 'public')
              AND NOT index_state.indisvalid
            """,
            (RUNTIME_SCHEMA,),
        ).fetchone()
        assert invalid_indexes == (0,)


def _insert_sentinel(url: str) -> None:
    vector = "[" + ",".join("0.5" for _ in range(EMBEDDING_DIMENSION)) + "]"
    with psycopg.connect(url) as connection:
        connection.execute(
            sql.SQL(
                """
                INSERT INTO {}.{} (
                    chunk_id, id_documento, embedding,
                    start_position, finished_position
                )
                VALUES (991, 992, %s, 0, 9)
                """
            ).format(sql.Identifier(RUNTIME_SCHEMA), sql.Identifier(EMBEDDINGS_TABLE)),
            (vector,),
        )


def _assert_sentinel_and_no_lock(url: str) -> None:
    with psycopg.connect(url) as connection:
        sentinel = connection.execute(
            sql.SQL(
                "SELECT chunk_id, id_documento FROM {}.{} WHERE chunk_id = 991"
            ).format(sql.Identifier(RUNTIME_SCHEMA), sql.Identifier(EMBEDDINGS_TABLE))
        ).fetchone()
        assert sentinel == (991, 992)

        held_locks = connection.execute(
            """
            SELECT count(*)
            FROM pg_locks
            WHERE locktype = 'advisory'
              AND classid = %s
              AND objid = %s
              AND granted
            """,
            RUNTIME_LOCK,
        ).fetchone()
        assert held_locks == (0,)


def _communicate_processes(processes: list[subprocess.Popen[str]]) -> None:
    results = []
    try:
        for process in processes:
            stdout, stderr = process.communicate(timeout=90)
            results.append((process.returncode, stdout, stderr))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()

    for returncode, stdout, stderr in results:
        assert returncode == 0, f"worker failed\nstdout:\n{stdout}\nstderr:\n{stderr}"


def _run_checkpointer_contention(url: str, signal_path: Path) -> None:
    test_file = Path(__file__).resolve()
    environment = _worker_environment(url)
    holder_signal = signal_path.with_name(f"{signal_path.name}-holder")
    follower_signal = signal_path.with_name(f"{signal_path.name}-follower")
    holder = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            str(test_file),
            "checkpointer-hold",
            url,
            str(holder_signal),
            str(follower_signal),
        ],
        cwd=test_file.parents[2],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    deadline = time.monotonic() + 30
    while not holder_signal.exists():
        if holder.poll() is not None:
            stdout, stderr = holder.communicate()
            pytest.fail(
                f"lock holder exited before contention\nstdout:\n{stdout}\n"
                f"stderr:\n{stderr}"
            )
        if time.monotonic() >= deadline:
            holder.kill()
            stdout, stderr = holder.communicate()
            pytest.fail(
                f"lock holder did not signal\nstdout:\n{stdout}\nstderr:\n{stderr}"
            )
        time.sleep(0.05)

    follower = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            str(test_file),
            "checkpointer-follow",
            url,
            str(follower_signal),
        ],
        cwd=test_file.parents[2],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _communicate_processes([holder, follower])


def _run_single_worker(url: str, mode: str) -> None:
    test_file = Path(__file__).resolve()
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, str(test_file), mode, url],
        cwd=test_file.parents[2],
        env=_worker_environment(url),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _communicate_processes([process])


def _assert_checkpointer_objects(url: str) -> None:
    with psycopg.connect(url) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                """,
                (CHECKPOINTER_SCHEMA,),
            )
        }
        assert tables == CHECKPOINTER_TABLES

        migrations = tuple(
            row[0]
            for row in connection.execute(
                sql.SQL("SELECT v FROM {}.checkpoint_migrations ORDER BY v").format(
                    sql.Identifier(CHECKPOINTER_SCHEMA)
                )
            )
        )
        assert migrations == tuple(range(10))

        invalid_indexes = connection.execute(
            """
            SELECT count(*)
            FROM pg_index AS index_state
            JOIN pg_class AS index_relation
              ON index_relation.oid = index_state.indexrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = index_relation.relnamespace
            WHERE namespace.nspname = %s
              AND NOT index_state.indisvalid
            """,
            (CHECKPOINTER_SCHEMA,),
        ).fetchone()
        assert invalid_indexes == (0,)


def _insert_checkpointer_sentinel(url: str) -> None:
    with psycopg.connect(url) as connection:
        connection.execute(
            sql.SQL(
                """
                INSERT INTO {}.checkpoints (
                    thread_id, checkpoint_ns, checkpoint_id,
                    checkpoint, metadata
                )
                VALUES (
                    'sentinel', '', 'sentinel-v1',
                    '{{}}'::jsonb, '{{}}'::jsonb
                )
                """
            ).format(sql.Identifier(CHECKPOINTER_SCHEMA))
        )


def _assert_checkpointer_sentinel_and_no_lock(url: str) -> None:
    with psycopg.connect(url) as connection:
        sentinel = connection.execute(
            sql.SQL(
                """
                SELECT thread_id, checkpoint_id
                FROM {}.checkpoints
                WHERE thread_id = 'sentinel'
                """
            ).format(sql.Identifier(CHECKPOINTER_SCHEMA))
        ).fetchone()
        assert sentinel == ("sentinel", "sentinel-v1")

        held_locks = connection.execute(
            """
            SELECT count(*)
            FROM pg_locks
            WHERE locktype = 'advisory'
              AND classid = %s
              AND objid = %s
              AND granted
            """,
            CHECKPOINTER_LOCK,
        ).fetchone()
        assert held_locks == (0,)


@pytest.mark.real_db
def test_parallel_database_bootstraps_are_additive_and_idempotent(
    tmp_path: Path,
) -> None:
    url = _database_url()
    _assert_clean_database(url)

    _run_parallel_runtime_bootstraps(url)
    _assert_runtime_objects(url)
    _insert_sentinel(url)

    _run_parallel_runtime_bootstraps(url)
    _assert_runtime_objects(url)
    _assert_sentinel_and_no_lock(url)
    _run_single_worker(url, "runtime-fail")
    _assert_sentinel_and_no_lock(url)

    _run_checkpointer_contention(url, tmp_path / "checkpointer-lock-acquired")
    _assert_checkpointer_objects(url)
    _insert_checkpointer_sentinel(url)

    _run_checkpointer_contention(url, tmp_path / "checkpointer-rerun-lock-acquired")
    _assert_checkpointer_objects(url)
    _assert_checkpointer_sentinel_and_no_lock(url)

    _run_single_worker(url, "checkpointer-fail")
    _assert_checkpointer_sentinel_and_no_lock(url)


async def _runtime_worker(url: str, mode: str) -> None:
    from sei_ia.data.database import runtime_bootstrap
    from sei_ia.data.database.async_db_connection import AsyncDbConnector
    from sei_ia.data.database.db_instances import BasePgvector

    connector = AsyncDbConnector(url, schema=RUNTIME_SCHEMA, base=BasePgvector)
    await connector.connect()
    if mode == "runtime-fail":

        def fail_after_lock(connection, metadata) -> None:  # noqa: ARG001
            raise RuntimeError("deliberate runtime bootstrap failure")

        runtime_bootstrap._initialize_database_objects = fail_after_lock

    try:
        await runtime_bootstrap.initialize_runtime_database(
            connector, BasePgvector.metadata
        )
    except RuntimeError as exc:
        if mode != "runtime-fail":
            raise
        assert str(exc) == "deliberate runtime bootstrap failure"
    else:
        if mode == "runtime-fail":
            raise AssertionError("deliberate runtime failure did not propagate")
    finally:
        await connector.close()


async def _checkpointer_worker(  # noqa: C901
    url: str,
    mode: str,
    signal_path: str | None = None,
    peer_signal_path: str | None = None,
) -> None:
    from sei_ia.services.session_fs import checkpointer

    checkpointer.settings.DB_SEIIA_CONNECTION_STRING = url

    if mode == "checkpointer-hold":
        original_acquire = checkpointer._acquire_setup_lock

        async def acquire_and_hold(connection, *, timeout_seconds=60.0):
            await original_acquire(
                connection,
                timeout_seconds=timeout_seconds,
            )
            if signal_path is None:
                raise RuntimeError("missing lock signal path")
            Path(signal_path).write_text("locked")
            if peer_signal_path is None:
                raise RuntimeError("missing follower signal path")
            deadline = time.monotonic() + 30
            while not Path(peer_signal_path).exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("follower did not observe lock contention")
                await asyncio.sleep(0.05)

        checkpointer._acquire_setup_lock = acquire_and_hold
    elif mode == "checkpointer-follow":
        original_acquire = checkpointer._acquire_setup_lock

        async def acquire_after_false_try(connection, *, timeout_seconds=60.0):
            cursor = await connection.execute(
                checkpointer._TRY_LOCK_SQL,
                checkpointer._LOCK_PARAMS,
            )
            row = await cursor.fetchone()
            if row is None or row["acquired"]:
                raise RuntimeError("follower did not encounter lock contention")
            if signal_path is None:
                raise RuntimeError("missing follower signal path")
            Path(signal_path).write_text("contended")
            await original_acquire(
                connection,
                timeout_seconds=timeout_seconds,
            )

        checkpointer._acquire_setup_lock = acquire_after_false_try
    elif mode == "checkpointer-fail":

        class FailingSaver:
            def __init__(self, connection) -> None:  # noqa: ARG002
                pass

            async def setup(self) -> None:
                raise RuntimeError("deliberate migration failure")

        checkpointer.AsyncPostgresSaver = FailingSaver

    try:
        await checkpointer.get_session_checkpointer()
    except RuntimeError as exc:
        if mode != "checkpointer-fail":
            raise
        assert str(exc) == "deliberate migration failure"
        assert checkpointer._pool is None
        assert checkpointer._saver is None
    else:
        if mode == "checkpointer-fail":
            raise AssertionError("deliberate failure did not propagate")
        await checkpointer.close_session_checkpointer()


if __name__ == "__main__":
    worker_mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if worker_mode in {"runtime", "runtime-fail"} and len(sys.argv) == 3:
        asyncio.run(_runtime_worker(sys.argv[2], worker_mode))
    elif worker_mode in {"checkpointer", "checkpointer-fail"} and len(sys.argv) == 3:
        asyncio.run(_checkpointer_worker(sys.argv[2], worker_mode))
    elif worker_mode == "checkpointer-follow" and len(sys.argv) == 4:
        asyncio.run(_checkpointer_worker(sys.argv[2], worker_mode, sys.argv[3]))
    elif worker_mode == "checkpointer-hold" and len(sys.argv) == 5:
        asyncio.run(
            _checkpointer_worker(sys.argv[2], worker_mode, sys.argv[3], sys.argv[4])
        )
    else:
        raise SystemExit(
            "usage: test_database_bootstrap.py "
            "{runtime|runtime-fail|checkpointer|checkpointer-follow|"
            "checkpointer-hold|checkpointer-fail} DATABASE_URL"
        )
