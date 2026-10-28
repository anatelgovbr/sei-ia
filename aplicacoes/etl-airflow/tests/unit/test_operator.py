"""Tests for jobs/scripts_airflow/operator.py."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from airflow.exceptions import AirflowException
from airflow.operators.python_operator import PythonOperator, PythonVirtualenvOperator

from jobs.scripts_airflow.operator import (
    CustomPythonRetryOperator,
    CustomPythonVirtualRetryOperator,
)


def _context(try_number: int):
    ti = MagicMock()
    ti.try_number = try_number
    return {"ti": ti}


def _noop():
    return None


class TestCustomPythonRetryOperator:
    def test_delegates_to_super_when_no_error(self):
        op = CustomPythonRetryOperator(task_id="t1", python_callable=lambda: None)
        with patch.object(PythonOperator, "execute", return_value="ok") as mock_exec:
            result = op.execute(_context(1))

        assert result == "ok"
        mock_exec.assert_called_once()

    def test_raises_airflow_exception_with_retry_delay(self):
        op = CustomPythonRetryOperator(
            task_id="t1",
            python_callable=lambda: None,
            retry_delays=[timedelta(seconds=1), timedelta(seconds=2)],
        )
        with patch.object(
            PythonOperator, "execute", side_effect=ValueError("boom")
        ), patch("jobs.scripts_airflow.operator.time.sleep") as mock_sleep, pytest.raises(
            AirflowException
        ):
            op.execute(_context(1))

        mock_sleep.assert_called_once_with(1)

    def test_reraises_original_when_retries_exhausted(self):
        op = CustomPythonRetryOperator(
            task_id="t1",
            python_callable=lambda: None,
            retry_delays=[timedelta(seconds=1)],
        )
        with patch.object(
            PythonOperator, "execute", side_effect=ValueError("boom")
        ), patch("jobs.scripts_airflow.operator.time.sleep"), pytest.raises(
            ValueError
        ):
            op.execute(_context(5))


class TestCustomPythonVirtualRetryOperator:
    def test_delegates_to_super_when_no_error(self):
        op = CustomPythonVirtualRetryOperator(
            task_id="t2", python_callable=_noop, requirements=[]
        )
        with patch.object(
            PythonVirtualenvOperator, "execute", return_value="ok"
        ) as mock_exec:
            result = op.execute(_context(1))

        assert result == "ok"
        mock_exec.assert_called_once()

    def test_raises_airflow_exception_with_retry_delay(self):
        op = CustomPythonVirtualRetryOperator(
            task_id="t2",
            python_callable=_noop,
            requirements=[],
            retry_delays=[timedelta(seconds=1), timedelta(seconds=2)],
        )
        with patch.object(
            PythonVirtualenvOperator, "execute", side_effect=AirflowException("boom")
        ), patch("jobs.scripts_airflow.operator.time.sleep") as mock_sleep, pytest.raises(
            AirflowException
        ):
            op.execute(_context(1))

        mock_sleep.assert_called_once_with(1)

    def test_reraises_when_retries_exhausted(self):
        op = CustomPythonVirtualRetryOperator(
            task_id="t2",
            python_callable=_noop,
            requirements=[],
            retry_delays=[timedelta(seconds=1)],
        )
        with patch.object(
            PythonVirtualenvOperator,
            "execute",
            side_effect=AirflowException("boom"),
        ), patch("jobs.scripts_airflow.operator.time.sleep"), pytest.raises(
            AirflowException
        ):
            op.execute(_context(5))
