"""Serviço de limpeza de cache e embeddings para documentos não cacheáveis."""

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql import text

from sei_ia.configs.settings_config import settings
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.cache.redis_client import RedisCache

logger = logging.getLogger(__name__)


async def cleanup_non_cacheable_documents(
    user_state: UserState,
    redis_client: RedisCache,
    db_pool: AsyncEngine,
) -> dict[str, Any]:
    """Deleta cache Redis e embeddings PostgreSQL para documentos com SinArmazenarCache='N'.

    Args:
        user_state: Estado do usuário contendo informações dos documentos
        redis_client: Cliente Redis para limpeza de cache
        db_pool: Pool de conexões PostgreSQL para limpeza de embeddings

    Returns:
        dict: Resultado da operação com documentos deletados e erros
            {
                "deleted_from_redis": [list of id_documento],
                "deleted_from_postgres": [list of id_documento],
                "errors": [...]
            }
    """
    # 1. Identificar documentos com flag "N"
    non_cacheable = _extract_non_cacheable_ids(user_state)

    if not non_cacheable:
        logger.debug(
            "Nenhum documento com SinArmazenarCache='N' encontrado para limpeza"
        )
        return {"deleted_from_redis": [], "deleted_from_postgres": [], "errors": []}

    logger.debug(
        f"Iniciando limpeza de {len(non_cacheable)} documentos com SinArmazenarCache='N': {non_cacheable}"
    )

    # 2. Deletar em paralelo Redis e PostgreSQL
    results = await asyncio.gather(
        _delete_redis_batch(non_cacheable, redis_client),
        _delete_embeddings_batch(non_cacheable, db_pool),
        return_exceptions=True,
    )

    # 3. Processar resultados
    redis_result = (
        results[0]
        if not isinstance(results[0], Exception)
        else {"deleted": [], "errors": [{"error": f"Exceção no Redis: {results[0]}"}]}
    )

    postgres_result = (
        results[1]
        if not isinstance(results[1], Exception)
        else {
            "deleted": [],
            "errors": [{"error": f"Exceção no PostgreSQL: {results[1]}"}],
        }
    )

    # 4. Log final
    logger.debug(
        f"Cache cleanup completado: "
        f"Redis deleted={len(redis_result['deleted'])}, "
        f"Postgres deleted={len(postgres_result['deleted'])}, "
        f"Redis errors={len(redis_result['errors'])}, "
        f"Postgres errors={len(postgres_result['errors'])}"
    )

    return {
        "deleted_from_redis": redis_result["deleted"],
        "deleted_from_postgres": postgres_result["deleted"],
        "errors": redis_result["errors"] + postgres_result["errors"],
    }


def _extract_non_cacheable_ids(user_state: UserState) -> list[str]:
    """Extrai todos id_documento com SinArmazenarCache='N' do user_state.

    Args:
        user_state: Estado do usuário

    Returns:
        list: Lista de IDs de documentos não cacheáveis (sem duplicatas)
    """
    ids = []
    id_procedimentos = user_state.get("id_procedimentos")

    if not id_procedimentos:
        return ids

    for proc in id_procedimentos:
        # Iterar sobre id_documentos que pode ser lista de strings ou ItemDocumentRequest
        id_documentos = proc.id_documentos if hasattr(proc, "id_documentos") else []

        for doc in id_documentos:
            # Pode ser string (formato antigo) ou ItemDocumentRequest
            if isinstance(doc, str):
                # Formato antigo não tem a flag, assume "S" (cachear)
                continue
            else:
                # É um objeto, pode ter sin_armazena_cache
                # Verificar no objeto original ou depois do processamento
                doc_dict = (
                    doc
                    if isinstance(doc, dict)
                    else (doc.model_dump() if hasattr(doc, "model_dump") else {})
                )
                sin_cache = doc_dict.get("sin_armazena_cache", "S")

                if sin_cache == "N":
                    id_doc = doc_dict.get("id_documento")
                    if id_doc:
                        ids.append(str(id_doc))

    # Remove duplicatas mantendo ordem
    return list(dict.fromkeys(ids))


