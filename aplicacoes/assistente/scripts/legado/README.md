# Arquivo histórico de RAG e pergunta

Esta pasta preserva somente o RAG clássico, o handler de pergunta e seus auxiliares diretos. Não é um pacote executável nem uma alternativa ao agente Session.

## Conteúdo preservado

- `sei_ia/agents/rag/`: busca por similaridade e processamento de citações.
- `sei_ia/agents/pergunta/`: decisão documental, validação, auto-indexação, geração de perguntas e multi-query retrieval.
- `sei_ia/agents/prompts/`: prompts clássicos preservados (rag, geração de perguntas, completation, sumarização, seletor de intenção, memória, disclaimer e busca web).
- `sei_ia/services/exceptions/rag_exceptions.py`: exceções usadas por esses módulos.
- `docs/rag-system/` e `docs/agents/question-handler.md`: documentação histórica desses fluxos.

Os demais componentes clássicos foram excluídos, incluindo grafo, workflow de chat, revisor gramatical, anexos, concatenação e scripts de diagnóstico clássicos.

## Limite com o código ativo

Os imports históricos foram preservados como referência, sem adaptar o arquivo para execução. Alguns apontam para módulos ativos ou caminhos antigos. Não importe este diretório no runtime nem use seus módulos para validar o chat atual.

Os auxiliares compartilhados usados pelo Session permanecem nos módulos ativos:

- `sei_ia/services/llm_models/stream_citations.py` e `citation_sources.py`: processamento de citações e referências.
- `sei_ia/data/etl/extract/doc_content.py`: extração documental, incluindo `get_doc_from_id_async` e `_find_page_range`.
- `scripts/smoke_helpers.py`: helpers dos diagnósticos ativos.

A infraestrutura de embeddings, o lifespan e o bootstrap do banco permanecem em `sei_ia/`. Esta limpeza não altera esses componentes, configurações ou dependências.
