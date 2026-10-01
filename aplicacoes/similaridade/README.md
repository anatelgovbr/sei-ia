# sei-similaridade API

API de Recomendação de Processos e Documentos do Sistema Eletrônico de Informações (SEI).

## Visão Geral

O **sei-similaridade** é uma API RESTful que encontra processos e documentos similares usando técnicas de Information Retrieval.

| Método | Descrição |
|--------|-----------|
| **WMLT** | Weighted More Like This - recomendação de processos com pesos por área de negócio |
| **Doc2Doc** | Busca de jurisprudências similares via MLT |

## Pré-requisitos

- Python 3.10+
- Apache Solr 9.0+
- PostgreSQL 15+

## Instalação

```bash
# Clonar repositório
git clone https://git.anatel.gov.br/processo_eletronico/sei-ia/sei-similaridade.git
cd sei-similaridade/api

# Instalar dependências
uv sync

# Configurar variáveis de ambiente
cp .env.example .env
nano .env

# Executar
uv run gunicorn -k uvicorn.workers.UvicornH11Worker api_sei.main:app --bind 0.0.0.0:8000
```

## Endpoints

| Endpoint | Descrição |
|----------|-----------|
| `GET /process-recommenders/weighted-mlt-recommender/recommendations/{id_protocolo}` | Processos similares (WMLT) |
| `GET /process-recommenders/weighted-mlt-recommender/indexed-ids/{id_protocolo}` | Verificar indexação |
| `GET /document-recommenders/mlt-recommender/recommendations` | Jurisprudências similares (Doc2Doc) |

## Documentação da API

Após iniciar a aplicação:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Documentação Completa

A documentação detalhada está disponível via MkDocs:

```bash
# Instalar mkdocs (se necessário)
uv add mkdocs mkdocs-material

# Executar servidor de documentação
mkdocs serve
```

Acesse http://localhost:8000 para visualizar:

- Arquitetura do sistema
- Fluxo detalhado do WMLT (8 etapas)
- Sistema de pesos e configuração
- Parâmetro text_weight do Doc2Doc
- Configuração do Solr e PostgreSQL
- Referência completa da API

## Estrutura do Projeto

```
api/
├── api_sei/              # Código-fonte
│   ├── routers/          # Endpoints
│   ├── services/         # Lógica de negócio
│   ├── db_models/        # Modelos Solr/PostgreSQL
│   └── resources/        # Utilitários (BM25, etc)
├── docs/                 # Documentação MkDocs
├── tests/                # Testes
└── pyproject.toml        # Dependências
``
