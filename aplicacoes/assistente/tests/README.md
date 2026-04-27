# Testes do Assistente SEI-IA

Este diretório contém todos os testes do sistema: unitários, integração e end-to-end.

## Estrutura dos Testes

```
tests/
├── conftest.py              # Configuração global do pytest + fixtures compartilhadas
├── fixtures/                # Fixtures compartilhadas
│   └── mock_data.py        # Dados mockados para testes
├── unit/                    # Testes unitários (47 testes - 100% passando)
│   ├── conftest.py         # Mocks específicos para testes unitários
│   ├── test_pergunta_init.py            # Teste do módulo principal (14 testes)
│   ├── test_multi_search_rag.py         # Teste busca múltipla (22 testes)
│   ├── test_document_decision_simple.py # Teste decisões de documento (4 testes)
│   ├── test_prompt_builders_simple.py   # Teste construção de prompts (6 testes)
│   └── test_pergunta_simple.py          # Testes básicos funcionais (5 testes)
├── e2e/                    # Testes end-to-end
│   ├── conftest.py         # Configuração de ambiente mock para E2E
│   ├── test_service.py     # Testes E2E completos (com mocks)
│   ├── test_cache_cleanup.py  # Testes E2E com banco real
│   └── mocks.py            # Mocks para testes E2E
├── rag/                    # Testes específicos do RAG
│   └── test_*.py
├── scenarios/              # Cenários de teste específicos
│   └── test_*.py
└── utils/                  # Utilitários para testes
    ├── test_helpers.py     # Helpers e assertions customizadas
    └── in_memory_cache.py  # Cache em memória para testes E2E
```

## Estrutura de conftest.py

A estrutura hierárquica de `conftest.py` é uma prática recomendada do pytest. O pytest carrega automaticamente fixtures de todos os `conftest.py` na hierarquia:

### `tests/conftest.py` (raiz)
**Propósito**: Fixtures e configurações compartilhadas por TODOS os testes

**Conteúdo**:
- Configurações de ambiente de teste
- Fixtures gerais (mock_user_state, mock_chunks, etc.)
- Fixtures de banco real (PostgreSQL com Testcontainers) para testes de integração
- Marcadores pytest customizados
- Helpers de assert

### `tests/unit/conftest.py`
**Propósito**: Mocks e configurações específicas para testes unitários

**Conteúdo**:
- Manipulação de sys.modules para mocks globais
- Mocks de banco de dados (AsyncDbConnector)
- Mocks de serviços externos (LLM, embeddings)
- Configuração de logging para testes unitários
- Isolamento completo de dependências externas

### `tests/e2e/conftest.py`
**Propósito**: Configurações de ambiente mock para testes E2E

**Conteúdo**:
- Mock de variáveis de ambiente
- Mock de embeddings (retorna embeddings fake)
- Mock de handlers externos (SEI API, Solr)
- Configuração de cache em memória (substitui Redis)
- Fixtures de cliente FastAPI para testes de endpoints

**Importante**: As fixtures de mock (`mock_environment`, `configure_in_memory_cache`, `reset_in_memory_cache`)
verificam se o teste está marcado com `@pytest.mark.real_db` e, se estiver, **não aplicam os mocks**.
Isso permite que testes E2E com banco real convivam no mesmo diretório que testes com mocks.

## Padrão de Imports para Testes com Banco Real

Testes marcados com `@pytest.mark.real_db` devem seguir este padrão:

```python
@pytest.mark.asyncio
@pytest.mark.real_db
async def test_with_real_database(insert_test_data):
    # ⚠️ IMPORTANTE: Imports dentro da função, não no nível do módulo
    from sei_ia.data.database.db_instances import app_db_instance
    from sei_ia.services.cache import get_cache
    from sei_ia.configs.settings_config import settings

    # ... código do teste
```

**Por quê?** Módulos como `db_instances` inicializam conexões no momento do import.
Se importados no nível do arquivo, usarão as configurações mockadas do `tests/e2e/conftest.py`
(executadas durante a coleta de testes), causando erro de conexão com "mock-db-host".
Ao importar dentro da função de teste, as fixtures já configuraram as settings corretamente
para o banco de testes Testcontainers.

## Marcadores Pytest

Use marcadores para organizar e filtrar testes:

```bash
# Executar apenas testes unitários
pytest -m unit

# Executar apenas testes E2E
pytest tests/e2e/

# Executar apenas testes que usam banco real
pytest -m real_db

# Executar todos exceto testes lentos
pytest -m "not slow"

# Executar apenas testes de integração
pytest -m integration
```

