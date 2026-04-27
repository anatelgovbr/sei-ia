"""
Configuração isolada para testes unitários (unit2) - VERSÃO MELHORADA.

Esta versão USA sys.modules MAS com salvamento/restauração do estado original
para evitar interferência com tests/e2e.
"""

import os
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# IMPORTANTE: Definir variáveis de ambiente ANTES de qualquer import
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("SOLR_ADDRESS", "http://localhost:8983/solr")
os.environ.setdefault("SOLR_USER", "test_user")
os.environ.setdefault("SOLR_PASSWORD", "test_password")
os.environ.setdefault("DB_SEIIA_HOST", "localhost")
os.environ.setdefault("DB_SEIIA_PORT", "5432")
os.environ.setdefault("DB_SEIIA_USER", "test_user")
os.environ.setdefault("DB_SEIIA_PWD", "test_password")
os.environ.setdefault("ASSISTENTE_EMBEDDING_API_KEY", "test_embedding_key")
os.environ.setdefault("ASSISTENTE_EMBEDDING_ENDPOINT", "https://test.openai.azure.com/")
os.environ.setdefault("ASSISTENTE_API_KEY_STANDARD_MODEL", "test_standard_key")
os.environ.setdefault(
    "ASSISTENTE_ENDPOINT_STANDARD_MODEL", "https://test.openai.azure.com/"
)
os.environ.setdefault("ASSISTENTE_NAME_STANDARD_MODEL", "gpt-4")
os.environ.setdefault("ASSISTENTE_API_KEY_MINI_MODEL", "test_mini_key")
os.environ.setdefault(
    "ASSISTENTE_ENDPOINT_MINI_MODEL", "https://test.openai.azure.com/"
)
os.environ.setdefault("ASSISTENTE_NAME_MINI_MODEL", "gpt-4o-mini")
os.environ.setdefault("SEI_API_DB_ADDRESS", "http://localhost:8000")
os.environ.setdefault("SEI_API_DB_IDENTIFIER_SERVICE", "SeiApiService")


# ===========================
# SEÇÃO: SALVAMENTO DE ESTADO
# ===========================

# Salvar estado original de sys.modules ANTES de aplicar mocks
_original_modules: dict[str, Any] = {}
_modules_to_mock = [
    "sei_ia.data.database.async_db_connection",
    "sei_ia.data.database.db_instances",
]


def _save_original_modules():
    """Salva estado original dos módulos que vamos mockar."""
    for module_name in _modules_to_mock:
        if module_name in sys.modules:
            _original_modules[module_name] = sys.modules[module_name]


def _restore_original_modules():
    """Restaura estado original dos módulos."""
    for module_name in _modules_to_mock:
        if module_name in _original_modules:
            sys.modules[module_name] = _original_modules[module_name]
        elif module_name in sys.modules:
            del sys.modules[module_name]


# Salvar estado ANTES de aplicar mocks
_save_original_modules()


# ===========================
# SEÇÃO: MOCKS GLOBAIS (apenas para unit2)
# ===========================

# Mock db_instances ANTES de qualquer import que o use
mock_app_db = AsyncMock()
mock_app_db.select_async = AsyncMock(return_value=[])
mock_app_db.execute_async = AsyncMock(return_value=None)
mock_app_db.insert_async = AsyncMock(return_value=None)

sys.modules["sei_ia.data.database.db_instances"] = Mock()
sys.modules["sei_ia.data.database.db_instances"].app_db_instance = mock_app_db


# ===========================
# SEÇÃO: FIXTURES
# ===========================


@pytest.fixture(autouse=True)
def mock_async_db_connector():
    """
    Mock isolado do AsyncDbConnector para testes unitários.

    Este fixture é aplicado automaticamente a todos os testes neste diretório
    (autouse=True), mas usa context manager @patch para garantir isolamento.
    """
    with patch(
        "sei_ia.data.database.async_db_connection.AsyncDbConnector"
    ) as mock_class:
        mock_instance = AsyncMock()
        mock_class.return_value = mock_instance

        # Configurar métodos comuns
        mock_instance.select_async = AsyncMock(return_value=[])
        mock_instance.execute_async = AsyncMock(return_value=None)
        mock_instance.insert_async = AsyncMock(return_value=None)

        yield mock_instance


@pytest.fixture
def mock_db_select_result():
    """Fixture para mockar resultados de queries do banco."""
    import pandas as pd

    return pd.DataFrame([{"id": 1, "name": "test1"}, {"id": 2, "name": "test2"}])


@pytest.fixture
def mock_embedding_generator():
    """Mock do gerador de embeddings."""
    with patch("sei_ia.services.embedder.pipeline.embedding_generator") as mock:
        mock.generate = MagicMock(return_value=iter([[0.1] * 1536]))
        yield mock


@pytest.fixture
def mock_similarity_query():
    """Mock da função similarity_query."""
    with patch("sei_ia.agents.rag.similarity.similarity_query") as mock:

        async def async_return(*args, **kwargs):
            return ("texto formatado", {})

        mock.side_effect = async_return
        yield mock


@pytest.fixture
def mock_llm_call():
    """Mock de chamadas ao LLM."""
    with patch("sei_ia.services.llm_models.chat_workflow.chat_gpt") as mock:
        mock.return_value = {
            "choices": [{"message": {"content": "Resposta mockada do LLM"}}]
        }
        yield mock


# Fixtures compartilhadas (sem modificação)
@pytest.fixture
def mock_user_state():
    """Fixture para UserState mockado básico."""
    from tests.fixtures.mock_data import create_mock_user_state_direct_path

    return create_mock_user_state_direct_path()


@pytest.fixture
def mock_rag_user_state():
    """Fixture para UserState mockado para RAG."""
    from tests.fixtures.mock_data import create_mock_user_state_rag_enhanced

    return create_mock_user_state_rag_enhanced()


@pytest.fixture
def mock_chunks():
    """Fixture para chunks mockados."""
    from tests.fixtures.mock_data import create_mock_chunks

    return create_mock_chunks()


@pytest.fixture
def mock_questions():
    """Fixture para perguntas mockadas."""
    from tests.fixtures.mock_data import create_mock_questions

    return create_mock_questions()


@pytest.fixture
def mock_search_results():
    """Fixture para resultados de busca mockados."""
    from tests.fixtures.mock_data import create_mock_search_results

    return create_mock_search_results()


@pytest.fixture
def assert_helpers():
    """Fixture com helpers de assert."""
    from tests.utils.test_helpers import TestAssertions

    return TestAssertions


# Configuração de logging
@pytest.fixture(autouse=True)
def configure_test_logging():
    """Configura logging para não poluir output dos testes."""
    import logging

    logging.getLogger().setLevel(logging.WARNING)
    yield


# ===========================
# SEÇÃO: CLEANUP AO FINALIZAR SESSÃO
# ===========================


@pytest.fixture(scope="session", autouse=True)
def cleanup_at_end():
    """Restaura sys.modules ao estado original ao finalizar TODA a sessão de testes."""
    yield
    # Ao finalizar todos os testes unit2, restaurar estado original
    _restore_original_modules()
