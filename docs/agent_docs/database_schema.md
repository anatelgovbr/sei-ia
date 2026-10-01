# Database schema

Schema lógico de **Postgres/pgvector** e **Solr**: onde cada dado mora e qual DDL ou ORM é autoritativo. Adjacências fora de escopo: containers e instâncias → `container_topology.md`; fluxo de embeddings → `service_architecture.md`; DSNs e protocolo das chamadas → `service_communication_patterns.md`; env vars de banco → `building_the_project.md` e `code_conventions.md`.

## Duas instâncias Postgres

`infra-postgres` (`docker-compose.yml:406`, `pgvector/pgvector:pg16`) é o DB das apps — objeto deste doc. `infra-postgres-airflow` (`:366`, `postgres:13`) guarda apenas o metastore do Airflow e está fora de escopo.

**Bootstrap:** initdb nativo monta `ops/database/ddl.sql` como `10-ddl.sql` e `ops/database/conf/init_pgvector.sql` como `20-init_pgvector.sql` em `/docker-entrypoint-initdb.d/` (`docker-compose.yml:422-423`); prefixo numérico define a ordem. Roda só na primeira inicialização do volume. Dois databases: `sei_similaridade` (`ddl.sql:1`) e `SEI_LLM` (`ddl.sql:74`). Extensão `vector` nos dois (`ddl.sql:3`, `init_pgvector.sql:2`).

## `sei_similaridade` — similaridade + etl-airflow

| Tabela | Papel | Definida em |
|---|---|---|
| `log_consume` | Log de chamadas da API de recomendação | `ddl.sql:9` + ORM `api_sei/db_models/models.py:22` |
| `feedback_jurisprudence` | Feedback doc2doc | `ddl.sql:26` + ORM `feedback.py:9` |
| `log_update_mlt` | Log de mudanças na fila (via trigger) | `ddl.sql:37` |
| `queue_update_mlt` | Fila de atualização MLT (PK composta) | `ddl.sql:48` |
| `version_register` | Hash/branch/tag das DAGs | `ddl.sql:59` |
| `config_mlt_fields_weights` | Pesos MLT em JSON | `ddl.sql:77` + ORM `models.py:74` (e ORM do writer no etl-airflow, `jobs/db_models/app_tables.py:51`) |
| `process_weighted_mlt_recommendation` | Recomendações WMLT persistidas | Só ORM `models.py:35` |
| `document_mlt_recommendation` | Recomendações doc2doc persistidas | Só ORM `models.py:54` |
| `feedback_process_weighted_mlt_recommendation` | Feedback de processo | Só ORM `feedback.py:28` |

**Autoridade dupla:** DDL no initdb e `Base.metadata.create_all` no startup (`aplicacoes/similaridade/db_connection/db_connection.py:52`). As três tabelas "Só ORM" não têm DDL — banco restaurado só do `ddl.sql` fica incompleto até a app subir.

Trigger `log_changes` em `queue_update_mlt` grava em `log_update_mlt` a cada INSERT/UPDATE (`ddl.sql:97`), coberto por `idx_log_protocolo_status_date` (`ddl.sql:100`).

**LEGADO — `embd_doc_minilm_*`:** lidas por rotas ocultas (`include_in_schema=False`), SQL hardcoded em `api_sei/resources/embed.py:8-9` e dinâmico em `api_sei/services/n_embeddings.py:100`. Nenhum `CREATE`/ORM/migração no repo — foram criadas fora dele. Caminho vivo é MLT (ver `service_architecture.md`).

## `SEI_LLM` — assistente

Tabelas de auditoria criadas pelo `init_pgvector.sql`:

| Tabela | Papel | Linha |
|---|---|---|
| `models` | Catálogo de modelos LLM (com seeds) | `:6` |
| `requests` | Log de requisições | `:37` |
| `messages` | Histórico de mensagens | `:51` |
| `ip_message` | Registro por IP/documento | `:64` |
| `feedback` | Avaliação de respostas (FK → messages) | `:77` |

