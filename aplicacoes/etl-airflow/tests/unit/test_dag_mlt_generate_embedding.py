"""Tests for jobs/dags/dag_objects/mlt_etl_process/dag_mlt_generate_embedding.py."""

from unittest.mock import AsyncMock, MagicMock, patch

from jobs.dags.dag_objects.mlt_etl_process import (
    dag_mlt_generate_embedding as mod,
)


def _dag_run(conf):
    dag_run = MagicMock()
    dag_run.conf = conf
    return dag_run


class TestGenerateEmbeddingsForBatch:
    def test_returns_early_when_slot_list_empty(self):
        mod.generate_embeddings_for_batch.function(dag_run=_dag_run({}))

    def test_returns_early_when_slot_list_none(self):
        mod.generate_embeddings_for_batch.function(
            dag_run=_dag_run({"slot_list": None})
        )

    def test_processes_batch_and_updates_status(self):
        fake_result = {
            "status": "processed",
            "processed_count": 1,
            "skipped_count": 1,
            "embeddings": [{"id_documento": "1", "chunks_count": 3}],
            "skipped_ids": ["2"],
            "no_content_ids": ["3"],
        }

        with patch.object(
            mod, "generate_embeddings_for_documents", new=AsyncMock(return_value=fake_result)
        ), patch.object(
            mod.sei_client,
            "md_ia_atualiza_documentos_vetorizaveis_async",
            new=AsyncMock(return_value=True),
        ):
            mod.generate_embeddings_for_batch.function(
                dag_run=_dag_run({"slot_list": ["1", "2", "3"]})
            )

    def test_reraises_on_service_error(self):
        with patch.object(
            mod,
            "generate_embeddings_for_documents",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            try:
                mod.generate_embeddings_for_batch.function(
                    dag_run=_dag_run({"slot_list": ["1"]})
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("expected RuntimeError to propagate")


class TestDagIsDefined:
    def test_dag_defined(self):
        assert mod.dag.dag_id == "documents_embedding_generation"
