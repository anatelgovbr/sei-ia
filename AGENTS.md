# CLAUDE.md

Servidor de Soluções de IA do Módulo SEI IA (Anatel) — backend que serve o [Módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia). Três submódulos: **Assistente** (GenAI sobre documentos do SEI), **Similaridade** (processos e documentos similares), **ETL/Airflow** (indexação e geração de embeddings).

## Mapa do repositório

Monorepo. Cada app tem `pyproject.toml`/`uv.lock`/Dockerfile/Makefile próprios.

- `aplicacoes/assistente/` — assistente GenAI (FastAPI).
- `aplicacoes/similaridade/` — recomendação de processos/documentos similares.
- `aplicacoes/etl-airflow/` — orquestração de indexação/embeddings (Airflow).
- `libs/sei_extraction/` — extração/tratamento de documentos do SEI (compartilhada pelos 3 apps).
- `libs/sei_api/` — cliente da API do SEI (compartilhada).
- `ops/` — infra de apoio: `solr/`, `database/`, `healthchecker.dockerfile`, `searxng/`, `fastcrw/`, `marker/`. Detalhes de runtime em `docs/agent_docs/container_topology.md`.
- `docker-compose.yml` · `Makefile` (`up`/`down`/`check`) · `default.env`. `make check` na raiz valida a config da stack (container `stack-config-checker`); `make check` nas apps valida qualidade de código (ver `running_tests.md`).

## Como trabalhar

- **Dev:** uma app por vez, com `.venv`/`uv` dentro de `aplicacoes/<app>` (Python 3.12 — nunca o do sistema).
- Antes de uma tarefa, leia o doc relevante em `docs/agent_docs/` (abaixo).


<agent_docs_index>

## docs/agent_docs/

- `building_the_project.md` — build (dev por app e imagens Docker), configuração (`.env` vs `default.env`/`security.env`/`litellm_config.yaml`), CI/CD.
- `running_tests.md` — testes (unit/integração/stack) e checks de qualidade.
- `code_conventions.md` — convenções do repo.
- `service_architecture.md` — o que cada app/lib faz e como o repo se divide (estrutura de código).
- `container_topology.md` — quais containers a stack sobe, de qual app vêm e por quê (runtime).
- `database_schema.md` — Postgres/pgvector e Solr.
- `service_communication_patterns.md` — como os serviços conversam (HTTP, fila, Airflow, proxy LiteLLM): protocolos, auth, libs cliente, streaming SSE.

</agent_docs_index>

<agent_docs_maintenance>

Estes docs são contrato, não comentário — mantenha-os sincronizados com o código:

- Ao mudar algo coberto por um doc acima (rota, container, schema, job de CI, convenção), **atualize o doc na mesma MR**. Doc desatualizado é pior que doc ausente.
- Ao criar/remover/renomear um doc em `docs/agent_docs/`, atualize o índice `<agent_docs_index>` acima.
- Estilo obrigatório (["Writing a good CLAUDE.md"](https://www.humanlayer.dev/blog/writing-a-good-claude-md)): enxuto, progressive disclosure, ponteiros `file:line` em vez de snippets, nada que Ruff/mypy já pegam. Verifique cada ponteiro `file:line` no código antes de gravar — não confie no texto anterior.

</agent_docs_maintenance>

## Regras universais

- Nomes de branches devem descrever o propósito da mudança, nunca o harness/runtime de agente usado para executá-la. Não inclua `codex`, `claude` nem o nome de qualquer outro harness; prefira, por exemplo, `docs/branch-naming-policy`.
- **Evitar fallbacks silenciosos** (try/except que mascara falha, alternar async/sync, recuperar de fonte secundária) salvo se o usuário pedir — na dúvida, perguntar. Bridges em fixtures de teste não contam.
