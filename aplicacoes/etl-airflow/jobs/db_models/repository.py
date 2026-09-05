"""repository module."""

from jobs.db_models.app_tables import Base_pg
from jobs.db_models.async_db_connection import AsyncDbConnector
from jobs.envs import (
    CONN_STRING_APP_DB,
)

_app_db: AsyncDbConnector | None = None


def get_app_db() -> AsyncDbConnector:
    """Retorna a instância global do AsyncDbConnector do banco da aplicação.

    Lazy pra não abrir conexão real no import (mesmo padrão de
    ``embedding.get_embeddings_db_connector``).

    Returns:
        AsyncDbConnector: Conector para o banco de dados da aplicação.
    """
    global _app_db
    if _app_db is None:
        _app_db = AsyncDbConnector(CONN_STRING_APP_DB, base=Base_pg)
    return _app_db
