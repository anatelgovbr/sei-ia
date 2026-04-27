"""Modulo de modelo de tabelas de embeddings do banco de dados PostgreSQL compartilhado."""

from urllib.parse import quote

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Integer, MetaData, func
from sqlalchemy.orm import declarative_base

from jobs.db_models.async_db_connection import AsyncDbConnector
from jobs.envs import (
    DB_SEIIA_ASSISTENTE,
    DB_SEIIA_ASSISTENTE_SCHEMA,
    DB_SEIIA_HOST,
    DB_SEIIA_PORT,
    DB_SEIIA_PWD,
    DB_SEIIA_USER,
    EMBEDDINGS_TABLE_NAME,
)

# Criar Base para os modelos do PostgreSQL
metadata = MetaData(schema=DB_SEIIA_ASSISTENTE_SCHEMA)
BasePgvector = declarative_base(metadata=metadata)


class EmbeddingsTable(BasePgvector):
    """Modelo de dados para embeddings.

    Attributes:
    - chunk_id (int): ID do chunk associado ao embedding.
    - id_documento (int): ID do documento associado ao embedding.
    - embedding (Vector): Vetor de embedding.
    - start_position (int): Posição inicial do chunk no documento original.
    - finished_position (int): Posição final do chunk no documento original.
    - created_at (DateTime): Data e hora de criação do registro (padrão é a data e hora atual UTC).
    Nota: O texto do chunk não é armazenado na tabela. Use start_position e finished_position
    para recuperar o conteúdo do documento original.
    """

    __tablename__ = EMBEDDINGS_TABLE_NAME
    __table_args__ = {"schema": DB_SEIIA_ASSISTENTE_SCHEMA}

    chunk_id = Column(Integer, primary_key=True)
    id_documento = Column(Integer, primary_key=True)
    embedding = Column(Vector)
    start_position = Column(Integer)
    finished_position = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())


# Instância global do AsyncDbConnector para embeddings
_embeddings_db_connector: AsyncDbConnector | None = None


def get_embeddings_db_connector() -> AsyncDbConnector:
    """Retorna a instância global do AsyncDbConnector para embeddings.

    Returns:
        AsyncDbConnector: Conector para o banco de dados de embeddings.
    """
    global _embeddings_db_connector
    if _embeddings_db_connector is None:
        pwd_quoted = quote(DB_SEIIA_PWD) if DB_SEIIA_PWD else ""
        conn_str = (
            f"postgresql://{DB_SEIIA_USER}:{pwd_quoted}@"
            f"{DB_SEIIA_HOST}:{DB_SEIIA_PORT}/{DB_SEIIA_ASSISTENTE}"
        )
        _embeddings_db_connector = AsyncDbConnector(
            conn_str, schema=DB_SEIIA_ASSISTENTE_SCHEMA, base=BasePgvector
        )
    return _embeddings_db_connector
