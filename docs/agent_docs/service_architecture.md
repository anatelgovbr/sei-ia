# Service architecture

Mapa estrutural do repo: **o que cada parte faz** e **onde colocar código novo** (estrutura de *código*). A topologia de *runtime* — quais containers sobem e por quê — está em `container_topology.md`. Build e config ficam em `building_the_project.md`; convenções em `code_conventions.md`; schema de DB em `database_schema.md`; como os serviços conversam em `service_communication_patterns.md`.

Monorepo: **3 apps + 2 libs compartilhadas + `ops/`**. Cada app tem `pyproject.toml`/`uv.lock`/Dockerfile próprios e roda isolada; as libs entram nas apps como **editáveis** (`../../libs/*`) — por isso o build roda de dentro da app (mecânica em `building_the_project.md`).

| Componente | Papel | Entrypoint | Porta (compose) |
|---|---|---|---|
| `aplicacoes/assistente/` | GenAI sobre documentos do SEI (FastAPI) | `sei_ia.main:app` | Ver `container_topology.md` |
| `aplicacoes/similaridade/` | Recomendação e feedback (Solr/Postgres) | `api_sei.main:app` / `app_api.main:app` | Ver `container_topology.md` |
| `aplicacoes/etl-airflow/` | Indexação/embeddings (Airflow + API REST) | DAGs + `jobs.api:app` | Ver `container_topology.md` |
| `libs/sei_extraction/` | Extração/tratamento de documentos do SEI | lib (importada) | — |
| `libs/sei_api/` | Cliente HTTP da API do SEI | lib (importada) | — |
| `ops/` + `docker-compose.yml` | Infra de apoio e orquestração da stack | — | — |

> App canônica desta doc: **`assistente`** (a mais madura). `similaridade` e `etl-airflow` aparecem **só onde divergem**.

## `assistente` — GenAI (app canônica)

O único endpoint público de chat é `/llm_lang/session_stream`, registrado por
`get_app()` em `sei_ia/main.py:118,157-161`. Os tiers internos de modelos, incluindo
`mini`, permanecem disponíveis aos agentes.

O pacote `routers/session/` contém o POST, os preflights internos e os helpers
de uploads e observabilidade. Conteúdo multimodal e reasoning compartilhados
ficam em `services/llm_models/message_content.py:12,67`. O Session não importa
o pacote de routers clássico. Materialização, SSE e Langfuse estão descritos
em `service_communication_patterns.md`.

Somente RAG, pergunta e seus auxiliares diretos permanecem em
`aplicacoes/assistente/scripts/legado/`, sem endpoints ou suporte operacional.
O grafo, `chat_workflow.py` e o orquestrador clássico de concatenação foram
excluídos. As funções vivas de extração documental foram
migradas para `sei_ia/data/etl/extract/doc_content.py` e as citações de streaming
para `sei_ia/services/llm_models/stream_citations.py` e `citation_sources.py`.
O pipeline de embeddings (`services/embedder/pipeline.py`), o gerador e o
provider Azure permanecem ativos em `sei_ia/` para atender o probe de inicialização
e o bootstrap do banco.
No deep-agent, `services/session_fs/manager.py:323` cria ou retoma a sessão. Antes
de materializar, o manager transforma o payload em `SessionDocumentSpec` e o
reconcilia com a política persistida em um `SessionDocumentPlan`; documentos `N` ou
com política desconhecida são agendados novamente mesmo quando não aparecem no
payload atual (`services/session_fs/types.py:153`; `services/session_fs/manager.py:105`).
Limites de paginação (`pag_doc_init` e `pag_doc_end`) são transportados ponta a ponta
do spec ao plan; qualquer alteração no intervalo de páginas invalida o reuso e força
materialização fresca, enquanto documentos voláteis implícitos herdam o intervalo
já persistido.
O manager mantém índices internos por ID, enquanto `SessionMeta.to_dict()` persiste
o `session.json` v2 como uma lista ordenada de processos com seus documentos
aninhados, metadados, `download_ext`, `sin_armazena_cache`, `pag_doc_init` e
`pag_doc_end` (`services/session_fs/types.py:179`, `:213`). O manifesto é acumulativo entre turnos
e também guarda a proveniência compacta da busca web mais recente
(`services/session_fs/manager.py:814`; `routers/session/stream.py:1740`). A tool
somente-leitura `read_session` entrega essa árvore inteira ou filtra por
processo/documento sem abrir conteúdo (`agents/session_agent/read_session.py:186`);
o agente então abre cada path no principal ou no explorador. `session.json` e
`proc_*` têm escrita negada, ficando `workspace/` como área editável
(`agents/session_agent/agent.py:364`).

