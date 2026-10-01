# Service communication patterns

Protocolos, quem chama quem, formato e auth entre os serviços da stack. Portas e containers → `container_topology.md`; schema de dados → `database_schema.md`; papel de cada app → `service_architecture.md`; env vars de build/subida → `building_the_project.md`.

## Mapa de chamadas

O SEI acessa um único `gateway-nginx` por HTTPS em três listeners: 8088 encaminha ao Assistente, 8082 à Similaridade e 8086 ao Feedback (`ops/gateway/nginx.conf:28-120`). O listener, não o path, resolve rotas comuns como `/health` e `/openapi.json`. O access log estruturado do gateway registra somente respostas `4xx`/`5xx` e mantém `/health` sempre silencioso; os registros incluem horário ISO/milisegundos, método, URI, status, tamanho da requisição, bytes enviados, duração, status/tempo do upstream e `traceparent` (`ops/gateway/nginx.conf:7-26`). Atrás dessa fronteira, o Nginx chama os backends por HTTP nas mesmas portas; certificado e chave existem somente no gateway. `SEIIA_GATEWAY_HOST` é simultaneamente o nome configurado no módulo, um alias Docker do gateway e um SAN obrigatório do certificado. O módulo valida TLS com a CA bundle fixa `/opt/sei/config/mod-ia/seiia.cert.pem`. O gateway preserva o `Host` público, define `X-Forwarded-Proto` e substitui `X-Forwarded-For` pelo endereço do cliente. Os workers Uvicorn aceitam esses headers somente no ambiente da stack, onde os três backends não publicam portas no host e confiam nos peers da rede Docker.

Existe UMA chamada HTTP app→app no runtime: a similaridade chama a API do etl para indexação sob demanda quando o processo não está no Solr — `GET {JOBS_API_ADDRESS}/process/unindexed/nr_process/{nr_process}` (`aplicacoes/similaridade/api_sei/resources/custom_parsedquery.py:165-180`), env `JOBS_API_ADDRESS` default `http://etl-airflow-api:8642` (`aplicacoes/similaridade/api_sei/envs.py:59`), servida por `aplicacoes/etl-airflow/jobs/api.py:53`. Jobs permanece somente na rede Docker, sem listener TLS nem porta 8090 no host. A chamada usa `requests` via `SolrRequests.get`, com `rows=1` e `start=0`, porque o sucesso da ETL é uma lista JSON e não o envelope `response.numFound` do Solr (`jobs/api_rest/services/process.py:31-50`). O HTTP 200 só é aceito quando o corpo é uma lista não vazia e o primeiro item é um objeto não vazio com o `id_protocolo` solicitado. Contrato ausente ou inválido vira 404; erros HTTP e de transporte propagam com seu status (`custom_parsedquery.py:172-178`; `api_sei/db_models/solr_select.py:283-292,411-421`). A chamada reutiliza a HTTPBasicAuth do Solr (`SOLR_USER`/`SOLR_PASSWORD`, `envs.py:63-66`). O assistente não chama nenhuma outra app. Todo o restante é app→infra (LiteLLM, Postgres, Solr, Redis, RabbitMQ, API do SEI, serviços de busca web).

## LiteLLM — caminho de modelos do Assistente e ETL

Assistente e ETL falam com modelos somente pelo proxy LiteLLM (`infra-litellm`, porta 4000). O template publica cinco aliases fixos (`standard`, `mini`, `nano`, `embedding`, `speech-to-text`) e tags `agents:<papel>`; modelos, endpoints e chaves permanecem como `os.environ/VAR`, injetadas pelo Compose a partir de `security.env`. O proxy exige `LITELLM_PROXY_API_KEY`, que também é fornecida aos dois clientes. A Similaridade não chama LLM no fluxo atual.

`LITELLM_PROXY_API_KEY` é a credencial da fronteira cliente→proxy. Na fronteira
proxy→provedor, os tiers `standard`, `mini` e `nano` usam, respectivamente,
`LITELLM_STANDARD_API_KEY`, `LITELLM_MINI_API_KEY` e `LITELLM_NANO_API_KEY`;
embeddings usa `LITELLM_EMBEDDING_API_KEY`; speech-to-text usa
`LITELLM_STT_API_KEY`. Cada chave acompanha `API_BASE` e `API_VERSION` próprios.
Uma chave do proxy não substitui uma chave de provedor, e um tier não herda a
credencial de outro.

