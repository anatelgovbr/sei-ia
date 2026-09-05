"""Tests for jobs/dags/dag_objects/mlt_etl_process/dag_mlt_start_embedding.py."""

import pickle
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jobs.dags.dag_objects.mlt_etl_process import (
    dag_mlt_start_embedding as mod,
)


class TestCheckAlreadyInAirflowQueueEmbedding:
    def test_filters_already_queued_ids(self):
        store_queue = [{"slot_list": ["1"]}]
        result, already = mod.check_already_in_airflow_queue_embedding.function(
            ["1", "2"], store_queue
        )
        assert result == ["2"]
        assert already == 1


class TestCheckAlreadyInQueueEmbeddingSync:
    def test_matches_public_behavior(self):
        store_queue = [{"slot_list": ["1"]}]
        result, already = mod._check_already_in_queue_embedding_sync(
            ["1", "2"], store_queue
        )
        assert result == ["2"]
        assert already == 1


class TestCheckQueueEmbedding:
    def test_returns_store_queue_slots_and_qnt(self):
        conf_bytes = pickle.dumps({"slot_list": ["1"]})
        fake_row = MagicMock()
        fake_row.conf = MagicMock()
        fake_row.conf.tobytes.return_value = conf_bytes
        fake_row.state = "running"

        fake_result = MagicMock()
        fake_result.fetchall.return_value = [fake_row]

        fake_conn = MagicMock()
        fake_conn.execute.return_value = fake_result
        fake_conn.__enter__ = MagicMock(return_value=fake_conn)
        fake_conn.__exit__ = MagicMock(return_value=False)

        fake_engine = MagicMock()
        fake_engine.connect.return_value = fake_conn

        with patch.object(mod.sa, "create_engine", return_value=fake_engine):
            store_queue, slots, qnt = mod.check_queue_embedding.function(
                conn_string="postgresql://x",
                estados_filtro=["running"],
                dag_id_filtro="dag1",
                limit_queue=10,
                batch_size=5,
            )

        assert len(store_queue) == 1
        assert slots == 10
        assert qnt == 50
        fake_engine.dispose.assert_called_once()


class TestTriggerEmbedding:
    def test_returns_early_when_no_slots(self):
        mod.trigger_embedding.function(
            lista_func_name="md_ia_lista_documentos_vetorizaveis",
            check_queue_result=([], 0, 0),
            dag_id="dag1",
        )

    def test_returns_early_when_nothing_to_vectorize(self):
        with patch.dict(
            mod.FUNC_MAP_EMBEDDING,
            {"md_ia_lista_documentos_vetorizaveis": MagicMock(return_value=[])},
        ):
            mod.trigger_embedding.function(
                lista_func_name="md_ia_lista_documentos_vetorizaveis",
                check_queue_result=([], 5, 10),
                dag_id="dag1",
            )

    def test_triggers_dag_for_found_documents(self):
        fake_lista_func = MagicMock(side_effect=[["1", "2"], []])

        with patch.dict(
            mod.FUNC_MAP_EMBEDDING,
            {"md_ia_lista_documentos_vetorizaveis": fake_lista_func},
        ), patch.object(mod, "AirflowDagTrigger") as mock_trigger_cls, patch.object(
            mod.asyncio, "run"
        ) as mock_run:
            mod.trigger_embedding.function(
                lista_func_name="md_ia_lista_documentos_vetorizaveis",
                check_queue_result=([], 1, 2),
                dag_id="dag1",
            )

        mock_trigger_cls.assert_called_once()
        mock_run.assert_called_once()


class TestDagIsDefined:
    def test_dag_documents_embedding_defined(self):
        assert mod.dag_documents_embedding.dag_id == "documents_update_embedding"