A **tabela de embeddings do RAG** é criada em runtime pelo lifespan do FastAPI (`sei_ia/main.py:78-119`). O bootstrap abre uma transação, obtém `pg_advisory_xact_lock`, cria schema/extensão, executa `metadata.create_all(checkfirst=True)`, garante a tabela dinâmica, os índices e `public.gateway_status`, e só então libera o startup (`data/database/runtime_bootstrap.py:29-78`; variante síncrona para setup explícito em `:81-89`). Todo esse trecho usa a mesma `Connection`; falha de DDL aborta o startup e a transação. `AsyncDbConnector` apenas constrói engines e abre pools: o construtor não cria tabelas.

Nome **dinâmico**: `{LITELLM_EMBEDDING_MODEL ou EMBEDDING_MODEL}_{MAX_LENGTH_CHUNK_SIZE}_{CHUNK_OVERLAP}`, com `-` e `/`→`_` (`configs/settings_config.py:455-464`). O alias de request `embedding` não participa desse nome quando o pin físico está configurado. Schema default `sei_llm`. Colunas: `chunk_id`, `id_documento`, `embedding`, `start_position`, `finished_position`, `created_at` (`data/database/table_manager.py:15-43`; ORM em `db_models/embedding.py:29-37`). A dimensão do vetor vem somente de `EMBEDDING_DIMENSION`, configurada por `ASSISTENTE_EMBEDDING_DIMENSION` (`settings_config.py:166`); não há inferência pelo nome do modelo. O bootstrap converte colunas legadas `vector` sem dimensão para `vector(EMBEDDING_DIMENSION)` antes dos índices (`table_manager.py:45-91`). Índices: btree em `id_documento` + IVFFLAT `vector_cosine_ops` `lists=100` (`table_manager.py:93-120`).

ORM `Feedback` do assistente (`db_models/feedback.py:10-29`) herda o schema `sei_llm` do `MetaData`. `public.gateway_status` guarda o estado singleton de rate limit (`runtime_bootstrap.py:41-59`). O bootstrap não remove, renomeia nem recria tabelas existentes. A única alteração automática é adicionar a dimensão configurada a uma coluna `vector` sem dimensão; o cast preserva embeddings compatíveis e falha se encontrar dados com outra dimensão.

### `seiia_session` — checkpointer do assistente

O schema dedicado é configurado por `ASSISTENTE_SESSION_CHECKPOINTER_SCHEMA`, default `seiia_session` (`configs/settings_config.py:273-275`). `AsyncPostgresSaver.setup()` é a autoridade das quatro tabelas: `checkpoint_migrations`, `checkpoints`, `checkpoint_blobs` e `checkpoint_writes`. A integração real verifica o conjunto exato e as migrações 0–9 (`tests/integration/test_database_bootstrap.py:294-332`).

O setup usa uma conexão dedicada `AUTOCOMMIT` desde `pg_try_advisory_lock` até `pg_advisory_unlock`; cria o schema e executa todas as migrações nessa mesma conexão (`services/session_fs/checkpointer.py:64-77`, pool em `:90-108`). A espera é feita em Python a cada 0,1 s, com timeout total explícito de 60 s (`:19-26`, `:33-53`), porque as migrações de índice usam `CREATE INDEX CONCURRENTLY`. O unlock roda em `finally`, e qualquer falha fecha o pool antes de propagar; as chaves são estáveis e distintas das usadas pelo bootstrap de `sei_llm`.

## Solr — dois cores vivos

Schema **autoritativo**: configsets do etl-airflow em `aplicacoes/etl-airflow/jobs/configs/solr_core_configs/configsets/`. Cores criados pelas DAGs e pelo startup da `jobs.api` via `create_solr_core` (`jobs/dags/database/create_solr_core.py:8`, chamado em `dag_mlt_etl_process.py:47`, `dag_mlt_etl_documents.py:44-46`, `jobs/api.py:39-49`).

