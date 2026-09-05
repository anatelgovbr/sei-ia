"""Tests for jobs/dags/dag_objects/mlt_etl_process/dag_mlt_cache_invalidation.py."""

from unittest.mock import AsyncMock, MagicMock, patch

from jobs.dags.dag_objects.mlt_etl_process import (
    dag_mlt_cache_invalidation as mod,
)


class TestDropCanceledProcessesFromSolr:
    def test_stops_when_no_more_items(self):
        with patch.object(
            mod.sei_client,
            "md_ia_lista_processos_indexaveis_cancelados",
            return_value=([], 0),
        ), patch.object(mod.SolrHandlers, "drop_by_field") as mock_drop:
            result = mod.drop_canceled_processes_from_solr.function(
                batch_size=10, solr_url="http://solr", solr_core="core", auth=None
            )

        assert result is True
        mock_drop.assert_not_called()

    def test_removes_batch_and_reports_status(self):
        with patch.object(
            mod.sei_client,
            "md_ia_lista_processos_indexaveis_cancelados",
            side_effect=[(["1", "2"], 2), ([], 2)],
        ), patch.object(mod.SolrHandlers, "drop_by_field") as mock_drop, patch.object(
            mod.sei_client,
            "md_ia_remove_processos_indexaveis_cancelados_async",
            new=AsyncMock(return_value=None),
        ):
            result = mod.drop_canceled_processes_from_solr.function(
                batch_size=10, solr_url="http://solr", solr_core="core", auth=None
            )

        assert result is True
        mock_drop.assert_called_once()


class TestDropCanceledDocumentsAndEmbeddings:
    def test_stops_when_no_more_items(self):
        with patch.object(
            mod.sei_client,
            "md_ia_lista_documentos_indexaveis_cancelados",
            return_value=([], 0),
        ):
            result = mod.drop_canceled_documents_and_embeddings.function(
                batch_size=10, solr_url="http://solr", solr_core="core", auth=None
            )

        assert result is True

    def test_removes_batch_solr_embeddings_and_cache(self):
        with patch.object(
            mod.sei_client,
            "md_ia_lista_documentos_indexaveis_cancelados",
            side_effect=[(["1"], 1), ([], 1)],
        ), patch.object(mod.SolrHandlers, "drop_by_field") as mock_drop, patch.object(
            mod, "delete_embeddings_by_document_ids", new=AsyncMock(return_value=1)
        ), patch.object(
            mod, "invalidate_document_cache", new=AsyncMock(return_value=1)
        ), patch.object(
            mod.sei_client,
            "md_ia_remove_documentos_indexaveis_cancelados_async",
            new=AsyncMock(return_value=None),
        ):
            result = mod.drop_canceled_documents_and_embeddings.function(
                batch_size=10, solr_url="http://solr", solr_core="core", auth=None
            )

        assert result is True
        mock_drop.assert_called_once()

    def test_continues_when_embedding_deletion_fails(self):
        with patch.object(
            mod.sei_client,
            "md_ia_lista_documentos_indexaveis_cancelados",
            side_effect=[(["1"], 1), ([], 1)],
        ), patch.object(mod.SolrHandlers, "drop_by_field"), patch.object(
            mod,
            "delete_embeddings_by_document_ids",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ), patch.object(
            mod, "invalidate_document_cache", new=AsyncMock(return_value=0)
        ), patch.object(
            mod.sei_client,
            "md_ia_remove_documentos_indexaveis_cancelados_async",
            new=AsyncMock(return_value=None),
        ):
            result = mod.drop_canceled_documents_and_embeddings.function(
                batch_size=10, solr_url="http://solr", solr_core="core", auth=None
            )

        assert result is True


class TestDagIsDefined:
    def test_dag_defined_with_expected_tasks(self):
        assert mod.dag.dag_id == "cache_invalidation"
