"""
Configuração do pytest para testes da intenção pergunta.
"""

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# Adicionar o diretório raiz do projeto ao Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configurar variáveis de ambiente para testes
os.environ["TESTING"] = "true"
os.environ["LOG_LEVEL"] = "WARNING"  # Reduzir logs durante testes


@pytest.fixture(scope="session")
def test_config():
    """Configuração global para testes."""
    return {"test_mode": True, "mock_external_apis": True, "log_level": "WARNING"}


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


# Hooks do pytest


def pytest_configure(config):
    """Configuração executada antes dos testes."""
    # Registrar marcadores customizados
    config.addinivalue_line("markers", "unit: marca teste como teste unitário")
    config.addinivalue_line(
        "markers", "integration: marca teste como teste de integração"
    )
    config.addinivalue_line("markers", "slow: marca teste como lento")
    config.addinivalue_line(
        "markers", "external_api: marca teste que usa APIs externas"
    )
    config.addinivalue_line(
        "markers",
        "real_db: marca teste que usa banco de dados real (PostgreSQL com Testcontainers)",
    )


def pytest_collection_modifyitems(config, items):
    """Modifica itens coletados antes da execução."""
    # Adicionar marker 'unit' para testes em tests/unit/
    # Adicionar marker 'integration' para testes em tests/integration/

    for item in items:
        test_path = str(item.fspath)

        if "/unit/" in test_path:
            item.add_marker(pytest.mark.unit)
        elif "/integration/" in test_path or "/scenarios/" in test_path:
            item.add_marker(pytest.mark.integration)


