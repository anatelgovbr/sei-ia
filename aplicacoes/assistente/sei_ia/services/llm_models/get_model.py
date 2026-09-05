"""Método de conexão com LLM via LiteLLM Proxy usando ChatOpenAI."""

import logging
from typing import Any

from langchain_openai import ChatOpenAI

from sei_ia.configs.settings_config import (
    LITELLM_MINI_ALIAS,
    LITELLM_NANO_ALIAS,
    LITELLM_STANDARD_ALIAS,
    settings,
)

logger = logging.getLogger(__name__)

# Papel do pipeline (tag agents:<agent_tag> no LiteLLM, controle de acesso via
# router_settings.enable_tag_filtering) -> tier físico do modelo por trás
# (standard/mini/nano, usado aqui para escolher a janela CTX_LEN_*). Ver
# litellm_config.template.yaml para as tags
# declaradas em cada entrada do model_list.
AGENT_TAG_TO_TIER: dict[str, str] = {
    "principal": "standard",
    "classificador": "mini",
    "busca_web": "mini",
    "explorador": "nano",
    "ocr": "nano",
    "triagem_busca": "nano",
}


def get_model_config(
    agent_tag: str, model_override: str | None = None
) -> dict[str, Any]:
    """Retorna as configurações específicas para o papel de agente solicitado.

    Com o proxy LiteLLM, as configurações são muito mais simples, pois o proxy
    gerencia toda a comunicação com Azure OpenAI.

    Args:
        agent_tag (str): Papel do agente ('principal', 'classificador',
            'explorador', 'ocr', 'busca_web', 'triagem_busca').
            Vira a tag ``agents:<agent_tag>`` mandada ao LiteLLM Proxy.
        model_override (str | None, optional): Alias do LiteLLM Proxy a usar no
            lugar do fixo por `agent_tag` (ex. `"openai/seiia-ds-gemini-pro"`).
            Deve já ter sido validado pelo chamador contra o catálogo ao vivo
            do proxy, ver `services/llm_models/model_catalog.validate_model_override`.

    Returns:
        Dict[str, Any]: Configurações do modelo solicitado.

    Raises:
        ValueError: Se o papel de agente for inválido.
    """
    # Configurações comuns
    base_config = {
        "base_url": settings.LITELLM_PROXY_URL,
        "api_key": settings.LITELLM_PROXY_API_KEY or "dummy-key",
        "timeout": settings.TIMEOUT_API,
        "max_retries": settings.MAX_RETRIES,
    }

    agent_tag_lower = agent_tag.lower()
    tier = AGENT_TAG_TO_TIER.get(agent_tag_lower)
    if tier is None:
        msg = (
            f"Papel de agente desconhecido: {agent_tag}. Papéis válidos: "
            f"{list(AGENT_TAG_TO_TIER)}"
        )
        raise ValueError(msg)

    # O request sempre usa o alias público estável do tier; model_name mantém
    # a identidade física para metadata, telemetria e respostas legadas.
    tier_configs = {
        "standard": {
            "model": LITELLM_STANDARD_ALIAS,
            "model_name": settings.LITELLM_STANDARD_MODEL,  # Para compatibilidade com código legado
            "max_ctx_len": settings.CTX_LEN_STANDARD_MODEL,
        },
        "mini": {
            "model": LITELLM_MINI_ALIAS,
            "model_name": settings.LITELLM_MINI_MODEL,  # Para compatibilidade com código legado
            "max_ctx_len": settings.CTX_LEN_MINI_MODEL,
        },
        "nano": {
            "model": LITELLM_NANO_ALIAS,
            "model_name": settings.LITELLM_NANO_MODEL,  # Para compatibilidade com código legado
            "max_ctx_len": settings.CTX_LEN_NANO_MODEL,
        },
    }

    # Combina configurações base com específicas do tier
    config = {
        **base_config,
        **tier_configs[tier],
        "tags": [f"agents:{agent_tag_lower}"],
    }

    if model_override:
        # Override substitui a identidade inteira do modelo: não há um "nome de
        # deployment" separado pra um alias liberado dinamicamente, então
        # `model_name` (campo usado na metadata de resposta) acompanha `model`.
        # A tag continua sendo a do papel — todos os aliases de override liberados
        # carregam a mesma tag `agents:principal` no litellm_config.
        config["model"] = model_override
        config["model_name"] = model_override

    return config


