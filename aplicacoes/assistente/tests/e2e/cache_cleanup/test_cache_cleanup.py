"""
Teste e2e para validar a funcionalidade de limpeza de cache/embeddings.

Testa:
1. Inserção de dados no PostgreSQL (embeddings) e Redis (cache)
2. Limpeza de documentos com sin_armazena_cache="N"
3. Preservação de documentos com sin_armazena_cache="S"

Uso:
    pytest tests/e2e/test_cache_cleanup.py -v
    pytest tests/e2e/test_cache_cleanup.py -v -s  # com logs

IMPORTANTE: Este teste usa @pytest.mark.real_db para evitar que fixtures de mock
do tests/e2e/conftest.py sejam aplicadas. Os imports de módulos que inicializam
conexões com banco são feitos dentro das funções de teste, não no nível do módulo.
"""

import logging

import pytest

logger = logging.getLogger(__name__)


# Importar constantes centralizadas do módulo de mocks
from tests.mocks import DOC_CACHEABLE_ID, DOC_VOLATILE_ID, DOC_VOLATILE_MULTI_ID

# ==================== TESTES ====================


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_cleanup_non_cacheable_documents(insert_test_data, db_connection):
    """
    Testa a limpeza de documentos não cacheáveis.

    Deve:
    - Deletar documentos com sin_armazena_cache="N" do Redis e PostgreSQL
    - Manter documentos com sin_armazena_cache="S"
    """
    # Imports dentro da função para evitar inicialização prematura de conexões
    from sqlalchemy import text

    from sei_ia.configs.settings_config import settings
    from sei_ia.data.pydantic_models import (
        ItemDocumentRequest,
        ItemRequestIdProcedimento,
        UserState,
    )
    from sei_ia.services.cache import get_cache
    from sei_ia.services.cache.cache_cleanup_service import (
        cleanup_non_cacheable_documents,
    )

    logger.info("🧪 Iniciando teste de limpeza...")

    # Criar user_state simulado
    user_state: UserState = {
        "id_request": 12345,
        "id_usuario": 999,
        "ip": "127.0.0.1",
        "endpoint_name": "/test",
        "id_topico": 1,
        "id_procedimentos": [
            ItemRequestIdProcedimento(
                id_procedimento="9999",
                id_documentos=[
                    ItemDocumentRequest(
                        id_documento=DOC_VOLATILE_ID, sin_armazena_cache="N"
                    ),
                    ItemDocumentRequest(
                        id_documento=DOC_CACHEABLE_ID, sin_armazena_cache="S"
                    ),
                    ItemDocumentRequest(
                        id_documento=DOC_VOLATILE_MULTI_ID, sin_armazena_cache="N"
                    ),
                ],
                metadata={},
            )
        ],
        "all_procs": [],
        "all_documents": [],
        "user_request": "teste",
        "system_prompt": "teste",
        "original_request_body": "",
        "intent": "pergunta",
        "model_type": "standard",
        "model_name": "test",
        "temperature": 0.1,
        "general_max_output_tokens": 4000,
        "general_max_ctx_len": 128000,
        "limit_rag": 64000,
        "use_websearch": False,
        "use_thinking": False,
        "summarize_history": False,
        "doc_paged": False,
        "doc_summarized": False,
        "doc_rag": False,
        "doc_false_rag": False,
        "all_tokens_counter": 100,
        "web_content": None,
        "last_prompt": "",
        "has_content": True,
        "skip_memory": False,
        "rag_method": None,
        "rag_documents_count": None,
        "rag_chunks_count": None,
        "rag_chunks_data": None,
        "id_to_formatted_map": None,
        "response": {},
    }

    # Verificar estado inicial
    cache = get_cache()

    doc1_before = await cache.get_document(DOC_VOLATILE_ID)
    doc2_before = await cache.get_document(DOC_CACHEABLE_ID)
    doc3_before = await cache.get_document(DOC_VOLATILE_MULTI_ID)

    assert doc1_before is not None, "Doc volátil 1 deve existir antes da limpeza"
    assert doc2_before is not None, "Doc cacheável deve existir antes da limpeza"
    assert doc3_before is not None, "Doc volátil multi deve existir antes da limpeza"

    async with db_connection.connect() as conn:
        result = await conn.execute(
            text(
                f"""
            SELECT id_documento, COUNT(*) as chunk_count
            FROM {settings.DB_SEIIA_ASSISTENTE_SCHEMA}.{settings.EMBEDDINGS_TABLE_NAME}
            WHERE id_documento IN (:doc1, :doc2, :doc3)
            GROUP BY id_documento
        """
            ),
            {
                "doc1": int(DOC_VOLATILE_ID),
                "doc2": int(DOC_CACHEABLE_ID),
                "doc3": int(DOC_VOLATILE_MULTI_ID),
            },
        )
        rows = result.fetchall()

    embeddings_before = {str(row[0]): row[1] for row in rows}

    assert embeddings_before.get(DOC_VOLATILE_ID, 0) == 1, (
        "Doc volátil 1 deve ter 1 chunk"
    )
    assert embeddings_before.get(DOC_CACHEABLE_ID, 0) == 1, (
        "Doc cacheável deve ter 1 chunk"
    )
    assert embeddings_before.get(DOC_VOLATILE_MULTI_ID, 0) == 3, (
        "Doc volátil multi deve ter 3 chunks"
    )

    # Executar limpeza
    logger.info("🧹 Executando limpeza...")

    cleanup_result = await cleanup_non_cacheable_documents(
        user_state=user_state,
        redis_client=cache,
        db_pool=db_connection,
    )

    logger.info(f"📊 Redis deletados: {cleanup_result['deleted_from_redis']}")
    logger.info(f"📊 Postgres deletados: {cleanup_result['deleted_from_postgres']}")
    logger.info(f"📊 Erros: {len(cleanup_result['errors'])}")

    # Verificar resultados
    assert len(cleanup_result["deleted_from_redis"]) == 2, (
        f"Deve deletar 2 docs do Redis, mas deletou {len(cleanup_result['deleted_from_redis'])}"
    )
    assert len(cleanup_result["deleted_from_postgres"]) == 2, (
        f"Deve deletar 2 docs do Postgres, mas deletou {len(cleanup_result['deleted_from_postgres'])}"
    )
    assert len(cleanup_result["errors"]) == 0, (
        f"Não deve haver erros, mas teve: {cleanup_result['errors']}"
    )

    # Verificar estado final - Redis
    doc1_after = await cache.get_document(DOC_VOLATILE_ID)
    doc2_after = await cache.get_document(DOC_CACHEABLE_ID)
    doc3_after = await cache.get_document(DOC_VOLATILE_MULTI_ID)

    assert doc1_after is None, "Doc volátil 1 deve ter sido deletado do Redis"
    assert doc2_after is not None, "Doc cacheável deve ter sido mantido no Redis"
    assert doc3_after is None, "Doc volátil multi deve ter sido deletado do Redis"

    # Verificar estado final - PostgreSQL
    async with db_connection.connect() as conn:
        result = await conn.execute(
            text(
                f"""
            SELECT id_documento, COUNT(*) as chunk_count
            FROM {settings.DB_SEIIA_ASSISTENTE_SCHEMA}.{settings.EMBEDDINGS_TABLE_NAME}
            WHERE id_documento IN (:doc1, :doc2, :doc3)
            GROUP BY id_documento
        """
            ),
            {
                "doc1": int(DOC_VOLATILE_ID),
                "doc2": int(DOC_CACHEABLE_ID),
                "doc3": int(DOC_VOLATILE_MULTI_ID),
            },
        )
        rows = result.fetchall()

    embeddings_after = {str(row[0]): row[1] for row in rows}

    assert embeddings_after.get(DOC_VOLATILE_ID, 0) == 0, (
        "Doc volátil 1 deve ter sido deletado do Postgres"
    )
    assert embeddings_after.get(DOC_CACHEABLE_ID, 0) == 1, (
        "Doc cacheável deve ter sido mantido no Postgres"
    )
    assert embeddings_after.get(DOC_VOLATILE_MULTI_ID, 0) == 0, (
        "Doc volátil multi deve ter sido deletado do Postgres (3 chunks)"
    )

    logger.info("✅ Teste passou!")


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_cleanup_with_no_documents(db_connection):
    """
    Testa limpeza quando não há documentos não cacheáveis.

    Deve retornar contadores zerados sem erros.
    """
    # Imports dentro da função para evitar inicialização prematura de conexões
    from sei_ia.data.pydantic_models import (
        ItemDocumentRequest,
        ItemRequestIdProcedimento,
        UserState,
    )
    from sei_ia.services.cache import get_cache
    from sei_ia.services.cache.cache_cleanup_service import (
        cleanup_non_cacheable_documents,
    )

    logger.info("🧪 Testando limpeza sem documentos...")

    user_state: UserState = {
        "id_request": 12345,
        "id_usuario": 999,
        "ip": "127.0.0.1",
        "endpoint_name": "/test",
        "id_topico": 1,
        "id_procedimentos": [
            ItemRequestIdProcedimento(
                id_procedimento="9999",
                id_documentos=[
                    ItemDocumentRequest(
                        id_documento=DOC_CACHEABLE_ID, sin_armazena_cache="S"
                    ),
                ],
                metadata={},
            )
        ],
        "all_procs": [],
        "all_documents": [],
        "user_request": "teste",
        "system_prompt": "teste",
        "original_request_body": "",
        "intent": "pergunta",
        "model_type": "standard",
        "model_name": "test",
        "temperature": 0.1,
        "general_max_output_tokens": 4000,
        "general_max_ctx_len": 128000,
        "limit_rag": 64000,
        "use_websearch": False,
        "use_thinking": False,
        "summarize_history": False,
        "doc_paged": False,
        "doc_summarized": False,
        "doc_rag": False,
        "doc_false_rag": False,
        "all_tokens_counter": 100,
        "web_content": None,
        "last_prompt": "",
        "has_content": True,
        "skip_memory": False,
        "rag_method": None,
        "rag_documents_count": None,
        "rag_chunks_count": None,
        "rag_chunks_data": None,
        "id_to_formatted_map": None,
        "response": {},
    }

    cache = get_cache()

    cleanup_result = await cleanup_non_cacheable_documents(
        user_state=user_state,
        redis_client=cache,
        db_pool=db_connection,
    )

    assert len(cleanup_result["deleted_from_redis"]) == 0, (
        f"Não deve deletar nada do Redis, mas deletou {len(cleanup_result['deleted_from_redis'])}"
    )
    assert len(cleanup_result["deleted_from_postgres"]) == 0, (
        f"Não deve deletar nada do Postgres, mas deletou {len(cleanup_result['deleted_from_postgres'])}"
    )
    assert len(cleanup_result["errors"]) == 0, (
        f"Não deve haver erros, mas teve: {cleanup_result['errors']}"
    )

    logger.info("✅ Teste passou!")


if __name__ == "__main__":
    # Permite rodar diretamente: python tests/e2e/test_cache_cleanup.py
    pytest.main([__file__, "-v", "-s"])
