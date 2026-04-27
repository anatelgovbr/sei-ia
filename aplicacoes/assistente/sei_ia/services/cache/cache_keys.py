"""Módulo para geração de chaves de cache consistentes."""

import hashlib
import json

from sei_ia.configs.settings_config import settings


class CacheKeyGenerator:
    """Gerador de chaves de cache para documentos."""

    @staticmethod
    def _create_hash(*args) -> str:
        """Cria hash SHA256 a partir dos argumentos fornecidos."""
        content = json.dumps(args, sort_keys=True, default=str)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def generate_document_key(
        id_documento: str,
        pag_ini: int | None = None,
        pag_fim: int | None = None,
        download_ext: bool | None = None,
        id_anexos: list[str] | None = None,
    ) -> str:
        """
        Gera chave única para um documento baseada nos seus parâmetros.

        Args:
            id_documento: ID do documento
            pag_ini: Página inicial (se aplicável)
            pag_fim: Página final (se aplicável)
            download_ext: Flag de download externo
            id_anexos: Lista de IDs de anexos

        Returns:
            str: Chave única para o documento
        """
        # Normalizar anexos para garantir ordem consistente
        anexos_normalized = sorted(id_anexos) if id_anexos else None

        # Criar hash baseado nos parâmetros
        param_hash = CacheKeyGenerator._create_hash(
            id_documento, pag_ini, pag_fim, download_ext, anexos_normalized
        )

        # Formatar chave final
        key = f"{settings.CACHE_KEY_PREFIX}{settings.CACHE_VERSION}:doc:{id_documento}:{param_hash}"
        return key

    @staticmethod
    def generate_stats_key() -> str:
        """Gera chave para estatísticas de cache."""
        return f"{settings.CACHE_KEY_PREFIX}{settings.CACHE_VERSION}:stats"

    @staticmethod
    def get_key_pattern() -> str:
        """Retorna padrão de chaves para busca."""
        return f"{settings.CACHE_KEY_PREFIX}{settings.CACHE_VERSION}:doc:*"


def generate_cache_key(
    id_documento: str,
    pag_ini: int | None = None,
    pag_fim: int | None = None,
    download_ext: bool | None = None,
    id_anexos: list[str] | None = None,
) -> str:
    """
    Função conveniente para gerar chaves de cache.

    Args:
        id_documento: ID do documento
        pag_ini: Página inicial (se aplicável)
        pag_fim: Página final (se aplicável)
        download_ext: Flag de download externo
        id_anexos: Lista de IDs de anexos

    Returns:
        str: Chave única para o documento
    """
    return CacheKeyGenerator.generate_document_key(
        id_documento, pag_ini, pag_fim, download_ext, id_anexos
    )
