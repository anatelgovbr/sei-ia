"""Regression tests for stable Airflow DAG scheduling boundaries."""

import ast
from pathlib import Path

from jobs.envs import DAGS_START_DATE, dags_default_args

DAG_OBJECTS_DIR = Path(__file__).parents[2] / "jobs" / "dags" / "dag_objects"


def _dag_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DAG"
    ]


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next(
        (keyword.value for keyword in call.keywords if keyword.arg == name), None
    )


def test_shared_start_date_is_fixed_and_timezone_aware():
    assert DAGS_START_DATE.year == 2024
    assert DAGS_START_DATE.month == 1
    assert DAGS_START_DATE.day == 1
    assert DAGS_START_DATE.tzinfo is not None
    assert "start_date" not in dags_default_args


def test_every_dag_declares_stable_start_date_and_disables_catchup():
    dag_count = 0

    for path in DAG_OBJECTS_DIR.rglob("*.py"):
        for call in _dag_calls(path):
            dag_count += 1
            start_date = _keyword(call, "start_date")
            catchup = _keyword(call, "catchup")

            assert isinstance(start_date, ast.Name), path
            assert start_date.id == "DAGS_START_DATE", path
            assert isinstance(catchup, ast.Constant), path
            assert catchup.value is False, path

    assert dag_count == 9
