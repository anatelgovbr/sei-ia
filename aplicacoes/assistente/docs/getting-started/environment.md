# Variáveis de Ambiente / Environment Variables

> Configuração completa das variáveis de ambiente do SEI-IA Assistente

## Visão Geral / Overview

O SEI-IA Assistente utiliza [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) para gerenciamento de configurações. Todas as variáveis são carregadas do arquivo `.env` na raiz do projeto.

---

## Arquitetura LiteLLM Proxy

O projeto utiliza **LiteLLM Proxy** para comunicação com modelos LLM. Isso significa que:

- As credenciais e endpoints dos modelos são configurados **no proxy**, não na aplicação
- A aplicação apenas conhece a URL do proxy e os tipos de modelo (`standard`, `mini`, `nano`, `think`)
- O proxy gerencia toda a comunicação com Azure OpenAI ou outros providers

```
Aplicação → LiteLLM Proxy → Azure OpenAI
                         → Outros providers (OpenAI, Anthropic, etc.)
```

---

## Variáveis Obrigatórias / Required Variables

### LiteLLM Proxy

```bash
# URL do proxy LiteLLM (obrigatório)
ASSISTENTE_LITELLM_PROXY_URL=http://localhost:4000

# API key para autenticação no proxy (opcional, depende da config do proxy)
# ASSISTENTE_LITELLM_PROXY_API_KEY=sua_api_key
```

### Banco de Dados PostgreSQL

```bash
# Conexão com PostgreSQL (obrigatório)
DB_SEIIA_HOST=localhost
DB_SEIIA_PORT=5432
DB_SEIIA_USER=seiia
DB_SEIIA_PWD=sua_senha_segura
DB_SEIIA_ASSISTENTE=SEI_LLM
DB_SEIIA_ASSISTENTE_SCHEMA=sei_llm
```

### SEI API

```bash
# Integração com o SEI (obrigatório)
SEI_API_DB_ADDRESS=https://api-sei.exemplo.gov.br
SEI_API_DB_IDENTIFIER_SERVICE=seu_token_servico
```

---

## Variáveis Opcionais / Optional Variables

### Aplicação

```bash
# Configurações gerais
ASSISTENTE_PORT=8088                    # Porta da API (default: 8088)
ENVIRONMENT=prod                         # Ambiente: dev, homol, prod
DEBUG=false                              # Modo debug
LOG_LEVEL=ERROR                          # Nível de log: DEBUG, INFO, WARNING, ERROR
```

### Configurações de Modelos

Os limites de contexto e output são configurados por tipo de modelo:

```bash
# Modelo Standard
ASSISTENTE_OUTPUT_TOKENS_STANDARD_MODEL=32768
ASSISTENTE_CTX_LEN_STANDARD_MODEL=250000

# Modelo Mini
ASSISTENTE_OUTPUT_TOKENS_MINI_MODEL=32000
ASSISTENTE_CTX_LEN_MINI_MODEL=250000

# Modelo Nano (opcional)
ASSISTENTE_OUTPUT_TOKENS_NANO_MODEL=30000
ASSISTENTE_CTX_LEN_NANO_MODEL=128000

# Modelo Think (para raciocínio)
ASSISTENTE_OUTPUT_TOKENS_THINK_MODEL=65000
ASSISTENTE_CTX_LEN_THINK_MODEL=128000
```

> **Nota**: Os nomes reais dos modelos (gpt-4.1, gpt-5.1, o4-mini, etc.) são configurados no LiteLLM Proxy, não na aplicação.

### Embeddings

```bash
# Modelo de embeddings (via LiteLLM Proxy)
ASSISTENTE_EMBEDDING_MODEL=text-embedding-3-small
ASSISTENTE_MAX_LENGTH_CHUNK_SIZE=1512
ASSISTENTE_CHUNK_OVERLAP=50
```

### Redis Cache

```bash
# Cache (opcional, mas recomendado)
ASSISTENTE_REDIS_URI=redis://localhost:6379/0
ASSISTENTE_CACHE_ENABLED=true
ASSISTENTE_CACHE_TTL_SECONDS=120
ASSISTENTE_CACHE_MAX_CONNECTIONS=100
ASSISTENTE_CACHE_COMPRESS=true
ASSISTENTE_CACHE_KEY_PREFIX=seiia:doc:
```

### RAG (Retrieval-Augmented Generation)

```bash
# Configurações de RAG
TOP_K_DOCUMENTS=5                        # Número de documentos a recuperar
MIN_SIMILARITY=0.3                       # Similaridade mínima (0.0 a 1.0)
ASSISTENTE_N_QUESTIONS=5                 # Perguntas adicionais para RAG enhanced
```

### Sumarização

