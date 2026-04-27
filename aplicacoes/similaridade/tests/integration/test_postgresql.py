import os
import pwd
import time
import unittest
import warnings

import docker
import sqlalchemy as sa
from sqlalchemy import exc
from sqlalchemy.orm import declarative_base

USER_HOST = pwd.getpwuid(os.getuid()).pw_name.replace("@", "")
TEST_POSTGRES_PORT = os.getenv("TEST_POSTGRES_PORT", 5432)
TEST_POSTGRES_SEI_DB_NAME = os.getenv("TEST_POSTGRES_SEI_DB_NAME", "sei_similaridade")
TEST_POSTGRES_ADDRESS = os.getenv(
    "TEST_POSTGRES_ADDRESS",
    f"postgresql://sei:seisimilaridade@localhost:{TEST_POSTGRES_PORT}/{TEST_POSTGRES_SEI_DB_NAME}",
)
TEST_POSTGRES_CONTAINER_NAME = os.getenv(
    "TEST_POSTGRES_CONTAINER_NAME", "tests-postgres"
)
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
TEST_POSTGRES_VERSION_MANAGER_DATA_PATH = os.path.abspath(
    os.getenv(
        "TEST_POSTGRES_VERSION_MANAGER_DATA_PATH",
        os.path.join(BASE_PATH, "data/postgres_version_manager.csv"),
    )
)

BASE_PATH = os.path.dirname(os.path.abspath(__file__))

Base = declarative_base()


def insert_from_dataframe(df, engine, table_name):
    """
    Inserts data from a DataFrame into a specified table.

    Args:
        df (pd.DataFrame): DataFrame containing the data.
        table_name (str): Name of the table to insert the data into.
    """
    try:
        df.to_sql(table_name, engine, if_exists="append", index=False)
        print(f"Data successfully inserted into {table_name}")
    except exc.SQLAlchemyError as e:
        warnings.warn(f"Failed to insert data into {table_name}: {e}")


def create_postgres_container():
    client = docker.from_env()
    container = client.containers.create(
        "ankane/pgvector:v0.5.0",
        name=f"{TEST_POSTGRES_CONTAINER_NAME}-{USER_HOST}",
        ports={"5432/tcp": TEST_POSTGRES_PORT},
        environment={
            "DB_SEIIA_USER": "sei",
            "DB_SEIIA_PWD": "seisimilaridade",
            "POSTGRES_DB": TEST_POSTGRES_SEI_DB_NAME,
        },
        network="test_similaridade",
        detach=True,
    )

    container.start()
    time.sleep(5)


def remove_postgres_container():
    client = docker.from_env()

    for container in client.containers.list(
        filters={"name": f"{TEST_POSTGRES_CONTAINER_NAME}-{USER_HOST}"}, all=True
    ):
        container.stop()
        container.remove()


def setup_database_postgres():
    remove_postgres_container()

    create_postgres_container()

    print("created database postgres")


def delete_database_postgres():
    remove_postgres_container()

    print("deleted database postgres")


def test_flow_postgresql():
    setup_database_postgres()


class TestConnection(unittest.TestCase):
    def setUp(self):
        setup_database_postgres()
        self.db_engine = sa.create_engine(TEST_POSTGRES_ADDRESS)

    def tearDown(self):
        self.db_engine.dispose()
        remove_postgres_container()

    def test_database_connection(self):
        connected = False
        try:
            with self.db_engine.connect():
                connected = True
        except exc.OperationalError as e:
            print(f"Erro de conexão: {e}")

        self.assertTrue(connected, "Não foi possível conectar ao banco de dados.")
