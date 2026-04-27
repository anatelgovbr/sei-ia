"""Module for managing database tables creation and validation."""

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from sei_ia.configs.settings_config import settings
from sei_ia.data.database.async_db_connection import AsyncDbConnector

logger = logging.getLogger(__name__)


class TableManager:
    """Manager for database tables creation and validation."""

    def __init__(self, db_connector: AsyncDbConnector):
        """Initialize the TableManager.

        Args:
            db_connector: Database connector instance
        """
        self.db = db_connector
        self.schema = settings.DB_SEIIA_ASSISTENTE_SCHEMA
        self.embeddings_table_name = settings.EMBEDDINGS_TABLE_NAME
        self.full_table_name = f"{self.schema}.{self.embeddings_table_name}"

    def create_embeddings_table(self) -> bool:
        """Create the embeddings table if it doesn't exist.

        Returns:
            bool: True if table was created or already exists, False on error
        """
        try:
            # Get embedding dimensions based on model
            embedding_dim = self._get_embedding_dimensions()

            # Create schema if not exists
            create_schema_sql = f"CREATE SCHEMA IF NOT EXISTS {self.schema};"

            # Create pgvector extension if not exists
            create_extension_sql = "CREATE EXTENSION IF NOT EXISTS vector;"

            # Create table SQL with full schema qualification
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.full_table_name} (
                chunk_id INTEGER NOT NULL,
                id_documento INTEGER NOT NULL,
                embedding vector({embedding_dim}) NOT NULL,
                start_position INTEGER NOT NULL,
                finished_position INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chunk_id, id_documento)
            );
            """

            # Create indexes for better performance
            create_indexes_sql = f"""
            CREATE INDEX IF NOT EXISTS idx_{self.embeddings_table_name}_id_documento
                ON {self.full_table_name}(id_documento);
            CREATE INDEX IF NOT EXISTS idx_{self.embeddings_table_name}_embedding
                ON {self.full_table_name} USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """

            session = self.db.get_session()
            try:
                # Create schema
                session.execute(text(create_schema_sql))
                session.commit()
                logger.info(f"Schema {self.schema} created or already exists")

                # Create extension
                session.execute(text(create_extension_sql))
                session.commit()
                logger.info("pgvector extension created or already exists")

                # Create table
                session.execute(text(create_table_sql))
                session.commit()
                logger.info(f"Table {self.full_table_name} created or already exists")

                # Create indexes
                for index_sql in create_indexes_sql.strip().split(";"):
                    if index_sql.strip():
                        session.execute(text(index_sql))
                session.commit()
                logger.info(
                    f"Indexes for {self.full_table_name} created or already exist"
                )

                return True

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error creating embeddings table: {e}")
                return False
            finally:
                session.close()

        except Exception as e:
            logger.error(f"Unexpected error creating embeddings table: {e}")
            return False

    def _get_embedding_dimensions(self) -> int:
        """Get embedding dimensions based on the model.

        Returns:
            int: Number of dimensions for the embedding vector
        """
        model_name = settings.EMBEDDING_MODEL.lower()

        # Check if table name contains dimension info (e.g., text_embedding_3_small_1256_50)
        # The format is: model_chunksize_overlap, where 1256 might be chunk size, not dimension

        # OpenAI models dimensions
        if "text-embedding-3-small" in model_name:
            return 1536
        elif "text-embedding-3-large" in model_name:
            return 3072
        elif "text-embedding-ada-002" in model_name:
            return 1536
        else:
            # Default dimension
            logger.warning(
                f"Unknown embedding model: {model_name}, using default dimension 1536"
            )
            return 1536

    def check_table_exists(self, table_name: str | None = None) -> bool:
        """Check if a table exists in the database.

        Args:
            table_name: Name of the table to check. If None, checks embeddings table.

        Returns:
            bool: True if table exists, False otherwise
        """
        if table_name is None:
            table_name = self.embeddings_table_name

        check_sql = f"""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = '{self.schema}'
            AND table_name = '{table_name}'
        );
        """

        try:
            session = self.db.get_session()
            try:
                result = session.execute(text(check_sql)).scalar()
                return bool(result)
            finally:
                session.close()
        except SQLAlchemyError as e:
            logger.error(f"Error checking if table {table_name} exists: {e}")
            return False

    def initialize_all_tables(self) -> bool:
        """Initialize all required tables for the application.

        Returns:
            bool: True if all tables were initialized successfully, False otherwise
        """
        try:
            # Check and create embeddings table
            if not self.check_table_exists():
                logger.info(
                    f"Table {self.embeddings_table_name} does not exist. Creating..."
                )
                if not self.create_embeddings_table():
                    logger.error(f"Failed to create table {self.embeddings_table_name}")
                    return False
                logger.info(f"Table {self.embeddings_table_name} created successfully")
            else:
                logger.info(f"Table {self.embeddings_table_name} already exists")

            # Add other tables initialization here if needed

            return True

        except Exception as e:
            logger.error(f"Error initializing tables: {e}")
            return False


async def initialize_database_tables(db_connector: AsyncDbConnector) -> bool:
    """Initialize all database tables asynchronously.

    Args:
        db_connector: Database connector instance

    Returns:
        bool: True if all tables were initialized successfully, False otherwise
    """
    try:
        table_manager = TableManager(db_connector)
        result = table_manager.initialize_all_tables()

        if result:
            logger.info("All database tables initialized successfully")
        else:
            logger.error("Failed to initialize some database tables")

        return result

    except Exception as e:
        logger.error(f"Error in async table initialization: {e}")
        return False
