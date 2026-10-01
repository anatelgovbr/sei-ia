# SEI-IA Assistente

> Assistente Virtual baseado em Inteligência Artificial para o Sistema Eletrônico de Informações (SEI)

[![Release](https://img.shields.io/github/v/release/Anatel/sei-ia)](https://img.shields.io/github/v/release/Anatel/sei-ia)
[![Build status](https://img.shields.io/github/actions/workflow/status/Anatel/sei-ia/main.yml?branch=main)](https://github.com/Anatel/sei-ia/actions/workflows/main.yml?query=branch%3Amain)
[![License](https://img.shields.io/github/license/Anatel/sei-ia)](https://img.shields.io/github/license/Anatel/sei-ia)

---

## Visão Geral / Overview

O **SEI-IA Assistente** é uma aplicação de inteligência artificial desenvolvida para auxiliar usuários no manejo de processos no SEI. Utiliza modelos de linguagem de grande escala (LLMs) para fornecer respostas inteligentes, sumarização de documentos e busca semântica avançada.

### Principais Funcionalidades / Key Features

| Funcionalidade | Descrição |
|----------------|-----------|
| **Perguntas e Respostas** | Responde perguntas sobre documentos do SEI. |
| **Sumarização** | Resume documentos extensos mantendo as informações essenciais |
| **Correção Gramatical** | Revisa e corrige textos com preservação do estilo original |
| **Busca Web** | Pesquisa e coleta de fontes com as ferramentas do Session |
| **Multi-modelo** | Papéis internos associados aos tiers standard, mini e nano |


O único endpoint de chat é `/llm_lang/session_stream`, com resposta SSE.
Somente RAG, pergunta e seus auxiliares diretos permanecem em `scripts/legado/`,
sem republicação de rotas e sem suporte operacional. A infraestrutura de embeddings
e o lifespan de inicialização com bootstrap de banco permanecem ativos em `sei_ia/`.
---


## Estrutura do Projeto / Project Structure

```
assistente/
├── sei_ia/                     # Código fonte principal ativo
│   ├── main.py                # Entry point FastAPI e lifespan
│   ├── agents/                # Agentes ativos
│   │   ├── session_agent/     # Agente do chat público (Session)
│   │   ├── websearch/         # Ferramentas de busca web (SearXNG/crawl)
│   │   └── prompts/           # Prompts do sistema
│   ├── routers/               # Endpoints da API (session, feedback, healthcheck)
│   ├── services/
│   │   ├── llm_models/        # Configuração de modelos e citações de stream
│   │   ├── embedder/          # Geração de embeddings e pipeline de inicialização
│   │   ├── session_fs/        # Gerenciamento de filesystem e sessões
│   │   └── cache/             # Cliente Redis
│   ├── data/                  # Modelos e ETL
│   │   ├── database/          # Conexões, bootstrap e ORM
│   │   ├── etl/               # Extração de documentos (doc_content)
│   │   └── pydantic_models.py
│   ├── configs/               # Configurações (settings_config)
│   └── middleware/            # Middlewares FastAPI
├── scripts/                   # Scripts de diagnóstico e testes
│   ├── smoke_session_host.py  # Smoke local do endpoint de sessão
│   ├── smoke_helpers.py       # Helpers ativos de diagnóstico
│   └── legado/                # Arquivo histórico de RAG e pergunta
├── tests/                     # Testes (unit, integration, e2e)
├── docs/                      # Documentação ativa da aplicação
├── pyproject.toml             # Dependências
└── assistente.dockerfile      # Container Docker
```

---

## Navegação da Documentação / Documentation Navigation

### Início Rápido / Getting Started
- [Instalação](getting-started/installation.md)
- [Variáveis de Ambiente](getting-started/environment.md)
- [Quickstart](getting-started/quickstart.md)

### Arquitetura / Architecture
- [Visão Geral](architecture/overview.md)
- [Componentes](architecture/components.md)

### API
- [Endpoints](api/endpoints.md)
- [Modelos de Dados](api/models.md)
- [Exemplos de Uso](api/examples.md)


### Agentes / Agents
- [Visão Geral](agents/overview.md)
- [Busca Web](agents/websearch.md)

### Arquivo Histórico (Legado)
- Código e documentação de RAG e pergunta em `scripts/legado/` (consulte `scripts/legado/README.md`)

### Prompts
- [Prompts de Sistema](prompts/system-prompts.md)
- [Prompts de Intenção](prompts/intent-prompts.md)
- [Prompts de Geração](prompts/generation-prompts.md)

### Integrações / Integrations
- [Azure OpenAI](integrations/azure-openai.md)
- [SEI API](integrations/sei-api.md)
- [PostgreSQL + pgvector](integrations/postgresql.md)
- [Redis](integrations/redis.md)
- [Observabilidade](integrations/observability.md)

---

## Versões e Compatibilidade / Versions

| Componente | Versão |
|------------|--------|
| Python | 3.12 |
| FastAPI | 0.115.8 |
| LangChain | 0.3.17 |
| LangGraph | 0.3.21 |
| PostgreSQL | 13+ (com pgvector) |

---

## Links Úteis / Useful Links

- [Repositório GitHub](https://github.com/Anatel/sei-ia)
