# SEI-IA Assistente

Assistente Virtual baseado em IA para o Sistema Eletrônico de Informações (SEI) da ANATEL.

## Pré-requisitos

- Python 3.12 (para desenvolvimento local)
- [uv](https://github.com/astral-sh/uv) (gerenciador de pacotes Python)
- [LiteLLM Proxy](https://docs.litellm.ai/docs/proxy/quick_start) (gateway para modelos LLM)
- Docker (para rodar o LiteLLM Proxy)

## Arquitetura LLM

O projeto utiliza **LiteLLM Proxy** como gateway para comunicação com modelos LLM (Azure OpenAI, OpenAI, etc.):

```
Assistente (API) → LiteLLM Proxy → Azure OpenAI / Outros Providers
```

Isso permite trocar modelos sem alterar código da aplicação.

## Início Rápido

### 1. Configurar o LiteLLM Proxy

Crie o arquivo `litellm_config.yaml` com seus modelos:

```yaml
model_list:
  - model_name: standard
    litellm_params:
      model: azure/<seu-deployment-standard>
      api_base: https://seu-endpoint.openai.azure.com/
      api_key: os.environ/AZURE_API_KEY
      api_version: "2024-10-21"

  - model_name: mini
    litellm_params:
      model: azure/<seu-deployment-mini>
      api_base: https://seu-endpoint.openai.azure.com/
      api_key: os.environ/AZURE_API_KEY
      api_version: "2024-10-21"

  - model_name: embedding
    litellm_params:
      model: azure/text-embedding-3-small
      api_base: https://seu-endpoint.openai.azure.com/
      api_key: os.environ/AZURE_API_KEY
      api_version: "2024-10-21"
```

### 2. Iniciar o LiteLLM Proxy

```bash
# Via Docker (recomendado)
docker run -d \
  --name litellm-proxy \
  -v $(pwd)/litellm_config.yaml:/app/config.yaml \
  -e AZURE_API_KEY=sua_api_key \
  -p 4000:4000 \
  ghcr.io/berriai/litellm:main-latest \
  --config /app/config.yaml

# Verificar se está rodando
curl http://localhost:4000/health
```

### 3. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Editar .env e configurar:
# - ASSISTENTE_LITELLM_PROXY_URL=http://localhost:4000
# - Credenciais do banco de dados
# - Credenciais da API SEI
```

### 4. Acessar a API

- **API**: `http://localhost:8088`
- **Docs (Swagger)**: `http://localhost:8088/docs`
- **Health Check**: `http://localhost:8088/health`

## Desenvolvimento Local

### Instalar dependências

```bash
# Com uv (recomendado)
uv sync

# Ou com pip
pip install -e ".[dev]"
```

### Rodar testes

```bash
uv run pytest tests/e2e/test_service.py
```

### Rodar a aplicação localmente

```bash
uv run uvicorn sei_ia.main:app --reload --port 8088
```

## Tipos de Modelo

A aplicação usa tipos abstratos de modelo. Os modelos reais são configurados no LiteLLM Proxy:

| Tipo | Uso |
|------|-----|
| `standard` | Modelo principal para respostas completas |
| `mini` | Modelo rápido e econômico |
| `nano` | Modelo leve (opcional) |
| `think` | Modelo de raciocínio |

## Documentação

A documentação completa está disponível via MkDocs.

### Gerar e visualizar documentação

```bash
# Instalar dependências de desenvolvimento (se ainda não instalou)
pip install -e ".[dev]"

# Servir documentação localmente (com hot-reload)
mkdocs serve

# Acessar em http://127.0.0.1:8000
```

## Estrutura do Projeto

```
assistente/
├── sei_ia/              # Código fonte principal
│   ├── configs/         # Configurações da aplicação
│   ├── routers/         # Endpoints da API
│   ├── services/        # Serviços e lógica de negócio
│   └── main.py          # Ponto de entrada da aplicação
├── tests/               # Testes automatizados
│   ├── unit/            # Testes unitários
│   ├── integration/     # Testes de integração
│   └── e2e/             # Testes end-to-end
├── docs/                # Documentação MkDocs
├── .env.example         # Exemplo de variáveis de ambiente
├── pyproject.toml       # Configuração do projeto Python
├── mkdocs.yml           # Configuração da documentação
```

## Banco de Dados

O projeto utiliza PostgreSQL com extensão pgvector para armazenamento de embeddings e busca semântica.

### Configuração do Schema

Certifique-se de que o banco de dados possui a extensão pgvector instalada:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
