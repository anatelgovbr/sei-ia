"""Testes auxiliares do Airflow para o healthchecker."""

from __future__ import annotations

import logging
import os

import pandas as pd


def run_command(container, command: str) -> str:
    result = container.exec_run(command)
    return result.output.decode("utf-8")


def convert_docker_airflow_output_to_df(text: str) -> tuple[pd.DataFrame, list[str]]:
    lines = text.splitlines()
    filtered_lines = []
    error_lines = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("="):
            continue
        if "Error:" in line or "list-import-errors" in line:
            error_lines.append(line)
            continue
        filtered_lines.append(line)

    data = []
    for row in filtered_lines:
        cells = [cell.strip() for cell in row.split("|")]
        data.append(cells)

    if data:
        return pd.DataFrame(data[1:], columns=data[0]), error_lines
    return pd.DataFrame(), error_lines


def get_airflow_dag_import_error(container, error_airflow_lines: list[str]) -> list[str]:
    if not error_airflow_lines:
        return []

    output_text_error = run_command(container, "airflow dags list-import-errors")
    lines = output_text_error.splitlines()
    dag_filename_error = []

    for line in lines:
        if line.startswith(("=", "filepath")):
            continue
        line_splited = line.split("|")
        if line_splited[0].startswith(" "):
            continue
        dag_filename_error.append(line_splited[0])

    logging.error("Existem erros nas dags:")
    logging.error("%s", dag_filename_error)
    return dag_filename_error


def get_dags_runs(container, airflow_dags_df: pd.DataFrame, dag_filename_error: list[str]) -> pd.DataFrame:
    runs_data = []

    for _, dag in airflow_dags_df.iterrows():
        dag_id = dag["dag_id"]
        runs_output = run_command(container, f"airflow dags list-runs -d {dag_id}")
        runs_df, _ = convert_docker_airflow_output_to_df(runs_output)

        for _, run_row in runs_df.iterrows():
            run_id = run_row["run_id"]
            state = run_row["state"]

            tasks_output = run_command(
                container, f"airflow tasks states-for-dag-run {dag_id} {run_id}"
            )
            tasks_df, _ = convert_docker_airflow_output_to_df(tasks_output)

            success = (tasks_df["state"] == "success").sum()
            failed = (tasks_df["state"] == "failed").sum()
            running = (tasks_df["state"] == "running").sum()
            up_for_retry = (tasks_df["state"] == "up_for_retry").sum()

            runs_data.append(
                [
                    dag_id,
                    dag["fileloc"],
                    dag["is_paused"],
                    state,
                    success,
                    failed,
                    running,
                    up_for_retry,
                ]
            )

    for file in dag_filename_error:
        runs_data.append(["no_name", file, True, "Indisponivel", 0, 0, 0, 0])

    runs_columns = [
        "dag_id",
        "file_loc",
        "is_paused",
        "status",
        "success",
        "failed",
        "running",
        "up_for_retry",
    ]
    return pd.DataFrame(runs_data, columns=runs_columns)


def compare_dag_runs(runs_df: pd.DataFrame, path: str | None = None) -> dict:
    unexpected_status = runs_df[
        ~runs_df["status"].isin(["success", "failed", "running", "up_for_retry"])
    ]
    non_success_runs = runs_df[runs_df["status"] != "success"]

    results = {
        "unexpected_status": unexpected_status[["dag_id", "file_loc", "status"]],
        "non_success_runs": non_success_runs[["dag_id", "file_loc", "status"]],
    }
    if path:
        unexpected_status.to_csv(
            os.path.join(path, "airflow_unexpected_status.csv"), index=False
        )
        non_success_runs.to_csv(
            os.path.join(path, "airflow_non_success_runs.csv"), index=False
        )
    return results


def report_dag_run_issues(results: dict, runs_df: pd.DataFrame) -> int:
    error = 0
    if not results["unexpected_status"].empty:
        logging.error("\nExistem execucoes com status inesperado nos DAGs:\n")
        logging.error(results["unexpected_status"].to_markdown(index=False))
        error += len(results["unexpected_status"])

    if not results["non_success_runs"].empty:
        logging.warning("\nExistem execucoes com estado diferente de success:\n")
        logging.warning(results["non_success_runs"].to_markdown(index=False))
        error += len(results["non_success_runs"])

    if error == 0:
        logging.info("\nNao foram encontrados erros nas execucoes dos DAGs.\n")
    return error
