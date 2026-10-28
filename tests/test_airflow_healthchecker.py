"""Regressoes do checker Airflow e de seu status global."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

import tests as healthchecker
from tests import airflow_tests, connectivity_tests, docker_tests, env_tests


class FakeContainer:
    def __init__(self, results: list[SimpleNamespace]) -> None:
        self.results = iter(results)

    def exec_run(self, command: str) -> SimpleNamespace:
        del command
        return next(self.results)


@pytest.mark.parametrize(
    "command", ["airflow dags list", "airflow dags list-import-errors"]
)
def test_run_command_rejects_nonzero_docker_exec(command: str) -> None:
    container = FakeContainer(
        [SimpleNamespace(exit_code=17, output=b"airflow command failed")]
    )

    with pytest.raises(RuntimeError, match="exit 17"):
        airflow_tests.run_command(container, command)


def test_import_error_check_rejects_failed_list_import_errors() -> None:
    container = FakeContainer(
        [SimpleNamespace(exit_code=23, output=b"could not inspect DAG imports")]
    )

    with pytest.raises(RuntimeError, match="exit 23"):
        airflow_tests.get_airflow_dag_import_error(container, ["Error: import failed"])


def test_public_checker_returns_failure_when_airflow_dags_list_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comparison = object()
    container_status_df = pd.DataFrame({"Nome": ["etl-airflow-webserver"]})
    airflow_container = FakeContainer(
        [SimpleNamespace(exit_code=31, output=b"unable to list DAGs")]
    )

    monkeypatch.setattr(healthchecker.os, "makedirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        healthchecker.logging,
        "FileHandler",
        lambda *args, **kwargs: healthchecker.logging.NullHandler(),
    )
    monkeypatch.setattr(healthchecker.logging, "basicConfig", lambda **kwargs: None)
    monkeypatch.setattr(healthchecker.logging, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(healthchecker.logging, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(healthchecker.logging, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        healthchecker.shutil, "make_archive", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(pd.DataFrame, "to_csv", lambda *args, **kwargs: None)

    monkeypatch.setattr(env_tests, "create_env_vars_df", lambda _: object())
    monkeypatch.setattr(env_tests, "consolidate_env_files", lambda _: object())
    monkeypatch.setattr(
        env_tests, "compare_env_variables", lambda *args, **kwargs: ({}, comparison)
    )
    monkeypatch.setattr(env_tests, "report_env_issues", lambda _: 0)
    monkeypatch.setattr(env_tests, "anonymize_and_save", lambda *args, **kwargs: None)

    monkeypatch.setattr(connectivity_tests, "create_connectivity_config", lambda _: {})
    monkeypatch.setattr(connectivity_tests, "test_connectivity_all", lambda _: {})
    monkeypatch.setattr(
        connectivity_tests, "test_api_connectivity_and_response_all", lambda _: {}
    )
    monkeypatch.setattr(connectivity_tests, "test_litellm_proxy_models", lambda: {})
    monkeypatch.setattr(connectivity_tests, "report_litellm_proxy_status", lambda _: 0)
    monkeypatch.setattr(connectivity_tests, "test_gateway_certificate_sans", lambda: {})
    monkeypatch.setattr(connectivity_tests, "create_solr_config", lambda _: {})
    monkeypatch.setattr(connectivity_tests, "test_connectivity_all_solr", lambda _: {})
    monkeypatch.setattr(
        connectivity_tests,
        "create_postgres_config",
        lambda _: ({}, object(), object()),
    )
    monkeypatch.setattr(
        connectivity_tests, "verify_all_tables", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr(
        connectivity_tests,
        "connectivity_report",
        lambda *args, **kwargs: (0, None),
    )

    monkeypatch.setattr(docker_tests, "get_docker_containers", lambda **kwargs: {})
    monkeypatch.setattr(
        docker_tests,
        "verify_status_docker",
        lambda *args, **kwargs: container_status_df,
    )
    monkeypatch.setattr(
        docker_tests,
        "report_container_status",
        lambda *args, **kwargs: (0, {}),
    )
    monkeypatch.setattr(docker_tests, "get_all_docker_logs", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        docker_tests, "save_logs_into_file", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(docker_tests, "report_docker_logs", lambda *args, **kwargs: 0)

    fake_client = SimpleNamespace(
        containers=SimpleNamespace(get=lambda _: airflow_container)
    )
    monkeypatch.setattr("docker.from_env", lambda: fake_client)

    with pytest.raises(SystemExit) as exc_info:
        healthchecker.test_all()

    assert exc_info.value.code != 0
