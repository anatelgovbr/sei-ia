# Instalação

Este guia mostra como instalar e executar a API sei-similaridade.

---

## Pré-requisitos

Antes de começar, você precisa ter:

| Componente | Versão | Descrição |
|------------|--------|-----------|
| Python | 3.10+ | Linguagem de programação |
| Apache Solr | 9.0+ | Motor de busca textual |
| PostgreSQL | 15+ | Banco de dados |

---

## Instalação

```bash
# Clonar o repositório
git clone https://git.anatel.gov.br/processo_eletronico/sei-ia/sei-similaridade.git
cd sei-similaridade/api

# Instalar dependências com uv
uv sync

# Copiar arquivo de configuração
cp .env.example .env

# Editar variáveis de ambiente
nano .env

# Iniciar servidor
uv run gunicorn -k uvicorn.workers.UvicornH11Worker api_sei.main:app --bind 0.0.0.0:8000
```

---

## Documentação da API

A API possui documentação interativa automática:

| Interface | URL | Descrição |
|-----------|-----|-----------|
| Swagger UI | http://localhost:8000/docs | Interface interativa |
| ReDoc | http://localhost:8000/redoc | Documentação estática |
| OpenAPI JSON | http://localhost:8000/openapi.json | Schema OpenAPI |

---

## Estrutura de Diretórios

```
api/
├── api_sei/                 # Código-fonte principal
│   ├── main.py              # Entry point FastAPI
│   ├── envs.py              # Variáveis de ambiente
│   ├── routers/             # Endpoints da API
│   ├── services/            # Lógica de negócio
│   ├── db_models/           # Modelos de banco
│   ├── pydantic_models/     # Schemas de validação
│   ├── repository/          # Persistência
│   └── resources/           # Utilitários (BM25, etc)
├── configs/                 # Configurações Solr
├── tests/                   # Testes
├── docs/                    # Documentação
└── pyproject.toml           # Dependências
```

---

## Próximos Passos

- [Variáveis de Ambiente](environment-variables.md) - Configurar conexões
- [WMLT](../wmlt/index.md) - Entender recomendação de processos
- [Doc2Doc](../doc2doc/index.md) - Entender busca de jurisprudência
