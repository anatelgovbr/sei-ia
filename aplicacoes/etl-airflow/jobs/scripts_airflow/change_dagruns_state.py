"""change_dagruns_state module."""

import logging

import requests
from envs import VERIFY_SSL, auth

logger = logging.getLogger(__name__)


def change_dagruns_state(dag_id, state, port, username, password, failed_runs) -> None:
    for dag_run in failed_runs:
        dag_run_id = dag_run["dag_run_id"]
        update_url = (
            f"http://localhost:{port}/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/update"
        )
        response = requests.post(
            url=update_url,
            payload={"state": state},
            auth=auth,
            verify=VERIFY_SSL,
            timeout=120,
        )
        if response.status_code == requests.codes.ok:
            logger.info(f"Dag run {dag_run_id} has been updated to queued.")
        else:
            logger.error(f"Error updating dag run {dag_run_id}: {response.content}")
