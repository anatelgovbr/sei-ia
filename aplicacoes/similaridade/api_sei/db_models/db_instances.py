"""Instâncias da base de dados."""

# from api_sei.db_models.db_connect import DBConnector
from api_sei.db_models.models import Base
from api_sei.envs import (
    CONN_STRING_APP_DB,
)
from db_connection.db_connection import DBConnector

app_db = DBConnector(CONN_STRING_APP_DB, schema="", base=Base)
