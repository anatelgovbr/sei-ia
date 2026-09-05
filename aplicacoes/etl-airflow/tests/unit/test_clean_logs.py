"""Tests for jobs/dags/dag_objects/clean_logs.py."""

from datetime import timedelta

from jobs.dags.dag_objects.clean_logs import dag, timestamp_before_now


def test_timestamp_before_now_returns_iso_like_format():
    result = timestamp_before_now(timedelta(days=30))
    assert len(result) == 19
    assert result[4] == "-"
    assert result[10] == "T"


def test_dag_and_clean_task_are_defined():
    assert dag.dag_id == "system_clean_airflow_logs"
    assert "clean_db" in dag.task_ids
