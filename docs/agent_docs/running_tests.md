# Running tests

A **fonte da verdade do que roda e bloqueia merge é o CI** (`.gitlab/ci/`). A imagem final candidata de cada componente afetado é criada primeiro e recebe um smoke de imports sem rede; depois as suítes executam o Python e o código dessa mesma candidata. No Assistente, esse Python é o Python de sistema da imagem final; o job instala somente `ci-test` nele e não cria `.venv`. O deploy reutiliza a candidata aprovada sem rebuild. Só `assistente` tem Makefile; ele oferece um gate de cobertura local extra (ver "Rodar localmente").

## O que roda no CI (verificado)

| Escopo | Comando (igual ao CI) | Job | Bloqueia merge? |
|---|---|---|---|
| Imagens afetadas | build seletivo + smoke da referência imutável | `build:candidates` | sim |
| Unit — assistente | `python -m pytest -n auto tests/unit` na candidata | `unit_test:assistente[:dev]` | pd/main sim · dev/hm não (`allow_failure`) |
| Integração DB — assistente | `python -m pytest tests/integration/test_database_bootstrap.py -n 0` na candidata | `integration_test:assistente:database_bootstrap` | sim |
| E2E — assistente | `python -m pytest tests/e2e -n auto -v --tb=short` na candidata | `e2e_test:assistente:dev` | dev/hm não (`allow_failure`); roda a suíte completa, incluindo os cenários de sessão, em branches de feature e novamente no push pós-merge para `dev`/`homologacao` |
| Unit — similaridade | `python -m pytest -n auto tests/unit` na candidata | `unit_test:similaridade[:dev]` | não (`allow_failure` temporário até a suíte estabilizar) |
| Unit — etl-airflow | `python -m pytest -n auto tests/unit` na candidata Airflow | `unit_test:etl-airflow[:dev]` | não (`allow_failure` temporário até a suíte estabilizar) |
| Lib `sei_extraction` | `python -m pytest tests -v --tb=short` na candidata Airflow | `test:sei-extraction` | sim, em todas as branches onde roda (sem `allow_failure`; só o `linter:sei-extraction` tem `allow_failure` em dev/hm) |
| Paridade de config de deploy | `pytest .gitlab/scripts/tests/` + contratos raiz de certificados, segredos, migração, gateway e Airflow (`.gitlab/ci/deploy-config-tests.yml:23`) | `test:deploy-config:parity` | sim, inclusive main, quando a configuração muda |

O job de integração sobe `pgvector/pgvector:pg16` vazio, marca o database como descartável e executa inicializações independentes em paralelo (`.gitlab/ci/quality-and-test.yml:581-612`; teste em `aplicacoes/assistente/tests/integration/test_database_bootstrap.py:381`). Ele valida idempotência, dimensão vetorial, as quatro tabelas e migrações do checkpointer, índices, preservação de sentinelas e liberação dos dois advisory locks depois de sucesso e falha. O teste recusa um database sem `ASSISTENTE_TEST_DATABASE_DISPOSABLE=1` ou com os schemas-alvo preexistentes (`test_database_bootstrap.py:35-49`).

Ponteiros dos demais jobs: `.gitlab/ci/quality-and-test.yml:501` e `:542` (unit assistente), `:795` e `:845` (E2E assistente), `:627` e `:668` (unit similaridade), `:712` e `:753` (unit etl-airflow), `:933` (sei_extraction); `.gitlab/ci/deploy-config-tests.yml:5` (paridade).

