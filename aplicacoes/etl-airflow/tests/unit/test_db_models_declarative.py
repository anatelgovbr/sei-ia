"""Tests for the SQLAlchemy declarative models in jobs/db_models.

app_tables.py and embedding.py only declare table metadata at import time
(no eager DB connection) — importing them is enough to exercise the class
bodies. get_embeddings_db_connector() is lazy (only connects when called),
so we patch AsyncDbConnector to avoid a real Postgres connection attempt.
"""

from unittest.mock import patch

from jobs.db_models.app_tables import (
    Base_pg,
    ConfigMltFieldsWeights,
    CountDocumentTokens,
    LogUpdateMlt,
    QueueUpdateMlt,
)
from jobs.db_models.embedding import (
    EmbeddingsTable,
    get_embeddings_db_connector,
)
import jobs.db_models.embedding as embedding_module


def test_declarative_tables_have_expected_names():
    assert QueueUpdateMlt.__tablename__ == "queue_update_mlt"
    assert LogUpdateMlt.__tablename__ == "log_update_mlt"
    assert CountDocumentTokens.__tablename__ == "count_document_tokens"
    assert ConfigMltFieldsWeights.__tablename__ == "config_mlt_fields_weights"
    assert QueueUpdateMlt.metadata is Base_pg.metadata


def test_embeddings_table_name_matches_configured_table():
    assert EmbeddingsTable.__table__.name == embedding_module.EMBEDDINGS_TABLE_NAME


def test_get_embeddings_db_connector_builds_singleton():
    embedding_module._embeddings_db_connector = None
    with patch("jobs.db_models.embedding.AsyncDbConnector") as mock_connector_cls:
        mock_connector_cls.return_value = "connector-instance"

        first = get_embeddings_db_connector()
        second = get_embeddings_db_connector()

        assert first == "connector-instance"
        assert second == "connector-instance"
        mock_connector_cls.assert_called_once()

    embedding_module._embeddings_db_connector = None
