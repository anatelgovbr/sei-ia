# Container topology

Topologia de **runtime**: quais containers a stack sobe, de qual app vêm e por quê. A estrutura de *código* (apps, libs, pastas) está em `service_architecture.md`; **como** buildar/subir em `building_the_project.md`; ambientes e hostnames estão na documentação interna de workflow (não incluída no mirror externo). Tudo é orquestrado pelo **`docker-compose.yml` na raiz**.

## Como ler

- O Compose base nomeia imagens customizadas como `sei-ia/<app>:local`; no CD, um override fixa cada serviço na referência imutável da release. Elas são buildadas dos **Dockerfiles das apps** (`context: .`, raiz do repo). Cada imagem compartilhada possui um único serviço representante com `build`, enquanto os demais somente referenciam a mesma tag. Mapa imagem↔app em `service_architecture.md`.
- O compose usa anchors YAML para defaults comuns: `x-websearch-common` (`docker-compose.yml:3`), `x-app-common` (`:10`), `x-airflow-common` (`:20`).
- **Profiles** decidem o que sobe: serviços sem profile são **sempre-on** no Compose. O comando oficial `make up` também ativa `web-search`; somente `checks` continua sob demanda por `make check` (`Makefile:1,13-15,60-61`).
- **Recursos**: todos os serviços sempre-on têm limites explícitos. `default.env` representa o servidor dedicado de referência (16 vCPUs, 128 GB RAM): três workers Airflow com concorrência oito e Solr com heap de 2–6 GB. Reduções feitas para laboratórios são overrides locais e não viram defaults de release.

## Serviços sempre-on

**Apps e gateway:**

| Container | Imagem / Dockerfile | Papel | Porta (host→cont.) | Depende de |
|---|---|---|---|---|
| `gateway-nginx` | Nginx 1.27 Alpine fixado por digest + `ops/gateway/nginx.conf` | Único terminador TLS das APIs do SEI; access log estruturado somente para `4xx`/`5xx`, sem `/health` | 8088→8088, 8082→8082, 8086→8086 | três backends healthy |
| `assistente` | assistente.dockerfile | GenAI (`gunicorn sei_ia.main:app`) | HTTP 8088 interno (`docker-compose.yml:62-100`) | postgres, redis, litellm |
| `similaridade` | api_sei.dockerfile (`api_sei.main:app`) | API de recomendação (Solr) | HTTP 8082 interno (`docker-compose.yml:164-180`) | postgres, solr |
| `similaridade-feedback` | **mesma imagem** (`app_api.main:app`) | Coleta de feedback (legado) | HTTP 8086 interno (`docker-compose.yml:192-208`) | postgres |

**Plano Airflow** (todos `sei-ia/etl-airflow:local`, exceto a API):

| Container | Papel | Porta | Depende de |
|---|---|---|---|
| `etl-airflow-init` | One-shot: `airflow db migrate` + cria usuário admin | — | postgres-airflow, rabbitmq, postgres (app), solr, redis (via anchor `x-airflow-common`, `docker-compose.yml:20`) |
| `etl-airflow-webserver` | UI + REST API do Airflow | 127.0.0.1:8081→8080 | init (completed) |
| `etl-airflow-scheduler` | Parser de DAGs + agendador | — | init |
| `etl-airflow-worker` | Worker Celery (executa as tasks) — `replicas: ${AIRFLOW_WORKERS_REPLICAS}` | — | init |
| `etl-airflow-triggerer` | Listener de triggers assíncronos | — | init |
| `etl-airflow-api` | `jobs.api:app` (jobs_api.dockerfile) — **indexação sob demanda**: processo no Solr / embeddings no pgvector | HTTP 8642 interno (`docker-compose.yml:334-367`) | webserver, **postgres (app)**, solr, redis, litellm |

> A `etl-airflow-api` faz **indexação sob demanda** de itens que as DAGs ainda não cobriram: `/process/unindexed/...` busca o processo no SEI e o **indexa na hora no Solr** (`jobs/api_rest/services/process.py:44`), consumido pela **`similaridade`**; `/embeddings/generate` gera e grava embeddings de documentos no **pgvector**. Daí depender de `infra-solr` + `infra-postgres` (app), não do Postgres de Airflow. Complementa o pipeline agendado — detalhe em `service_architecture.md`.

**Infra** (imagens externas, todas internas à rede):

| Container | Imagem | Papel |
|---|---|---|
| `infra-postgres` | `pgvector/pgvector:pg16` fixada por digest | **DB das apps** (assistente + similaridade), com pgvector |
| `infra-postgres-airflow` | `postgres:13` fixada por digest | DB de **metadados do Airflow** (estado/DAGs/runs) — separado do das apps |
| `infra-solr` | `sei-ia/infra-solr:local` (solr.dockerfile) | Busca full-text + MLT + KNN |
| `infra-redis` | `redis:7.2-alpine` fixada por digest | Cache de documentos compartilhado pelo Assistente e ETL |
| `infra-rabbitmq` | `rabbitmq:3-management` fixada por digest | Broker Celery dos workers Airflow; o healthcheck roda como `rabbitmq` para não criar o cookie Erlang com proprietário incorreto (`docker-compose.yml:409-428`) |
| `infra-litellm` | LiteLLM `main-stable` fixada por digest | Proxy LLM autenticado (porta 4000) para Assistente e ETL |

