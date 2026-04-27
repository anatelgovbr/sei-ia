# Azure OpenAI

> Integração com modelos LLM e Embeddings via LiteLLM Proxy

## Arquitetura

O SEI-IA Assistente utiliza **LiteLLM Proxy** para comunicação com Azure OpenAI. Isso permite:

- Centralizar credenciais e configurações no proxy
- Facilitar troca de modelos sem alterar código
- Suportar múltiplos providers (Azure, OpenAI, Anthropic, etc.)

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Assistente    │ ──── │  LiteLLM Proxy  │ ──── │  Azure OpenAI   │
│   (ChatOpenAI)  │      │  localhost:4000 │      │  (modelos LLM)  │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

## Model Types

O sistema abstrai os modelos em 4 tipos:

| Model Type | Uso |
|------------|-----|
| `standard` | Modelo principal para respostas completas |
| `mini` | Modelo rápido e econômico |
| `nano` | Modelo leve (opcional) |
| `think` | Modelo de raciocínio (força temperature=1.0) |

> **Importante**: Os nomes reais dos modelos (ex: gpt-4.1, gpt-5.1, o4-mini) são configurados
> exclusivamente no LiteLLM Proxy. A aplicação apenas conhece os tipos abstratos acima.

## Configuração

### Variáveis de Ambiente

```bash
# URL do proxy LiteLLM
ASSISTENTE_LITELLM_PROXY_URL=http://localhost:4000

# API key do proxy (opcional, depende da configuração do proxy)
# ASSISTENTE_LITELLM_PROXY_API_KEY=sua_api_key

# Limites de contexto e output
ASSISTENTE_OUTPUT_TOKENS_STANDARD_MODEL=32768
ASSISTENTE_CTX_LEN_STANDARD_MODEL=250000
```

### Configuração do LiteLLM Proxy

O proxy deve ser configurado separadamente com os modelos Azure OpenAI.

**Estrutura básica do `litellm_config.yaml`:**

```yaml
model_list:
  - model_name: standard           # Nome que a aplicação usa
    litellm_params:
      model: azure/<seu-modelo>    # Modelo real no Azure
      api_base: https://seu-endpoint.openai.azure.com/
      api_key: sua_api_key
      api_version: "2024-10-21"

  - model_name: mini
    litellm_params:
      model: azure/<seu-modelo-mini>
      api_base: ...

  - model_name: think
    litellm_params:
      model: azure/<seu-modelo-reasoning>
      api_base: ...

  - model_name: embedding          # Para embeddings
    litellm_params:
      model: azure/text-embedding-3-small
      api_base: ...
```

> **Nota**: Os modelos reais (`azure/<modelo>`) dependem do que você tem disponível
> no seu Azure OpenAI. Consulte a documentação do LiteLLM para mais opções.

## Factory de Modelos

O arquivo `sei_ia/services/llm_models/get_model.py` é o ponto central para obtenção de modelos:

```python
from langchain_openai import ChatOpenAI
from sei_ia.configs.settings_config import settings

def get_model(model_type: str = "mini", temperature: float = 0.0) -> ChatOpenAI:
    """Cria instância do modelo LLM via LiteLLM Proxy."""
    config = get_model_config(model_type)

    # Para modelos de raciocínio, força temperature=1.0
    if model_type.lower() == "think":
        temperature = 1.0

    return ChatOpenAI(
        model=config["model"],               # "standard", "mini", "nano", "think"
        base_url=settings.LITELLM_PROXY_URL, # http://localhost:4000
        api_key=settings.LITELLM_PROXY_API_KEY or "dummy-key",
        temperature=temperature,
        max_tokens=config["max_tokens"],
        timeout=settings.TIMEOUT_API,
        max_retries=settings.MAX_RETRIES,
    )
```

### Uso

```python
from sei_ia.services.llm_models.get_model import get_model

# Modelo padrão (mini)
model = get_model("mini", temperature=0.7)
response = model.invoke("Olá!")

# Modelo de raciocínio
model = get_model("think")
response = model.invoke("Resolva: 2+2")

# Com LangChain chains
chain = prompt | get_model("standard")
```

## Embeddings

Embeddings também são gerados via LiteLLM Proxy:

- Modelo: `text-embedding-3-small`
- Dimensões: 1536
- Máximo de tokens: 8191

**Arquivo**: `sei_ia/services/embedder/embedding_generator.py`

## Tratamento de Erros

O sistema trata erros de conexão com o proxy/Azure:

```python
from litellm.exceptions import APIConnectionError

try:
    response = model.invoke(prompt)
except (httpx.RemoteProtocolError, APIConnectionError) as exc:
    # Erro de conexão - streaming interrompido
    logger.exception(f"Erro de conexão: {exc}")
    raise HTTPException(status_code=500)
```

## Retry e Backoff

O retry é gerenciado em duas camadas:

1. **ChatOpenAI**: `max_retries=5` (configurável via `ASSISTENTE_MAX_RETRIES`)
2. **LiteLLM Proxy**: Configurações de retry do próprio proxy

Variáveis relacionadas:

```bash
ASSISTENTE_MAX_RETRIES=5
ASSISTENTE_BACKOFF_MAX_TRIES=99
ASSISTENTE_BACKOFF_MAX_TIME=240
ASSISTENTE_BACKOFF_INITIAL_WAIT=1.0
```
