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
git clone -b $branch --single-branch --depth 1 https://oauth2:$GIT_TOKEN@$GIT_BASE_URL/app-api.git tmp/app-api

echo "Repo api cloned ("$branch")"

# Copia dockerfile do api_sei
cp ./tmp/app-api/app-api-feedback.dockerfile /app/tmp/api_deployer/sei_similaridade_deploy/app-api-feedback.dockerfile




# Inicia os serviços Docker Compose
docker compose -f docker-compose-prod.yaml build --build-arg CACHEBUST=$(date +%s) app-api-feedback
docker compose -f docker-compose-prod.yaml -p $PROJECT_NAME up app-api-feedback -d --force-recreate


#rm -rf tmp/app-api

echo "success"
exit 0