> **LangFuse não está na stack padrão.** A observabilidade LangFuse só roda no ambiente transversal (documentação interna de workflow, não incluída no mirror externo) e não sobe com o compose padrão; **releases externos não incluem LangFuse por padrão**. As apps integram com ele só quando configurado nesse ambiente (ex.: `aplicacoes/assistente/sei_ia/configs/langfuse_config.py`).

## Por que vários containers por app

- **Três APIs → um gateway:** Assistente, Similaridade e Feedback rodam em HTTP interno. O `gateway-nginx` termina o mesmo certificado em três listeners; a porta seleciona o backend mesmo para caminhos sobrepostos como `/health` e `/openapi.json`.
- **Gateway resiliente:** `init: true` recolhe processos filhos do healthcheck, o driver `json-file` limita os logs a `20m × 5` e `TZ=America/Sao_Paulo` mantém o horário ISO em UTC-3; o access log em stdout registra somente `4xx`/`5xx`. O request buffering e o limite de `100M` do listener do Assistente permanecem inalterados (`docker-compose.yml:114-162`; `ops/gateway/nginx.conf:7-60`).
- **`similaridade` → 2 containers:** `similaridade` (API principal, 8082) e `similaridade-feedback` (8086) usam a **mesma imagem** com **comandos diferentes** (`api_sei.main:app` vs `app_api.main:app`) — o feedback legado fica isolado em processo próprio.
- **`etl-airflow` → 6 containers:** o plano Airflow exige init + webserver + scheduler + worker(s) + triggerer; a `etl-airflow-api` é um container à parte (Dockerfile próprio) porque faz **indexação sob demanda** (Solr/embedding) — imediata e síncrona —, não a orquestração agendada das DAGs.

## Profiles

- **`web-search`** (anchor `x-websearch-common`, `docker-compose.yml:3-8`) — pilha oficial de busca web/crawl consumida pelo `assistente`: `infra-searxng`, `infra-lightpanda`, `infra-chrome`, `infra-fastcrw`, `infra-byparr`, `infra-marker`. O Makefile ativa esse profile em todos os comandos da stack, portanto `make up` constrói e inicia os seis serviços junto com os demais. O operador só precisa informar `--profile web-search` ao executar o Compose diretamente. Protocolo em `service_communication_patterns.md`.
- **`checks`:** `stack-config-checker` (`ops/healthchecker.dockerfile`, dependências exatas em `ops/healthchecker-requirements.txt`, roda `teste.py`): `make check` o executa com `compose run --rm --no-deps` contra a stack já iniciada. Reprova diferenças no inventário `.env`, health, OOM/reinícios, erros recentes, TLS/SAN, conectividade — incluindo o SearXNG —, aliases LiteLLM e imports das DAGs. O PEM público é montado separadamente e uma `tmpfs` mascara a `.runtime` do bind raiz para não expor a chave.

## Entrypoints e isolamento

- **APIs HTTPS expostas ao SEI:** somente `gateway-nginx` em 8088, 8082 e 8086. As URLs e portas do SEI não mudam.
- **Outros acessos:** `etl-airflow-webserver` publica 8081 apenas no loopback. Jobs não publica porta no host; `similaridade` o acessa por `http://etl-airflow-api:8642` na rede Docker.
- **Debug explícito:** `docker-compose.debug.yml` publica Postgres, Solr, Redis e LiteLLM somente quando passado com `-f`; não existe `docker-compose.override.yml` para carregamento automático.
- **Rede:** todos em `seiia` (`docker-compose.yml:741-744`) — rede **externa/pré-existente** (criada no host antes do `up`; nome via `${COMPOSE_NETWORK_NAME}`).
- **Solr em volume limpo:** os configsets ficam na imagem e o entrypoint os sincroniza para o volume antes de iniciar (`ops/solr/solr.dockerfile:11-15`; `ops/solr/entrypoint.sh:65-69`). A API de jobs cria `processos_bm25` e `documentos_bm25` após o Solr ficar saudável (`aplicacoes/etl-airflow/jobs/api.py:36-51`).
- **Volumes nomeados:** `redis_data` (persistência Redis), `health_checker_logs` (logs do checker), `byparr_camoufox_cache` (cache do byparr) — `docker-compose.yml:746-749`.

## Fora da stack: agente de métricas do CD

Nos servidores implantados pelo CD roda também o projeto Compose `seiia-telegraf`, com métricas de host e de containers em `:50055`. Ele não pertence a este `docker-compose.yml` e não sobe com `make up`; o mecanismo está em `building_the_project.md`, em "Agente de métricas (Telegraf) — somente CD".

## Fora de escopo (cross-ref)

Como buildar/subir e config (`.env`/`security.env`) → `building_the_project.md`; ambientes/hostnames e CI-vars → documentação interna de workflow (não incluída no mirror externo); estrutura de código e o que cada app faz → `service_architecture.md`; protocolos entre serviços → `service_communication_patterns.md`.
