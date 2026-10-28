# Arquitetura do Assistente

## Fluxo público de chat

`POST /llm_lang/session_stream` é o único endpoint público de chat. Ele usa o
agente Session e responde em SSE. O tier interno `mini` continua disponível aos
agentes, sem uma rota HTTP própria.

1. `sei_ia/main.py` monta os routers, middlewares e lifespan.
2. `routers/session/stream.py` recebe o request, valida modelo/reasoning e prepara
   documentos, anexos e histórico.
3. `services/session_fs/` cria ou retoma a sessão por usuário e tópico, reconcilia
   o manifesto documental e gerencia filesystem, checkpoint e TTL.
4. `agents/session_agent/` escolhe modo e complexidade e constrói o agente.
   Conforme o volume de contexto, ele recebe conteúdo injetado ou acessa os
   documentos no filesystem da sessão.
5. O modelo é acessado pelo proxy LiteLLM. Quando habilitada, a busca web usa
   `WebResearchAgent` ou `DeepResearchAgent`.
6. O router transmite `status`, `reasoning` e `content`, finalizando com `metadata`
   e `end`. Falhas durante o stream são comunicadas por `error`.

## Fronteiras dos módulos

| Módulo | Responsabilidade |
|---|---|
| `routers/session/` | HTTP, preparação de uploads, emissão SSE e observabilidade do request |
| `agents/session_agent/` | Agente, prompts, classificação, leitura da sessão e uso de modelos |
| `services/session_fs/` | Manifesto, arquivos, checkpoints PostgreSQL e expiração |
| `services/llm_models/` | Catálogo, seleção de modelos e conteúdo multimodal/reasoning |
| `data/etl/` e `libs/sei_extraction` | Busca e extração documental |
| `services/cache/` | Cache Redis e anexos por tópico |
| `data/database/` | Conexões, persistência e cliente SEI |

A API também mantém health, feedback, catálogo de modelos e rotas operacionais.
Consulte o OpenAPI da aplicação para o inventário e os schemas atuais.

## Persistência e inicialização

O lifespan conecta o banco, executa o bootstrap e inicia o checkpointer e o
sweeper de sessões. O encerramento fecha esses recursos. Uma chamada HTTP local
real exige os serviços configurados; instanciar apenas `FastAPI` em um teste não
prova esse caminho.

O manifesto documental é acumulativo entre turnos. A política de cache de cada
documento determina quando ele precisa ser buscado novamente no SEI. O histórico
remoto pode atualizar a janela do agente; duas chamadas HTTP isoladas não
reproduzem, por si só, as gravações realizadas pelo frontend SEI.

## Fluxo clássico e arquivo histórico

Somente RAG, pergunta e seus auxiliares diretos permanecem em `scripts/legado/`,
sem publicação de rotas e sem suporte operacional. Os demais componentes
clássicos, incluindo grafo, sumarização, disclaimer e memória, foram excluídos.

As funções vivas necessárias ao Session foram integradas aos caminhos ativos:
o processamento de citações e fontes em `sei_ia/services/llm_models/stream_citations.py`
e `citation_sources.py`, e a extração documental em `sei_ia/data/etl/extract/doc_content.py`.

A infraestrutura de embeddings (`sei_ia/services/embedder/pipeline.py`, o gerador,
o provider Azure e os modelos ORM de pgvector) permanece ativa para garantir o
probe de conexão durante o startup e a inicialização idempotente das tabelas pelo
`TableManager`.

Os experimentos e benchmarks permanecem preservados em
`experimentos/latencia-session-vs-classico/`, mantendo seus relatórios e dados
históricos intactos.

## Referências

- [Componentes](components.md)
- [Endpoints](../api/endpoints.md)
- [Exemplos SSE](../api/examples.md)
- Arquivo histórico: consulte `scripts/legado/README.md` e `scripts/legado/docs/`
