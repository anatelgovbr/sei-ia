"""Tests for jobs/scripts_airflow/change_dagruns_state.py."""

from unittest.mock import MagicMock, patch

from jobs.scripts_airflow.change_dagruns_state import change_dagruns_state


class TestChangeDagrunsState:
    def test_logs_success_for_each_run(self, caplog):
        response = MagicMock(status_code=200)
        failed_runs = [{"dag_run_id": "run1"}, {"dag_run_id": "run2"}]

        with patch("requests.post", return_value=response) as mock_post, caplog.at_level(
            "INFO"
        ):
            change_dagruns_state("dag1", "queued", 8080, failed_runs)

        assert mock_post.call_count == 2
        assert "run1" in caplog.text
        assert "run2" in caplog.text

    def test_logs_error_when_update_fails(self, caplog):
        response = MagicMock(status_code=500, content=b"erro")
        failed_runs = [{"dag_run_id": "run1"}]

        with patch("requests.post", return_value=response), caplog.at_level("ERROR"):
            change_dagruns_state("dag1", "queued", 8080, failed_runs)

        assert "Error updating dag run run1" in caplog.text
