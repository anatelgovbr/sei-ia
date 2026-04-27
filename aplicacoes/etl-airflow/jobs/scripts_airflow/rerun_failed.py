"""Script para otimizar a reexecução de dags que falharam."""

import re

import requests


def trigger_and_delete_dag_runs(dag_id, port, username, password, runs) -> None:
    for dag_run in runs:
        dag_run_id = dag_run["dag_run_id"]

        # Trigger a new DAG run
        trigger_url = f"http://localhost:{port}/api/v1/dags/{dag_id}/dagRuns"
        response = requests.post(
            url=trigger_url,
            payload={"conf": {"id_process": dag_run["conf"]["id_process"]}},
            auth=(username, password),
            timeout=120,
        )

        if response.status_code == 200:
            pass
        else:
            pass

        # Delete the old DAG run

        response = requests.get(
            url=f"http://localhost:{port}/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}",
            auth=(username, password),
            timeout=120,
        )
        if response.status_code == 204:
            pass
        else:
            pass


def clear_dag_runs(dag_id, port, username, password, runs) -> None:
    for dag_run in runs:
        dag_run_id = dag_run["dag_run_id"]
        response = requests.get(
            url=f"http://localhost:{port}/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}",
            auth=(username, password),
            timeout=120,
        )
        if response.status_code == 200:
            pass
        else:
            pass


dag_id = "send_process_to_solr"
username = "airflow"
password = "airflow"  # noqa: S105 - Local dev default, not production secret
port = 8081

all_dag_runs = []
offset = 0
has_new_runs = True

while has_new_runs:
    response = requests.get(
        url=f"http://localhost:{port}/api/v1/dags/{dag_id}/dagRuns?offset={offset}",
        auth=(username, password),
        timeout=120,
    )
    if response.status_code != 200:
        break

    dag_runs = response.json()["dag_runs"]
    all_dag_runs.extend(dag_runs)
    has_new_runs = len(dag_runs) > 0
    offset += len(dag_runs)


for run in all_dag_runs:
    run["conf"]["id_process"] = re.sub(r"[^a-zA-Z0-9]", "", run["conf"]["id_process"])

failed_runs = [run for run in all_dag_runs if run["state"] == "failed"]

# Rerun failed dag runs
trigger_and_delete_dag_runs(dag_id, port, username, password, failed_runs)
