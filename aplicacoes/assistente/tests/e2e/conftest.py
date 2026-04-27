# Definir variáveis de ambiente obrigatórias
import asyncio
import os
import sys
import warnings
from unittest.mock import MagicMock, patch

import pytest

# IMPORTANTE: Mock antecipado do AsyncDbConnector para evitar erro durante imports
# O db_instances.py cria app_db_instance no nível de módulo, o que causaria erro
# se tentasse conectar a um banco mockado que não existe
_mock_db_connector = MagicMock()
_mock_db_connector.return_value = MagicMock(
    pool=MagicMock(),
    engine=MagicMock(),
    session=MagicMock(),
)

# Aplicar patch antes de qualquer import que possa usar db_instances
sys.modules["sei_ia.data.database.async_db_connection"] = MagicMock()
sys.modules[
    "sei_ia.data.database.async_db_connection"
].AsyncDbConnector = _mock_db_connector

# Suprimir aviso de deprecação do SwigPyPacked
warnings.filterwarnings(
    "ignore",
    message="builtin type SwigPyPacked has no __module__ attribute",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore", category=DeprecationWarning, module=".*SwigPyPacked.*"
)

# Configurar variáveis de ambiente no nível de módulo
# IMPORTANTE: Deve definir TODAS as variáveis obrigatórias antes de qualquer import
# que instancie o Pydantic Settings (sei_ia.configs.settings_config.settings)
_should_mock = not any("cache_cleanup" in arg for arg in sys.argv)

if _should_mock:
    os.environ.update(
        {
            # Configurações da API SEI
            "SEI_API_DB_ADDRESS": "http://mock-sei-api:8000",
            "SEI_API_DB_IDENTIFIER_SERVICE": "mock-identifier",
            "ASSISTENTE_OUTPUT_TOKENS_THINK_MODEL": "50000",
            # Configurações do Solr (mock)
            "SOLR_ADDRESS": "http://mock-solr:8983/solr",
            "SOLR_USER": "mock-solr-user",
            "SOLR_PASSWORD": "mock-solr-password",
            # Configurações de Banco de Dados (mock)
            # IMPORTANTE: Essas variáveis são obrigatórias para o Pydantic Settings
            # O mock real da conexão é feito via fixture mock_environment usando patches
            "DB_SEIIA_HOST": "mock-db-host",
            "DB_SEIIA_PORT": "5432",
            "DB_SEIIA_USER": "mock-db-user",
            "DB_SEIIA_PWD": "mock-db-password",
            # Configurações de Embeddings (mock)
            "ASSISTENTE_EMBEDDING_API_KEY": "mock-embedding-api-key",
            "ASSISTENTE_EMBEDDING_ENDPOINT": "https://mock-embedding.openai.azure.com/",
            # Configurações do modelo Standard (mock)
            "ASSISTENTE_API_KEY_STANDARD_MODEL": "mock-standard-api-key",
            "ASSISTENTE_ENDPOINT_STANDARD_MODEL": "https://mock-standard.openai.azure.com/",
            "ASSISTENTE_NAME_STANDARD_MODEL": "gpt-4",
            # Configurações do modelo Mini (mock)
            "ASSISTENTE_API_KEY_MINI_MODEL": "mock-mini-api-key",
            "ASSISTENTE_ENDPOINT_MINI_MODEL": "https://mock-mini.openai.azure.com/",
            "ASSISTENTE_NAME_MINI_MODEL": "gpt-4-mini",
        }
    )


