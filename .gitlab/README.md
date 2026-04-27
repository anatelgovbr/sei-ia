# GitLab CI e Runner

Configuracao minima de CI/CD, runner em container e deploy incremental por servidor.

## O que existe

- [`.gitlab-ci.yml`](/home/lx.ennio.colab/seiia_stack/deploy-monorepo/.gitlab-ci.yml) inclui [`.gitlab/ci/runner-branch-check.yml`](/home/lx.ennio.colab/seiia_stack/deploy-monorepo/.gitlab/ci/runner-branch-check.yml) e [`.gitlab/ci/deploy-dev.yml`](/home/lx.ennio.colab/seiia_stack/deploy-monorepo/.gitlab/ci/deploy-dev.yml)
- o job `runner-branch-check` roda em `push`
- o job `deploy-dev` roda depois do `precheck` e chama [`.gitlab/scripts/deploy_changed.sh`](/home/lx.ennio.colab/seiia_stack/deploy-monorepo/.gitlab/scripts/deploy_changed.sh)
- o runner usa executor Docker em container
- o runner e os containers dos jobs usam a rede `docker-host-bridge`
- `ENVIRONMENT` e `TARGET_BRANCH` no host decidem se o job executa ou faz `skip`
- o deploy faz `git pull --ff-only` no checkout persistente do host, detecta arquivos alterados, rebuilda apenas as imagens afetadas e sobe apenas os servicos necessarios
- o deploy sempre carrega `docker-compose.yml` e adiciona `docker-compose.override.yml` apenas quando `ENVIRONMENT=dev` ou `ENVIRONMENT=homolog`
- os builds acontecem no Docker do host via `/var/run/docker.sock`

## Arquivos do runner

- [`.gitlab/runner/docker-compose.yml`](/home/lx.ennio.colab/seiia_stack/deploy-monorepo/.gitlab/runner/docker-compose.yml): sobe o container do runner
- [`.gitlab/runner/.env.example`](/home/lx.ennio.colab/seiia_stack/deploy-monorepo/.gitlab/runner/.env.example): variaveis por servidor
- [`.gitlab/runner/entrypoint.sh`](/home/lx.ennio.colab/seiia_stack/deploy-monorepo/.gitlab/runner/entrypoint.sh): gera o `config.toml` na subida do container
- [`.gitlab/buildkit/buildkitd.toml`](/opt/seiia_deploy/.gitlab/buildkit/buildkitd.toml): fixa os DNS usados pelo BuildKit nos `RUN` do `docker buildx`
- [`.gitlab/scripts/ensure_buildx_builder.sh`](/opt/seiia_deploy/.gitlab/scripts/ensure_buildx_builder.sh): cria ou reutiliza o builder `seiia-bridge` na rede `docker-host-bridge`

## Subir

```bash
cp .gitlab/runner/.env.example .gitlab/runner/.env
docker compose -f .gitlab/runner/docker-compose.yml up -d --force-recreate
```

Edite o `.env` local antes de subir:

- `ENVIRONMENT=dev`, `homolog` ou `prod`
- `TARGET_BRANCH=dev`, `homolog` ou `main`
- `DEPLOY_REPO_PATH` com o checkout real daquele servidor
- `RUNNER_TOKEN`
- `RUNNER_DNS_SERVERS`
- `RUNNER_NETWORK_NAME`

## Variavel do GitLab

- `DEPLOY_GIT_TOKEN`: token HTTP usado pelo job de deploy para executar `git fetch/pull` no checkout persistente do host sem depender de chave SSH dentro do container do job

## Regras de deploy

- `aplicacoes/assistente/**`: build e rollout de `assistente`
- `aplicacoes/assistente/nginx.dockerfile` e `aplicacoes/assistente/sei_ia/configs/nginx.conf`: build e rollout de `assistente-nginx`
- `aplicacoes/similaridade/**`: build de `similaridade` e rollout de `similaridade` e `similaridade-feedback`
- `aplicacoes/etl-airflow/**`: build de `etl-airflow-webserver` e `etl-airflow-api`, rerun de `etl-airflow-init` e rollout dos servicos ETL
- `aplicacoes/etl-airflow/jobs/configs/solr_core_configs/**` e `ops/solr/**`: tambem build e rollout de `infra-solr`
- `docker-compose.yml`, `docker-compose.override.yml`, `default.env`, `security.env` e `llm_config.yaml`: `docker compose up -d --no-build`
- `assistente-nginx` publica `${ASSISTENTE_PORT:-8088}:443` no compose base, portanto a porta do assistente e padrao em todos os ambientes
- `docker-compose.override.yml` publica apenas `infra-postgres`, `infra-solr` e `infra-litellm`, e esse arquivo so e aplicado em `dev` e `homolog`
- `ops/database/ddl.sql` e `ops/database/conf/init_pgvector.sql`: falha intencional para intervencao manual
- caminhos nao mapeados falham para evitar deploy parcial incorreto

## Mapeamento por servidor

- servidor de desenvolvimento: `ENVIRONMENT=dev` e `TARGET_BRANCH=dev`
- servidor de homologacao: `ENVIRONMENT=homolog` e `TARGET_BRANCH=homolog`
- servidor de producao: `ENVIRONMENT=prod` e `TARGET_BRANCH=main`
- tags de runner usadas pela pipeline: `dev`, `homologacao` e `prod`

Todos podem receber a mesma pipeline. A selecao primaria agora e por `tag` do runner e, em seguida, cada servidor ainda faz `skip` quando a branch do commit nao bate com o `TARGET_BRANCH` do seu proprio runner.

## Atualizar

```bash
docker compose -f .gitlab/runner/docker-compose.yml up -d --force-recreate
```

## Parar

```bash
docker compose -f .gitlab/runner/docker-compose.yml down
```

## Decisoes

- o desenho segue o padrao do `gitlab-runner-avalia-ds`: runner em container e acesso ao `docker.sock`
- a diferenca e que aqui o `config.toml` e gerado a partir do `.env` local do servidor, para suportar `dev`, `homolog` e `prod`
- o deploy usa o checkout persistente do host como fonte de verdade; o job do GitLab nao faz checkout proprio
- o token do runner fica apenas no `.env` local, nao no template versionado
- esta regra de branch e operacional, nao uma barreira forte de seguranca
- o deploy agora prepara um builder BuildKit dedicado antes dos builds para evitar falhas de DNS dentro de `apt-get`, `dnf` e `wget`
- o deploy agora registra a duracao das fases principais para separar demora de build, `etl-airflow-init` e healthchecks
