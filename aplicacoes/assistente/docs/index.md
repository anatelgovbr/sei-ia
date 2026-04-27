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
| **Busca Web** | Integração com Bing para pesquisas na internet quando necessário |
| **Multi-modelo** | Suporte a múltiplos tipos de modelo: standard, mini, e modelos de raciocínio |

---


## Estrutura do Projeto / Project Structure

```
assistente/
├── sei_ia/                     # Código fonte principal
│   ├── main.py                # Entry point FastAPI
│   ├── agents/                # Agentes LLM e workflows
│   │   ├── chat_completion_graph.py
│   │   ├── pergunta/          # Handler de perguntas + RAG
│   │   ├── summarize/         # Sumarização
│   │   ├── websearch/         # Busca web
│   │   └── prompts/           # Prompts do sistema
│   ├── routers/               # Endpoints da API
│   ├── services/              
│   │   ├── llm_models/        # Configuração de modelos
│   │   ├── embedder/          # Geração de embeddings
│   │   └── cache/             # Cliente Redis
│   ├── data/                  # Modelos e ETL
│   │   ├── database/          # Conexões e ORM
│   │   ├── etl/               # Extração de documentos
│   │   └── pydantic_models.py
│   ├── configs/               # Configurações
│   └── middleware/            # Middlewares FastAPI
├── tests/                     # Testes
├── docs/                      
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
- [Workflow LangGraph](architecture/workflow.md)

### API
- [Endpoints](api/endpoints.md)
- [Modelos de Dados](api/models.md)
- [Exemplos de Uso](api/examples.md)

### Sistema RAG / RAG System
- [Visão Geral](rag-system/overview.md)
- [Embeddings](rag-system/embeddings.md)
- [Retrieval](rag-system/retrieval.md)
- [Indexação Automática](rag-system/auto-indexing.md)

### Agentes / Agents
- [Visão Geral](agents/overview.md)
- [Classificador de Intenção](agents/intent-selector.md)
- [Handler de Perguntas](agents/question-handler.md)
- [Sumarizador](agents/summarizer.md)
- [Busca Web](agents/websearch.md)

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
