"""
Serviço para recuperação de conteúdo de chunks usando estratégia em camadas.

Hierarquia de busca:
1. user_state (memória da sessão)
2. Redis cache
3. API SEI
"""

import logging

from sei_ia.data.pydantic_models import UserState
from sei_ia.services.cache.redis_client import RedisCache
from sei_ia.services.exceptions.http_exceptions import HTTPException404

logger = logging.getLogger(__name__)


class ChunkContentRetriever:
    """
    Recupera conteúdo de chunks usando start/end positions com estratégia em camadas.
    """

    def __init__(self, cache_client: RedisCache | None = None):
        """
        Inicializa o retriever.

        Args:
            cache_client: Cliente Redis para cache (opcional)
        """
        self.cache_client = cache_client

    async def get_chunk_content(
        self,
        id_documento: str,
        start_position: int,
        end_position: int,
        user_state: UserState | None = None,
    ) -> str | None:
        """
        Recupera o conteúdo de um chunk baseado em suas posições.

        Estratégia de busca em camadas:
        1. Busca em user_state.id_procedimentos[].id_documentos[].content
        2. Se não encontrar → busca no Redis cache

        Args:
            id_documento: ID do documento
            start_position: Posição inicial do chunk no documento
            end_position: Posição final do chunk no documento
            user_state: Estado do usuário com documentos em memória

        Returns:
            Conteúdo do chunk ou None se não encontrado
        """
        # Garantir que as posições são inteiros (podem vir como float do banco)
        start_position = int(start_position)
        end_position = int(end_position)

        # Camada 1: Buscar em user_state
        if user_state:
            content = await self._get_from_user_state(
                id_documento, start_position, end_position, user_state
            )
            if content is not None:
                logger.debug(
                    f"Chunk recuperado de user_state: doc={id_documento}, "
                    f"pos=[{start_position}:{end_position}]"
                )
                return content

        # Camada 2: Buscar em Redis cache
        if self.cache_client:
            content = await self._get_from_cache(
                id_documento, start_position, end_position
            )
            if content is not None:
                logger.debug(
                    f"Chunk recuperado de Redis: doc={id_documento}, "
                    f"pos=[{start_position}:{end_position}]"
                )
                return content

        raise HTTPException404(
            detail=f"Documento {id_documento} não encontrado durante a recuperação de chunks"
        )

    async def _get_from_user_state(
        self,
        id_documento: str,
        start_position: int,
        end_position: int,
        user_state: UserState,
    ) -> str | None:
        """
        Busca conteúdo do chunk no user_state.

        Args:
            id_documento: ID do documento
            start_position: Posição inicial
            end_position: Posição final
            user_state: Estado do usuário

        Returns:
            Conteúdo do chunk ou None
        """
        try:
            # Buscar em id_procedimentos
            id_procedimentos = user_state.get("id_procedimentos", [])
            if not id_procedimentos:
                return None

            # Normalizar id_documento removendo .0 se houver
            id_doc_normalized = (
                id_documento.replace(".0", "") if ".0" in id_documento else id_documento
            )

            for proc in id_procedimentos:
                # Acessar atributos Pydantic corretamente
                # proc pode ser dict ou objeto Pydantic (ItemRequestIdProcedimento)
                if hasattr(proc, "id_documentos"):
                    # É um objeto Pydantic
                    id_documentos = proc.id_documentos
                else:
                    # É um dict
                    id_documentos = proc.get("id_documentos", [])

                for doc in id_documentos:
                    # Normalizar ID do documento do user_state para comparação
                    # doc pode ser dict ou objeto Pydantic (ItemDocumentRequest)
                    if hasattr(doc, "id_documento"):
                        # É um objeto Pydantic
                        doc_id_raw = doc.id_documento
                        content = doc.content
                    else:
                        # É um dict
                        doc_id_raw = doc.get("id_documento", "")
                        content = doc.get("content", "")

                    doc_id = str(doc_id_raw).replace(".0", "")

                    if doc_id == id_doc_normalized:
                        if content and len(content) >= end_position:
                            return content[start_position:end_position]
                        else:
                            logger.warning(
                                f"Documento {id_documento} encontrado mas conteúdo "
                                f"insuficiente: len={len(content)}, expected>={end_position}"
                            )
                            return None

            logger.debug(
                f"Documento {id_documento} (normalizado: {id_doc_normalized}) não encontrado em user_state"
            )
            return None

        except Exception as e:
            logger.error(f"Erro ao buscar chunk em user_state: {e}", exc_info=True)
            return None

    async def _get_from_cache(
        self, id_documento: str, start_position: int, end_position: int
    ) -> str | None:
        """
        Busca conteúdo do chunk no Redis cache.

        Args:
            id_documento: ID do documento
            start_position: Posição inicial
            end_position: Posição final

        Returns:
            Conteúdo do chunk ou None
        """
        try:
            if not self.cache_client:
                return None

            # Buscar documento completo no cache usando o método get_document
            cached_doc = await self.cache_client.get_document(id_documento)

            if cached_doc:
                content = cached_doc.get("content", "")
                if content and len(content) >= end_position:
                    return content[start_position:end_position]
                else:
                    logger.warning(
                        f"Documento {id_documento} em cache mas conteúdo "
                        f"insuficiente: len={len(content)}, expected>={end_position}"
                    )
                    return None

            return None

        except Exception as e:
            logger.error(f"Erro ao buscar chunk em Redis cache: {e}", exc_info=True)
            return None

    async def get_multiple_chunks(
        self,
        chunks_info: list[dict],
        user_state: UserState | None = None,
    ) -> dict[str, str]:
        """
        Recupera múltiplos chunks em batch.

        Args:
            chunks_info: Lista de dicts com {id_documento, start_position, end_position}
            user_state: Estado do usuário

        Returns:
            Dict mapeando (id_documento, start, end) → conteúdo
        """
        results = {}

        for chunk in chunks_info:
            id_doc = chunk["id_documento"]
            start = chunk["start_position"]
            end = chunk["end_position"]

            content = await self.get_chunk_content(id_doc, start, end, user_state)

            key = f"{id_doc}:{start}:{end}"
            results[key] = content if content else ""

        return results
