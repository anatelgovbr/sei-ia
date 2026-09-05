"""get_all_dagruns module."""

# %%
import requests

from jobs.envs import AIRFLOW_WWW_USER_PASSWORD, AIRFLOW_WWW_USER_USERNAME

dag_id = "send_process_to_solr"
username = AIRFLOW_WWW_USER_USERNAME
password = AIRFLOW_WWW_USER_PASSWORD
port = 8100
limit = 1000000  # Increase limit to retrieve more runs
offset = 0

all_dag_runs = []
while True:
    response = requests.get(
        url=f"http://localhost:{port}/api/v1/dags/{dag_id}/dagRuns?offset={offset}",
        auth=(username, password),
        timeout=120,
    )
    if response.status_code != 200:
        break

    dag_runs = response.json()["dag_runs"]
    all_dag_runs.extend(dag_runs)

    if len(all_dag_runs) > limit:
        break

    offset += limit

# %%