Anatomia de `sei_ia/` (onde colocar o quê):

- `routers/` — endpoints HTTP: `session/`, `feedback.py`, `healthcheck.py`, `llm_models.py` e autotestes em `tests/`. Registro em `sei_ia/main.py:157-161`.
- `agents/` — Session em `session_agent/`, busca em `websearch/` e prompts. Somente RAG e pergunta foram preservados sob `scripts/legado/sei_ia/agents/`, com seus prompts e exceções; os demais componentes clássicos foram excluídos.
- `services/` — **lógica de negócio reutilizável**: `embedder/` (com ABC `EmbeddingProvider`), `cache/`, `session_fs/`, `llm_models/`, `persistance/`, `exceptions/`. Código chamado por routers/agents, sem HTTP.
- `data/` — **modelos e camada de dados**: `pydantic_models.py` (schemas de request/response), `database/` (ORM, `sei_client.py`, `table_manager.py`), `etl/extract/`.
- `configs/` — `settings_config.py` (env vars, ver `code_conventions.md`), além de logging/langfuse/gunicorn.
- `middleware/` — timeout, logging de request, handlers de exceção centralizados.
- `main.py` — fábrica `get_app()`.

## `similaridade` — recomendação (diverge)

Recomendação por similaridade com **Solr como backbone**. Estrutura própria (não segue o layout do `assistente`):

- `api_sei/` — **API principal**, exposta pelo gateway. Rotas **vivas** em `mlt_recommender`: `/process-recommenders/weighted-mlt-recommender/recommendations/{id_protocolo}` (`api_sei/routers/mlt_recommender.py:61`) e `/process-recommenders/weighted-mlt-recommender/indexed-ids/{id_protocolo}` (`:100`). Rotas **ocultas** (`include_in_schema=False`): `/process-recommenders/mlt-recommender/...` (`:30`) e `/process-recommenders/hwmlt-recommender/...` (`:84`). Recomendadores por embedding — `n_embeddings` (pgvector `embd_doc_minilm_*`), `rerank` e o KNN denso do Solr (`embedding_full`) — também são **legado** (`include_in_schema=False`). Caminho vivo: MLT lexical via Solr (`mlt_recommender`, `jurisprudence_recommender`).
- `app_api/` — **camada legada só de feedback** (`app_api/main.py:38`): endpoints `/process-recommenders/feedbacks` e `/document-recommenders/feedbacks` (`:66`, `:83`). Serviço separado; exposição em `container_topology.md`.
- `db_connection/` — conector PostgreSQL.

**Diverge do `assistente`:** sem pydantic-settings — config por `os.getenv` em `api_sei/envs.py:16`. Há `*.old` files mortos em `api_sei/` (não citar como autoritativos).

## `etl-airflow` — indexação e embeddings (diverge)

Orquestração batch/agendada via Airflow. O **mesmo código `jobs/`** roda como dois tipos de container (topologia em `container_topology.md`):

**Plano de orquestração — DAGs** (`jobs/dags/dag_objects/mlt_etl_process/`), nos containers scheduler/worker/triggerer. Padrão **starter → worker**: a starter roda a cada ~1min, busca pendências no SEI e dispara a worker em lote.

- `process_update_index` / `documents_update_index` (starter) → `process_indexing` / `documents_indexing` (worker) — indexam **texto no Solr** (cores `processos_bm25` / `documentos_bm25`; schema, configsets e drift em `database_schema.md`).
- `documents_update_embedding` (starter) → `documents_embedding_generation` (worker) — geram **embeddings** de documentos (ver "Embeddings (transversal)").
- `cache_invalidation` (~5min) — remove cancelados de Solr/pgvector/Redis.

**Plano de API — `jobs.api:app`** (container interno `etl-airflow-api`, `jobs/api.py:22`): **indexação sob demanda** dos itens que as DAGs ainda não cobriram. `/process/unindexed/...` (`:53`) busca o processo no SEI e o **indexa na hora no Solr** (`jobs/api_rest/services/process.py:44`) — consultado pela **`similaridade`** (`aplicacoes/similaridade/api_sei/resources/custom_parsedquery.py:165-180`; protocolo em `service_communication_patterns.md`); `/embeddings/generate` (`jobs/api_rest/routers/embeddings.py`) gera e grava embeddings de documentos no pgvector. A geração compartilha a **mesma função** da DAG (`generate_embeddings_for_documents`, `jobs/api_rest/services/embedding_service.py:212`): a DAG chama direto; a API expõe por HTTP interno.

