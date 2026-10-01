"""Conector simples de banco para o healthchecker."""

from __future__ import annotations

import logging
import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine.mock import MockConnection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool


class DBConnector:
    """Classe para conexao com banco de dados."""

    base = declarative_base()

    def __init__(
        self,
        connection_string: str,
        schema: str,
        base: declarative_base = base,
        airflow_conn: object | None = None,
        pool_size: int = 5,
        max_overflow: int = 10,
    ) -> None:
        self.connection_string = connection_string
        self.base = base
        self.schema = schema
        self.airflow_conn = airflow_conn
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.engine = self.connect()

    def connect(self) -> MockConnection | object | None:
        try:
            if self.airflow_conn:
                return self.airflow_conn

            engine = create_engine(
                self.connection_string,
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_recycle=360,
                pool_pre_ping=True,
            )
            self.base.metadata.create_all(engine)
        except SQLAlchemyError as exc:
            masked_connection_string = self.hide_pwd(self.connection_string)
            logging.exception("Falha ao conectar ao banco.")
            raise ValueError(
                f"Banco relacional indisponivel. CONNECTION_STRING: {masked_connection_string}"
            ) from exc
        return engine

    def hide_pwd(self, connection_string: str) -> str:
        return re.sub(r"(:)([^:@]+)(@)", r"\1****\3", connection_string)

    def get_session(self) -> sessionmaker:
        try:
            session_maker = sessionmaker(bind=self.engine)
            return session_maker()
        except SQLAlchemyError as exc:
            raise SQLAlchemyError("Falha ao obter sessao.") from exc

    def execute_query(self, sql: str) -> list:
        if self.engine is None:
            raise ValueError(
                f"Banco relacional indisponivel. CONNECTION_STRING: {self.connection_string}"
            )
        session = self.get_session()
        try:
            return session.execute(text(sql)).fetchall()
        except SQLAlchemyError as exc:
            session.rollback()
            logging.exception("Falha ao executar consulta: %s", sql)
            raise ValueError("Erro interno do servidor ao executar consulta.") from exc
        finally:
            session.close()
