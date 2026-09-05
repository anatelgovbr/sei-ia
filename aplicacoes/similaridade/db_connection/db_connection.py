"""Shared SQLAlchemy connector used by similaridade."""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool


class Base(DeclarativeBase):
    """Fallback base when a project-specific base is not provided."""


class DBConnector:
    """Thin wrapper around SQLAlchemy used by the legacy similarity services."""

    def __init__(
        self,
        connection_string: str | None,
        schema: str,
        base: type[DeclarativeBase] = Base,
        pool_size: int = 5,
        max_overflow: int = 10,
    ) -> None:
        self.connection_string = connection_string
        self.schema = schema
        self.base = base
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.engine = self.connect()

    def connect(self) -> Any:
        """Create a pooled SQLAlchemy engine."""
        if not self.connection_string:
            raise ValueError("CONN_STRING_APP_DB nao configurada.")

        try:
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
            masked = self.hide_pwd(self.connection_string)
            logging.exception("Falha ao conectar no banco relacional.")
            raise ValueError(
                f"Banco relacional indisponivel. CONNECTION_STRING: {masked}"
            ) from exc

        return engine

    def hide_pwd(self, connection_string: str) -> str:
        """Mask the password in a connection string."""
        return re.sub(r"(:)([^:@]+)(@)", r"\1****\3", connection_string)

    def get_session(self) -> Session:
        """Return a new SQLAlchemy session."""
        self.base.metadata.create_all(self.engine)
        session_maker = sessionmaker(bind=self.engine)
        return session_maker()

    def execute(self, sql: str) -> None:
        """Execute a SQL statement and commit the transaction."""
        session = self.get_session()
        try:
            session.execute(text(sql))
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            logging.exception("Falha ao executar SQL.")
            raise SQLAlchemyError("Failed to execute query.") from exc
        finally:
            session.close()

    def execute_query(self, sql: str) -> list[Any]:
        """Execute a query and return all rows."""
        session = self.get_session()
        try:
            return list(session.execute(text(sql)).fetchall())
        except SQLAlchemyError as exc:
            session.rollback()
            logging.exception("Falha ao executar consulta.")
            raise ValueError(
                "Erro interno do servidor ao executar a consulta."
            ) from exc
        finally:
            session.close()

    def execute_query_one(self, sql: str) -> Any | None:
        """Execute a query and return the first row."""
        session = self.get_session()
        try:
            return session.execute(text(sql)).first()
        except SQLAlchemyError as exc:
            session.rollback()
            logging.exception("Falha ao executar consulta unitária.")
            raise SQLAlchemyError("Failed to execute query.") from exc
        finally:
            session.close()

    def get_dataframe(self, sql: str) -> pd.DataFrame:
        """Execute a query and normalize the result into a DataFrame."""
        rows = self.execute_query(sql)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([row._asdict() for row in rows])

    def add(
        self,
        obj: Any,
        *,
        overwrite: bool = False,
        primary_key_field: str = "id",
    ) -> Any:
        """Persist one ORM object."""
        session = self.get_session()
        try:
            if overwrite:
                primary_keys = obj.__table__.primary_key.columns.keys()
                filters = {key: getattr(obj, key) for key in primary_keys}
                existing_row = session.query(obj.__class__).filter_by(**filters).first()
                if existing_row:
                    session.delete(existing_row)
                    session.commit()

            session.add(obj)
            session.commit()
            session.refresh(obj)
            if primary_key_field and hasattr(obj, primary_key_field):
                logging.info(
                    "Objeto inserido no banco: %s",
                    getattr(obj, primary_key_field),
                )
            return obj
        except SQLAlchemyError as exc:
            session.rollback()
            logging.exception("Falha ao adicionar objeto.")
            raise SQLAlchemyError("Failed to add object to the database.") from exc
        finally:
            session.close()

    def add_all(self, objs: list[Any]) -> bool:
        """Persist a list of ORM objects."""
        session = self.get_session()
        try:
            session.add_all(objs)
            session.commit()
            return True
        except SQLAlchemyError as exc:
            session.rollback()
            logging.exception("Falha ao adicionar objetos.")
            raise SQLAlchemyError("Failed to add objects to the database.") from exc
        finally:
            session.close()

    def test_connection(self) -> bool:
        """Return True when the database answers a trivial query."""
        try:
            return self.execute_query_one("SELECT 1") is not None
        except (SQLAlchemyError, ValueError):
            return False
