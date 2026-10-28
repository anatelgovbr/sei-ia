"""Tests for jobs/scripts_airflow/get_all_dagruns.py.

This is a standalone script (not a reusable module) that fetches DAG runs
in a loop at import time. We mock requests.get before import and force a
fresh import each time via sys.modules, matching the pattern used for
module-level side-effecting scripts elsewhere in the codebase.
"""

import sys
from unittest.mock import MagicMock, patch


def _fresh_import():
    sys.modules.pop("jobs.scripts_airflow.get_all_dagruns", None)
    import jobs.scripts_airflow.get_all_dagruns as mod

    return mod


def test_collects_dag_runs_until_non_200_response():
    first_page = MagicMock(status_code=200)
    first_page.json.return_value = {
        "dag_runs": [{"dag_run_id": "run1"}, {"dag_run_id": "run2"}]
    }
    stop_page = MagicMock(status_code=404)

    with patch("requests.get", side_effect=[first_page, stop_page]) as mock_get:
        mod = _fresh_import()

    assert mock_get.call_count == 2
    assert len(mod.all_dag_runs) == 2

    sys.modules.pop("jobs.scripts_airflow.get_all_dagruns", None)