@pytest.fixture(autouse=True, scope="function")
def mock_environment(request):
    """
    Mock global das dependências externas para testes E2E.

    Nota: Não é aplicado a testes marcados com @pytest.mark.real_db,
    pois esses testes precisam de banco de dados real.
    """
    # Verificar se o teste está marcado com 'real_db'
    if "real_db" in request.keywords:
        # Não aplicar mocks para testes com banco real
        yield
        return

    # Mock do serviço de embeddings para evitar chamadas HTTP reais
    def mock_generate_embeddings(texts, *args, **kwargs):
        """Mock que retorna embeddings fake para qualquer texto."""
        import numpy as np

        # Retornar um embedding de dimensão 1536 (padrão do text-embedding-3-small)
        return [np.random.rand(1536).tolist() for _ in texts]

    # Mock para o SEIDBHandler - evita chamadas HTTP
    async def mock_fetch_metadata_procedimentos(*args, **kwargs):
        """Mock que retorna metadados fake para procedimentos."""
        return {}  # Retorna dict vazio, os metadados são opcionais

    async def mock_fetch_metadata_documentos(*args, **kwargs):
        """Mock que retorna metadados fake para documentos."""
        return {}  # Retorna dict vazio, os metadados são opcionais

    # Mock para get_model_config que adiciona campos esperados pelos testes
    def mock_get_model_config(model_type: str = "mini"):
        """Mock que retorna configuração completa do modelo incluindo campos legados."""
        from sei_ia.services.llm_models.get_model import (
            get_model_config as original_get_model_config,
        )

        # Pegar configuração original
        config = original_get_model_config(model_type)

        # Adicionar campos que faltam (para compatibilidade com código legado)
        model_configs_extra = {
            "standard": {
                "model_name": "gpt-4o",
                "max_ctx_len": 250_000,
                "max_output_tokens": 16_000,
            },
            "mini": {
                "model_name": "gpt-4o-mini",
                "max_ctx_len": 250_000,
                "max_output_tokens": 16_000,
            },
            "nano": {
                "model_name": "gpt-4o-mini",
                "max_ctx_len": 128_000,
                "max_output_tokens": 16_000,
            },
            "think": {
                "model_name": "o1",
                "max_ctx_len": 128_000,
                "max_output_tokens": 50_000,
            },
        }

        model_type_lower = model_type.lower()
        if model_type_lower in model_configs_extra:
            config.update(model_configs_extra[model_type_lower])

        return config

    with (
        patch("sei_ia.data.database.async_db_connection.AsyncDbConnector") as mock_db,
        patch("sei_ia.data.database.solr_handlers.create_solr_core") as mock_solr_core,
        patch(
            "sei_ia.services.embedder.providers.azure.AzureOpenAIEmbeddingProvider.generate_embeddings",
            side_effect=mock_generate_embeddings,
        ),
        patch(
            "sei_ia.data.etl.extract.metadata.fetch_procedimentos_metadata_batch",
            side_effect=mock_fetch_metadata_procedimentos,
        ),
        patch(
            "sei_ia.data.etl.extract.metadata.fetch_documentos_metadata_batch",
            side_effect=mock_fetch_metadata_documentos,
        ),
        patch(
            "sei_ia.routers.chat.get_model_config",
            side_effect=mock_get_model_config,
        ),
        patch(
            "sei_ia.routers.chat.model_response.get_model_config",
            side_effect=mock_get_model_config,
        ),
    ):
        # Configurar mocks
        mock_db.return_value = MagicMock()
        mock_solr_core.return_value = None

        yield


@pytest.fixture
def mock_solr_post():
    """Mock para chamadas Solr"""
    with patch("sei_ia.data.database.solr_handlers.SolrRequests.post") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def test_app():
    """Fixture para criar app de teste"""
    from sei_ia.main import get_app
    from sei_ia.routers.chat.gpt_4o_mini_128k import router as chat_router

    app = get_app(
        enable_timeout_middleware=False,
        enable_request_middleware=False,
    )
    app.include_router(chat_router)
    return app


@pytest.fixture
def client(test_app):
    """Fixture para cliente de teste"""
    from fastapi.testclient import TestClient

    return TestClient(test_app)


@pytest.fixture(autouse=True)
def configure_in_memory_cache(request, monkeypatch):
    """
    Substitui o cache Redis por implementação em memória durante os testes e2e.

    Nota: Não é aplicado a testes marcados com @pytest.mark.real_db,
    pois esses testes usam Redis real ou fixtures próprias de cache.
    """
    # Verificar se o teste está marcado com 'real_db'
    if "real_db" in request.keywords:
        # Não substituir cache para testes com banco real
        yield
        return

    import sei_ia.data.etl.concatenate_documents as concatenate_module
    from sei_ia.configs import settings_config
    from sei_ia.services import cache as cache_package
    from sei_ia.services.cache import redis_client as cache_module
    from tests.utils.in_memory_cache import get_in_memory_cache

    cache_instance = get_in_memory_cache()

    monkeypatch.setenv("ASSISTENTE_CACHE_ENABLED", "true")
    monkeypatch.setenv("ASSISTENTE_CACHE_COMPRESS", "false")
    monkeypatch.setattr(settings_config.settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings_config.settings, "CACHE_COMPRESS", False)

    monkeypatch.setattr(cache_module, "get_cache", lambda: cache_instance)
    monkeypatch.setattr(cache_package, "get_cache", lambda: cache_instance)
    monkeypatch.setattr(concatenate_module, "get_cache", lambda: cache_instance)

    yield

    cache = get_in_memory_cache()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(cache.close())
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def reset_in_memory_cache(request):
    """
    Reseta cache em memória após cada teste.

    Nota: Não é aplicado a testes marcados com @pytest.mark.real_db.
    """
    # Verificar se o teste está marcado com 'real_db'
    if "real_db" in request.keywords:
        # Não resetar cache em memória para testes com banco real
        yield
        return

    from tests.utils.in_memory_cache import reset_in_memory_cache as reset_cache

    yield

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(reset_cache())
    finally:
        loop.close()
