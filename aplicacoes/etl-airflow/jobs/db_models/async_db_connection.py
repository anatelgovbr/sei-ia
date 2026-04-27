"""Module for asynchronous PostgreSQL database connection and gateway status management."""

import asyncio
import logging
import re
from typing import TYPE_CHECKING

import asyncpg
import pandas as pd
from asyncpg.pool import Pool
from sqlalchemy import Table, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from asyncpg.pool import Pool

logger = logging.getLogger(__name__)


class AsyncDbQueryError(Exception):
    """Custom exception for async database query errors."""


class AsyncDbConnector:
    """Asynchronous database connector for PostgreSQL using asyncpg."""

    def __init__(
        self,
        conn_str: str,
        schema: str = "public",
        base: DeclarativeMeta | None = None,
        pool_size: int = 5,
        max_overflow: int = 10,
    ) -> None:
        """Initialize the AsyncDbConnector with no connection pool.

        Args:
            conn_str (str): Connection string for the database.
            schema (str): Database schema name. Defaults to "public".
            base: SQLAlchemy declarative base. Defaults to None.
            pool_size (int): Size of the connection pool. Defaults to 5.
            max_overflow (int): Maximum overflow connections. Defaults to 10.
        """
        self.pool: Pool | None = None
        self._pool_lock = asyncio.Lock()
        self.conn_str = conn_str
        self.schema = schema
        self.base = base
        self.pool_size = pool_size
        self.max_overflow = max_overflow

        # Criando também engine SQLAlchemy para compatibilidade com DBConnector
        try:
            self.engine = create_engine(
                self.conn_str,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_recycle=360,
                pool_pre_ping=True,
            )
            if self.base:
                self.base.metadata.create_all(self.engine, checkfirst=True)
            logger.info("Database engine created successfully.")
        except SQLAlchemyError as e:
            logger.exception("Failed to connect to the database.")
            masked_connection_string = self.hide_password(self.conn_str)
            logger.debug(f"Connection string used: {masked_connection_string}")
            msg = f"Banco relacional indisponível\nCONNECTION_STRING: {masked_connection_string}"
            raise SQLAlchemyError(msg) from e

    def hide_password(self, connection_string: str) -> str:
        """Usando uma expressão regular para substituir a senha."""
        return re.sub(r"(:)([^:@]+)(@)", r"\1****\3", connection_string)

    async def connect(self) -> "AsyncDbConnector":
        """Asynchronously connect to PostgreSQL and create a connection pool."""
        if self.pool is not None:
            return self

        async with self._pool_lock:
            if self.pool is None:
                self.pool = await asyncpg.create_pool(
                    self.conn_str,
                    min_size=2,
                    max_size=self.pool_size + self.max_overflow,
                )
        return self

    async def close(self) -> None:
        """Close the connection pool and dispose of the SQLAlchemy engine."""
        # Dispose SQLAlchemy engine primeiro (usado para sync operations)
        if self.engine:
            self.engine.dispose()
            logger.info("SQLAlchemy engine disposed successfully")

        # Fechar pool asyncpg apenas se não houver mais tasks usando
        # Em ambientes de teste/desenvolvimento, pode haver tasks pendentes
        if self.pool:
            try:
                # Aguardar período maior para tasks pendentes completarem
                # Isso evita "pool is closing" e "protocol state" errors
                logger.debug(
                    "Aguardando tasks pendentes completarem antes de fechar pool..."
                )
                await asyncio.sleep(2.0)
                await self.pool.close()
                self.pool = None
                logger.info("AsyncPG pool closed successfully")
            except Exception as e:
                logger.warning(
                    f"Erro ao fechar pool asyncpg (tasks ainda em execução): {e}"
                )

    def get_session(self) -> Session:
        """Obtém uma sessão de banco de dados compatível com SQLAlchemy.

        Returns:
            sessionmaker: Sessão do SQLAlchemy.

        Raises:
            SQLAlchemyError: Se houver um erro ao obter a sessão.
        """
        try:
            session_maker = sessionmaker(bind=self.engine)
            logger.debug("Criando a sessão com o BD")
            return session_maker()
        except SQLAlchemyError as e:
            logger.exception("Failed to retrieve the session.")
            msg = "Failed to retrieve the record."
            raise SQLAlchemyError(msg) from e

    def add(
        self, obj: Table, *, returns_obj: bool = False, overwrite: bool = False
    ) -> Table | bool:
        """Adiciona um objeto ao banco de dados.

        Args:
            obj (Table): Objeto a ser adicionado ao banco de dados.
            returns_obj(bool): se o método retorna um objeto ou não.
            overwrite (bool, optional): Se True, remove o objeto do banco de
                dados caso ele já exista. Defaults to False.

        Returns:
            Table: O objeto adicionado ou True para sucesso.

        Raises:
            SQLAlchemyError: Se houver um erro ao adicionar o objeto.
        """
        session = self.get_session()
        try:
            logger.debug("Adicionando um objeto ao banco de dados.")
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
            logger.debug("Objeto inserido no banco")
        except SQLAlchemyError as e:
            session.rollback()
            logger.exception("Failed to add object to the database.")
            msg = "Failed to add object to the database."
            raise SQLAlchemyError(msg) from e
        else:
            if returns_obj:
                return obj
            return True
        finally:
            session.close()

    def add_all(
        self, objs: list[Table], *, returns_objs: bool = False, overwrite: bool = False
    ) -> list[Table] | bool:
        """Adiciona uma lista de objetos ao banco de dados.

        Args:
            objs (list[Table]): Lista de objetos a serem adicionados ao banco de dados.
            returns_objs (bool): Se o método retorna os objetos ou não.
            overwrite (bool): Se True, remove os objetos existentes com as mesmas
                chaves primárias antes de inserir os novos. Defaults to False.

        Returns:
            list[Table] | bool: Lista de objetos adicionados se returns_objs for True,
                                caso contrário retorna True para sucesso.

        Raises:
            SQLAlchemyError: Se houver um erro ao adicionar os objetos.
        """
        session = self.get_session()

        try:
            logger.debug("Adicionando múltiplos objetos ao banco de dados.")
            for obj in objs:
                if overwrite:
                    primary_keys = obj.__table__.primary_key.columns.keys()
                    filters = {key: getattr(obj, key) for key in primary_keys}
                    existing_row = (
                        session.query(obj.__class__).filter_by(**filters).first()
                    )
                    if existing_row:
                        session.delete(existing_row)

                session.add(obj)
                session.flush()

            session.commit()
            logger.debug("Todos os objetos foram inseridos no banco de dados.")
        except SQLAlchemyError as e:
            session.rollback()
            logger.exception("Falha ao adicionar a lista de objetos ao banco de dados.")
            msg = "Failed to add objects to the database."
            raise SQLAlchemyError(msg) from e
        else:
            if returns_objs:
                return objs
            return True
        finally:
            session.close()

    def get(self, model: Table, primary_key: int | str) -> object | None:
        """Recupera um objeto do banco de dados pelo seu primary key.

        Args:
            model (Table): Modelo da tabela do objeto.
            primary_key (Union[int, str]): Chave primária do objeto.

        Returns:
            Optional[object]: Objeto recuperado do banco de dados.

        Raises:
            SQLAlchemyError: Se houver um erro ao recuperar o objeto.
        """
        session = self.get_session()
        try:
            logger.debug("Recuperando objeto do banco de dados pelo seu primary key")
            return session.query(model).get(primary_key)
        except SQLAlchemyError as e:
            session.rollback()
            logger.exception("Failed to retrieve the record.")
            msg = "Failed to retrieve the record."
            raise SQLAlchemyError(msg) from e
        finally:
            session.close()

    def execute_query(self, sql: str) -> list:
        """Executa uma consulta SQL e retorna todos os resultados.

        Args:
            sql (str): Consulta SQL a ser executada.

        Returns:
            List: Resultados da consulta.

        Raises:
            SQLAlchemyError: Se houver um erro ao executar a consulta.
        """
        if self.engine is None:
            raise SQLAlchemyError(
                detail=(
                    f"Banco relacional indisponível\nCONNECTION_STRING: {self.conn_str}"
                )
            )
        session = self.get_session()
        try:
            return session.execute(text(sql)).fetchall()
        except SQLAlchemyError as e:
            session.rollback()
            msg = f"Failed to execute select query. Query: {sql}"
            logger.exception(msg=msg)
            raise SQLAlchemyError(detail=msg) from e
        finally:
            session.close()

    async def execute_query_async(self, sql: str) -> list:
        """Executa uma consulta SQL de forma assíncrona e retorna todos os resultados.

        Args:
            sql (str): Consulta SQL a ser executada.

        Returns:
            List: Resultados da consulta.

        Raises:
            AsyncDbQueryError: Se houver um erro ao executar a consulta.
        """
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            try:
                return await conn.fetch(sql)
            except Exception as e:
                logger.exception(f"Failed to execute async query. Query: {sql}")
                msg = f"Failed to execute async query: {e!s}"
                raise AsyncDbQueryError(msg) from e

    def select(self, sql: str) -> pd.DataFrame:
        """Executa uma consulta SQL e retorna os resultados como um DataFrame.

        Args:
            sql (str): Consulta SQL a ser executada.

        Returns:
            pd.DataFrame: Resultados da consulta em um DataFrame.
        """
        logger.debug("Executando a query")
        session = self.get_session()
        try:
            result = session.execute(text(sql))
            columns = result.keys()
            res = result.fetchall()
        except SQLAlchemyError as e:
            session.rollback()
            logger.exception("Falha ao executar a consulta.")
            msg = "Falha ao executar a consulta."
            raise SQLAlchemyError(msg) from e
        else:
            return pd.DataFrame(res, columns=columns)
        finally:
            session.close()

    def test_connection(self) -> bool:
        """Testa a conexão com o banco de dados tentando executar uma simples consulta.

        Returns:
            bool: Retorna True se a conexão foi bem-sucedida, False caso contrário.
        """
        try:
            # Executa uma simples consulta para verificar a conexão
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            logger.exception("Failed to test connection")
            return False
        else:
            return True

    async def test_connection_async(self) -> bool:
        """Testa a conexão com o banco de dados assincronamente.

        Returns:
            bool: Retorna True se a conexão foi bem-sucedida, False caso contrário.
        """
        if not self.pool:
            try:
                await self.connect()
            except Exception:
                logger.exception("Failed to connect to database")
                return False

        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception:
            logger.exception("Failed to test async connection")
            return False
        else:
            return True

    async def add_async(
        self, obj: Table, *, returns_obj: bool = False, overwrite: bool = False
    ) -> Table | bool:
        """Adiciona um objeto ao banco de dados de forma assíncrona.

        Args:
            obj (Table): Objeto a ser adicionado ao banco de dados.
            returns_obj(bool): se o método retorna um objeto ou não.
            overwrite (bool, optional): Se True, remove o objeto do banco de
                dados caso ele já exista. Defaults to False.

        Returns:
            Table: O objeto adicionado ou True para sucesso.

        Raises:
            SQLAlchemyError: Se houver um erro ao adicionar o objeto.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self.add(obj, returns_obj=returns_obj, overwrite=overwrite)
        )

    async def add_all_async(
        self, objs: list[Table], *, returns_objs: bool = False, overwrite: bool = False
    ) -> list[Table] | bool:
        """Adiciona uma lista de objetos ao banco de dados de forma assíncrona.

        Args:
            objs (list[Table]): Lista de objetos a serem adicionados ao banco de dados.
            returns_objs (bool): Se o método retorna os objetos ou não.
            overwrite (bool): Se True, remove os objetos existentes com as mesmas
                chaves primárias antes de inserir os novos. Defaults to False.

        Returns:
            list[Table] | bool: Lista de objetos adicionados se returns_objs for True,
                                caso contrário retorna True para sucesso.

        Raises:
            SQLAlchemyError: Se houver um erro ao adicionar os objetos.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.add_all(objs, returns_objs=returns_objs, overwrite=overwrite),
        )

    async def get_async(self, model: Table, primary_key: int | str) -> object | None:
        """Recupera um objeto do banco de dados pelo seu primary key de forma assíncrona.

        Args:
            model (Table): Modelo da tabela do objeto.
            primary_key (Union[int, str]): Chave primária do objeto.

        Returns:
            Optional[object]: Objeto recuperado do banco de dados.

        Raises:
            SQLAlchemyError: Se houver um erro ao recuperar o objeto.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.get(model, primary_key))

    async def execute_query_sql(self, sql: str) -> list:
        """Executa uma consulta SQL de forma assíncrona (utilizando SQLAlchemy) e retorna todos os resultados.

        Args:
            sql (str): Consulta SQL a ser executada.

        Returns:
            List: Resultados da consulta.

        Raises:
            SQLAlchemyError: Se houver um erro ao executar a consulta.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.execute_query(sql))

    async def select_async(self, sql: str) -> pd.DataFrame:
        """Executa uma consulta SQL de forma assíncrona e retorna os resultados como um DataFrame.

        Args:
            sql (str): Consulta SQL a ser executada.

        Returns:
            pd.DataFrame: Resultados da consulta em um DataFrame.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.select(sql))

    def execute(self, sql: str) -> None:
        """Executa SQL sem retorno (INSERT, UPDATE, DELETE, DDL).

        Args:
            sql (str): Comando SQL a ser executado.

        Raises:
            SQLAlchemyError: Se houver um erro ao executar o comando.
        """
        session = self.get_session()
        try:
            session.execute(text(sql))
            session.commit()
            logger.debug("SQL executado com sucesso")
        except SQLAlchemyError:
            session.rollback()
            logger.exception(f"Falha ao executar SQL: {sql[:100]}...")
            raise
        finally:
            session.close()

    def execute_query_one(self, sql: str) -> dict | None:
        """Executa uma consulta SQL e retorna o primeiro resultado como dicionário.

        Args:
            sql (str): Consulta SQL a ser executada.

        Returns:
            dict | None: Primeira linha como dicionário ou None se não houver resultados.

        Raises:
            SQLAlchemyError: Se houver um erro ao executar a consulta.
        """
        session = self.get_session()
        try:
            result = session.execute(text(sql))
            row = result.fetchone()
            if row:
                return dict(row._mapping)  # noqa: SLF001
            return None
        except SQLAlchemyError:
            session.rollback()
            logger.exception(f"Falha ao executar query: {sql[:100]}...")
            raise
        finally:
            session.close()
