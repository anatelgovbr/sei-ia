# Source Lock do Bootstrap

## Repositorios usados como base

- `assistente`: branch `main`, commit `ce158a7bb289`
- `similaridade`: branch `master`, commit `0093bc473129`
- `etl-airflow`: branch `main`, commit `c89ca0cb1bc4`
- `deploy`: branch `master`, commit `4d30bf36365d`
- `app-api`: branch `master`, commit `486df78664f9`

## Observacao

Os diretórios do monorepo foram realinhados com esses clones limpos do GitLab.
Os overlays criados no monorepo depois disso permanecem locais ao bootstrap:

- fusao do `app-api` em `similaridade`
- pipeline raiz do monorepo
- manifests raiz de deploy
- saneamento dos env files do bootstrap
- versionamento de `default.env` na raiz do bootstrap atual