- **Ambiente do job:** cada suíte usa a referência local `sei-ia/<componente>:ci-<pipeline>`, publicada somente depois do probe, com `pull_policy: never`. O helper instala apenas o grupo travado `ci-test`; no Assistente ele usa `uv pip install --system --python /usr/local/bin/python --no-deps`, sem criar `.venv`. Depois copia testes e auxiliares para a camada efêmera da candidata, executa no diretório do código da imagem e recusa qualquer import que aponte para o checkout (`.gitlab/ci/quality-and-test.yml`; `.gitlab/scripts/run_candidate_tests.sh`).
- **Gatilho:** cada job só roda quando há mudança no escopo da app/lib (`changes:` nas `rules`).
- **Paridade:** o job reutiliza `docker:27-cli` do build/deploy, com Compose V2, e instala Git, jq, Make, OpenSSL e Python no container efêmero. A suíte roda sem root, em virtualenv, para verificar também falhas reais de permissão; testa o Compose e `make config` sem ativar a stack. Nenhum pacote é instalado no host do runner.
- **Primeiro push da branch:** o GitLab considera todas as `rules:changes`
  verdadeiras quando `CI_COMMIT_BEFORE_SHA` é zero. Nesse caso,
  `build:candidates` publica as candidatas de todas as aplicações, reutilizando o
  cache por fingerprint ou reconstruindo somente a imagem ausente, antes que os
  jobs com `pull_policy: never` sejam preparados
  (`.gitlab/scripts/deploy_changed.sh:551`).
- **Cobertura:** o unit gera `coverage.xml` (artifact), consumido pelo SonarQube (`.gitlab/ci/sonar.yml`).

Lint e Sonar analisam o checkout; as suítes analisam a candidata. A prova da imagem começa no `build:candidates`, que executa o smoke na referência final, e continua nos testes que usam a referência `ci-<pipeline>` com o mesmo image ID. O deploy confirma que o container saudável usa a referência de release daquele ID. A candidata Jobs API recebe smoke próprio; o código compartilhado de Jobs e das bibliotecas também é exercitado pelos unitários na candidata Airflow, que contém a mesma fonte. O Sonar roda antes da ativação e sua reprovação fica visível, mas temporariamente não bloqueia nenhuma branch, inclusive produção. Como o daemon Docker fica no host e não enxerga o filesystem do job, o CI copia o checkout limpo para um volume Docker temporário, monta esse volume somente no scanner e o remove no `after_script` (`.gitlab/ci/sonar.yml`). O BuildKit integrado `default` constrói candidatas e scanner com `network: host`/`--network host` somente durante o build; os containers do scanner continuam na rede `sonarnet`. Relatórios Bandit ficam fora de `sonar.working.directory`, pois o scanner limpa esse diretório antes de importar o relatório (`ops/sonarqube/scan-all.sh`).

Os downloads do pequeno grupo `ci-test` ficam no cache UV local do runner, sob `uid0`, fora do checkout. A tabela BPE que o Tiktoken baixa separadamente também fica no `/cache` do host. O runner não arquiva esses diretórios no cache do GitLab. As dependências da aplicação e wheels grandes, como Torch, pertencem às layers e cache mounts BuildKit das candidatas; o job de teste não as reinstala. Os caches BuildKit das imagens UID 4000 e do Airflow UID 50000 são independentes desse volume do runner. Para Ruff/Regexploit, `cache:quality-tools` publica uma vez o cache Pip pequeno; os consumidores usam `policy: pull`. Antes da primeira pipeline que usa candidatas, recrie ou reinicie o container do runner uma vez para carregar `allowed_pull_policies` e liberar `pull_policy: never`.

O runner aceita dois jobs simultâneos. Suítes com `-n auto` ficam limitadas a quatro workers por job por `PYTEST_XDIST_AUTO_NUM_WORKERS`; builds de candidatas são serializados por ambiente com `resource_group`, enquanto checks e testes independentes podem ocupar os dois slots (`.gitlab/runner/entrypoint.sh`; `.gitlab/ci/build-candidates.yml`; `.gitlab/ci/quality-and-test.yml`).

Uma pipeline de feature aprovada pelo Sonar grava no servidor de desenvolvimento um comprovante da árvore Git e da assinatura da candidata. Na pipeline do merge em `dev`, os gates encerram imediatamente quando `build:candidates` prova que os inputs são idênticos. A otimização não se aplica a merge com conteúdo diferente nem a homologação/produção, porque os servidores continuam isolados (`.gitlab/ci/build-candidates.yml`; `.gitlab/ci/sonar.yml`; `.gitlab/scripts/release_manifest.py`).

