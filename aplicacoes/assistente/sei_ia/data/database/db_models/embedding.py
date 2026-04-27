"""Modulo de modelo de tabelas do banco de dados."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from sei_ia.configs.settings_config import settings
from sei_ia.data.database.db_instances import BasePgvector


class EmbeddingsTable(BasePgvector):
    """Modelo de dados para embeddings.

    Attributes:
    - chunk_id (int): ID do chunk associado ao embedding.
    - id_documento (int): ID do documento associado ao embedding.
    - id_procedimento (int): ID do procedimento associado ao embedding.
    - embedding (Vector): Vetor de embedding com dimensão configurável via EMBEDDING_DIMENSION.
    - start_position (int): Posição inicial do chunk no documento original.
    - finished_position (int): Posição final do chunk no documento original.
    - created_at (DateTime): Data e hora de criação do registro (padrão é a data e hora atual UTC).
    Nota: O texto do chunk não é armazenado na tabela. Use start_position e finished_position
    para recuperar o conteúdo do documento original via ChunkContentRetriever.
    """

    __tablename__ = settings.EMBEDDINGS_TABLE_NAME
    __table_args__ = {"schema": settings.DB_SEIIA_ASSISTENTE_SCHEMA}

    chunk_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_documento: Mapped[int] = mapped_column(Integer, primary_key=True)
    embedding: Mapped[Vector] = mapped_column(Vector(settings.EMBEDDING_DIMENSION))
    start_position: Mapped[int] = mapped_column(Integer)
    finished_position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