| Uso | Lib cliente | Modelos/papéis | Envs |
|---|---|---|---|
| assistente chat | `langchain_openai.ChatOpenAI` (`sei_ia/services/llm_models/get_model.py:125`) | alias `standard`/`mini`/`nano`, com tag do papel; thinking é `reasoning_effort` no request | `ASSISTENTE_LITELLM_PROXY_URL`, `ASSISTENTE_LITELLM_PROXY_API_KEY` |
| assistente embeddings | SDK `openai` sync+async (`services/embedder/embedding_generator.py:64`; `services/async_llm_requests/async_requests.py:229`) | alias `embedding`, tag `agents:embedding` | mesmas envs |
| etl-airflow embeddings | SDK `openai` via `LiteLLMEmbeddingProvider` (`aplicacoes/etl-airflow/jobs/services/embedder/embedding_generator.py:50`) | alias `embedding` | `LITELLM_PROXY_URL`/`LITELLM_PROXY_API_KEY` |

ETL e Assistente também fazem chamadas HTTP diretas autenticadas ao proxy: `POST {base}/v1/embeddings` pode resolver o deployment Azure pelo header `llm_provider-x-ms-deployment-name` (`litellm.py:87-132`; `azure.py:131-186`). No deploy integrado, o Compose fixa `LITELLM_EMBEDDING_MODEL_NAME=embedding` para roteamento e mantém `EMBEDDING_BASE_MODEL=${LITELLM_EMBEDDING_MODEL}` para tokenização e identidade da tabela, no Airflow e na Jobs API (`docker-compose.yml:43-45,355-357`). A tabela continua derivada somente do pin, chunk size e overlap; corrigir o roteamento não a renomeia (`jobs/envs.py:269`). Esse pin também evita rede na importação das DAGs; somente uma execução isolada sem ele tenta `GET {base}/model/info` (`jobs/envs.py:217`). No Assistente, speech-to-text usa o alias `speech-to-text`; ele e o catálogo público `GET /models` consultam `/model/info` com cache (`services/llm_models/speech_to_text.py:109-180`; `services/llm_models/model_catalog.py:75-189`; `routers/llm_models.py:20-40`). O `session_stream` usa a janela local do tier, mas valida `model` e `reasoning_effort` informados no payload contra esse catálogo. Falhas não são mascaradas: o endpoint de catálogo devolve 502 e valores incompatíveis viram 422 ou frame SSE de erro. A Similaridade não fala com o LiteLLM no fluxo atual (ver `service_architecture.md`).

No fluxo de áudio (`speech-to-text`), todo arquivo é normalizado antes do envio: entradas não-OGG são recomprimidas para Opus/OGG 16 kHz mono (`_transcode_to_ogg`), enquanto arquivos OGG passam por remux stream-copy (`_remux_ogg`, `-c:a copy -f ogg`) para corrigir containers com trailing nulls sem recodificação (`aplicacoes/assistente/sei_ia/services/llm_models/speech_to_text.py:285-330,495-559`).

## Postgres

| App | DSN | Driver | Modo |
|---|---|---|---|
| assistente | DB `SEI_LLM` (`configs/settings_config.py:94`); DSN montado em `model_post_init` a partir de `DB_SEIIA_*` (`configs/settings_config.py:462-480`) | psycopg2 + asyncpg | Triplo: engine sync, `create_async_engine` (asyncpg) e pool asyncpg nativo min 2/max 15 (`data/database/async_db_connection.py:67-127`) |
| similaridade | `postgresql+psycopg2://` montado em `api_sei/envs.py:24-27` (override por env `CONN_STRING_APP_DB`) → DB `sei_similaridade` | psycopg2 | 100% sync, QueuePool (`db_connection/db_connection.py:44-51`) |
| etl-airflow | `CONN_STRING_APP_DB` puro por env (`jobs/envs.py:67`) + DSN pgvector próprio para `SEI_LLM` (`jobs/db_models/embedding.py:62-70`) | psycopg2 + asyncpg | Engine sync + pool asyncpg (a variante do etl de `AsyncDbConnector` não tem async engine) |

Pool comum aos três engines sync: `pool_size=5, max_overflow=10, pool_recycle=360, pool_pre_ping=True`.