### Marcadores disponíveis:
- `@pytest.mark.unit` - Testes unitários (aplicado automaticamente em `tests/unit/`)
- `@pytest.mark.integration` - Testes de integração
- `@pytest.mark.real_db` - Testes que usam banco de dados real (PostgreSQL com Testcontainers)
- `@pytest.mark.slow` - Testes lentos
- `@pytest.mark.external_api` - Testes que usam APIs externas (desabilitados por padrão)


## Cenários Testados (47 testes - 100% passando)

### 1. Módulo Principal (test_pergunta_init.py - 14 testes)
**Classe TestProcessQuestionIntent:**
- ✅ `test_process_question_intent_direct_path` - Fluxo direto quando documentos cabem no contexto
- ✅ `test_process_question_intent_rag_enhanced` - Ativação do RAG Enhanced quando documentos não cabem

**Classe TestCheckInitialSize:**
- ✅ `test_check_initial_size_documents_fit` - Validação quando documentos cabem no limite de tokens
- ✅ `test_check_initial_size_documents_dont_fit` - Validação quando documentos excedem limite
- ✅ `test_check_initial_size_boundary_case` - Teste de caso limite (exatamente no limite)

**Classe TestBuildDirectPrompt:**
- ✅ `test_build_direct_prompt_single_document` - Construção de prompt com 1 documento
- ✅ `test_build_direct_prompt_multiple_documents` - Construção de prompt com múltiplos documentos
- ✅ `test_build_direct_prompt_no_content` - Construção de prompt sem conteúdo de documentos

**Classe TestMakePromptWithRagEnhanced:**
- ✅ `test_rag_enhanced_complete_documents_flow` - RAG Enhanced usando documentos completos
- ✅ `test_rag_enhanced_grouped_chunks_flow` - RAG Enhanced usando chunks agrupados
- ✅ `test_rag_enhanced_error_handling` - Tratamento de erros na geração de perguntas
- ✅ `test_rag_enhanced_no_results` - RAG Enhanced quando não há resultados de busca

**Classe TestIntegrationFlow:**
- ✅ `test_full_flow_direct_path` - Fluxo completo de integração do caminho direto
- ✅ `test_full_flow_rag_complete_docs` - Fluxo completo de integração RAG Enhanced

### 2. Busca Múltipla RAG (test_multi_search_rag.py - 22 testes)
**Classe TestSearchWithMultipleQuestions:**
- ✅ `test_search_with_multiple_questions_success` - Busca bem-sucedida com múltiplas perguntas
- ✅ `test_search_with_multiple_questions_duplicate_removal` - Remoção de chunks duplicados durante busca
- ✅ `test_search_with_multiple_questions_error_handling` - Tratamento de erros durante busca múltipla
- ✅ `test_search_score_aggregation` - Agregação e ordenação de scores de relevância
- ✅ `test_search_empty_questions` - Comportamento com lista vazia de perguntas

**Classe TestSearchSingleQuestion:**
- ✅ `test_search_single_question_success` - Busca bem-sucedida com pergunta única
- ✅ `test_search_single_question_multiple_docs` - Busca retornando múltiplos documentos
- ✅ `test_search_single_question_no_results` - Busca sem resultados
- ✅ `test_search_single_question_embedding_error` - Erro na geração de embeddings

**Classe TestRemoveDuplicateChunks:**
- ✅ `test_remove_duplicate_chunks_no_duplicates` - Lista sem duplicatas permanece inalterada
- ✅ `test_remove_duplicate_chunks_with_duplicates` - Remoção de chunks duplicados preservando maior score
- ✅ `test_remove_duplicate_chunks_whitespace_differences` - Chunks com espaços diferentes
- ✅ `test_remove_duplicate_chunks_empty_list` - Lista vazia retorna lista vazia
- ✅ `test_remove_duplicate_chunks_preserves_highest_score` - Preservação do chunk com maior score
- ✅ `test_remove_duplicate_chunks_case_sensitivity` - Sensibilidade a maiúsculas/minúsculas

**Classe TestChunkValidation:**
- ✅ `test_chunk_structure_validation` - Validação de estrutura de chunks individuais
- ✅ `test_chunk_scores_are_valid` - Validação de scores de similaridade (0-1)
- ✅ `test_chunks_have_document_ids` - Validação de presença de IDs de documento

