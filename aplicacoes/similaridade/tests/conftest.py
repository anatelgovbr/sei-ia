"""Configuração compartilhada para tests/unit e tests/integration."""

import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("SOLR_ADDRESS", "http://localhost:8999")
os.environ.setdefault("SOLR_MLT_PROCESS_CORE", "test_dag_mlt_process")

# api_sei/db_models/db_instances.py cria app_db = DBConnector(...) no nível de
# módulo, e DBConnector.__init__ conecta ao Postgres imediatamente. Sem este mock,
# qualquer teste que importe (mesmo transitivamente) db_instances tentaria abrir
# uma conexão real já na coleta. Mesmo padrão usado em
# aplicacoes/assistente/tests/unit/conftest.py para app_db_instance.
sys.modules["api_sei.db_models.db_instances"] = MagicMock(app_db=MagicMock())