O metastore do Airflow é conexão separada (`AIRFLOW__DATABASE__SQL_ALCHEMY_CONN`, `jobs/envs.py:94-96`). A API interna de jobs também recebe esse DSN porque importa a configuração compartilhada de `jobs/envs.py` (`docker-compose.yml:338-359`).

## Solr

Auth básica compartilhada: `HTTPBasicAuth(SOLR_USER, SOLR_PASSWORD)`, montada na similaridade (`api_sei/envs.py:61-64`) e no etl (`jobs/envs.py:99-108`), passada por chamada.

Leitura (similaridade): `SolrRequests.select` (`requests` sync, `api_sei/db_models/solr_select.py:307`) e a função `async_solr_requests` (`httpx.AsyncClient` para queries paralelas, `api_sei/db_models/solr_select.py:38-66`) — nos handlers `/mlt` e `/select` (`api_sei/db_models/solr_mlt.py:284-373`). As consultas assíncronas usam `SOLR_READ_TIMEOUT_SECONDS` para leitura, com default de 30 s, separado do deadline global `SEI_API_DB_TIMEOUT` de 120 s.

A indexação sob demanda usa `commitWithin: 1000` (`aplicacoes/etl-airflow/jobs/dags/database/generic_sender.py:84-95`), portanto o HTTP 200 do update não garante visibilidade imediata no searcher. Após o sucesso da ETL, a similaridade consulta o Solr até cinco vezes, com início imediato e novas tentativas a cada 2 s. Cada GET tem timeout de 2 s e o polling respeita um prazo monotônico total de 10 s antes de extrair os termos (`custom_parsedquery.py:91-125`, chamada em `:180`). Uma `parsedquery` vazia faz o MLT customizado devolver `recommendation: []`, inclusive com `debug=true` ou `normalized=true`, sem enviar POST em branco nem `*:*` ao Solr (`api_sei/db_models/solr_mlt.py:357-368,387-416`; propagação pelos agregadores em `api_sei/services/hybrid.py:112-121` e `api_sei/services/rerank.py:85-88`).

O listener HTTPS da Similaridade mantém `proxy_read_timeout 280s`: 120 s para a chamada à Jobs API, 10 s para a visibilidade no Solr, 120 s para a consulta final de recomendação e 30 s de margem operacional. Assim o gateway não encerra uma requisição válida antes dos limites do backend (`ops/gateway/nginx.conf:76-91`; `aplicacoes/similaridade/api_sei/envs.py:72-73`; `aplicacoes/similaridade/api_sei/resources/custom_parsedquery.py:41-44,159-180`; `aplicacoes/similaridade/api_sei/db_models/solr_mlt.py:364-368`; `aplicacoes/similaridade/api_sei/db_models/solr_select.py:38-66`).

Escrita e administração do Solr pertencem ao etl-airflow: `GenericSender` envia documentos e os jobs administram os cores. O Assistente não grava logs de chat no Solr. Veja `jobs/dags/database/generic_sender.py` e `jobs/db_models/solr_handlers.py`.

## Redis

Padrão produtor/invalidador sobre o mesmo Redis (`REDIS_URI`, default `redis://infra-redis:6379/0`).

Assistente (produtor): `redis.asyncio` com `BlockingConnectionPool` (`sei_ia/services/cache/redis_client.py:109-117`) — cache de documentos com TTL (chaves diferenciadas por intervalo via `pag_ini`/`pag_fim` em `cache_keys.py`, impedindo que cache de documento inteiro atenda requisições parciais), cache de anexos por tópico (`services/cache/topic_attachments.py`), lock distribuído SET NX + Lua para release atômico (`redis_client.py:332-399`) e circuit breaker que abre após 5 erros consecutivos e reseta em 60s (`redis_client.py:68-71`).

etl-airflow (invalidador): mesma lib, `ConnectionPool` simples, só `invalidate_documents` — SCAN por prefixo + delete após reindexação (`aplicacoes/etl-airflow/jobs/services/cache/redis_client.py:90-137`, chamado por `jobs/dags/dag_objects/mlt_etl_process/dag_mlt_cache_invalidation.py:139-142`). A similaridade não usa Redis.

## RabbitMQ / Celery

Exclusivo do etl-airflow: `CeleryExecutor` (`default.env:12`), broker `amqp://...@infra-rabbitmq:5672//` com credenciais `AIRFLOW_AMQP_USER`/`AIRFLOW_AMQP_PASSWORD` (`docker-compose.yml:36`), result backend no Postgres do Airflow — não no Redis (`docker-compose.yml:35`).