## Apps com gate parcial no CI

`similaridade` e `etl-airflow` têm job de CI (`unit_test:<app>[:dev]`, ver tabela acima), mas rodam só `tests/unit` — `tests/integration/` não entra no gate (Solr/Postgres mockados via `tests/integration/mock_solr.py` no similaridade; no etl-airflow, `tests/integration/test_solr.py` sobe um container Solr real via `docker` SDK). Local, sem restrição: `uv run pytest -n auto tests` roda tudo (unit + integration), mas `tests/integration` do etl-airflow precisa de Docker disponível.

## Lint e formatação (Ruff)

O quality gate do CI é **Ruff** pinado `ruff==0.14.10` (`.quality_job`, `.gitlab/ci/quality-and-test.yml:1`), **não** `make check`.

- `linter:<app>` → `ruff check --statistics .` (`:103`)
- `formatter:<app>` → `ruff format --check .` (`:164`)
- Apps: `assistente`, `similaridade`, `etl-airflow`; lib: `linter:sei-extraction` (sem formatter).
- **dev/hm:** `allow_failure` (não bloqueia). **pd/main:** bloqueia o merge.
- Ruff é determinístico — não é trabalho do Claude refazer à mão.

## Config de pytest

`[tool.pytest.ini_options]` em `aplicacoes/assistente/pyproject.toml:123` — `addopts` com `--cov=sei_ia` e relatórios, `--strict-markers`; `pytest-xdist` habilita `-n auto` (paralelo). Fixtures e hooks compartilhados em `aplicacoes/assistente/tests/conftest.py` (`test_config` por sessão; mocks de user/RAG/chunks; `pytest_collection_modifyitems`).

## Rodar localmente (dev)

De dentro de `aplicacoes/assistente`, na `.venv` (`uv sync --extra dev`):

- Unit: `uv run pytest -n auto tests/unit`
- Bootstrap real: defina `ASSISTENTE_TEST_DATABASE_URL` para um PostgreSQL com pgvector **descartável e vazio**, defina `ASSISTENTE_TEST_DATABASE_DISPOSABLE=1` e rode `uv run pytest tests/integration/test_database_bootstrap.py -n 0`. O teste não limpa o banco; descarte a instância depois.
- E2E completo: `uv run pytest -n auto tests/e2e`
- Um teste só: `uv run pytest tests/unit/<arquivo>::<teste>`
- Unit + gate de cobertura local: `make test` — roda pytest `tests/unit` e aplica o Quality Gate de 80% no *new code* vs `origin/dev` (reproduz o SonarQube), via `aplicacoes/assistente/scripts/check_coverage_gate.py`. O task `pre-commit` (taskipy, `aplicacoes/assistente/pyproject.toml:173`) faz ruff check + ruff format + esse gate.
- Smoke dos endpoints: consulte `aplicacoes/assistente/scripts/README.md`.
- Worktrees Codex instalam os hooks da raiz no setup. O `pre-commit` permanece rápido;
  o `pre-push` primeiro reproduz a renderização sem segredos usada por
  `build:candidates` quando muda Compose, contrato de ambiente, hook ou CI. Ele
  também executa `uv run --group ci-test pytest -n auto --maxfail=1 tests/unit` e
  `uv run --group ci-test pytest --maxfail=1 tests/e2e/test_feedback.py -v --tb=short`
  quando o push
  altera `aplicacoes/assistente`, `libs/sei_api` ou `libs/sei_extraction`. Quando o
  push altera `libs/sei_extraction` ou seu job de CI, executa também
  `uv run --extra dev --extra extract python -m pytest --maxfail=1 tests -v --tb=short`
  de dentro da biblioteca. O extra `extract` instala o cliente OpenAI usado pelos
  testes OCR. Instale ambos os hooks da raiz com
  `uv run --project aplicacoes/assistente --frozen pre-commit install --config .pre-commit-config.yaml --hook-type pre-commit --hook-type pre-push`.
  Esses gates são locais e não mudam as regras de disparo do CI/MR.

