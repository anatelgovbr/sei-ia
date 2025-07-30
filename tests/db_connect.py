"""Módulo de conexão com banco de dados."""

import logging
import re

import pandas as pd
from sqlalchemy import Table, create_engine, text
from sqlalchemy.engine.mock import MockConnection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

#from embedder.http_exceptions import HTTPException503

# logger = logging.get# logger(__name__)


class DBConnector:
    """Classe para conexão com os bancos de dados.

    Args:
        connection_string (str): String de conexão com o banco de dados.
        schema (str): Nome do schema do banco de dados.
        base (declarative_base, optional): Base declarativa do SQLAlchemy.
            Defaults to declarative_base().
        airflow_conn (optional): Conexão com o Airflow, se aplicável.
            Defaults to None.
    """

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
        """Inicializa o conector do banco de dados."""
        self.connection_string = connection_string
        self.base = base
        self.schema = schema
        self.airflow_conn = airflow_conn
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.engine = self.connect()

    def connect(self) -> MockConnection | object | None:
        """Conecta ao banco de dados.

        Returns:
            Union[MockConnection, Optional[object]]: Objeto de conexão do
                SQLAlchemy.

        Raises:
            HTTPException503: Se houver um erro ao conectar ao banco de dados.
        """
        try:
            if self.airflow_conn:
                logging.info("Using Airflow connection.")
                return self.airflow_conn

            logging.info("Creating database engine.")
            engine = create_engine(
                self.connection_string,
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_recycle=360,
                pool_pre_ping=True,
            )
            self.base.metadata.create_all(engine)
            logging.info("Database engine created successfully.")
        except SQLAlchemyError as e:
            logging.exception("Failed to connect to the database.")
            masked_connection_string = self.hide_pwd(self.connection_string)
            logging.debug(f"Connection string used: {masked_connection_string}")
            logging.error(e)
            raise ValueError(
                "Banco relacional indisponível\nCONNECTION_STRING:" f" {masked_connection_string}")
        else:
            return engine

    def hide_pwd(self, connection_string: str) -> str:
        """Usando uma expressão regular para substituir a senha."""
        return re.sub(r"(:)([^:@]+)(@)", r"\1****\3", connection_string)

    def get_session(self) -> sessionmaker:
        """Obtém uma sessão de banco de dados.

        Returns:
            sessionmaker: Sessão do SQLAlchemy.

        Raises:
            SQLAlchemyError: Se houver um erro ao obter a sessão.
        """
        try:
            session_maker = sessionmaker(bind=self.engine)
            return session_maker()
        except SQLAlchemyError as e:
            logging.exception("Failed to retrieve the session.")
            msg = "Failed to retrieve the record."
            raise SQLAlchemyError(msg) from e

    def execute(self, sql: str) -> None:
        """Executa uma consulta SQL.

        Args:
            sql (str): Consulta SQL a ser executada.

        Raises:
            SQLAlchemyError: Se houver um erro ao executar a consulta.
        """
        session = self.get_session()
        try:
            session.execute(text(sql))
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            logging.exception("Failed to execute query.")
            msg = "Failed to execute query."
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
            HTTPException503: Se houver um erro ao executar a consulta.
        """
        if self.engine is None:
            raise ValueError(
                "Banco relacional indisponível\nCONNECTION_STRING:" f" {self.connection_string}"
            )
        session = self.get_session()
        try:
            return session.execute(text(sql)).fetchall()
        except SQLAlchemyError as e:
            session.rollback()
            logging.exception(f"Failed to execute select query. Query: {sql}")
            raise ValueError("Erro interno do servidor ao executar a consulta.") from e
        finally:
            session.close()

    def execute_query_one(self, sql: str) -> object | None:
        """Executa uma consulta SQL e retorna o primeiro resultado.

        Args:
            sql (str): Consulta SQL a ser executada.

        Returns:
            Optional[object]: Primeiro resultado da consulta.

        Raises:
            SQLAlchemyError: Se houver um erro ao executar a consulta.
        """
        session = self.get_session()
        try:
            return session.execute(text(sql)).first()
        except SQLAlchemyError as e:
            session.rollback()
            logging.exception("Failed to execute query.")
            msg = "Failed to execute query."
            raise SQLAlchemyError(msg) from e
        finally:
            session.close()

    def execute_insert(self, sql: str) -> bool:
        """Executa uma consulta de inserção SQL.

        Args:
            sql (str): Consulta SQL a ser executada.

        Returns:
            bool: True se a inserção foi bem-sucedida.

        Raises:
            SQLAlchemyError: Se houver um erro ao executar a consulta.
        """
        session = self.get_session()
        try:
            session.execute(text(sql))
            session.commit()
            logging.info("Insert Successful!")
        except SQLAlchemyError as e:
            session.rollback()
            logging.exception("Failed to execute insert.")
            msg = "Failed to execute insert."
            raise SQLAlchemyError(msg) from e
        else:
            return True
        finally:
            session.close()

    def add(self, obj: Table, *, overwrite: bool = True, primary_key_field: str = "id") -> Table:
        """Adiciona um objeto ao banco de dados.

        Args:
            obj (Table): Objeto a ser adicionado ao banco de dados.
            overwrite (bool, optional): Se True, remove o objeto do banco de
                dados caso ele já exista. Defaults to True.
            primary_key_field (str, optional): O nome do campo chave primária

        Returns:
            Table: O objeto adicionado.

        Raises:
            SQLAlchemyError: Se houver um erro ao adicionar o objeto.
        """
        session = self.get_session()
        self.base.metadata.create_all(self.engine)
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
            if primary_key_field:
                logging.info(f"Objeto inserido no banco: {getattr(obj, primary_key_field)}")
        except SQLAlchemyError as e:
            session.rollback()
            logging.exception("Failed to add object to the database.")
            msg = "Failed to add object to the database."
            raise SQLAlchemyError(msg) from e
        else:
            return obj
        finally:
            session.close()

    def add_all(self, objs: list[Table]) -> bool:
        """Adiciona uma lista de objetos ao banco de dados.

        Args:
            objs (List[Table]): Lista de objetos a serem adicionados.

        Returns:
            bool: True se os objetos foram adicionados com sucesso.

        Raises:
            SQLAlchemyError: Se houver um erro ao adicionar os objetos.
        """
        session = self.get_session()
        try:
            session.add_all(objs)
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            logging.exception("Failed to add objects to the database.")
            msg = "Failed to add objects to the database."
            raise SQLAlchemyError(msg) from e
        else:
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
            return session.query(model).get(primary_key)
        except SQLAlchemyError as e:
            session.rollback()
            logging.exception("Failed to retrieve the record.")
            msg = "Failed to retrieve the record."
            raise SQLAlchemyError(msg) from e
        finally:
            session.close()

    def select(self, sql: str, *, return_dataframe: bool = True) -> pd.DataFrame:
        """Executa uma consulta SQL e retorna os resultados como um DataFrame.

        Args:
            sql (str): Consulta SQL a ser executada.
            return_dataframe (bool, optional): Se True, retorna os resultados em DFs

        Returns:
            pd.DataFrame: Resultados da consulta em um DataFrame.
        """
        self.base.metadata.create_all(self.engine)
        res = self.execute_query(sql)
        if len(res) > 0:
            res = [r._asdict() for r in res]
        if return_dataframe:
            return pd.DataFrame(res)
        return []

    def insert_replace(self, data: dict, table_model) -> None:
        """Insere dados em uma tabela, substituindo os dados existentes.

        Args:
            data (dict): Dados a serem inseridos.
            table_model (DeclarativeBase): Modelo da tabela.

        """
        session = self.get_session()
        try:
            table_name = table_model.__tablename__
            table = table_model.__table__

            columns = [c.name for c in table.columns]
            filtered_data = [{k: v for k, v in row.items() if k in columns} for row in data]

            temp_table_name = f"temp_{table_name}"
            temp_table = table_model.__table__.tometadata(self.base.metadata, name=temp_table_name)
            self.base.metadata.create_all(self.engine, tables=[temp_table])

            with self.engine.connect() as conn:
                conn.execute(temp_table.insert(), filtered_data)
                conn.commit()

            with self.engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
                conn.execute(text(f"ALTER TABLE {temp_table_name} RENAME TO {table_name}"))

            logging.info(f"Data successfully inserted into {table_name}")
        except SQLAlchemyError as e:
            error_message = f"Failed to insert data into {table_name}"
            logging.exception(error_message)
            raise SQLAlchemyError(error_message) from e
        finally:
            session.close()

    def insert_from_dataframe(self, df: pd.DataFrame, table_name: str, if_exists="append"):
        """Warning: Não recomendado ! Lento e gasta muita memoria.
        Insere dados de um DataFrame em uma tabela do banco de dados.

        Args:
            df (pd.DataFrame): DataFrame contendo os dados a serem inseridos.
            table_name (str): Nome da tabela onde os dados serão inseridos.
            if_exists (str): Ação a ser tomada se a tabela já existir.
                Pode ser 'append' ou 'replace'. Default é 'append'.

        Raises:
            SQLAlchemyError: Se houver um erro ao inserir os dados.
        """
        session = self.get_session()
        try:
            if if_exists == "replace":
                # Usa a lógica do método insert_replace
                temp_table_name = f"temp_{table_name}"
                temp_table = Table(temp_table_name, self.base.metadata, autoload_with=self.engine)

                # Insere os dados na tabela temporária
                df.to_sql(temp_table_name, self.engine, if_exists="replace", index=False)

                with self.engine.begin() as conn:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
                    conn.execute(text(f"ALTER TABLE {temp_table_name} RENAME TO {table_name}"))
            else:
                # Append diretamente à tabela existente
                df.to_sql(table_name, self.engine, if_exists="append", index=False)

            logging.info(f"Dados inseridos com sucesso na tabela {table_name}")
        except SQLAlchemyError as e:
            session.rollback()
            logging.error(f"Falha ao inserir dados na tabela {table_name}: {e}")
            raise SQLAlchemyError(f"Falha ao inserir dados na tabela {table_name}") from e
        finally:
            session.close()
