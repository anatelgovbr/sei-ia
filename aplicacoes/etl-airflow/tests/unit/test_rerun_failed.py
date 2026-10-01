"""Tests for jobs/scripts_airflow/rerun_failed.py.

Standalone script that fetches dag runs, cleans up ids and re-triggers
failed ones — all at import time. requests.get/post are mocked before
import; the module is re-imported fresh each time (see get_all_dagruns
test for the same pattern).
"""

import sys
from unittest.mock import MagicMock, patch


def _fresh_import():
    sys.modules.pop("jobs.scripts_airflow.rerun_failed", None)
    import jobs.scripts_airflow.rerun_failed as mod

    return mod


def test_reruns_only_failed_dag_runs():
    list_page = MagicMock(status_code=200)
    list_page.json.return_value = {
        "dag_runs": [
            {
                "dag_run_id": "run1",
                "state": "failed",
                "conf": {"id_process": "123-abc"},
            },
            {
                "dag_run_id": "run2",
                "state": "success",
                "conf": {"id_process": "456"},
            },
        ]
    }
    stop_page = MagicMock(status_code=404)
    post_response = MagicMock(status_code=200)

    with patch(
        "requests.get", side_effect=[list_page, stop_page, MagicMock(status_code=200)]
    ) as mock_get, patch("requests.post", return_value=post_response) as mock_post:
        mod = _fresh_import()

    assert len(mod.all_dag_runs) == 2
    assert mod.all_dag_runs[0]["conf"]["id_process"] == "123abc"
    assert len(mod.failed_runs) == 1
    assert mod.failed_runs[0]["dag_run_id"] == "run1"
    mock_post.assert_called_once()
    assert mock_get.call_count == 3

    sys.modules.pop("jobs.scripts_airflow.rerun_failed", None)


def test_clear_dag_runs_gets_each_run():
    from jobs.scripts_airflow import rerun_failed as mod

    response = MagicMock(status_code=200)
    runs = [{"dag_run_id": "a"}, {"dag_run_id": "b"}]

    with patch("requests.get", return_value=response) as mock_get:
        mod.clear_dag_runs("dag1", 8080, "user", "pwd", runs)

    assert mock_get.call_count == 2