De dentro de `aplicacoes/similaridade` (`uv sync --extra dev --extra otel` — o `otel` é necessário porque `api_sei/main.py` importa middleware do OpenTelemetry incondicionalmente, e é um extra separado do `dev`):

- Unit (igual ao CI): `uv run pytest -n auto tests/unit`
- Unit + integration (mockado, sem Docker): `uv run pytest -n auto tests`

## Smoke tests do Assistente

O CI bloqueia merge, mas uma mudança de integração só está pronta depois de uma
chamada real com o código local. Os pontos de entrada canônicos ficam em
`aplicacoes/assistente/scripts/`:

- `smoke_session_host.py`: `/llm_lang/session_stream` em uvicorn local, com payload
  JSON e documentos do SEI;
- `smoke_session_stack.sh`: chama o mesmo endpoint pela stack já iniciada; não sobe,
  reinicia nem derruba containers.

Exemplos:

```bash
cd aplicacoes/assistente
uv run python scripts/smoke_session_host.py --payload scripts/req_8116731.json
scripts/smoke_session_stack.sh --payload scripts/req_8116731.json
```

O modo host precisa de `ASSISTENTE_LITELLM_PROXY_URL` resolvível pelo host; nomes da
rede Compose só funcionam no modo stack. Para o contrato completo, opções e
configuração de trace, use o README da pasta.

Para revisar uma mudança, suba uma API supervisionada a partir da worktree
alterada e chame `smoke_session_host.py` com `--no-serve --no-blob-check` e
`--url` apontando para esse processo. Não reutilize uma API de origem desconhecida.
Use serviços autorizados, arquivos de sessão isolados e IDs de teste apropriados.
O startup executa bootstrap de banco; encerrar o processo não desfaz essas escritas.

Confirme HTTP 200, `Content-Type: text/event-stream`, conteúdo não vazio, ausência
de `error` e uma `metadata` seguida de `end`. Para continuidade, envie dois turnos
com o mesmo usuário/tópico e `no_cache: false` no segundo payload. Verifique a
resposta, não apenas o exit code do smoke. `session_local_e2e.py` usa TestClient e
substituições de SEI/checkpointer, mesmo com LLM real, portanto não substitui essa prova.
Não crie testes de 404 para as rotas retiradas.

## Aceitação funcional da release

A aceitação externa continua manual pela interface do SEI: entre com um usuário
autorizado, abra o Assistente, envie `Oi` e confirme que a resposta aparece
normalmente. O CI executa os E2Es herméticos do endpoint de sessão, uploads,
modos e busca web, mas eles não exercitam módulo, certificado, gateway, backend
e modelo reais em conjunto.

## Fluxo de fix

Bug não fecha sem teste que o prove. Ordem:

1. **Reproduza com chamada real** — use o smoke correspondente ao endpoint e evidencie o problema **antes** de mexer no código.
2. **Escreva um teste que captura o erro** — simula o cenário e verifica o comportamento errado; ele deve **falhar** no código atual.
3. **Conserte até o teste passar** — e revalide com a chamada real do passo 1.

## Padrão de teste

- **Comportamento, não unit inútil.** O teste valida o comportamento esperado do que mudou, não a mecânica trivial de uma função. Teste que não pega regressão real não merece existir.
- **Fixture quando necessário** para montar o cenário do comportamento, não para inflar contagem.
- **Reutilize fixture existente** se ela já cobre o edge case; só crie nova quando nenhuma cobrir.
- Markers (`aplicacoes/assistente/tests/conftest.py:70`): `unit`, `integration`, `slow`, `external_api` (pulado em modo teste, `:101`), `real_db` (PostgreSQL via Testcontainers). `unit`/`integration` são aplicados por path automaticamente (`:87`).

## Fixtures (onde encontrar)