Workers: 3 réplicas × concorrência 8 (`default.env:111-112`), fila default (sem filas nomeadas). Assistente e similaridade não usam Celery nem filas.

## API do SEI

REST sobre HTTP GET puro via `libs/sei_api` (`SeiApiClient`, `libs/sei_api/src/sei_api/client.py:12-27`); `requests` sync (`_base.py:113`) e `httpx` async (`_async.py:115`). Base URL: `${SEI_ADDRESS}/sei/controlador_ws.php` (env `SEI_API_DB_ADDRESS`, `docker-compose.yml:18`). Auth inteiramente por query string em toda request: `SiglaSistema` (env `SEI_API_DB_USER`) + `IdentificacaoServico` (env `SEI_API_DB_IDENTIFIER_SERVICE`) + `servico` com o nome do endpoint (`_base.py:89-99`) — sem headers, sem body.

Endpoints são a família `md_ia_*` (listagem de indexáveis/vetorizáveis, consulta de documento/conteúdo/processo, histórico de tópico). As três apps embrulham o client: assistente em `sei_ia/data/database/sei_client.py:86-103` (com `content_extractor` do `sei_extraction` e timeout que vira HTTP 412), etl em `jobs/db_models/sei_client.py:68-80` (com extractor), similaridade em `api_sei/db_models/sei_client.py:22-31` (sem extractor).

## Busca web (assistente)

Ativada por `use_websearch` no request. O agente Session instancia a ferramenta somente quando a flag está ligada (`agents/session_agent/agent.py:249`). RAG e pergunta permanecem em `scripts/legado/`, sem publicação de rotas. O grafo clássico foi excluído.

Cadeia, toda `httpx.AsyncClient` sem auth: SearXNG `GET {SEARX_BASE_URL}/search?format=json` (`agents/websearch/searx_crawl_tool.py:1009-1014`) → fastCRW `POST {FASTCRW_BASE_URL}/v1/scrape` com `{"url", "formats": ["markdown","rawHtml"]}` (`searx_crawl_tool.py:1392-1398`) → fallback byparr `POST {BYPARR_BASE_URL}/v1` (API FlareSolverr-compatible, `cmd: request.get`) só quando o fastCRW retorna vazio (`searx_crawl_tool.py:1317-1325`, gate em `:1404`).

## Streaming SSE

O streaming do Assistente é `/llm_lang/session_stream` (`sei_ia/routers/session/stream.py:701-707`), que responde com `StreamingResponse` e `media_type="text/event-stream"` (`session/stream.py:1693-1695`).

No gateway, buffering e cache de proxy ficam desligados e o upstream usa HTTP/1.1 com timeout de 600 s (`ops/gateway/nginx.conf:41-57`). Cada conexão SSE é encaminhada de forma independente; streams simultâneos não compartilham resposta nem aguardam buffer comum.

Formato: frames SSE `data: {json}\n\n` com campo `type` ∈ `status`/`reasoning`/`content`/`metadata`/`end`/`error` (helpers `_frame`/`_error_frame` em `session/stream.py:298-309`).

O frame final do `/llm_lang/session_stream` expõe o shape esperado pelo frontend em `metadata.data`. O `id_message` é o inteiro positivo gerado pelo `RequestMiddleware`; chamadas diretas podem fornecer `request.id_request` como fallback. O endpoint recusa iniciar o stream se nenhuma fonte produzir um valor válido, e reutiliza o mesmo ID na observabilidade e no frame final (`middleware/middleware_request.py:21-24`; `routers/session/stream.py:709-712,726-769,1490-1509`).

O `/llm_lang/session_stream` emite `Preparando sessão`, `Baixando documentos` e heartbeat sanitizado durante a preparação/materialização, no intervalo `ASSISTENTE_SESSION_PREPARATION_HEARTBEAT_INTERVAL_SECONDS`; depois do início do agente, emite heartbeat sanitizado `stage=session_agent` no intervalo `ASSISTENTE_SESSION_AGENT_HEARTBEAT_INTERVAL_SECONDS` (15–30 s). Esses frames não contêm path, documento ou prompt (`routers/session/stream.py:295-314,893-910,997-1022,1334-1390`). Em sessão preexistente, o término da preparação é `Sessão carregada` quando nenhum documento foi materializado — inclusive se algum pedido ficou indisponível — ou `Sessão atualizada` quando houve adição/atualização (`routers/session/stream.py:1041-1050`). `use_thinking=false` suprime o status `Pensando` e os frames `reasoning` (`routers/session/stream.py:1309-1310,1422-1427`).

