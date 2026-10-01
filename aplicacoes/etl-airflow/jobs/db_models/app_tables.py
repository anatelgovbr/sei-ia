"""app_tables module."""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base_pg = declarative_base()


class QueueUpdateMlt(Base_pg):
    __tablename__ = "queue_update_mlt"
    __table_args__ = (
        Index(
            "idx_id_protocolo_update_status",
            "id_protocolo",
            "update_status",
            unique=True,
        ),
    )

    id_tipo_procedimento = Column(BigInteger)
    id_protocolo = Column(String, primary_key=True)
    created_at = Column(DateTime(timezone=True))
    dt_update = Column(DateTime(timezone=True))
    update_status = Column(String(50))
    priority = Column(BigInteger)


class LogUpdateMlt(Base_pg):
    __tablename__ = "log_update_mlt"
    id = Column(BigInteger, autoincrement=True, primary_key=True)
    id_tipo_procedimento = Column(BigInteger)
    id_protocolo = Column(String(100))
    created_at = Column(DateTime())
    dt_update = Column(DateTime())
    update_status = Column(String(50))
    priority = Column(BigInteger)


class CountDocumentTokens(Base_pg):
    __tablename__ = "count_document_tokens"
    id_protocolo = Column(String, primary_key=True)
    id_documento = Column(String, primary_key=True)
    id_serie = Column(String)
    id_tipo_procedimento = Column(String)
    sta_documento = Column(String)
    token_count = Column(BigInteger)
    word_count = Column(BigInteger)


class ConfigMltFieldsWeights(Base_pg):
    __tablename__ = "config_mlt_fields_weights"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    weights = Column(JSON, nullable=False)
    created_on = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
