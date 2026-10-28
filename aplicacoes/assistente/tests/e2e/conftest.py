# Definir variáveis de ambiente obrigatórias
import asyncio
import os
import warnings
from unittest.mock import MagicMock, patch

import pytest

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
_should_mock = True

if _should_mock:
    os.environ.update(
        {
            # Configurações da API SEI
            "SEI_API_DB_ADDRESS": "http://mock-sei-api:8000",
            "SEI_API_DB_IDENTIFIER_SERVICE": "mock-identifier",
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
    def mock_generate_embeddings(texts, *args, **kwargs):  # noqa: ARG001
        """Mock que retorna embeddings fake para qualquer texto."""
        import numpy as np

        # Retornar um embedding de dimensão 1536 (padrão do text-embedding-3-small)
        return [np.random.rand(1536).tolist() for _ in texts]

    # Mock para o SEIDBHandler - evita chamadas HTTP
    async def mock_fetch_metadata_procedimentos(*args, **kwargs):  # noqa: ARG001
        """Mock que retorna metadados fake para procedimentos."""
        return {}  # Retorna dict vazio, os metadados são opcionais

    async def mock_fetch_metadata_documentos(*args, **kwargs):  # noqa: ARG001
        """Mock que retorna metadados fake para documentos."""
        return {}  # Retorna dict vazio, os metadados são opcionais

    # Bridge async→sync para o endpoint content_doc. Os testes E2E mockam o
    # endpoint sync `md_ia_consulta_conteudo_documento` via `responses` lib
    # (intercepta `requests`). O código de produção chama a versão async via
    # httpx (não interceptada por `responses`). Este bridge faz a versão async
    # delegar para a sync apenas no contexto de teste, permitindo que cada
    # `mock_*` continue declarando uma rota única.
    async def mock_md_ia_consulta_conteudo_documento_async(
        id_documento: str, **_kwargs
    ):
        from sei_ia.data.database.sei_client import sei_client

        df = sei_client.md_ia_consulta_conteudo_documento(id_documento)
        if df.empty:
            return {"id_documento": id_documento, "content_doc": None}
        row = df.loc[0]
        extra = row.get("extra_metadata") if "extra_metadata" in df.columns else {}
        if not isinstance(extra, dict):
            extra = {}
        return {
            "id_documento": id_documento,
            "tipo_conteudo": row.get("tipo_conteudo")
            if "tipo_conteudo" in df.columns
            else None,
            "content_doc": row.get("content_doc"),
            "extra_metadata": extra,
        }

    with (
        patch("sei_ia.data.database.async_db_connection.AsyncDbConnector") as mock_db,
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
            "sei_ia.data.database.sei_client.sei_client.md_ia_consulta_conteudo_documento_async",
            side_effect=mock_md_ia_consulta_conteudo_documento_async,
        ),
    ):
        # Configurar mocks
        mock_db.return_value = MagicMock()

        yield


@pytest.fixture
def test_app():
    """Fixture para criar app de teste"""
    from sei_ia.main import get_app

    return get_app(
        enable_timeout_middleware=False,
        enable_request_middleware=False,
    )


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