```bash
# Configurações de sumarização
ASSISTENTE_SUMMARIZE_MODEL=mini
ASSISTENTE_SUMMARIZE_CHUNK_SIZE=16000
ASSISTENTE_SUMMARIZE_CHUNK_MAX_OUTPUT=4000
ASSISTENTE_SUMMARIZE_TOKENS_LIMIT_MULTIPLIER=5.0
```

### Timeouts

```bash
# Timeouts em segundos
ASSISTENTE_TIMEOUT_API=900               # Timeout geral da API (15 min)
ASSISTENTE_TIMEOUT_GET_DOC=120           # Timeout para buscar documentos
SEI_API_DB_TIMEOUT=120                   # Timeout da API SEI
```

### Azure Web Search (Bing)

```bash
# Busca web (opcional)
PROJECT_ENDPOINT=https://seu-projeto.cognitiveservices.azure.com
AZURE_WEB_AGENT_ID=seu_agent_id
BING_CONNECTION_NAME=bing_connection
MODEL_DEPLOYMENT_NAME=gpt-4o
```

### Observabilidade

```bash
# Langfuse
ASSISTENTE_USE_LANGFUSE=false
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_URL=http://langfuse:3005

# OpenTelemetry (requer extra otel)
ENABLE_OTEL_METRICS=false
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

---

## Exemplo de .env Completo

```bash
# ====================
# BANCO DE DADOS
# ====================
DB_SEIIA_HOST=postgres
DB_SEIIA_PORT=5432
DB_SEIIA_USER=seiia
DB_SEIIA_PWD=sua_senha_segura
DB_SEIIA_ASSISTENTE=SEI_LLM
DB_SEIIA_ASSISTENTE_SCHEMA=sei_llm
DB_SEIIA_POOL_MIN_SIZE=1
DB_SEIIA_POOL_MAX_SIZE=10

# ====================
# LITELLM PROXY
# ====================
# O proxy gerencia as credenciais dos modelos Azure OpenAI
ASSISTENTE_LITELLM_PROXY_URL=http://litellm-proxy:4000
# ASSISTENTE_LITELLM_PROXY_API_KEY=opcional

# ====================
# CONFIGURACOES DE MODELOS
# ====================
# Limites de contexto e output (os nomes dos modelos sao configurados no proxy)
ASSISTENTE_OUTPUT_TOKENS_STANDARD_MODEL=32768
ASSISTENTE_CTX_LEN_STANDARD_MODEL=250000
ASSISTENTE_OUTPUT_TOKENS_MINI_MODEL=32000
ASSISTENTE_CTX_LEN_MINI_MODEL=250000

# ====================
# EMBEDDINGS
# ====================
ASSISTENTE_EMBEDDING_MODEL=text-embedding-3-small
ASSISTENTE_MAX_LENGTH_CHUNK_SIZE=1512
ASSISTENTE_CHUNK_OVERLAP=50

# ====================
# SEI API
# ====================
SEI_API_DB_ADDRESS=https://api-sei.exemplo.gov.br
SEI_API_DB_IDENTIFIER_SERVICE=token_servico
SEI_API_DB_USER=Usuario_IA
SEI_API_DB_TIMEOUT=120
SEI_API_SEMAPHORE=30

# ====================
# REDIS
# ====================
ASSISTENTE_REDIS_URI=redis://redis:6379/0
ASSISTENTE_CACHE_ENABLED=true
ASSISTENTE_CACHE_TTL_SECONDS=120

# ====================
# APLICACAO
# ====================
ASSISTENTE_PORT=8088
ENVIRONMENT=prod
LOG_LEVEL=ERROR
ASSISTENTE_VERIFY_SSL=false
```

---

## Tipos de Modelo

O sistema suporta 4 tipos de modelo, configurados no LiteLLM Proxy:

| Tipo | Uso | Context Length | Output Tokens |
|------|-----|----------------|---------------|
| `standard` | Modelo principal para respostas completas | 250k | 32k |
| `mini` | Modelo rápido para tarefas simples | 250k | 32k |
| `nano` | Modelo leve (opcional) | 128k | 30k |
| `think` | Modelo de raciocínio para análises complexas | 128k | 65k |

> **Importante**: O modelo `think` força `temperature=1.0` automaticamente, conforme exigido pelo Azure OpenAI para modelos de raciocínio.

---

## Validação das Variáveis

O sistema valida automaticamente as variáveis obrigatórias na inicialização. Se alguma estiver faltando, você verá um erro como:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
DB_SEIIA_HOST
  Field required [type=missing, input_value={...}, input_type=dict]
```

---

## Referência do Código

Arquivo de configuração: `sei_ia/configs/settings_config.py`
