"""Cache em memória para uso em testes.

Fornece uma implementação compatível com a interface usada pelo
`RedisCache`, porém armazenando os documentos em um dicionário local.
"""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sei_ia.services.cache.cache_keys import generate_cache_key


class InMemoryCache:
    """Implementação assíncrona de cache em memória."""

    def __init__(self):
        self._store: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "errors": 0,
            "total_requests": 0,
        }

    async def get_document(
        self,
        id_documento: str,
        pag_ini: int | None = None,
        pag_fim: int | None = None,
        download_ext: bool | None = None,
        id_anexos: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Recupera documento armazenado em memória."""

        key = generate_cache_key(
            id_documento, pag_ini, pag_fim, download_ext, id_anexos
        )
        async with self._lock:
            self._stats["total_requests"] += 1
            document = self._store.get(key)
            if document is None:
                self._stats["misses"] += 1
                return None

            self._stats["hits"] += 1
            return deepcopy(document)

    async def set_document(
        self,
        document: dict[str, Any],
        pag_ini: int | None = None,
        pag_fim: int | None = None,
        download_ext: bool | None = None,
        id_anexos: list[str] | None = None,
    ) -> bool:
        """Armazena documento em memória."""

        key = generate_cache_key(
            document["id_documento"], pag_ini, pag_fim, download_ext, id_anexos
        )
        async with self._lock:
            stored_document = deepcopy(document)
            stored_document["cached_at"] = datetime.now(UTC).isoformat()
            self._store[key] = stored_document
        return True

    async def delete_document(
        self,
        id_documento: str,
        pag_ini: int | None = None,
        pag_fim: int | None = None,
        download_ext: bool | None = None,
        id_anexos: list[str] | None = None,
    ) -> bool:
        """Remove documento do cache em memória."""

        key = generate_cache_key(
            id_documento, pag_ini, pag_fim, download_ext, id_anexos
        )
        async with self._lock:
            return self._store.pop(key, None) is not None

    async def clear_cache(self) -> bool:
        """Remove todos os documentos armazenados."""

        async with self._lock:
            self._store.clear()
        return True

    async def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas básicas do cache."""

        async with self._lock:
            stats_copy = deepcopy(self._stats)
            stats_copy.update(
                {
                    "status": "connected",
                    "cached_documents": len(self._store),
                }
            )
        stats_copy["last_updated"] = datetime.now(UTC).isoformat()
        return stats_copy

    async def close(self):
        """Mantido para compatibilidade com RedisCache."""

        await self.clear_cache()


_in_memory_cache_instance: InMemoryCache | None = None


def get_in_memory_cache() -> InMemoryCache:
    """Retorna instância singleton do cache em memória."""

    global _in_memory_cache_instance
    if _in_memory_cache_instance is None:
        _in_memory_cache_instance = InMemoryCache()
    return _in_memory_cache_instance


async def reset_in_memory_cache():
    """Reseta o cache em memória."""

    cache = get_in_memory_cache()
    await cache.clear_cache()
    async with cache._lock:  # type: ignore[attr-defined]
        cache._stats.update(
            {
                "hits": 0,
                "misses": 0,
                "errors": 0,
                "total_requests": 0,
            }
        )


async def populate_cache_with_document(
    id_documento: str,
    id_documento_formatado: str,
    content: str,
    metadata: str,
    doc_tokens: int,
    doc_paged: bool = False,
    pag_doc_init: int | None = None,
    pag_doc_end: int | None = None,
    download_ext: bool | None = None,
    id_anexos: list[str] | None = None,
) -> bool:
    """Popula o cache em memória com um documento mockado.

    Args:
        id_documento: ID do documento
        id_documento_formatado: ID formatado do documento
        content: Conteúdo do documento
        metadata: Metadados do documento
        doc_tokens: Número de tokens do documento
        doc_paged: Se o documento é paginado
        pag_doc_init: Página inicial (se paginado)
        pag_doc_end: Página final (se paginado)
        download_ext: Flag de download externo
        id_anexos: Lista de IDs de anexos

    Returns:
        bool: True se armazenado com sucesso
    """
    cache = get_in_memory_cache()

    document = {
        "id_documento": id_documento,
        "id_documento_formatado": id_documento_formatado,
        "content": content,
        "metadata": metadata,
        "doc_tokens": doc_tokens,
        "doc_paged": doc_paged,
        "pag_doc_init": pag_doc_init,
        "pag_doc_end": pag_doc_end,
        "download_ext": download_ext,
        "id_anexos": id_anexos,
    }

    return await cache.set_document(
        document=document,
        pag_ini=pag_doc_init,
        pag_fim=pag_doc_end,
        download_ext=download_ext,
        id_anexos=id_anexos,
    )
