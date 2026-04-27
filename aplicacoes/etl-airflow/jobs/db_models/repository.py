"""repository module."""

from jobs.db_models.app_tables import Base_pg
from jobs.db_models.async_db_connection import AsyncDbConnector
from jobs.envs import (
    CONN_STRING_APP_DB,
)

app_db = AsyncDbConnector(CONN_STRING_APP_DB, base=Base_pg)