def pytest_runtest_setup(item):
    """Setup executado antes de cada teste."""
    # Configurações específicas por tipo de teste
    if "external_api" in item.keywords:
        pytest.skip("Testes de API externa desabilitados em modo de teste")


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Setup automático para todos os testes."""
    # Mock de configurações que poderiam causar efeitos colaterais
    monkeypatch.setenv("ENVIRONMENT", "test")

    # Mock do logger para reduzir output durante testes
    import logging

    logging.getLogger().setLevel(logging.WARNING)


# Fixtures para mockar serviços externos


@pytest.fixture
def mock_openai_api(monkeypatch):
    """Mock da API OpenAI."""

    def mock_chat_completion(*args, **kwargs):
        return {"choices": [{"message": {"content": "Resposta mockada do LLM"}}]}

    monkeypatch.setattr(
        "sei_ia.services.llm_models.chat_workflow.chat_gpt", mock_chat_completion
    )


@pytest.fixture
def mock_database(monkeypatch):
    """Mock do banco de dados."""
    from tests.fixtures.mock_data import create_mock_similarity_df

    def mock_select_async(*args, **kwargs):
        return create_mock_similarity_df()

    monkeypatch.setattr(
        "sei_ia.data.database.db_instances.app_db_instance.select_async",
        mock_select_async,
    )


@pytest.fixture
def mock_embedding_service(monkeypatch):
    """Mock do serviço de embeddings."""
    from tests.fixtures.mock_data import create_mock_embedding

    def mock_generate(*args, **kwargs):
        return iter([create_mock_embedding()])

    monkeypatch.setattr(
        "sei_ia.services.embedder.pipeline.embedding_generator.generate", mock_generate
    )


# Utilities para testes


@pytest.fixture
def assert_helpers():
    """Fixture com helpers de assert."""
    from tests.utils.test_helpers import TestAssertions

    return TestAssertions


# Cleanup fixtures


@pytest.fixture(scope="function", autouse=True)
def cleanup_after_test():
    """Cleanup automático após cada teste."""
    yield
    # Cleanup aqui se necessário
    pass


# ==================== FIXTURES PARA TESTES COM BANCO REAL (PostgreSQL) ====================
# Nota: Estas fixtures são usadas apenas em testes que precisam de banco de dados real
# (como testes de cache cleanup). A maioria dos testes e2e usa mocks.


@pytest.fixture(scope="session")
def postgres_container():
    """
    Inicia um container PostgreSQL com pgvector para testes que precisam de banco real.

    O container é compartilhado entre todos os testes (scope="session")
    para melhor performance.

    Nota: Usado principalmente em testes de integração com banco real.
    """
    import logging
    import os

    from testcontainers.postgres import PostgresContainer

    logger = logging.getLogger(__name__)

    # Configurar Testcontainers para evitar conflito de porta
    os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"

    logger.info("🚀 Iniciando PostgreSQL com Testcontainers...")

    container = (
        PostgresContainer(
            image="ankane/pgvector:latest",
            username="test_user",
            password="test_pass",
            dbname="seiia_test",
        )
        .with_bind_ports(5432, 5532)
        .with_kwargs(network="docker-host-bridge")
    )

    container.start()

    # Obter host e porta
    host = container.get_container_host_ip()
    # Como mapeamos porta fixa, usar diretamente a porta 5532
    port = 5532

    logger.info(f"✅ PostgreSQL iniciado em {host}:{port}")

    yield container

    logger.info("🛑 Parando PostgreSQL...")
    container.stop()
    logger.info("✅ PostgreSQL parado")


@pytest.fixture(scope="session")
def redis_container():
    """
    Inicia um container Redis para testes que precisam de cache real.

    O container é compartilhado entre todos os testes (scope="session")
    para melhor performance.

    Nota: Usado principalmente em testes de integração com Redis real.
    """
    import logging
    import os

    from testcontainers.redis import RedisContainer

    logger = logging.getLogger(__name__)

    # Configurar Testcontainers para evitar conflito de porta
    os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"

    logger.info("🚀 Iniciando Redis com Testcontainers...")

    container = RedisContainer(image="redis:7-alpine").with_kwargs(
        network="docker-host-bridge"
    )

    container.start()

    # Obter host e porta dinamicamente
    host = container.get_container_host_ip()
    port = container.get_exposed_port(6379)

    logger.info(f"✅ Redis iniciado em {host}:{port}")

    yield container

    logger.info("🛑 Parando Redis...")
    container.stop()
    logger.info("✅ Redis parado")


@pytest.fixture(scope="session")
def db_config(postgres_container):
    """
    Retorna a configuração de conexão do banco de testes.

    Returns:
        dict: Configuração com host, port, user, password, database
    """
    return {
        "host": postgres_container.get_container_host_ip(),
        "port": 5532,  # Porta mapeada fixa
        "user": postgres_container.username,
        "password": postgres_container.password,
        "database": postgres_container.dbname,
    }


@pytest.fixture(scope="session")
def redis_config(redis_container):
    """
    Retorna a configuração de conexão do Redis de testes.

    Returns:
        dict: Configuração com host, port
    """
    return {
        "host": redis_container.get_container_host_ip(),
        "port": redis_container.get_exposed_port(6379),  # Porta dinâmica
    }


@pytest_asyncio.fixture(scope="session", autouse=False)
async def configure_settings(
    db_config, redis_config, postgres_container, redis_container
):
    """
    Configura as settings globalmente para usar PostgreSQL e Redis de testes.

    Nota: autouse=False pois só deve ser usado em testes que precisam do banco real.
    Use esta fixture explicitamente nos testes que precisam de banco real.
    """
    import logging

    from sei_ia.configs.settings_config import settings

    logger = logging.getLogger(__name__)

    # Salvar configuração original
    original_config = {
        "DB_SEIIA_HOST": settings.DB_SEIIA_HOST,
        "DB_SEIIA_PORT": settings.DB_SEIIA_PORT,
        "DB_SEIIA_USER": settings.DB_SEIIA_USER,
        "DB_SEIIA_PWD": settings.DB_SEIIA_PWD,
        "DB_SEIIA_ASSISTENTE": settings.DB_SEIIA_ASSISTENTE,
        "REDIS_URI": settings.REDIS_URI,
        "CACHE_ENABLED": settings.CACHE_ENABLED,
    }

    # Aplicar configuração de teste - PostgreSQL
    settings.DB_SEIIA_HOST = db_config["host"]
    settings.DB_SEIIA_PORT = db_config["port"]
    settings.DB_SEIIA_USER = db_config["user"]
    settings.DB_SEIIA_PWD = db_config["password"]
    settings.DB_SEIIA_ASSISTENTE = db_config["database"]

    # Aplicar configuração de teste - Redis
    redis_uri = f"redis://{redis_config['host']}:{redis_config['port']}/0"
    settings.REDIS_URI = redis_uri
    settings.CACHE_ENABLED = True

    # Resetar cache para garantir que use o novo Redis URI
    from sei_ia.services.cache.redis_client import reset_cache

    await reset_cache()

    logger.info(
        f"✅ PostgreSQL configurado: {db_config['host']}:{db_config['port']}/{db_config['database']}"
    )
    logger.info(f"✅ Redis configurado: {redis_uri}")

    # Criar engine temporário para inicializar tabelas
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    temp_engine = create_async_engine(
        f"postgresql+asyncpg://{db_config['user']}:{db_config['password']}@"
        f"{db_config['host']}:{db_config['port']}/{db_config['database']}",
        pool_pre_ping=True,
    )

    # Criar tabelas
    async with temp_engine.connect() as conn:
        # Criar extensão pgvector
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # Criar schema
        await conn.execute(
            text(f"CREATE SCHEMA IF NOT EXISTS {settings.DB_SEIIA_ASSISTENTE_SCHEMA}")
        )

        # Criar tabela de embeddings
        await conn.execute(
            text(f"""
            CREATE TABLE IF NOT EXISTS {settings.DB_SEIIA_ASSISTENTE_SCHEMA}.{settings.EMBEDDINGS_TABLE_NAME} (
                chunk_id INTEGER NOT NULL,
                id_documento INTEGER NOT NULL,
                embedding vector(1536),
                start_position INTEGER,
                finished_position INTEGER,
                created_at TIMESTAMP,
                PRIMARY KEY (chunk_id, id_documento)
            )
        """)
        )

        await conn.commit()

    await temp_engine.dispose()
    logger.info("✅ Tabelas de teste criadas com sucesso")

    yield

    # Restaurar configuração original
    settings.DB_SEIIA_HOST = original_config["DB_SEIIA_HOST"]
    settings.DB_SEIIA_PORT = original_config["DB_SEIIA_PORT"]
    settings.DB_SEIIA_USER = original_config["DB_SEIIA_USER"]
    settings.DB_SEIIA_PWD = original_config["DB_SEIIA_PWD"]
    settings.DB_SEIIA_ASSISTENTE = original_config["DB_SEIIA_ASSISTENTE"]
    settings.REDIS_URI = original_config["REDIS_URI"]
    settings.CACHE_ENABLED = original_config["CACHE_ENABLED"]

    logger.info("✅ Settings restauradas")


@pytest_asyncio.fixture(scope="function")
async def db_connection(configure_settings, db_config):
    """
    Fixture que provê um AsyncEngine SQLAlchemy para testes.

    IMPORTANTE: Retorna um engine SQLAlchemy, não o app_db_instance.
    Usado pelos testes de cache cleanup que precisam de um AsyncEngine.
    """
    import logging

    from sqlalchemy.ext.asyncio import create_async_engine

    logger = logging.getLogger(__name__)

    connection_string = (
        f"postgresql+asyncpg://{db_config['user']}:{db_config['password']}@"
        f"{db_config['host']}:{db_config['port']}/{db_config['database']}"
    )

    engine = create_async_engine(
        connection_string,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

    logger.info(f"✅ Engine SQLAlchemy criado: {db_config['host']}:{db_config['port']}")

    try:
        yield engine
    finally:
        await engine.dispose()
        logger.info("✅ Engine SQLAlchemy disposto")


@pytest_asyncio.fixture(scope="function")
async def clean_test_data(db_connection):
    """
    Fixture que limpa dados de teste antes e depois de cada teste.

    IMPORTANTE: Usa o engine SQLAlchemy do db_connection.
    """
    import logging

    from sqlalchemy import text

    from sei_ia.configs.settings_config import settings
    from sei_ia.services.cache import get_cache
    from tests.mocks import get_all_test_document_ids

    logger = logging.getLogger(__name__)

    cache = get_cache()

    test_doc_ids = get_all_test_document_ids()

    # Limpar antes do teste
    async with db_connection.connect() as conn:
        await conn.execute(
            text(
                f"""
                DELETE FROM {settings.DB_SEIIA_ASSISTENTE_SCHEMA}.{settings.EMBEDDINGS_TABLE_NAME}
                WHERE id_documento IN (:doc1, :doc2, :doc3)
                """
            ),
            {
                "doc1": int(test_doc_ids[0]),
                "doc2": int(test_doc_ids[1]),
                "doc3": int(test_doc_ids[2]),
            },
        )
        await conn.commit()

    for doc_id in test_doc_ids:
        await cache.delete_document(doc_id)

    logger.info("🧹 Dados de teste limpos (before)")

    yield

    # Limpar depois do teste
    async with db_connection.connect() as conn:
        await conn.execute(
            text(
                f"""
                DELETE FROM {settings.DB_SEIIA_ASSISTENTE_SCHEMA}.{settings.EMBEDDINGS_TABLE_NAME}
                WHERE id_documento IN (:doc1, :doc2, :doc3)
                """
            ),
            {
                "doc1": int(test_doc_ids[0]),
                "doc2": int(test_doc_ids[1]),
                "doc3": int(test_doc_ids[2]),
            },
        )
        await conn.commit()

    for doc_id in test_doc_ids:
        await cache.delete_document(doc_id)

    logger.info("🧹 Dados de teste limpos (after)")


@pytest_asyncio.fixture(scope="function")
async def insert_test_data(clean_test_data, db_connection):
    """
    Fixture que insere dados de teste no PostgreSQL e Redis.

    IMPORTANTE: Usa o engine SQLAlchemy do db_connection.
    """
    import logging
    from datetime import datetime

    from sqlalchemy import text

    from sei_ia.configs.settings_config import settings
    from sei_ia.services.cache import get_cache
    from tests.mocks import (
        create_cacheable_document_data,
        create_volatile_document_data,
        create_volatile_multi_chunk_document_data,
        create_volatile_multi_chunk_embeddings,
    )

    logger = logging.getLogger(__name__)

    logger.info("📝 Inserindo dados de teste...")

    cache = get_cache()
    logger.info(f"Cache habilitado: {cache._enabled}")

    # Obter dados de teste das factories
    doc_volatile = create_volatile_document_data()
    doc_cacheable = create_cacheable_document_data()
    doc_volatile_multi = create_volatile_multi_chunk_document_data()
    doc_volatile_multi_chunks = create_volatile_multi_chunk_embeddings()

    # Inserir embeddings no PostgreSQL
    async with db_connection.connect() as conn:
        # Documento 1: Volátil (1 chunk)
        await conn.execute(
            text(
                f"""
                INSERT INTO {settings.DB_SEIIA_ASSISTENTE_SCHEMA}.{settings.EMBEDDINGS_TABLE_NAME}
                (chunk_id, id_documento, embedding, start_position, finished_position, created_at)
                VALUES (:chunk_id, :id_doc, CAST(:embedding AS vector), :start_pos, :end_pos, :created_at)
                """
            ),
            {
                "chunk_id": doc_volatile["chunk_id"],
                "id_doc": int(doc_volatile["id_documento"]),
                "embedding": str(doc_volatile["embedding"]),
                "start_pos": doc_volatile["start_position"],
                "end_pos": doc_volatile["end_position"],
                "created_at": datetime.now(),
            },
        )

        # Documento 2: Cacheável (1 chunk)
        await conn.execute(
            text(
                f"""
                INSERT INTO {settings.DB_SEIIA_ASSISTENTE_SCHEMA}.{settings.EMBEDDINGS_TABLE_NAME}
                (chunk_id, id_documento, embedding, start_position, finished_position, created_at)
                VALUES (:chunk_id, :id_doc, CAST(:embedding AS vector), :start_pos, :end_pos, :created_at)
                """
            ),
            {
                "chunk_id": doc_cacheable["chunk_id"],
                "id_doc": int(doc_cacheable["id_documento"]),
                "embedding": str(doc_cacheable["embedding"]),
                "start_pos": doc_cacheable["start_position"],
                "end_pos": doc_cacheable["end_position"],
                "created_at": datetime.now(),
            },
        )

        # Documento 3: Volátil com múltiplos chunks
        for chunk_data in doc_volatile_multi_chunks:
            await conn.execute(
                text(
                    f"""
                    INSERT INTO {settings.DB_SEIIA_ASSISTENTE_SCHEMA}.{settings.EMBEDDINGS_TABLE_NAME}
                    (chunk_id, id_documento, embedding, start_position, finished_position, created_at)
                    VALUES (:chunk_id, :id_doc, CAST(:embedding AS vector), :start_pos, :end_pos, :created_at)
                    """
                ),
                {
                    "chunk_id": chunk_data["chunk_id"],
                    "id_doc": int(chunk_data["id_documento"]),
                    "embedding": str(chunk_data["embedding"]),
                    "start_pos": chunk_data["start_position"],
                    "end_pos": chunk_data["end_position"],
                    "created_at": chunk_data["created_at"],
                },
            )

        await conn.commit()

    # Inserir documentos no Redis
    logger.info("🔄 Inserindo documentos no Redis...")

    # Preparar dados para o Redis (sem os campos específicos do PostgreSQL)
    redis_doc_volatile = {
        k: v
        for k, v in doc_volatile.items()
        if k not in ["embedding", "chunk_id", "start_position", "end_position"]
    }
    redis_doc_cacheable = {
        k: v
        for k, v in doc_cacheable.items()
        if k not in ["embedding", "chunk_id", "start_position", "end_position"]
    }
    redis_doc_volatile_multi = doc_volatile_multi.copy()

    result1 = await cache.set_document(redis_doc_volatile)
    logger.info(f"Doc volátil 1 inserido: {result1}")

    result2 = await cache.set_document(redis_doc_cacheable)
    logger.info(f"Doc cacheável inserido: {result2}")

    result3 = await cache.set_document(redis_doc_volatile_multi)
    logger.info(f"Doc volátil multi inserido: {result3}")

    logger.info("✅ Dados de teste inseridos")

    yield
