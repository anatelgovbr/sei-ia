# Testes do Assistente SEI-IA

Este diretório concentra as suítes de testes do SEI-IA Assistente: unitários, integração e end-to-end (E2E).

## Estrutura dos Testes

```text
tests/
├── conftest.py              # Configuração global do pytest e fixtures compartilhadas
├── fixtures/                # Fixtures e dados de teste
│   ├── documents/           # Amostras documentais por tipo de arquivo (PDF, DOCX, áudio, etc.)
│   └── mock_data.py         # Mocks estruturados para testes
├── unit/                    # Testes unitários dos módulos ativos
│   ├── conftest.py          # Mocks e isolamento específicos para unitários
│   ├── test_session_*.py    # Testes de routers, schemas, manager, modos e observabilidade da sessão
│   ├── test_stream_processor_final.py # Testes do processamento de citações no streaming
│   ├── test_sources.py      # Testes de metadados e formatação de fontes
│   ├── test_embedding_*.py  # Testes de validação e pipeline de embeddings mantido
│   ├── test_searx_crawl_*.py # Testes de busca web e agentes de pesquisa
│   ├── test_database_*.py   # Testes de lifecycle e configurações de banco
│   └── ...                  # Testes de middleware, helpers e utilitários
├── integration/             # Testes de integração com banco de dados
│   └── test_database_bootstrap.py # Validação real do lifespan, TableManager, pgvector, checkpointer e locks
├── e2e/                     # Testes end-to-end
│   ├── conftest.py          # Ambiente mock e fixtures para E2E
│   ├── test_session_stream.py # Validação completa do streaming SSE (/llm_lang/session_stream)
│   ├── test_session_uploads.py # Testes de uploads de documentos e áudio
│   ├── test_session_modes.py   # Testes dos modos injected e filesystem
│   ├── test_session_websearch.py # Testes de integração do fluxo de busca web
│   └── ...                  # Concorrência, timeouts e handlers de exceção
└── utils/                   # Utilitários para testes
    └── in_memory_cache.py   # Cache em memória para simulação nos testes
```

## Limpeza de Testes Legados

Com o arquivamento do fluxo clássico e do RAG sob `scripts/legado/`:
- Foram removidos os testes exclusivos do código arquivado (testes do grafo antigo `chat_completion_graph`, handlers de pergunta/RAG em `pergunta/`, seleção de chunks clássica, agentes e runners antigos de `tests/rag/`).
- Foram removidos testes puramente mecânicos auditados (asserts de defaults estáticos, cópias de campos ou eco de mocks sem validação de comportamento).
- **Preservados e migrados**: Os testes de citações de stream (`test_stream_processor_final.py`, `test_sources.py`) foram migrados para os módulos vivos em `services/llm_models/`. Os testes de inicialização do banco (`test_database_bootstrap.py`), validação de embeddings (`test_embedding_empty_input.py`, `test_embedder_resolve.py`), extração de documentos e toda a suíte do Session Agent permanecem ativos.

## Estrutura de conftest.py

A hierarquia de `conftest.py` segue as recomendações do pytest:

### `tests/conftest.py` (raiz)
- Configurações de ambiente de teste;
- Fixtures gerais (`test_config`, mocks compartilhados);
- Marcadores customizados (`unit`, `integration`, `real_db`, `slow`, `external_api`).

### `tests/unit/conftest.py`
- Mocks de banco de dados e serviços externos;
- Configuração de logging e isolamento de dependências externas.

### `tests/e2e/conftest.py`
- Mocks de variáveis de ambiente e serviços externos;
- Configuração de cache em memória;
- Clientes FastAPI para validação dos endpoints.

## Marcadores Pytest e Execução Local

```bash
# Executar apenas testes unitários
pytest tests/unit

# Executar apenas testes E2E
pytest tests/e2e

# Executar integração de banco em PostgreSQL descartável (exige container pgvector vazio)
ASSISTENTE_TEST_DATABASE_URL="postgresql+asyncpg://seiia:senha@localhost:5432/teste" \
ASSISTENTE_TEST_DATABASE_DISPOSABLE=1 \
pytest tests/integration/test_database_bootstrap.py -n 0
```

### Marcadores disponíveis:
- `@pytest.mark.unit` - Testes unitários (aplicado automaticamente em `tests/unit/`)
- `@pytest.mark.integration` - Testes de integração (aplicado em `tests/integration/`)
- `@pytest.mark.real_db` - Testes que utilizam banco de dados real (PostgreSQL com pgvector)
- `@pytest.mark.slow` - Testes com tempo de execução elevado
- `@pytest.mark.external_api` - Testes que dependem de APIs externas (desabilitados por padrão em modo teste)
