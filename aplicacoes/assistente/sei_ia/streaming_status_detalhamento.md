# Detalhamento do Streaming de Status — Guia de Modificações

## Contexto

O endpoint de streaming hoje envia apenas os seguintes status genéricos:

- `Pesquisando informações na Internet`
- `Pesquisa na Internet concluída`
- `Recuperando mensagens anteriores do tópico`
- `Mensagens anteriores do tópico carregadas`
- `Processando os documentos`
- `Documentos processados`

O objetivo é detalhar cada etapa por documento, indicando entrada no RAG, geração de embeddings e busca por chunks.

---

## 1. Emissores de `_status` — Modificar Primeiro

Esses são os 4 arquivos que já emitem status e precisam ser enriquecidos com detalhes por documento/etapa.

| Responsabilidade | Link |
|---|---|
| **Documentos** — emite `fetching_documents` / `fetching_documents_end` | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/data/etl/concatenate_documents.py |
| **Histórico do tópico** — emite `fetching_history` / `fetching_history_end` | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/agents/memory/session/conversation.py |
| **Busca web** — emite `websearch` / `websearch_end` (workflow) | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/services/llm_models/chat_workflow.py |
| **Busca web** — emite `websearch` / `websearch_end` (nó do grafo) | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/agents/chat_completion_graph.py |

### O que adicionar nesses arquivos

```
concatenate_documents.py  →  "Buscando documento <nome> (X de N)..."
                             "Documento <nome> carregado"

conversation.py           →  "Carregando mensagem X de N do histórico do tópico..."
                             "Histórico do tópico carregado"

chat_workflow.py /        →  "Iniciando busca web: <query>..."
chat_completion_graph.py     "Resultado recebido de <fonte>"
```

---

## 2. Pipeline RAG — Emitir Status de Entrada e Embeddings por Documento

| Responsabilidade | Link |
|---|---|
| **Orquestrador RAG** — decide se entra no RAG, faz auto-indexação | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/agents/pergunta/__init__.py |
| **Auto-indexação** — indexa documentos faltantes, aqui ficam os embeddings | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/agents/pergunta/auto_indexing.py |
| **Multi-search RAG** — busca por chunks similares | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/agents/pergunta/multi_search_rag.py |
| **Validação de documentos** | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/agents/pergunta/document_validation.py |
| **Pipeline de embedding** — geração dos vetores | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/services/embedder/pipeline.py |
| **Gerador de embeddings** | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/services/embedder/embedding_generator.py |
| **Retriever de chunks** — busca por similaridade | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/services/embedder/chunk_retriever.py |

### O que adicionar nesses arquivos

```
agents/pergunta/__init__.py  →  "Entrando no RAG para o documento <nome>"
                                "RAG finalizado para o documento <nome>"

auto_indexing.py             →  "Gerando embeddings do documento <nome>..."
                                "Embeddings concluídos para o documento <nome>"

chunk_retriever.py           →  "Buscando trechos relevantes em <nome>..."
                                "X trechos encontrados em <nome>"
```

---

## 3. Endpoints de Streaming — Referência

Não precisam ser modificados diretamente, mas são o ponto de entrada para entender o fluxo.

| Responsabilidade | Link |
|---|---|
| **Endpoint principal** — `POST /llm_lang/stream` | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/routers/chat/gpt_4o_128k.py |
| **Endpoint RLM** — `POST /llm_lang/rlm_stream` | https://git.anatel.gov.br/processo_eletronico/sei-ia/monorepo/-/blob/main/aplicacoes/assistente/sei_ia/routers/chat/rlm_stream.py |

---

## Ordem de Implementação Sugerida

1. `concatenate_documents.py` — maior impacto visível, cobre a listagem por documento
2. `agents/pergunta/__init__.py` + `auto_indexing.py` — cobre entrada no RAG e embeddings
3. `services/embedder/chunk_retriever.py` — cobre busca por chunks
4. `agents/memory/session/conversation.py` — cobre histórico por mensagem
5. `services/llm_models/chat_workflow.py` + `agents/chat_completion_graph.py` — cobre busca web detalhada