async def _delete_redis_batch(
    id_documentos: list[str], redis_client: RedisCache
) -> dict[str, Any]:
    """Deleta todas as chaves Redis para os id_documento especificados.

    Usa SCAN para encontrar todas as variações de hash (paginação, anexos, etc).

    Args:
        id_documentos: Lista de IDs de documentos para deletar
        redis_client: Cliente Redis

    Returns:
        dict: {"deleted": [ids deletados], "errors": [erros]}
    """
    if not id_documentos:
        return {"deleted": [], "errors": []}

    deleted = []
    errors = []

    # Verificar se Redis está habilitado e acessível
    client = await redis_client._get_client()
    if client is None:
        logger.warning("Redis client não disponível, pulando limpeza de cache")
        return {"deleted": [], "errors": [{"error": "Redis client não disponível"}]}

    for id_doc in id_documentos:
        try:
            # Pattern para encontrar todas as chaves desse documento
            # Exemplo: seiia:v1:doc:123:*
            pattern = (
                f"{settings.CACHE_KEY_PREFIX}{settings.CACHE_VERSION}:doc:{id_doc}:*"
            )

            # Coletar todas as chaves que correspondem ao pattern
            keys_to_delete = []
            async for key in redis_client._scan_iter_pattern(pattern):
                keys_to_delete.append(key)

            if keys_to_delete:
                # Deletar todas as chaves em batch usando pipeline
                async with client.pipeline() as pipe:
                    for key in keys_to_delete:
                        pipe.delete(key)
                    await pipe.execute()

                deleted.append(id_doc)
                logger.debug(
                    f"✓ Redis: Deletadas {len(keys_to_delete)} chaves do documento {id_doc}"
                )
            else:
                logger.debug(
                    f"⊘ Redis: Nenhuma chave encontrada para documento {id_doc}"
                )

        except Exception as e:
            error_msg = f"Erro ao deletar documento {id_doc} do Redis: {e}"
            logger.warning(error_msg)
            errors.append({"id_documento": id_doc, "error": str(e)})

    return {"deleted": deleted, "errors": errors}


async def _delete_embeddings_batch(
    id_documentos: list[str], db_pool: AsyncEngine
) -> dict[str, Any]:
    """Deleta embeddings do PostgreSQL em batch único.

    Args:
        id_documentos: Lista de IDs de documentos
        db_pool: Pool de conexões AsyncEngine do SQLAlchemy

    Returns:
        dict: {"deleted": [ids deletados], "errors": [erros]}
    """
    if not id_documentos:
        return {"deleted": [], "errors": []}

    if not hasattr(db_pool, "connect") or not callable(db_pool.connect):
        error_msg = (
            f"db_pool deve ser um AsyncEngine, mas recebeu {type(db_pool).__name__}"
        )
        logger.warning(error_msg)
        return {
            "deleted": [],
            "errors": [{"id_documentos": id_documentos, "error": error_msg}],
        }

    try:
        id_docs_int = [int(id_doc) for id_doc in id_documentos]

        async with db_pool.connect() as conn:
            async with conn.begin():
                query = text(f"""
                    DELETE FROM {settings.DB_SEIIA_ASSISTENTE_SCHEMA}.{settings.EMBEDDINGS_TABLE_NAME}
                    WHERE id_documento = ANY(:ids)
                    RETURNING id_documento
                """)

                result = await conn.execute(query, {"ids": id_docs_int})
                deleted_rows = result.fetchall()

            deleted_ids = list({str(row[0]) for row in deleted_rows})

            if deleted_ids:
                logger.debug(
                    f"✓ PostgreSQL: Deletados embeddings de {len(deleted_ids)} documentos: {deleted_ids}"
                )
            else:
                logger.debug(
                    f"⊘ PostgreSQL: Nenhum embedding encontrado para os documentos: {id_documentos}"
                )

            return {"deleted": deleted_ids, "errors": []}

    except Exception as e:
        error_msg = f"Erro ao deletar embeddings do PostgreSQL: {e}"
        logger.exception(error_msg)
        return {
            "deleted": [],
            "errors": [{"id_documentos": id_documentos, "error": str(e)}],
        }
