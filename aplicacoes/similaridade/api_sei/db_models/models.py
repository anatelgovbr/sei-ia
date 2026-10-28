"""Handles recommendation requests to database."""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    Sequence,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class LogConsume(Base):
    """Modelo de dados para log de consumo de API."""

    __tablename__ = "log_consume"

    id = Column(Integer, primary_key=True, autoincrement=True)
    time_created = Column(DateTime(timezone=False), server_default=func.now())
    api_recomend_url = Column(Text, nullable=False)
    status_code = Column(Integer, nullable=False)
    id_protocol = Column(PG_ARRAY(BigInteger), nullable=False)
    id_user = Column(BigInteger, nullable=True)


class ProcessWeightedMLTRecommendation(Base):
    """Modelo de dados para processos recomendados."""

    __tablename__ = "process_weighted_mlt_recommendation"

    id_recommendation = Column(Integer, primary_key=True)
    id_protocolo = Column(String, nullable=False)
    id_user = Column(BigInteger, nullable=True)
    rows = Column(Integer, default=10)
    parsedquery_field = Column(String)
    id_field = Column(String, nullable=False)
    fq = Column(PG_ARRAY(String), nullable=True)
    debug = Column(Boolean, default=False)
    extraction_method = Column(String)
    recommendation = Column(JSON)
    created_at = Column(DateTime, default=func.now())
    requested_at = Column(DateTime)


class DocumentMLTRecommendation(Base):
    """Modelo de dados para documentos recomendados."""

    __tablename__ = "document_mlt_recommendation"

    id_recommendation = Column(BigInteger, primary_key=True, autoincrement=True)
    text = Column(String)
    list_id_doc = Column(PG_ARRAY(Integer))
    list_type_id_doc = Column(PG_ARRAY(Integer))
    rows = Column(Integer)
    include_citations = Column(Boolean)
    text_weight = Column(Float)
    normalized = Column(Boolean)
    fq = Column(PG_ARRAY(String))
    recommendation = Column(JSON)
    created_at = Column(DateTime, default=func.now())
    requested_at = Column(DateTime)
    id_user = Column(BigInteger, nullable=True)


class ConfigMltFieldsWeights(Base):
    __tablename__ = "config_mlt_fields_weights"

    id = Column(
        BigInteger, Sequence("config_mlt_fields_weights_id_seq"), primary_key=True
    )
    weights = Column(JSON, nullable=False)
    created_on = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
