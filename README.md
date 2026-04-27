# sei-ia-monorepo

Relatorio simples do estado atual do bootstrap do monorepo `sei-ia`.

## Estrutura atual

```text
sei-ia-monorepo/
├── aplicacoes/assistente/
├── aplicacoes/similaridade/
├── aplicacoes/etl-airflow/
├── docker-compose.yml
├── docker-compose.override.yml
├── default.env
├── security_example.env
├── litellm_config.template.yaml
├── healthchecker.yml
├── ops/
├── ci/
├── docs/
└── migration_notes/
```

## O que ja existe

- o monorepo foi montado a partir de clones reais do GitLab
- `assistente` veio da `main`
- `similaridade` veio da `master`
- `etl-airflow` veio da `main`
- `deploy` veio da `master` como base para reorganizar os manifests raiz e `ops/`
- `app-api` veio da `master` como referencia para a fusao do feedback
- `jobs` foi renomeado para `etl-airflow`
- `api` foi renomeada para `similaridade`
- `app-api` deixou de existir como servico separado e teve a primeira fusao feita dentro de `similaridade`
- a pipeline raiz do GitLab ja existe com estagios de setup, quality, test, build, deploy e sync
- cada aplicacao ja tem pipeline propria
- `assistente` ja possui testes automatizados conectados na pipeline
- `similaridade` e `etl-airflow` ja possuem lint, format, build e deploy, mas ainda sem testes automatizados consolidados
- o deploy ja foi reorganizado por unidades reais: `assistente`, `similaridade`, `etl-airflow`, `etl-airflow-api` e `infra-shared`
- os manifests raiz (`docker-compose.yml`, `docker-compose.override.yml`, `default.env`, `security_example.env`, `litellm_config.template.yaml` e `healthchecker.yml`) representam o contrato atual do runtime local
- `default.env` e `litellm_config.template.yaml` ficam versionados na raiz; os valores sensiveis ficam nos secrets do GitLab e sao gerados automaticamente no deploy
- os arquivos sensiveis continuam fora do Git ou como template, com destaque para `security_example.env`
- ja existe um job de espelhamento para GitHub, mas ele ainda nao foi ativado de verdade

## O que falta

- registrar e configurar os runners do GitLab com as tags esperadas para build e deploy
- configurar as variaveis protegidas do GitLab que alimentam apenas o `security.env` no deploy
- fechar a estrategia de tags de imagem no deploy para garantir que o ambiente suba exatamente a imagem gerada no build
- revisar o contrato de variaveis do `compose` para cobrir todos os servicos e imagens usados no runtime novo
- preparar o host alvo de deploy com Docker, Compose, acesso ao registry, rede e volumes esperados
- ativar de fato o espelhamento continuo para GitHub
- ampliar a integracao do `app-api` dentro de `similaridade` alem da primeira fusao de feedback
- adicionar testes automatizados reais para `similaridade`
- adicionar testes automatizados reais para `etl-airflow`

## Observacoes

- o legado original continua intacto fora desta pasta
- este repositorio ainda e um bootstrap de migracao, nao a versao final de producao
- segredos nao devem ser commitados no monorepo

## BuildKit e DNS no Docker

Durante a validacao do `docker compose up -d`, os builds com `buildx` falhavam dentro de `RUN apt-get update`, `RUN dnf ...` e ate `RUN wget ...` com erro de resolucao DNS. O comportamento observado foi:

- `docker run --network docker-host-bridge ...` resolvia e baixava normalmente
- `docker buildx build ...` falhava dentro do `RUN`
- dentro do passo de build, o `resolv.conf` estava sendo gerado com DNS publicos do Google (`8.8.8.8`, `8.8.4.4` e equivalentes IPv6), que nao eram alcancaveis neste host

O problema foi isolado com Dockerfiles minimos e resolvido configurando o BuildKit para usar explicitamente os DNS do host:

- [buildkitd.toml](/opt/seiia_deploy/.gitlab/buildkit/buildkitd.toml)
- [ensure_buildx_builder.sh](/opt/seiia_deploy/.gitlab/scripts/ensure_buildx_builder.sh)
- [run_deploy_debug.sh](/opt/seiia_deploy/.gitlab/scripts/run_deploy_debug.sh)

Como funciona:

- o script cria ou reutiliza o builder `seiia-bridge`
- esse builder usa a rede `docker-host-bridge`
- o arquivo `buildkitd.toml` fixa os nameservers internos do ambiente
- o deploy em [deploy_changed.sh](/opt/seiia_deploy/.gitlab/scripts/deploy_changed.sh) agora prepara automaticamente esse builder antes dos builds
- o deploy tambem registra a duracao das fases de `build`, `etl-airflow-init`, `rollout` e `health checks`

Para debug local, o deploy pode ser executado em background sem bloquear o terminal:

```bash
bash .gitlab/scripts/run_deploy_debug.sh
tail -f .gitlab/tmp/deploy-debug-*.log
```

Se precisar recriar manualmente:

```bash
bash .gitlab/scripts/ensure_buildx_builder.sh
BUILDX_BUILDER=seiia-bridge docker compose --env-file default.env --env-file security.env up -d
```
