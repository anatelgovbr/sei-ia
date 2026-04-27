# Status da Implementacao do Monorepo

## Entregue nesta etapa

- estrutura inicial do monorepo criada
- `assistente`, `similaridade` e `etl-airflow` realocados para `aplicacoes/`
- rotas de feedback do `app-api` incorporadas em `similaridade`
- pipeline raiz do GitLab criada com divisao por aplicacao
- manifests raiz de deploy criados como contrato inicial (`docker-compose.yml`, `docker-compose.override.yml`, `default.env`, `security_example.env`, `litellm_config_example.yaml`, `healthchecker.yml`)
- topologia do `etl-airflow` explicitada no compose novo
- renderizacao de env files no runner adicionada ao fluxo de deploy
- `default.env` passou a ficar na raiz do repositorio
- configuracoes compartilhadas do Airflow seguem consolidadas no `default.env`
- script de deploy refatorado para unidades reais (`assistente`, `similaridade`, `etl-airflow`, `etl-airflow-api`, `infra-shared`)

## Deliberadamente pendente

- remocao total dos manifests legados herdados do `deploy`
- endurecimento de testes em `similaridade` e `etl-airflow`
- normalizacao completa do deploy do `etl-airflow`
- espelhamento real para GitHub
