"""Tests for jobs/dags/dag_objects/mlt_etl_process/dag_mlt_start_etl.py.

Airflow's @task decorator wraps the callable — the raw undecorated function
is reachable via `.function`, which is how TaskFlow tasks are unit tested
without a running DAG context.
"""

import asyncio
import pickle
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from jobs.dags.dag_objects.mlt_etl_process import dag_mlt_start_etl as mod


class TestCheckAlreadyInAirflowQueue:
    def test_filters_already_queued_ids(self):
        store_queue = [
            {
                "slot_list": [["1", "type1"]],
                "interested_max": 1,
                "related_processes_max": 1,
            }
        ]
        result, already = mod.check_already_in_airflow_queue.function(
            ["1", "2"], store_queue
        )
        assert result == ["2"]
        assert already == 1

    def test_empty_queue_keeps_all(self):
        result, already = mod.check_already_in_airflow_queue.function(["1"], [])
        assert result == ["1"]
        assert already == 0


class TestCheckAlreadyInQueueSync:
    def test_matches_public_behavior(self):
        store_queue = [
            {
                "slot_list": [["1", "type1"]],
                "interested_max": 1,
                "related_processes_max": 1,
            }
        ]
        result, already = mod._check_already_in_queue_sync(["1", "2"], store_queue)
        assert result == ["2"]
        assert already == 1


class TestSplitSet:
    def test_distributes_round_robin(self):
        result = mod.split_set([1, 2, 3, 4, 5], 2)
        assert len(result) == 2
        assert sorted(result[0] + result[1]) == [1, 2, 3, 4, 5]

    def test_more_slots_than_items(self):
        result = mod.split_set([1], 3)
        assert result == [[1], [], []]


class TestTriggerSlotsAsync:
    def test_triggers_dag_for_each_chunk(self):
        fake_trigger = MagicMock()
        fake_trigger.trigger_dag = AsyncMock(return_value=None)

        asyncio.run(
            mod._trigger_slots_async(
                fake_trigger, "dag1", [[("1", "t1")], [("2", "t2")]], ["1", "2"]
            )
        )

        assert fake_trigger.trigger_dag.await_count == 2


class TestCheckQueue:
    def test_returns_store_queue_slots_and_qnt(self):
        conf_bytes = pickle.dumps(
            {"slot_list": [["1", "t1"]], "interested_max": 1, "related_processes_max": 1}
        )
        fake_row = MagicMock()
        fake_row.conf = MagicMock()
        fake_row.conf.tobytes.return_value = conf_bytes
        fake_row.state = "queued"

        fake_result = MagicMock()
        fake_result.fetchall.return_value = [fake_row]

        fake_conn = MagicMock()
        fake_conn.execute.return_value = fake_result
        fake_conn.__enter__ = MagicMock(return_value=fake_conn)
        fake_conn.__exit__ = MagicMock(return_value=False)

        fake_engine = MagicMock()
        fake_engine.connect.return_value = fake_conn

        with patch.object(mod.sa, "create_engine", return_value=fake_engine):
            store_queue, slots, qnt = mod.check_queue.function(
                conn_string="postgresql://x",
                estados_filtro=["queued"],
                dag_id_filtro="dag1",
                limit_queue=10,
                batch_size=5,
            )

        assert len(store_queue) == 1
        assert slots == 9
        assert qnt == 45
        fake_engine.dispose.assert_called_once()

    def test_disposes_engine_even_on_error(self):
        fake_engine = MagicMock()
        fake_engine.connect.side_effect = RuntimeError("boom")

        with patch.object(
            mod.sa, "create_engine", return_value=fake_engine
        ), pytest.raises(RuntimeError):
            mod.check_queue.function(
                conn_string="postgresql://x",
                estados_filtro=["queued"],
                dag_id_filtro="dag1",
                limit_queue=10,
                batch_size=5,
            )

        fake_engine.dispose.assert_called_once()


class TestTriggerIndex:
    def test_returns_early_when_no_slots(self, caplog):
        mod.trigger_index.function(
            lista_func_name="md_ia_lista_processos_indexaveis",
            consulta_func_name="md_ia_consulta_processo",
            check_queue_result=([], 0, 0),
            dag_id="dag1",
        )

    def test_returns_early_when_nothing_to_index(self):
        with patch.dict(
            mod.FUNC_MAP,
            {"md_ia_lista_processos_indexaveis": MagicMock(return_value=[])},
        ):
            mod.trigger_index.function(
                lista_func_name="md_ia_lista_processos_indexaveis",
                consulta_func_name="md_ia_consulta_processo",
                check_queue_result=([], 5, 10),
                dag_id="dag1",
            )

    def test_raises_when_metadata_missing(self):
        fake_lista_func = MagicMock(return_value=["1"])
        fake_consulta_func = MagicMock(return_value=pd.DataFrame())

        with patch.dict(
            mod.FUNC_MAP,
            {
                "md_ia_lista_processos_indexaveis": fake_lista_func,
                "md_ia_consulta_processo": fake_consulta_func,
            },
        ), pytest.raises(RuntimeError):
            mod.trigger_index.function(
                lista_func_name="md_ia_lista_processos_indexaveis",
                consulta_func_name="md_ia_consulta_processo",
                check_queue_result=([], 5, 10),
                dag_id="dag1",
            )

    def test_triggers_dags_for_found_metadata(self):
        fake_lista_func = MagicMock(side_effect=[["1"], []])
        fake_consulta_func = MagicMock(
            return_value=pd.DataFrame(
                {"id_protocolo": ["1"], "id_type_process": ["7"]}
            )
        )

        with patch.dict(
            mod.FUNC_MAP,
            {
                "md_ia_lista_processos_indexaveis": fake_lista_func,
                "md_ia_consulta_processo": fake_consulta_func,
            },
        ), patch.object(mod, "AirflowDagTrigger") as mock_trigger_cls, patch.object(
            mod.asyncio, "run"
        ) as mock_run:
            mod.trigger_index.function(
                lista_func_name="md_ia_lista_processos_indexaveis",
                consulta_func_name="md_ia_consulta_processo",
                check_queue_result=([], 1, 1),
                dag_id="dag1",
            )

        mock_trigger_cls.assert_called_once()
        mock_run.assert_called_once()


class TestDagsAreDefined:
    def test_process_and_documents_dags_exist(self):
        assert mod.dag.dag_id == "process_update_index"
        assert mod.dag_documents.dag_id == "documents_update_index"