**`processos_bm25`** (env `SOLR_MLT_PROCESS_CORE`, `default.env:50`) — configset `process`. Campos com `termVectors=true`: `assunto_text/conclusao_text/corpo_text/ementa_text/referencias_text` (`managed-schema.xml:138-142`); `id_protocolo` é a `<uniqueKey>` (`managed-schema.xml:4`, campo em `:148`). Escrita: `GenericSender` na DAG (`dag_mlt_etl_process.py:71-76`; endpoints `/update/json/docs` bulk em `generic_sender.py:61`, `/update` doc-a-doc em `:84-95`) e indexação sob demanda (`jobs/api_rest/services/process.py:44-46`). Leitura: `SolrMlt` (`aplicacoes/similaridade/api_sei/db_models/solr_mlt.py:45`). O protocolo da indexação sob demanda está em `service_communication_patterns.md`.

**`documentos_bm25`** (env `SOLR_MLT_JURISPRUDENCE_CORE`, `jobs/envs.py:54`) — configset `jurisprudence`. Campos: `content` `termVectors=true` (`managed-schema.xml:140`), `id_document`/`id_process` (`:141-142`). Escrita: `GenericSender` (`dag_mlt_etl_documents.py:76-78`). Leitura: MLT jurisprudência.

BM25 é a similarity default do Solr (nenhum `<similarity>` declarado); relevância MLT via `termVectors`.

**LEGADO — `embedding_full`:** tipo `embedding_vector` = `solr.DenseVectorField`, `vectorDimension=768`, cosine (configset `process`, `managed-schema.xml:42`, campo em `:147`). Nenhum writer no repo; único leitor é o KNN legado (`api_sei/services/embeddings.py:19`). Existe ainda um terceiro configset `sei_protocolos`, usado só em testes de integração (`tests/integration/test_solr.py:24`).

> **DRIFT:** a similaridade mantém cópia própria dos configsets em `aplicacoes/similaridade/configs/solr_core_configs/configsets/` — desatualizada. No `process` faltam `version_manager_id` e `metadata_citations` (etl-airflow `:146`, `:155`); no `jurisprudence` falta `dt_ref_insert` (`:143`). A fonte que vai ao Solr é sempre a do etl-airflow.

## Gotchas

- **Bug no DDL:** `config_mlt_fields_weights` (`ddl.sql:77`) cai no `sei_similaridade` por falta de `\c SEI_LLM` após `CREATE DATABASE SEI_LLM` (`:74`). A tabela **tem leitor vivo**: `read_mlt_fields_weights` em `api_sei/resources/custom_parsedquery.py:279` (SQL nas `:292` e `:340`), chamada pelas classes `FasterCustomParsedQuery`/`ManualExtractCustomParsedQuery` no fluxo MLT vivo (`solr_mlt.py:315-348`). O writer mora no **etl-airflow**: a DAG horária `system_create_mlt_weights_config` (`jobs/dags/dag_objects/sync_config.py:8`) executa `jobs/configs/parameters/conf_mlt_fields_weights.py` — insere pesos default se a tabela estiver vazia (`:31-40`) e grava pesos computados do SEI (`:174-178`). Antes da primeira execução da DAG, a tabela vazia faz o MLT levantar `ResourceNotFoundException`.
- **Tabelas só-ORM:** as três de recomendação/feedback da similaridade não existem no DDL — banco restaurado fica incompleto até a app subir.
- **Nome dinâmico de tabela:** trocar modelo ou chunk via env cria tabela nova; a anterior fica órfã sem migração automática. O bootstrap nunca migra ou apaga a tabela anterior.
- **Mudança de dimensão:** o bootstrap migra somente `vector` sem dimensão. Uma coluna `vector(n)` diferente de `ASSISTENTE_EMBEDDING_DIMENSION` aborta o startup com erro explícito. Mude a dimensão apenas junto de um novo nome dinâmico de tabela ou de uma migração operacional explícita.
- **Cópias da similaridade divergem:** não editar os managed-schemas da similaridade achando que afetam o Solr — edite os do etl-airflow.
- **`embd_doc_minilm_*` e `embedding_full`** são legado sem writer no repo — não tratar como schema vivo.
