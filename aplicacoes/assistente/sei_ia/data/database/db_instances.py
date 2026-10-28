"""Modulo de instacias dos bancos de dados."""

from sqlalchemy import MetaData
from sqlalchemy.orm import declarative_base

from sei_ia.configs.settings_config import settings
from sei_ia.data.database.async_db_connection import AsyncDbConnector

metadata = MetaData(schema=settings.DB_SEIIA_ASSISTENTE_SCHEMA)
BasePgvector = declarative_base(metadata=metadata)


CONN_PGVECTOR_STRING = (
    f"postgresql://{settings.DB_SEIIA_USER}:{settings.DB_SEIIA_PWD}@"
    f"{settings.DB_SEIIA_HOST}:{settings.DB_SEIIA_PORT}/{settings.DB_SEIIA_ASSISTENTE}"
)

app_db_instance = AsyncDbConnector(
    CONN_PGVECTOR_STRING, schema=settings.DB_SEIIA_ASSISTENTE_SCHEMA, base=BasePgvector
)
