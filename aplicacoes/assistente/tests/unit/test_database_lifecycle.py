"""Regressions for database bootstrap and borrowed connector ownership."""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sei_ia.data.database.async_db_connection import AsyncDbConnector
from sei_ia.data.database.table_manager import TableManager
from sei_ia.services.async_llm_requests.async_requests import process_requests


def test_connector_construction_does_not_run_ddl() -> None:
    base = MagicMock()

    with (
        patch(
            "sei_ia.data.database.async_db_connection.create_engine",
            return_value=MagicMock(),
        ),
        patch(
            "sei_ia.data.database.async_db_connection.create_async_engine",
            return_value=MagicMock(),
        ),
    ):
        AsyncDbConnector("postgresql://db/test", base=base)

    base.metadata.create_all.assert_not_called()


@pytest.mark.asyncio
async def test_connector_close_releases_ownership_and_propagates_failures() -> None:
    connector = object.__new__(AsyncDbConnector)
    pool = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("pool close")))
    async_engine = SimpleNamespace(dispose=AsyncMock())
    engine = MagicMock()
    connector.pool = pool
    connector.async_engine = async_engine
    connector.engine = engine

    with pytest.raises(ExceptionGroup, match="database resources"):
        await connector.close()

    assert connector.pool is None
    async_engine.dispose.assert_awaited_once_with()
    engine.dispose.assert_called_once_with()


def test_table_manager_reuses_the_caller_connection() -> None:
    connection = MagicMock()
    connection.execute.return_value.scalar.return_value = False

    manager = TableManager(connection)
    manager.initialize_all_tables()

    assert connection.execute.call_count == 4
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
    connection.close.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_uses_one_locked_transaction(monkeypatch) -> None:
    runtime_bootstrap = importlib.import_module(
        "sei_ia.data.database.runtime_bootstrap"
    )
    events: list[tuple[str, object]] = []

    class SyncConnection:
        dialect = SimpleNamespace(
            identifier_preparer=SimpleNamespace(quote=lambda identifier: identifier)
        )

        def execute(self, statement, params=None):
            events.append(("ddl", str(statement)))
            result = MagicMock()
            result.scalar.return_value = True
            return result

    sync_connection = SyncConnection()

    class AsyncConnection:
        async def execute(self, statement, params=None):
            events.append(("lock", str(statement)))

        async def run_sync(self, operation):
            events.append(("run_sync", sync_connection))
            operation(sync_connection)

    class BeginContext:
        async def __aenter__(self):
            return AsyncConnection()

        async def __aexit__(self, exc_type, exc, traceback):
            events.append(("transaction_exit", exc_type))

    engine = MagicMock()
    engine.begin.return_value = BeginContext()
    db = SimpleNamespace(async_engine=engine)
    metadata = MagicMock()

    class FakeTableManager:
        def __init__(self, connection):
            events.append(("table_manager_init", connection))

        def initialize_all_tables(self):
            events.append(("table_manager_run", sync_connection))

    monkeypatch.setattr(runtime_bootstrap, "TableManager", FakeTableManager)
    monkeypatch.setattr(runtime_bootstrap, "_register_database_models", lambda: None)

    await runtime_bootstrap.initialize_runtime_database(db, metadata)

    assert events[0][0] == "lock"
    assert "pg_advisory_xact_lock" in events[0][1]
    metadata.create_all.assert_called_once_with(sync_connection, checkfirst=True)
    assert ("table_manager_init", sync_connection) in events
    assert ("table_manager_run", sync_connection) in events
    assert events[-1] == ("transaction_exit", None)


def test_lifespan_has_one_bootstrap_owner() -> None:
    main_path = Path(__file__).parents[2] / "sei_ia" / "main.py"
    tree = ast.parse(main_path.read_text())
    lifespan = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "initialize_database_tables"
    )
    called_names = [
        node.func.id
        for node in ast.walk(lifespan)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    called_attributes = [
        node.func.attr
        for node in ast.walk(lifespan)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]

    assert called_names.count("initialize_runtime_database") == 1
    assert "create_all" not in called_attributes
    assert "TableManager" not in called_names


def test_session_bootstrap_failure_is_not_silenced() -> None:
    main_path = Path(__file__).parents[2] / "sei_ia" / "main.py"
    tree = ast.parse(main_path.read_text())
    session_start = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_start_session_runtime"
    )

    assert not any(
        isinstance(node, ast.ExceptHandler) for node in ast.walk(session_start)
    )


def test_session_shutdown_failure_is_not_silenced() -> None:
    main_path = Path(__file__).parents[2] / "sei_ia" / "main.py"
    tree = ast.parse(main_path.read_text())
    session_stop = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_stop_session_runtime"
    )
    lifespan = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "initialize_database_tables"
    )
    called_names = {
        node.func.id
        for node in ast.walk(lifespan)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert not any(
        isinstance(node, ast.ExceptHandler) for node in ast.walk(session_stop)
    )
    assert "ExceptionGroup" in called_names


def test_smoke_client_enters_application_lifespan() -> None:
    smoke_path = Path(__file__).parents[2] / "scripts" / "smoke_endpoint_host.py"
    tree = ast.parse(smoke_path.read_text())
    context_calls = [
        item.context_expr.func.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.With, ast.AsyncWith))
        for item in node.items
        if isinstance(item.context_expr, ast.Call)
        and isinstance(item.context_expr.func, ast.Name)
    ]

    assert "TestClient" in context_calls


@pytest.mark.asyncio
async def test_process_requests_borrows_database_connector(tmp_path: Path) -> None:
    requests_path = tmp_path / "requests.jsonl"
    results_path = tmp_path / "results.jsonl"
    requests_path.write_text("")
    db = AsyncMock()

    await process_requests(
        requests_filepath=requests_path,
        save_filepath=results_path,
        api_endpoint="embeddings",
        llm_client=MagicMock(),
        db=db,
    )

    db.connect.assert_not_awaited()
    db.initialize_gateway_table.assert_not_awaited()
    db.close.assert_not_awaited()
