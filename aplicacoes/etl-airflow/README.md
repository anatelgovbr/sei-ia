# SEI-Similaridade Jobs

[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)
[![Airflow](https://img.shields.io/badge/airflow-2.9.3-orange)](https://airflow.apache.org/)

Sistema de ETL que processa dados do SEI (Sistema Eletrônico de Informações) e disponibiliza para outros sistemas.

## O que o Jobs faz

Ele é responsável pelo ETL:

| Pipeline | Destino | Consumidor |
|----------|---------|------------|
| **Indexação de Processos** | Apache Solr | `api_sei` (similaridade de processos) |
| **Indexação de Documentos** | Apache Solr | `api_sei` (Doc2Doc) |
| **Geração de Embeddings** | PostgreSQL + pgvector | Assistente (RAG) |

```
SEI API ──► Jobs (ETL) ──► Solr ──► api_sei (Similaridade)
                      └──► PostgreSQL ──► Assistente (RAG)
```

## Documentação Completa

A documentação completa está disponível via MkDocs:

```bash
# Instalar dependências de documentação
uv sync --group docs

# Executar servidor local
mkdocs serve

# Acessar em http://localhost:8000
```

Para build estático:
```bash
mkdocs build
# Arquivos gerados em site/
```

## Quick Start

### Pré-requisitos

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (gerenciador de pacotes)
- Docker e Docker Compose
- Acesso à API do SEI
- LiteLLM Proxy configurado (para embeddings)

### Instalação

```bash
git clone https://git.anatel.gov.br/processo_eletronico/sei-ia/sei-similaridade/jobs.git
cd jobs
uv sync
```

### Execução Local

```bash
# API REST
uvicorn jobs.api:app --reload --host 0.0.0.0 --port 8000

# Airflow
airflow db init
airflow webserver --port 8080 &
airflow scheduler
```

### Docker

```bash
docker-compose -f docker-compose-local-desenv.yml up -d
```

## LiteLLM Proxy

O Jobs utiliza **LiteLLM Proxy** para geração de embeddings, permitindo abstrair diferentes provedores. O padrão é **Azure OpenAI**.

```
Jobs ──► LiteLLM Proxy ──► Azure OpenAI
              │
              └── Roteia para o provider configurado
```

O Jobs obtém automaticamente as informações do modelo (nome, versão da API) consultando o endpoint `/model/info` do LiteLLM Proxy.

### Subindo um container LiteLLM com Azure OpenAI

**1. Criar arquivo de configuração `litellm_config.yaml`:**

Teste de CICD ETL em `dev` disparado em 2026-03-18 para validar rollout isolado do stack ETL e healthcheck do `etl-airflow-api`.

```yaml
model_list:
  - model_name: embedding
    litellm_params:
      model: azure/<seu-deployment-name>
      api_base: os.environ/AZURE_API_BASE
      api_key: os.environ/AZURE_API_KEY
      api_version: "2024-10-21"
```

**2. Subir o container:**

```bash
docker run -d \
  --name litellm-proxy \
  -v $(pwd)/litellm_config.yaml:/app/config.yaml \
  -e AZURE_API_KEY=sua-chave-azure \
  -e AZURE_API_BASE=https://seu-recurso.openai.azure.com/ \
  -p 4000:4000 \
  ghcr.io/berriai/litellm:main-stable \
  --config /app/config.yaml
```

**3. Testar a conexão:**

```bash
# Verificar modelos disponíveis
curl http://localhost:4000/model/info

# Testar geração de embedding
curl http://localhost:4000/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "embedding", "input": ["teste de embedding"]}'
```

### Variáveis de ambiente Azure

| Variável | Descrição |
|----------|-----------|
| `AZURE_API_KEY` | Chave de API do Azure OpenAI |
| `AZURE_API_BASE` | URL base do recurso Azure (ex: `https://meu-recurso.openai.azure.com/`) |

### Configuração no Jobs

```bash
export LITELLM_PROXY_URL=http://litellm:4000
export LITELLM_MODEL_NAME=embedding
```

## Variáveis de Ambiente

### Obrigatórias

| Variável | Descrição |
|----------|-----------|
| `SOLR_ADDRESS` | URL do Apache Solr |
| `SEI_API_DB_ADDRESS` | URL da API do SEI |
| `DB_SEIIA_HOST` | Host do PostgreSQL (embeddings) |
| `LITELLM_PROXY_URL` | URL do LiteLLM Proxy |

### SEI API

| Variável | Default | Descrição |
|----------|---------|-----------|
| `SEI_API_DB_ADDRESS` | - | URL base da API do SEI |
| `SEI_API_DB_USER` | `Usuario_IA` | Usuário da API |
| `SEI_API_DB_TIMEOUT` | `120` | Timeout em segundos |
| `SEI_API_MAX_CONCURRENCY` | `15` | Requisições concorrentes |

### Apache Solr

| Variável | Default | Descrição |
|----------|---------|-----------|
| `SOLR_ADDRESS` | - | URL do Solr |
| `SOLR_USER` | - | Usuário |
| `SOLR_PASSWORD` | - | Senha |
| `SOLR_MLT_PROCESS_CORE` | - | Core para processos |
| `SOLR_MLT_JURISPRUDENCE_CORE` | `documentos_bm25` | Core para documentos |

### LiteLLM e Embeddings

| Variável | Default | Descrição |
|----------|---------|-----------|
| `LITELLM_PROXY_URL` | `http://localhost:4000` | URL do LiteLLM Proxy |
| `LITELLM_MODEL_NAME` | `embedding` | Nome do modelo no proxy |
| `MAX_LENGTH_CHUNK_SIZE` | `1512` | Tamanho do chunk (tokens) |
| `CHUNK_OVERLAP` | `50` | Overlap entre chunks |

### PostgreSQL (Embeddings)

| Variável | Default | Descrição |
|----------|---------|-----------|
| `DB_SEIIA_HOST` | - | Host |
| `DB_SEIIA_PORT` | `5432` | Porta |
| `DB_SEIIA_USER` | - | Usuário |
| `DB_SEIIA_PWD` | - | Senha |
| `DB_SEIIA_ASSISTENTE` | `SEI_LLM` | Nome do banco |
| `DB_SEIIA_ASSISTENTE_SCHEMA` | `sei_llm` | Schema |

### Redis (Cache)

| Variável | Default | Descrição |
|----------|---------|-----------|
| `JOBS_REDIS_URI` | `redis://redis_cache:6379/0` | URI de conexão |
| `JOBS_CACHE_ENABLED` | `true` | Habilitar cache |

### Airflow e Indexação

| Variável | Default | Descrição |
|----------|---------|-----------|
| `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` | - | Connection string |
| `INDEX_PROCESS_BATCH_SIZE` | `5` | Lote de processos |
| `EMBEDDING_BATCH_SIZE` | `10` | Lote de embeddings |
| `LIMIT_QUEUE` | `100` | Máximo de DAGs simultâneas |

## DAGs do Airflow

| DAG | Schedule | Função |
|-----|----------|--------|
| `process_update_index` | `*/1 * * * *` | Enfileira processos |
| `process_indexing` | Triggered | Indexa processos no Solr |
| `documents_update_index` | `*/1 * * * *` | Enfileira documentos |
| `documents_indexing` | Triggered | Indexa documentos no Solr |
| `documents_update_embedding` | `*/1 * * * *` | Enfileira para embeddings |
| `documents_embedding_generation` | Triggered | Gera embeddings |
| `cache_invalidation` | `*/5 * * * *` | Remove itens cancelados |
| `system_clean_airflow_logs` | `0 20 * * *` | Limpa logs antigos |
| `system_create_mlt_weights_config` | `0 * * * *` | Atualiza pesos MLT |

## Estrutura do Projeto

```
jobs/
├── jobs/                    # Pacote principal
│   ├── api.py               # FastAPI
│   ├── envs.py              # Variáveis de ambiente
│   ├── api_rest/            # Endpoints REST
│   ├── dags/                # DAGs do Airflow
│   │   ├── dag_objects/     # Definições das DAGs
│   │   ├── preprocessing/   # ProcessFromSEI, ProcessTransformed
│   │   └── database/        # GenericSender (Solr)
│   ├── services/
│   │   ├── cache/           # Cliente Redis
│   │   └── embedder/        # LiteLLMEmbeddingProvider
│   └── db_models/           # SEIDBHandler, modelos
├── docs/                    # Documentação MkDocs
├── tests/                   # Testes
└── mkdocs.yml               # Configuração MkDocs
```

Validacao deploy ETL via CI em 2026-03-18 15:06 - ajuste de wait oneshot.

Teste CI apos otimizar cache do jobs_api.dockerfile em 2026-03-18T16:08:05-03:00
