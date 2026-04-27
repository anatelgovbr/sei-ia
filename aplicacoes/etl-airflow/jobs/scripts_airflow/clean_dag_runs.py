"""clean_dag_runs module."""

import requests

from jobs.envs import (
    AIRFLOW_API_BASE_URL,
    AIRFLOW_WWW_USER_PASSWORD,
    AIRFLOW_WWW_USER_USERNAME,
)


def clean_dag_run(dag_id, state) -> None:
    """Deleta execuções em fila de uma DAG específica no Airflow via REST API.

    Parâmetros:
    - airflow_base_url: URL base da instância do Airflow, incluindo '/api/v1'.
    - dag_id: ID da DAG cujas execuções em fila devem ser deletadas.
    - state: estado das execuções em fila que devem ser deletadas.
    """
    headers = {
        "Authorization": f"Basic {AIRFLOW_WWW_USER_USERNAME}:{AIRFLOW_WWW_USER_PASSWORD}"
    }
    # Lista as execuções em fila para a DAG específica
    list_runs_endpoint = f"{AIRFLOW_API_BASE_URL}/dags/{dag_id}/dagRuns?state={state}"
    response = requests.get(list_runs_endpoint, headers=headers, timeout=120)
    if response.status_code != requests.codes.ok:
        return

    runs_in_queue = response.json().get("dag_runs", [])

    # Deleta ou cancela cada execução em fila
    for run in runs_in_queue:
        dag_run_id = run["dag_run_id"]
        delete_run_endpoint = (
            f"{AIRFLOW_API_BASE_URL}/dags/{dag_id}/dagRuns/{dag_run_id}"
        )
        delete_response = requests.delete(
            delete_run_endpoint, headers=headers, timeout=120
        )
        if delete_response.status_code != 204:
            msg = f"Erro ao limpar as execuções em espera da Dag : {dag_run_id}."
            raise Exception(
                msg,
                f"code : {delete_response.status_code}",
                f"response : {delete_response.json()}",
            )
