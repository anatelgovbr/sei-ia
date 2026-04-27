"""Configuração centralizada do Langfuse com filtragem de traces.

BASEADO NA ISSUE OFICIAL: https://github.com/orgs/langfuse/discussions/8492

SOLUÇÃO: Criar o cliente Langfuse com blocked_instrumentation_scopes NO INÍCIO
do main.py, ANTES de importar qualquer router que use CallbackHandler().
"""

import logging
from typing import Any

from sei_ia.configs.settings_config import settings

logger = logging.getLogger(__name__)

# Cliente Langfuse global - criado uma única vez
_langfuse_client = None


# Configuração de limites de truncamento por campo
# Valores razoáveis para manter contexto útil sem enviar documentos completos
TRUNCATE_LIMITS = {
    "content": 3000,  # Conteúdo de documentos: ~3KB (primeiros parágrafos)
    "last_prompt": 5000,  # Prompt final: ~5KB (contexto completo geralmente)
    "user_request": 2000,  # Request do usuário: ~2KB (geralmente é pequeno, mas permite textos longos)
    "text": 2000,  # Campo genérico 'text'
    "default": 100_000,  # Limite padrão para strings não especificadas
}


def truncate_large_fields(data: Any) -> Any:
    """
    Trunca campos grandes antes de enviar ao Langfuse.

    Esta função é aplicada automaticamente pelo cliente Langfuse em TODOS
    os dados (input, output, metadata) antes de enviá-los ao servidor.

    Args:
        data: Dados a serem processados (pode ser str, dict, list, ou qualquer tipo)

    Returns:
        Dados processados com campos grandes truncados

    Exemplo de redução:
        - content de 141KB → 3KB (primeiros parágrafos + indicador de truncamento)
        - last_prompt de 145KB → 5KB (início do prompt)
        - Mantém: IDs, metadata, métricas, tags, tokens, etc.
    """
    # Campos específicos que devem ser truncados
    # NOTA: 'response' foi removido - a resposta do modelo deve ser sempre mantida inteira
    FIELDS_TO_TRUNCATE = {
        "content",
        "last_prompt",
        "user_request",
        "original_request_body",
        "text",
    }

    if isinstance(data, str):
        # Truncar strings longas com limite padrão
        max_length = TRUNCATE_LIMITS["default"]
        if len(data) > max_length:
            truncated_chars = len(data) - max_length
            return (
                data[:max_length]
                + f"\n\n... [TRUNCATED: {truncated_chars:,} chars omitted, total size: {len(data):,} chars]"
            )
        return data

    elif isinstance(data, dict):
        # Processar dicionários recursivamente
        result = {}
        for key, value in data.items():
            # Verificar se é um campo que deve ser truncado
            if key in FIELDS_TO_TRUNCATE and isinstance(value, str):
                max_length = TRUNCATE_LIMITS.get(key, TRUNCATE_LIMITS["default"])
                if len(value) > max_length:
                    truncated_chars = len(value) - max_length
                    result[key] = (
                        value[:max_length]
                        + f"\n\n... [TRUNCATED: {truncated_chars:,} chars omitted, original size: {len(value):,} chars]"
                    )
                else:
                    result[key] = value
            else:
                # Processar recursivamente (pode ter 'content' aninhado em subdicts)
                result[key] = truncate_large_fields(value)
        return result

    elif isinstance(data, list):
        # Processar listas recursivamente
        return [truncate_large_fields(item) for item in data]

    # Outros tipos (int, bool, None, etc.) passam sem modificação
    return data


def initialize_langfuse_singleton():
    """Cria o cliente Langfuse COM blocked_instrumentation_scopes.

    DEVE ser chamado NO INÍCIO do main.py!

    Ref: https://github.com/orgs/langfuse/discussions/8492
    """
    global _langfuse_client

    if _langfuse_client is not None:
        logger.debug("Langfuse já inicializado")
        return _langfuse_client

    try:
        if not settings.USE_LANGFUSE:
            logger.info("Langfuse desabilitado (USE_LANGFUSE=False)")
            return None

        from langfuse import Langfuse

        # Lista de scopes bloqueados
        blocked_scopes = [
            "opentelemetry.instrumentation.requests",
            "opentelemetry.instrumentation.httpx",
            "opentelemetry.instrumentation.sqlalchemy",
            "opentelemetry.instrumentation.fastapi",  # Bloqueia traces automáticos do FastAPI (healthchecks, etc)
        ]

        # Cria o cliente (primeira chamada = se torna o singleton)
        # mask= aplica truncate_large_fields ANTES de enviar dados ao Langfuse
        _langfuse_client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_URL,
            blocked_instrumentation_scopes=blocked_scopes,
            mask=truncate_large_fields,  # Trunca campos grandes automaticamente
        )

        logger.info(
            "✅ Langfuse inicializado com truncamento automático de campos grandes "
            f"(content: {TRUNCATE_LIMITS['content']:,} chars, "
            f"last_prompt: {TRUNCATE_LIMITS['last_prompt']:,} chars)"
        )

        return _langfuse_client

    except Exception as e:
        logger.error(f"❌ Erro ao configurar Langfuse: {e}")
        return None


def get_configured_langfuse_client():
    """Retorna o cliente Langfuse."""
    if _langfuse_client is None:
        return initialize_langfuse_singleton()
    return _langfuse_client
