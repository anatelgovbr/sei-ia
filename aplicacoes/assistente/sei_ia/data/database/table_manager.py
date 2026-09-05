"""Runtime DDL for the dynamic embeddings table."""

import logging

from sqlalchemy import Connection, text

from sei_ia.configs.settings_config import settings

logger = logging.getLogger(__name__)


class TableManager:
    """Create the dynamic embeddings table on a caller-owned connection."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self.schema = settings.DB_SEIIA_ASSISTENTE_SCHEMA
        self.embeddings_table_name = settings.EMBEDDINGS_TABLE_NAME
        self.embedding_dimension = settings.EMBEDDING_DIMENSION
        preparer = connection.dialect.identifier_preparer
        self._table = (
            f"{preparer.quote(self.schema)}."
            f"{preparer.quote(self.embeddings_table_name)}"
        )

    def create_embeddings_table(self) -> None:
        """Create the configured embeddings table without transaction control."""
        self.connection.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    chunk_id INTEGER NOT NULL,
                    id_documento INTEGER NOT NULL,
                    embedding vector({self.embedding_dimension}) NOT NULL,
                    start_position INTEGER NOT NULL,
                    finished_position INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chunk_id, id_documento)
                )
                """
            )
        )
        logger.info("Table %s.%s ensured", self.schema, self.embeddings_table_name)

    def ensure_embedding_dimension(self) -> None:
        """Add the configured typmod to legacy dimensionless vector columns."""
        column_type = self.connection.execute(
            text(
                """
                SELECT format_type(attribute.atttypid, attribute.atttypmod)
                FROM pg_attribute AS attribute
                JOIN pg_class AS relation ON relation.oid = attribute.attrelid
                JOIN pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = :schema
                  AND relation.relname = :table_name
                  AND attribute.attname = 'embedding'
                  AND NOT attribute.attisdropped
                """
            ),
            {
                "schema": self.schema,
                "table_name": self.embeddings_table_name,
            },
        ).scalar()
        expected_type = f"vector({self.embedding_dimension})"
        if column_type == expected_type:
            return
        if column_type != "vector":
            msg = (
                f"Coluna {self.schema}.{self.embeddings_table_name}.embedding "
                f"deveria ser {expected_type}, mas é {column_type!r}."
            )
            raise RuntimeError(msg)

        self.connection.execute(
            text(
                f"""
                ALTER TABLE {self._table}
                ALTER COLUMN embedding
                TYPE vector({self.embedding_dimension})
                USING embedding::vector({self.embedding_dimension})
                """
            )
        )
        logger.info(
            "Column %s.%s.embedding migrated to vector(%d)",
            self.schema,
            self.embeddings_table_name,
            self.embedding_dimension,
        )

    def ensure_indexes(self) -> None:
        """Ensure both embeddings indexes even when ORM created the table."""
        preparer = self.connection.dialect.identifier_preparer
        document_index = preparer.quote(
            f"idx_{self.embeddings_table_name}_id_documento"
        )
        embedding_index = preparer.quote(f"idx_{self.embeddings_table_name}_embedding")
        self.connection.execute(
            text(
                f"""
                CREATE INDEX IF NOT EXISTS {document_index}
                ON {self._table}(id_documento)
                """
            )
        )
        self.connection.execute(
            text(
                f"""
                CREATE INDEX IF NOT EXISTS {embedding_index}
                ON {self._table}
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """
            )
        )
        logger.info(
            "Indexes for %s.%s ensured", self.schema, self.embeddings_table_name
        )

    def check_table_exists(self, table_name: str | None = None) -> bool:
        """Return whether the configured schema contains the target table."""
        target_table = table_name or self.embeddings_table_name
        return bool(
            self.connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = :schema
                          AND table_name = :table_name
                    )
                    """
                ),
                {"schema": self.schema, "table_name": target_table},
            ).scalar()
        )

    def initialize_all_tables(self) -> None:
        """Ensure the embeddings table and indexes on the supplied connection."""
        if not self.check_table_exists():
            self.create_embeddings_table()
        else:
            self.ensure_embedding_dimension()
        self.ensure_indexes()