Erros: `HTTPException` não atravessa o stream — quando o gerador roda, o status HTTP 200 já foi enviado, então levantar exceção não vira resposta 4xx/5xx. No `/llm_lang/session_stream`, as exceções capturadas dentro do gerador viram um frame `{"type": "error", "status_code": int, "detail": str, "timestamp": float}`, com o status embutido no payload, via `_error_frame` (`session/stream.py:303-310`) e `_map_exception` (`:334-359`), com catches em `:1878-1973`. `detail` é sempre string. Não há modelo Pydantic para frames SSE — são dict literals serializados. Quando o upstream do LLM silencia entre trechos e estoura o watchdog do LangChain (`StreamChunkTimeoutError`), a exceção é mapeada para `status_code=504` com mensagem sanitizada e um payload de diagnóstico com 10 campos em whitelist (`error_code="upstream_stream_timeout"`, `id_message`, `trace_id`, `stage`, `retryable=true`, `retry_mode="manual"`, `partial_response`, `timeout_s`, `model`, `chunks_received`). Esse diagnóstico e contadores coerentes de eventos SSE são copiados para o trace raiz e a observação de finalização. O trace registra `retryable=true` indicando reenvio manual pelo usuário; não há retry nem duplicação automática de resposta parcial, e frames de sucesso (`metadata`/`end`) não são emitidos em falha. Na factory compartilhada `get_model` (`services/llm_models/get_model.py:195-197`), o watchdog `stream_chunk_timeout` deriva do mesmo valor de `timeout` (`ASSISTENTE_TIMEOUT_API`, 900 s), substituindo o default de 120 s da biblioteca. O tradeoff de unificar em 900 s pode permitir que respostas longas com pausas completem normalmente, mas estende a espera quando o upstream trava silenciosamente; heartbeats SSE mantêm o cliente informado enquanto o watchdog aguarda.

No runtime pinned do benchmark isolado, o frame final `metadata` também pode carregar os documentos fresh efetivamente abertos para o judge protegido (`session/stream.py:551-590,1493-1544`; inventário em `:1269-1291`). O export exige snapshot pinned ativo; o header de coleta sozinho não o habilita. Esse SSE contém material sigiloso e deve permanecer em artefato `0600`; nenhum conteúdo bruto entra no resumo sanitizado, relatório ou ledger.

## Langfuse no session stream

