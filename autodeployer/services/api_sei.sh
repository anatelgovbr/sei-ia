#!/bin/bash
set -e # Se algum comando falhar , o script para


# Verifica se o ambeinte é dev, homol ou prod
if [ "$ENVIRONMENT" != "dev" ] && [ "$ENVIRONMENT" != "homol" ] && [ "$ENVIRONMENT" != "prod" ]; then
    echo "Erro: não foi possível identificar ambiente válido."
    exit 1
fi


# Identifica branch conforme ambiente
if [ "$ENVIRONMENT" = "dev" ]; then
    branch='desenvolvimento'
    
fi
if [ "$ENVIRONMENT" = "homol" ]; then
    branch='homologacao'

fi
if [ "$ENVIRONMENT" = "prod" ]; then
    branch='master'

fi
echo Branch de ambiente definida: $branch

# Ajusta pwd e paths
cd /app/

rm -rf tmp/api_deployer

# Clonar o repositório do deploy em DS
git clone -b $branch --single-branch --depth 1 https://oauth2:$GIT_TOKEN@$GIT_BASE_URL/deploy.git tmp/api_deployer/sei_similaridade_deploy
echo "Repo deploy cloned ("$branch")"

cat tmp/api_deployer/sei_similaridade_deploy/env_files/default.env > .env
echo "" >> .env
cat tmp/api_deployer/sei_similaridade_deploy/env_files/$ENVIRONMENT.env >> .env
echo "" >> .env
cat ./security.env >> .env

cp .env /app/tmp/api_deployer/sei_similaridade_deploy/.env
source .env


# Ajusta pwd
cd /app/tmp/api_deployer/sei_similaridade_deploy/


# Clonar o repositório da API em DS
git clone -b $branch --single-branch --depth 1 https://oauth2:$GIT_TOKEN@$GIT_BASE_URL/api.git tmp/api

echo "Repo api cloned ("$branch")"

# Copia dockerfile do api_sei
cp ./tmp/api/api_sei.dockerfile /app/tmp/api_deployer/sei_similaridade_deploy/api_sei.dockerfile


# Inicia os serviços Docker Compose
export OTEL_SERVICE_NAME=$ENVIRONMENT-api-sei
# export OTEL_RESOURCE_ATTRIBUTES="service.name=$OTEL_SERVICE_NAME"
docker compose -f docker-compose-prod.yaml build --build-arg CACHEBUST=$(date +%s) api_sei
docker compose -f docker-compose-prod.yaml -p $PROJECT_NAME up api_sei -d --force-recreate



#rm -rf tmp/api

echo "success"
exit 0