### 3. Decisão de Documentos (test_document_decision_simple.py - 4 testes)
**Classe TestDocumentDecision:**
- ✅ `test_check_documents_fit_empty_set` - Conjunto vazio de documentos sempre cabe
- ✅ `test_calculate_max_chunks_empty` - Cálculo com lista vazia de chunks
- ✅ `test_calculate_max_chunks_normal` - Cálculo normal de chunks máximos
- ✅ `test_check_documents_fit_with_mock_docs` - Verificação com documentos mockados reais

### 4. Construção de Prompts (test_prompt_builders_simple.py - 6 testes)
**Classe TestPromptBuilders:**
- ✅ `test_format_metadata_dict_simple` - Formatação de metadados com dados normais
- ✅ `test_format_metadata_dict_empty` - Formatação de metadados vazios
- ✅ `test_build_prompt_with_complete_documents_empty` - Prompt com conjunto vazio de documentos
- ✅ `test_build_prompt_with_grouped_chunks_empty` - Prompt com lista vazia de chunks
- ✅ `test_build_prompt_with_grouped_chunks_normal` - Prompt com chunks normais
- ✅ `test_build_prompt_with_complete_documents_with_mock_docs` - Prompt com documentos mockados

### 5. Funcionalidades Básicas (test_pergunta_simple.py - 5 testes)
**Classe TestQuestionGenerator:**
- ✅ `test_generate_questions_success` - Geração bem-sucedida de múltiplas perguntas

**Classe TestDocumentDecision:**
- ✅ `test_check_documents_fit_empty_set` - Verificação com conjunto vazio
- ✅ `test_calculate_max_chunks_basic` - Cálculo básico de chunks máximos

**Classe TestBasicFunctionality:**
- ✅ `test_user_state_structure` - Validação da estrutura do UserState mockado
- ✅ `test_mock_chunks_structure` - Validação da estrutura dos chunks mockados

## Mocks Utilizados

### UserState Mock
```python
# Exemplo de uso
from tests.fixtures.mock_data import create_mock_user_state_direct_path
user_state = create_mock_user_state_direct_path()
```

### Chunks Mock
```python
# Exemplo de uso
from tests.fixtures.mock_data import create_mock_chunks
chunks = create_mock_chunks()
```

### Cenários Predefinidos
```python
# Exemplo de uso
from tests.fixtures.mock_data import MockScenarios
user_state = MockScenarios.large_documents_need_rag()
```

## Validações Testadas

### Estrutura de Dados
- ✅ UserState tem campos obrigatórios
- ✅ Chunks têm estrutura correta
- ✅ Scores de similaridade são válidos (0-1)
- ✅ IDs de documento estão presentes

### Fluxo de Execução
- ✅ Decisões de roteamento corretas
- ✅ Fallbacks não são utilizados incorretamente
- ✅ Erros são propagados adequadamente
- ✅ Contadores de token são razoáveis

### Qualidade dos Prompts
- ✅ Prompts contêm metadados esperados
- ✅ Chunks são ordenados por relevância
- ✅ Scores de relevância são preservados
- ✅ Formatação está correta

### Funcionalidades Específicas Testadas
- ✅ **Roteamento inteligente** - caminho direto vs RAG Enhanced baseado em tamanho dos documentos
- ✅ **Geração de múltiplas perguntas** - LLM gera perguntas relacionadas para melhorar busca
- ✅ **Busca assíncrona** - múltiplas consultas de similaridade executadas em paralelo
- ✅ **Deduplicação de chunks** - preserva chunks únicos mantendo maiores scores
- ✅ **Agregação de scores** - combina relevância de múltiplas buscas
- ✅ **Decisão de contexto** - verifica se documentos cabem no limite de tokens
- ✅ **Construção de prompts** - formatação correta para documentos completos ou chunks
- ✅ **Tratamento de erros** - propagação adequada sem fallbacks mascarados

## Assertions Customizadas

```python
# Helpers disponíveis em test_helpers.py
from tests.utils.test_helpers import (
    assert_user_state_structure,      # Valida estrutura do UserState
    assert_direct_path_result,        # Valida resultado do caminho direto
    assert_rag_enhanced_result,       # Valida resultado do RAG Enhanced
    validate_search_results,          # Valida estrutura dos resultados de busca
    validate_chunk_structure,         # Valida estrutura de chunks individuais
    validate_document_decision,       # Valida resultado de decisão de documento
    TestAssertions                    # Classe com validações avançadas
)

# Exemplos de uso:
assert_direct_path_result(user_state)
assert_rag_enhanced_result(user_state, "complete_documents")
validate_search_results(search_results)
TestAssertions.assert_no_duplicate_chunks(chunks)
TestAssertions.assert_metadata_consistency(user_state)
```