O trace raiz `session_stream` nasce antes da validação e recebe `session_id`, `user_id`, `request_id`, versão, ambiente e tags de resultado/modo (`routers/session/stream.py:707-769`). O header `X-Langfuse-Trace-Id` só é reutilizado quando contém 32 caracteres hexadecimais minúsculos; qualquer outro valor é substituído (`routers/session/stream.py:111-115`). Seu `input` é o body sanitizado persistido como uma única string. Antes do envio, `ip` e `trace` são removidos, `no_cache` só permanece quando é `true` e todo campo `content` dentro dos documentos é retirado recursivamente (`routers/session/observability.py:33-110`). O metadata inicial repete esse texto em `original_request`, prefixado por uma única `\` para facilitar copiar/colar na UI (`routers/session/stream.py:732-769`). O `RunnableConfig` também carrega `langfuse_session_id` e `langfuse_user_id`; assim, o callback nativo liga os spans LangChain/deepagents à mesma sessão e ao mesmo usuário (`routers/session/stream.py:1241-1265`).

A árvore semântica usa `session.accept_request`, `session.prepare`, `session.materialize_documents`, `session.decide_mode`, `session.agent` e `session.finalize_stream`, além dos spans de classificação/preflight. Uma fonte de conteúdo usa o vocabulário sanitizado `available`/`empty`/`unavailable`; `empty` exige motivo de ausência textual e `unavailable`, motivo de recuperação/processamento, sem carregar erro cru (`data/content_status.py:13-61`). A sessão converte toda busca em outcome, inclusive 204, binário ausente e falha de extração (`routers/session/stream.py:339-468`).

O manifesto v2 registra todos os documentos pedidos: `requested_doc_ids` é o inventário lógico, enquanto `doc_ids` contém somente os que têm arquivo local. Internamente, manager e router usam índices por ID; no `session.json`, `processos` é uma lista ordenada e cada item contém seus documentos completos e ordenados, inclusive `metadata`, `download_ext` e `sin_armazena_cache` (`services/session_fs/types.py:151`, serialização em `:182`). O leitor aceita v1 e o migra em memória para v2 com política e `download_ext` desconhecidos (`null`); esses documentos são revalidados na mesma resolução antes da gravação v2 (`services/session_fs/types.py:222`; `services/session_fs/manager.py:99`). Uma pasta existente sem manifesto legível falha fechada e só pode ser recriada com `no_cache=true` (`services/session_fs/manager.py:302`). A tool `read_session` captura a árvore por closure em um snapshot imutável, expõe esses campos e navega o catálogo inteiro ou filtra por processo/documento, sem reler disco/rede nem devolver conteúdo integral (`agents/session_agent/read_session.py:105`, `:186`). Cada documento pode ter `content_state`, `content_reason`, número formatado e `arquivo`; uma materialização indisponível usa arquivo nulo. O trace separa `requested` (payload atual) de `scheduled` (payload reconciliado com o manifesto), além de expor reutilizados, materializados, disponíveis e indisponíveis (`routers/session/observability.py:219`).

O `session_stream` não reserva `max_output_tokens`: os modelos de texto e
`get_model` omitem `max_completion_tokens`/`max_tokens`, deixando o limite efetivo
da resposta a cargo do provider. O profile informa `max_input_tokens` ao Deep
Agents, que descarrega resultados grandes de tools, compacta o histórico ao se
aproximar da janela e tenta novamente após overflow. A `read_session` devolve o
catálogo sem impor um orçamento paralelo (`agents/session_agent/read_session.py:188-265`;
`agents/session_agent/agent.py:221-224,318-330`). O modo `injected` continua limitado
pelo threshold anterior à montagem do agente (`agents/session_agent/mode.py:25-55`).

O request aceita o campo opcional `mode` (`injected` ou `filesystem`) para testes; ausente/nulo mantém a decisão automática pelo threshold e, quando informado, o override aparece no span `session.decide_mode` (`routers/session/stream.py:212`, `:1200`; `agents/session_agent/mode.py:31`). A decisão documental considera somente `id_procedimentos[].id_documentos[]` do payload e o manifesto persistido; mencionar um número no texto livre não agenda documento (`routers/session/stream.py:529`). No primeiro uso, política ausente força leitura fresca para o SEI decidir. Em seguida, payload sem a flag herda a política anterior; todo documento persistido com `sin_armazena_cache="N"` ou `null` volta ao plano mesmo se foi omitido do payload ou se o turno trouxe somente outros processos/documentos (`services/session_fs/manager.py:99`).

Cada busca obrigatória ignora o arquivo local, elimina as variantes Redis e consulta de novo os metadados e o conteúdo; os metadados são repassados à extração para não provocar uma segunda consulta redundante (`routers/session/stream.py:362`). A resposta fresca do SEI define a política persistida para a iteração seguinte. Se a busca falhar, o manager apaga o arquivo anterior e preserva `N` ou `null`, mantendo o documento elegível para nova tentativa sem servir conteúdo obsoleto (`services/session_fs/manager.py:538`). Documentos confirmados como `S` conservam o reuso normal. O manifesto v2 continua acumulativo: um turno sem `id_procedimentos` preserva a árvore existente e novos processos/documentos são anexados mantendo a ordem anterior. `removed_from_manifest` permanece vazio nesse fluxo incremental; `files_pruned=false` explicita que arquivos não são podados — apagar uma cópia obsoleta após falha de atualização obrigatória é uma operação distinta (`services/session_fs/manager.py:382`, `:456`).

Quando a busca web rasa está ativa, o manifesto v2 também mantém a seção top-level `websearch`: `searched` é cumulativo, `path` é o diretório real `web/`, `latest_response_sources` lista as fontes vinculadas à resposta mais recente e `other_sources` guarda as demais fontes consultadas. A tool `read_session` expõe o indicador, o path, as fontes recentes e somente `other_sources_count`; em turnos posteriores sem websearch a seção é preservada (`agents/websearch/web_research_agent.py:418`; `agents/session_agent/read_session.py:164`; `services/session_fs/types.py:151`; `routers/session/stream.py:1617`, `:1855`).

No `session_stream`, uploads são processados por item de modo tolerante: cada bloco XML conserva ID, nome, extensão, estado e motivo; uma falha individual vira `unavailable` e não aborta o lote. A orquestração está em `routers/session/uploads.py:63`, usando os extratores existentes de `data/etl/extract/uploads.py`. O cache de anexos preserva estado/motivo e trata imagem sem bytes persistidos como `unavailable/visual_not_retained`. A remoção no SEI ocorre depois da resposta do agente, apenas para IDs elegíveis; a limpeza local de temporários não confirma a remoção da fonte.

A árvore automática de LangChain/deepagents usa `SessionLangfuseCallback` somente no `/session_stream`. Inputs e outputs de chains, generations e tools como `read_file` e `grep` viram resumos com tipo, bytes, caracteres ou itens e SHA-256; mensagens, erros e argumentos derivados recebem a mesma redação. O callback preserva nome, tipo, duração e token usage (`agents/session_agent/langfuse_callback.py:77-262`; criação e uso em `routers/session/stream.py:1152-1157,1292-1303`). Em paralelo, `SessionModelUsageHandler` agrega input total, cache read/write, output e reasoning por profile e por iteração; o metadata raiz registra `config_models`, `iteration_usage`, `model_usage` e `ocr_usage` (`agents/session_agent/usage.py:175-322`; `routers/session/stream.py:847-848,1465-1478`).

No encerramento, `session_stream.output.response.output` recebe o conteúdo integral da resposta do agente, sem truncamento; o mesmo objeto registra caracteres, bytes, SHA-256, contagem de frames SSE e envio de `metadata`/`end` (`routers/session/observability.py:309-342`; `routers/session/stream.py:1493-1593`). Falha, cancelamento ou interrupção preservam o resumo disponível e atualizam resultado, etapa, status e tags antes do flush (`routers/session/stream.py:1595-1686`).

O preflight estático `GET /llm_lang/session_benchmark_preflight` não abre sessão, recebe corpus nem chama LLM. Ele expõe profiles, aliases, reasoning, contextos e retry do cliente (`session/benchmark.py:27-74`). O preflight live `GET /llm_lang/session_benchmark_live_preflight`, habilitado somente quando o evidence index isolado está configurado, consulta o processo informado com o `sei_client` efetivo e devolve apenas hashes/status/tipo/duração; host cruzado, 401/403, vazio ou contrato divergente falham fechados (`session/benchmark.py:96-165`). O contrato completo está em `aplicacoes/assistente/experimentos/latencia-session-vs-classico/LONG_CONTEXT.md`.

A configuração e a política geral de mascaramento do Langfuse estão em `aplicacoes/assistente/docs/getting-started/environment.md`; o uso no harness protegido e sua relação com o benchmark estão em `aplicacoes/assistente/experimentos/latencia-session-vs-classico/LONG_CONTEXT.md`.

## Gotchas

- A chamada similaridade→etl-api reutiliza a HTTPBasicAuth do Solr (`custom_parsedquery.py:165-170`) — trocar credencial do Solr afeta também essa rota.

- A busca web ativa não usa Azure Bing Grounding. O session agent escolhe
  `WebResearchAgent` ou `DeepResearchAgent` no bloco de busca
  (`agents/session_agent/agent.py:262-333`).

- `MARKER_BASE_URL` existe no settings (`settings_config.py:451-454`) e o serviço expõe `POST /convert` (`ops/marker/server.py:20`), mas nenhum código no repo o chama — PDF é extraído localmente via pymupdf (`libs/sei_extraction/src/sei_extraction/parsers/pdf.py:28`). Setting sem consumidor.

- Fallback hardcoded do SearXNG no settings é `:8081` (`settings_config.py:438-441`), mas `default.env:80` define `:8080` — o env vence; não confie no default do código.

- O result backend do Celery é o Postgres do Airflow, não o Redis — o `infra-redis` é só cache do assistente/etl.

- A similaridade é a única app 100% sync com o Postgres (psycopg2 + QueuePool); não há caminho async nela.

- Consumidor do stream SSE: não confie no status HTTP (sempre 200 depois que o stream abre) — o erro real chega como frame `type: "error"` com `status_code` dentro do JSON.
