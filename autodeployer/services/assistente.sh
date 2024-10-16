#!/bin/bash

set -e # Se algum comando falhar , o script para

echo "========================================================================="
echo "$(date) Deploy do projeto ASSISTENTE iniciado..."

# Verifica se o ambiente é dev, homol ou prod
if [ "$ENVIRONMENT" != "dev" ] && [ "$ENVIRONMENT" != "homol" ] && [ "$ENVIRONMENT" != "prod" ]; then
  echo "$(date) Erro: não foi possível identificar ambiente válido."
  exit 1
fi

# Identifica branch conforme ambiente
if [ "$ENVIRONMENT" = "dev" ]; then
  export_pgvector_port="-f docker-compose-dev.yaml"
  branch_deploy="desenvolvimento"
  branch_assistente="desenvolvimento"
fi
if [ "$ENVIRONMENT" = "homol" ]; then
  export_pgvector_port="-f docker-compose-dev.yaml"
  branch_deploy='homologacao'
  branch_assistente='homologacao'
fi
if [ "$ENVIRONMENT" = "prod" ]; then
  export_pgvector_port=""
  branch_deploy='master'
  branch_assistente='main'

fi
echo $(date) Branch de ambiente definida: $branch_deploy

# Ajusta pwd e paths
cd /app/
# rm -rf tmp/api_deployer

# # Clonando o repositório deploy
# git clone -b $branch_deploy --single-branch --depth 1 \
#   https://oauth2:$GIT_TOKEN@git.anatel.gov.br/processo_eletronico/sei-ia/sei-similaridade/deploy.git \
#   tmp/api_deployer/sei_similaridade_deploy
# echo "$(date) Repositório deploy clonado a partir da branch ("$branch_deploy")"

# cat tmp/api_deployer/sei_similaridade_deploy/env_files/default.env >.env
# echo "" >>.env
# cat tmp/api_deployer/sei_similaridade_deploy/env_files/$ENVIRONMENT.env >>.env
# echo "" >>.env
# cat ./security.env >>.env

# cp .env /app/tmp/api_deployer/sei_similaridade_deploy/.env
source .env

cd /app/tmp/api_deployer/sei_similaridade_deploy

# Clonar o repositório do Assistente  em DS
git clone -b $branch_assistente --single-branch --depth 1 \
  https://oauth2:$GIT_TOKEN@git.anatel.gov.br/processo_eletronico/sei-ia/assistente.git tmp/assistente
echo "$(date) Repositório assistente clonado a partir da branch ("$branch_assistente")"

cp tmp/assistente/assistente.dockerfile .
cp tmp/assistente/nginx.dockerfile .

PROJECT_NAME=sei_ia
# Build e deploy do Assistente
docker compose \
  -f docker-compose-prod.yaml \
  $export_pgvector_port \
  -p $PROJECT_NAME \
  up --build \
  api_assistente nginx_assistente \
  -d --force-recreate

echo "`date` Esperando estabilizacao da stack..."
sleep 20

echo "`date` Executando testes da api_assistente..."
curl -X 'GET' 'http://api_assistente:8088/tests' -H 'accept: application/json'|jq

if [ $? = 0 ]
then
    echo "`date` O endepoint de testes rodou integralmente com sucesso!"
else
  echo "$(date) Houve algum erro ao executar os testes do endpoint de testes!"
fi

rm assistente.dockerfile nginx.dockerfile

echo "$(date) Deploy do assistente finalizado!"