- `aplicacoes/assistente/tests/fixtures/documents/` — um arquivo de exemplo por content-type (csv, doc/docx, htm/html, jpg/jpeg, png, webp, json, md, txt, rtf, tsv, xml, mp3, wav, odp/ods/odt, ppt/pptx, xls/xlsb/xlsm/xlsx).
- `aplicacoes/assistente/tests/fixtures/mock_data.py` — fábricas de UserState, chunks, questions, search results, embeddings.
- `aplicacoes/assistente/tests/conftest.py` — fixtures de sessão (config, mocks de LLM/DB/embeddings, Testcontainers Postgres/Redis). Conftest por área em `tests/{unit,services,rag,e2e}/conftest.py`.
- `aplicacoes/etl-airflow/tests/integration/fixtures/` — fixtures de integração do ETL.
- `libs/sei_extraction/tests/conftest.py` — fixtures da lib de extração.

## Apontar para o SEI de produção (`.env`)

Para validar fluxos que dependem de **documentos completos**, aponte o SEI no `.env` local (gitignored) para o ambiente de produção:

- `SEI_ADDRESS` — endereço do SEI. Os smoke scripts e o compose aceitam `SEI_ADDRESS` e mapeiam para o campo real do `Settings`, `SEI_API_DB_ADDRESS` (`scripts/smoke_endpoint_host.py:218-225`; `configs/settings_config.py:393`).
- A **chave de verificação** é o `SEI_API_DB_IDENTIFIER_SERVICE` (o `IdentificacaoServico`, tratado como token pela lib `sei_api`), junto com `SEI_API_DB_USER` (`Usuario_IA`). O client monta a conexão com esses três — `sei_client.py:88-90`. A chave fica **só no `.env`/`security.env` local**, nunca commitada.
- **Por quê produção:** o SEI de homologação pode não conter todos os documentos (externos); para validar com documentos completos, aponte o `.env` para o SEI de produção. O detalhe dos ambientes (nomenclatura, o que cada um contém) está na documentação interna de workflow, não incluída no mirror externo.

## Gotchas

- **Cobertura é avaliada pelo Sonar (e pelo gate local), não pelo job de pytest:** no CI, `unit_test:assistente` roda pytest **sem** falhar por cobertura — gera `coverage.xml` e o **SonarQube** aplica o gate de 80%. A reprovação é temporariamente informativa em todas as branches, inclusive produção. Localmente, `make test` / `task pre-commit` reproduzem esse gate antes do MR (`scripts/check_coverage_gate.py`). Pytest verde no CI ≠ cobertura ok.
- **`make check` ≠ CI:** o alvo `check` de `aplicacoes/assistente/` roda `uv lock --locked` + pre-commit + mypy + deptry; o CI usa só os jobs Ruff. São checks diferentes. Na raiz, `make check` executa um contêiner efêmero contra a stack já iniciada, sem derrubá-la. Ele reprova contrato `.env`, health, OOM/reinício, logs recentes, TLS/SAN, conectividade, os cinco aliases do LiteLLM e erros de importação das DAGs.
- **mypy em `make check` da assistente:** o `uv sync --extra dev` (de `aplicacoes/assistente`) **não instala mypy** — ele não está declarado em `optional-dependencies` nem em `dependency-groups` da assistente diretamente (vem de `libs/sei_api[dev]`, que não é ativado transitivamente). O **deptry** não está declarado em lugar nenhum. Instale ambos manualmente na `.venv` da assistente (`uv pip install mypy deptry`) antes de rodar `make check`.
- **`test:deploy-config:parity`** executa também o gerador real com catálogo fictício (via `jq`), valida aliases fixos, reasoning e rejeição de catálogo inválido. Confere que o gerador emite exatamente o contrato de `security_example.env` e copia o template LiteLLM sem renderizar segredos (contexto em `building_the_project.md` › "Configuração de ambiente").
- `etl-airflow` só roda `tests/unit` no CI (`allow_failure` temporário) — ver "Apps com gate parcial no CI".
