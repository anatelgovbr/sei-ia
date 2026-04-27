"""Método de conexão com LLM via LiteLLM Proxy usando ChatOpenAI."""

import logging
from typing import Any

from langchain_openai import ChatOpenAI

from sei_ia.configs.settings_config import settings

logger = logging.getLogger(__name__)


def get_model_config(model_type: str = "mini") -> dict[str, Any]:
    """Retorna as configurações específicas para o tipo de modelo solicitado.

    Com o proxy LiteLLM, as configurações são muito mais simples, pois o proxy
    gerencia toda a comunicação com Azure OpenAI.

    Args:
        model_type (str, optional): Tipo do modelo ('mini', 'standard', 'nano', 'think').
            Defaults to "mini".

    Returns:
        Dict[str, Any]: Configurações do modelo solicitado.

    Raises:
        ValueError: Se o tipo de modelo for inválido.
    """
    # Configurações comuns
    base_config = {
        "base_url": settings.LITELLM_PROXY_URL,
        "api_key": settings.LITELLM_PROXY_API_KEY or "dummy-key",
        "timeout": settings.TIMEOUT_API,
        "max_retries": settings.MAX_RETRIES,
    }

    # Configurações específicas por modelo
    model_configs = {
        "standard": {
            "model": settings.LITELLM_STANDARD_MODEL_NAME,
            "model_name": settings.LITELLM_STANDARD_MODEL,  # Para compatibilidade com código legado
            "max_tokens": settings.OUTPUT_TOKENS_STANDARD_MODEL,
            "max_output_tokens": settings.OUTPUT_TOKENS_STANDARD_MODEL,  # Alias para compatibilidade
            "max_ctx_len": settings.CTX_LEN_STANDARD_MODEL,
        },
        "mini": {
            "model": settings.LITELLM_MINI_MODEL_NAME,
            "model_name": settings.LITELLM_MINI_MODEL,  # Para compatibilidade com código legado
            "max_tokens": settings.OUTPUT_TOKENS_MINI_MODEL,
            "max_output_tokens": settings.OUTPUT_TOKENS_MINI_MODEL,  # Alias para compatibilidade
            "max_ctx_len": settings.CTX_LEN_MINI_MODEL,
        },
        "nano": {
            "model": settings.LITELLM_NANO_MODEL_NAME,
            "model_name": settings.LITELLM_NANO_MODEL,  # Para compatibilidade com código legado
            "max_tokens": settings.OUTPUT_TOKENS_NANO_MODEL,
            "max_output_tokens": settings.OUTPUT_TOKENS_NANO_MODEL,  # Alias para compatibilidade
            "max_ctx_len": settings.CTX_LEN_NANO_MODEL,
        },
        "think": {
            "model": settings.LITELLM_THINK_MODEL_NAME,
            "model_name": settings.LITELLM_STANDARD_MODEL,  # Para compatibilidade com código legado (think usa o mesmo modelo base)
            "max_tokens": settings.OUTPUT_TOKENS_THINK_MODEL,
            "max_output_tokens": settings.OUTPUT_TOKENS_THINK_MODEL,  # Alias para compatibilidade
            "max_ctx_len": settings.CTX_LEN_THINK_MODEL,
        },
    }

    model_type_lower = model_type.lower()
    if model_type_lower not in model_configs:
        msg = f"Tipo de modelo inválido: {model_type}. Tipos válidos: {list(model_configs.keys())}"
        raise ValueError(msg)

    # Combina configurações base com específicas do modelo
    config = {**base_config, **model_configs[model_type_lower]}

    return config


def get_summarize_model() -> dict:
    """Retorna a configuração para o modelo de sumarização.

    Returns:
        Dict[str, Any]: Configurações do modelo de sumarização.
    """
    model_config = get_model_config(settings.SUMMARIZE_MODEL)
    return {
        **model_config,
        "temperature": settings.SUMMARIZE_TEMPERATURE,
        "token_encoding_name": settings.SUMMARIZE_ENCODING_NAME,
        "chunk_size": settings.SUMMARIZE_CHUNK_SIZE,
    }


