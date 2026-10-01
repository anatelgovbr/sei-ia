"""Tests for jobs/scripts_airflow/trigger_dag.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from jobs.scripts_airflow.trigger_dag import (
    AirflowDagTrigger,
    main,
    trigger_dag_simple,
)

pytestmark = pytest.mark.asyncio


def _mock_async_client(response):
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.get = AsyncMock(return_value=response)
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    return client


class TestTriggerDag:
    async def test_returns_json_on_success(self):
        trigger = AirflowDagTrigger(base_url="http://airflow/api/v1")
        response = MagicMock(status_code=200)
        response.json.return_value = {"dag_run_id": "abc"}

        with patch("httpx.AsyncClient", return_value=_mock_async_client(response)):
            result = await trigger.trigger_dag("dag1", conf={"a": 1})

        assert result == {"dag_run_id": "abc"}

    async def test_uses_custom_dag_run_id(self):
        trigger = AirflowDagTrigger(base_url="http://airflow/api/v1")
        response = MagicMock(status_code=200)
        response.json.return_value = {"dag_run_id": "custom"}
        client = _mock_async_client(response)

        with patch("httpx.AsyncClient", return_value=client):
            await trigger.trigger_dag("dag1", dag_run_id="custom")

        payload = client.post.call_args.kwargs["json"]
        assert payload["dag_run_id"] == "custom"

    async def test_raises_runtime_error_on_non_200(self):
        trigger = AirflowDagTrigger(base_url="http://airflow/api/v1")
        response = MagicMock(status_code=500, text="erro interno")

        with patch(
            "httpx.AsyncClient", return_value=_mock_async_client(response)
        ), pytest.raises(RuntimeError):
            await trigger.trigger_dag("dag1")

    async def test_wraps_request_error(self):
        trigger = AirflowDagTrigger(base_url="http://airflow/api/v1")
        client = AsyncMock()
        client.post = AsyncMock(
            side_effect=httpx.RequestError("boom", request=MagicMock())
        )
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False

        with patch("httpx.AsyncClient", return_value=client), pytest.raises(
            RuntimeError
        ):
            await trigger.trigger_dag("dag1")


class TestTriggerDagWithParams:
    async def test_forwards_kwargs_as_conf(self):
        trigger = AirflowDagTrigger(base_url="http://airflow/api/v1")
        with patch.object(
            trigger, "trigger_dag", new=AsyncMock(return_value={"ok": True})
        ) as mock_trigger:
            await trigger.trigger_dag_with_params("dag1", foo="bar")

        mock_trigger.assert_awaited_once_with(dag_id="dag1", conf={"foo": "bar"})


class TestGetDagInfo:
    async def test_returns_json_on_success(self):
        trigger = AirflowDagTrigger(base_url="http://airflow/api/v1")
        response = MagicMock(status_code=200)
        response.json.return_value = {"dag_id": "dag1"}

        with patch("httpx.AsyncClient", return_value=_mock_async_client(response)):
            result = await trigger.get_dag_info("dag1")

        assert result == {"dag_id": "dag1"}

    async def test_raises_runtime_error_on_failure(self):
        trigger = AirflowDagTrigger(base_url="http://airflow/api/v1")
        response = MagicMock(status_code=404, text="not found")

        with patch(
            "httpx.AsyncClient", return_value=_mock_async_client(response)
        ), pytest.raises(RuntimeError):
            await trigger.get_dag_info("dag1")

    async def test_wraps_request_error(self):
        trigger = AirflowDagTrigger(base_url="http://airflow/api/v1")
        client = AsyncMock()
        client.get = AsyncMock(
            side_effect=httpx.RequestError("boom", request=MagicMock())
        )
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False

        with patch("httpx.AsyncClient", return_value=client), pytest.raises(
            RuntimeError
        ):
            await trigger.get_dag_info("dag1")


class TestTriggerDagSimple:
    async def test_builds_trigger_and_calls_trigger_dag(self):
        with patch.object(
            AirflowDagTrigger, "trigger_dag", new=AsyncMock(return_value={"ok": True})
        ) as mock_trigger:
            result = await trigger_dag_simple("dag1", conf={"a": 1})

        assert result == {"ok": True}
        mock_trigger.assert_awaited_once()


class TestMain:
    async def test_suppresses_exceptions(self):
        with patch.object(
            AirflowDagTrigger,
            "trigger_dag",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await main()
