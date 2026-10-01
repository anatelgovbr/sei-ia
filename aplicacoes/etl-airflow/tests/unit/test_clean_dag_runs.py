"""Tests for jobs/scripts_airflow/clean_dag_runs.py."""

from unittest.mock import MagicMock, patch

import pytest

from jobs.scripts_airflow.clean_dag_runs import clean_dag_run


class TestCleanDagRun:
    def test_returns_early_when_list_fails(self):
        list_response = MagicMock(status_code=500)
        with patch("requests.get", return_value=list_response) as mock_get, patch(
            "requests.delete"
        ) as mock_delete:
            clean_dag_run("dag1", "queued")

        mock_get.assert_called_once()
        mock_delete.assert_not_called()

    def test_deletes_each_queued_run(self):
        list_response = MagicMock(status_code=200)
        list_response.json.return_value = {
            "dag_runs": [{"dag_run_id": "run1"}, {"dag_run_id": "run2"}]
        }
        delete_response = MagicMock(status_code=204)

        with patch("requests.get", return_value=list_response), patch(
            "requests.delete", return_value=delete_response
        ) as mock_delete:
            clean_dag_run("dag1", "queued")

        assert mock_delete.call_count == 2

    def test_raises_when_delete_fails(self):
        list_response = MagicMock(status_code=200)
        list_response.json.return_value = {"dag_runs": [{"dag_run_id": "run1"}]}
        delete_response = MagicMock(status_code=500)
        delete_response.json.return_value = {"error": "boom"}

        with patch("requests.get", return_value=list_response), patch(
            "requests.delete", return_value=delete_response
        ), pytest.raises(RuntimeError):
            clean_dag_run("dag1", "queued")