**Diverge:** config nativa do Airflow (não pydantic-settings); broker Celery (`infra-rabbitmq`); DB de metadados próprio (`infra-postgres-airflow`); webserver na 8081 (`docker-compose.yml:226-230`).

## Embeddings e RAG (só o `assistente`)

Quem **gera** (escreve) e quem **usa** (lê) embeddings, e onde os vetores moram:

| Papel | App / caminho | Onde mora |
|---|---|---|
| Gera (batch) | `etl-airflow` — DAG `documents_embedding_generation` / endpoint `/embeddings/generate` | pgvector (schema `sei_llm`) |
| Gera (sob demanda) | `assistente` — probe de startup e infraestrutura de embeddings ativa (`services/embedder/pipeline.py`) | pgvector |
| Usa | `assistente` — busca RAG clássica arquivada como histórico (`scripts/legado/sei_ia/agents/rag/similarity.py`) | pgvector |

- **Modelo:** toda geração chama o **proxy LiteLLM** pelo alias `embedding` (`litellm_config.template.yaml`) — nenhum app fala com a Azure direto (config em `building_the_project.md`). O startup e o bootstrap do Assistente mantêm a infraestrutura de embeddings ativa em `sei_ia/` para validar a conexão com o provider e garantir tabelas/dimensões.
- A `similaridade` **não usa embeddings no vivo** — a recomendação viva é MLT lexical (Solr); seus recomendadores por embedding (`n_embeddings`, `rerank`, KNN `embedding_full`) são legado. O protocolo das chamadas fica em `service_communication_patterns.md`.

## `libs/` — compartilhado pelos 3 apps

Código comum às 3 apps, consumido como dependência **editável** (alterar a lib reflete nas apps sem reinstalar):

- **`sei_extraction`** — extração/tratamento de documentos. API pública em `src/sei_extraction/__init__.py`: orquestrador `fetch_document_text` + `DownloadPolicy`, helpers de texto (`clean_text`, `html_to_markdown`), e os **ports** (protocolos de injeção: `SeiContentSource`, `SeiFileDownloader`, `AudioTranscriber`, `VisionOCRClient` — `ports.py`). As apps implementam os ports e **delegam** a extração à lib, em vez de duplicá-la.
- **`sei_api`** — cliente HTTP da API do SEI. Público em `src/sei_api/__init__.py`: `SeiApiClient` + `SeiApiConfig` (dataclass `frozen` com `base_url`/`sigla_sistema`/`identificacao_servico`, `config.py:6`). O `IdentificacaoServico` (token) é **anonimizado** em mensagens de erro (`SeiApiError`, `exceptions.py:15`). No `assistente`, é embrulhado por `data/database/sei_client.py`.

## `ops/` + orquestração

`ops/` guarda a **infra de apoio**: gateway Nginx, imagens/config de Solr e Postgres+pgvector, healthchecker, config do SonarQube (`sonarqube/`) e serviços da busca web oficial (`searxng/`, `fastcrw/`, `marker/`). O `gateway-nginx` é a única fronteira TLS das APIs do SEI (`ops/gateway/nginx.conf:28`, `:63`, `:94`); o **`docker-compose.yml` na raiz** conecta o gateway, as apps e a infra.

> **LiteLLM** (`infra-litellm`, porta 4000) é o proxy transversal por onde **todas** as apps falam com LLM (protocolo em `service_communication_patterns.md`; config em `building_the_project.md`). **LangFuse** (observabilidade) **não** está na stack padrão: só roda no **ambiente da Anatel** (servidor transversal — documentação interna de workflow, não incluída no mirror externo) e não sobe com o compose; **releases externos não o incluem por padrão**.

A topologia completa (todos os containers, profiles opcionais, `depends_on`, por que cada app vira mais de um container) está em `container_topology.md`.

## Onde colocar algo novo

| Quero adicionar… | Vai em |
|---|---|
| Endpoint HTTP no `assistente` | `aplicacoes/assistente/sei_ia/routers/` |
| Passo de orquestração LLM / prompt | `aplicacoes/assistente/sei_ia/agents/` (prompts em `agents/prompts/`) |
| Lógica reutilizável sem HTTP | `aplicacoes/assistente/sei_ia/services/` |
| Schema de request/response ou modelo de DB | `aplicacoes/assistente/sei_ia/data/` |
| Extração/parse de documento do SEI | `libs/sei_extraction/` (não duplicar na app) |
| Chamada nova à API do SEI | `libs/sei_api/` |
| DAG ou indexação | `aplicacoes/etl-airflow/jobs/dags/dag_objects/` |
| Serviço de infra na stack | `ops/` + `docker-compose.yml` |