def get_summarize_model() -> dict:
    """Retorna a configuração para o modelo de sumarização.

    Returns:
        Dict[str, Any]: Configurações do modelo de sumarização.
    """
    model_config = get_model_config(settings.SUMMARIZE_MODEL)
    return {
        **model_config,
        "token_encoding_name": settings.SUMMARIZE_ENCODING_NAME,
        "chunk_size": settings.SUMMARIZE_CHUNK_SIZE,
    }


def get_model(
    agent_tag: str,
    temperature: float | None = None,
    model_override: str | None = None,
    **kwargs: Any,
) -> ChatOpenAI:
    """Cria uma instância do modelo LLM usando LiteLLM Proxy.

    Esta é a função principal para obter modelos LLM no projeto.
    Usa ChatOpenAI apontando para o proxy LiteLLM, que gerencia a comunicação
    com Azure OpenAI.

    Args:
        agent_tag (str): Papel do agente ('principal', 'classificador',
            'explorador', 'ocr', 'busca_web', 'triagem_busca').
        temperature (float | None, optional): Temperatura do modelo. Quando
            ``None``, o campo não é enviado e o proxy/modelo aplica seu default.
        model_override (str | None, optional): Alias do LiteLLM Proxy a usar no
            lugar do fixo por `agent_tag`. Deve já ter sido validado pelo
            chamador contra o catálogo ao vivo do proxy, ver
            `services/llm_models/model_catalog.validate_model_override`.
        **kwargs: Parâmetros adicionais para passar ao ChatOpenAI.

    Returns:
        ChatOpenAI: Instância configurada do modelo LLM.

    Examples:
        >>> # Uso básico
        >>> model = get_model("classificador", temperature=0.7)
        >>> response = model.invoke("Hello!")

        >>> # Com LangChain chains
        >>> chain = prompt | get_model("principal")

        >>> # Com LangGraph
        >>> def my_node(state):
        ...     model = get_model("classificador")
        ...     return model.invoke(state["messages"])
    """
    # Obtém configurações do modelo
    config = get_model_config(agent_tag, model_override=model_override)

    # Prepara parâmetros do ChatOpenAI
    openai_config = {
        "model": config["model"],
        "base_url": config["base_url"],
        "api_key": config["api_key"],
        "timeout": config["timeout"],
        "max_retries": config["max_retries"],
    }
    if temperature is not None:
        openai_config["temperature"] = temperature

    # IMPORTANTE: Os parâmetros customizados de retry (num_retries, retry_policy, etc.)
    # NÃO são suportados pela API OpenAI/LiteLLM em model_kwargs.
    # O retry é gerenciado pelo parâmetro max_retries do ChatOpenAI e pelo LiteLLM Proxy.
    # Removemos completamente a tentativa de passar esses parâmetros via model_kwargs.

    # Sobrescreve com argumentos adicionais
    model_kwargs = kwargs.pop("model_kwargs", {})

    # Parâmetros não reconhecidos pelo ChatOpenAI devem ir para model_kwargs.
    _non_standard = ["response_format"]
    for key in _non_standard:
        if key in kwargs:
            model_kwargs[key] = kwargs.pop(key)

    if model_kwargs:
        openai_config["model_kwargs"] = model_kwargs

    openai_config.update(kwargs)

    # "tags" vai por `extra_body` (campo nativo do ChatOpenAI pra parâmetros
    # extras do corpo da requisição), nunca como kwarg solto: colidiria com o
    # `tags`/`config` do próprio Runnable do LangChain (rastreio
    # LangSmith/Langfuse), que é outra coisa. É o que o LiteLLM lê pra tag
    # filtering (`router_settings.enable_tag_filtering`). Um `extra_body` já
    # vindo em kwargs (ex. rebind num client reaproveitado pra outro papel via
    # `.bind(extra_body={"tags": [...]})`) tem prioridade sobre a tag default
    # de `agent_tag`.
    openai_config["extra_body"] = {
        "tags": config.get("tags"),
        **openai_config.get("extra_body", {}),
    }

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
    except Exception:
        logger.exception("Erro ao criar ChatOpenAI. Configuração: %s", debug_config)
        raise


# Alias para compatibilidade com código legado
get_llm_model = get_model