def get_model(
    model_type: str,
    temperature: float = 0.0,
    **kwargs: Any,
) -> ChatOpenAI:
    """Cria uma instância do modelo LLM usando LiteLLM Proxy.

    Esta é a função principal para obter modelos LLM no projeto.
    Usa ChatOpenAI apontando para o proxy LiteLLM, que gerencia a comunicação
    com Azure OpenAI.

    Args:
        model_type (str): Tipo do modelo ('mini', 'standard', 'nano', 'think').
        temperature (float, optional): Temperatura do modelo. Defaults to 0.0.
            Nota: Modelos de raciocínio (tipo 'think') usam temperature=1.0 automaticamente.
        **kwargs: Parâmetros adicionais para passar ao ChatOpenAI.

    Returns:
        ChatOpenAI: Instância configurada do modelo LLM.

    Examples:
        >>> # Uso básico
        >>> model = get_model("mini", temperature=0.7)
        >>> response = model.invoke("Hello!")

        >>> # Com modelos de raciocínio (think)
        >>> model = get_model("think")
        >>> response = model.invoke("Resolva: 2+2")

        >>> # Com LangChain chains
        >>> chain = prompt | get_model("standard")

        >>> # Com LangGraph
        >>> def my_node(state):
        ...     model = get_model("mini")
        ...     return model.invoke(state["messages"])
    """
    # Obtém configurações do modelo
    config = get_model_config(model_type)

    # Para modelos de raciocínio (think), força temperature=1.0
    # O proxy LiteLLM/Azure OpenAI exige isso para modelos GPT-5
    if model_type.lower() == "think":
        temperature = 1.0
        logger.debug(
            "Modelo 'think' detectado - forçando temperature=1.0 (exigido pelo Azure)"
        )

    # Prepara parâmetros do ChatOpenAI
    openai_config = {
        "model": config["model"],
        "base_url": config["base_url"],
        "api_key": config["api_key"],
        "temperature": temperature,
        "max_tokens": config["max_tokens"],
        "timeout": config["timeout"],
        "max_retries": config["max_retries"],
    }

    # IMPORTANTE: Os parâmetros customizados de retry (num_retries, retry_policy, etc.)
    # NÃO são suportados pela API OpenAI/LiteLLM em model_kwargs.
    # O retry é gerenciado pelo parâmetro max_retries do ChatOpenAI e pelo LiteLLM Proxy.
    # Removemos completamente a tentativa de passar esses parâmetros via model_kwargs.

    # Sobrescreve com argumentos adicionais
    model_kwargs = kwargs.pop("model_kwargs", {})

    # Parâmetros não reconhecidos pelo ChatOpenAI devem ir para model_kwargs
    _non_standard = ["response_format"]
    for key in _non_standard:
        if key in kwargs:
            model_kwargs[key] = kwargs.pop(key)

    if model_kwargs:
        openai_config["model_kwargs"] = model_kwargs

    openai_config.update(kwargs)

    # Remove parâmetros None
    openai_config = {k: v for k, v in openai_config.items() if v is not None}

    logger.info(
        f"Criando ChatOpenAI via proxy para modelo: {config['model']} (temperature={temperature})"
    )

    # Debug: Log da configuração (sem API key)
    debug_config = {k: v for k, v in openai_config.items() if k != "api_key"}
    logger.debug(f"Configuração ChatOpenAI: {debug_config}")

    try:
        return ChatOpenAI(**openai_config)
    except Exception as e:
        logger.error(f"Erro ao criar ChatOpenAI: {e}")
        logger.error(f"Configuração que causou erro: {debug_config}")
        raise


# Alias para compatibilidade com código legado
get_llm_model = get_model
