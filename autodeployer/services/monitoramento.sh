#!/bin/bash
set -e # Se algum comando falhar , o script para


echo "`date` Deploy do projeto monitoramento iniciado..."

# Verifica se o ambeinte é dev, homol ou prod
if [ "$ENVIRONMENT" != "dev" ] && [ "$ENVIRONMENT" != "homol" ] && [ "$ENVIRONMENT" != "prod" ]; then
    echo "`date` Erro: não foi possível identificar ambiente válido."
    exit 1
fi


# Identifica branch conforme ambiente
if [ "$ENVIRONMENT" = "dev" ]; then
    branch_deploy='desenvolvimento'
    branch_monitoramento='desenvolvimento'
fi
if [ "$ENVIRONMENT" = "homol" ]; then
    branch_deploy='homologacao'
    branch_monitoramento='homologacao'
fi
if [ "$ENVIRONMENT" = "prod" ]; then
    branch_deploy='master'
    branch_monitoramento='main'

fi
echo `date` Branch de ambiente definida: $branch_deploy

# Ajusta pwd e paths
cd /app/

# rm -rf tmp/api_deployer

# # Clonando o repositório deploy
# git clone -b $branch_deploy --single-branch --depth 1 https://oauth2:$GIT_TOKEN@$GIT_BASE_URL/deploy.git tmp/api_deployer/sei_similaridade_deploy
# echo "`date` Repositório deploy clonado a partir da branch ("$branch_deploy")"

# cat tmp/api_deployer/sei_similaridade_deploy/env_files/default.env > .env
# echo "" >> .env
# cat tmp/api_deployer/sei_similaridade_deploy/env_files/$ENVIRONMENT.env >> .env
# echo "" >> .env
# cat ./security.env >> .env

# cp .env /app/tmp/api_deployer/sei_similaridade_deploy/.env
source .env


# Ajusta pwd
cd /app/tmp/api_deployer/sei_similaridade_deploy


# Clonar o repositório da API em DS
git clone -b $branch_monitoramento --single-branch --depth 1 https://oauth2:$GIT_TOKEN@git.anatel.gov.br/processo_eletronico/sei-ia/monitoramento.git tmp/monitoramento

echo "`date` Repositório monitoramento clonado a partir da branch ("$branch_monitoramento")"

# Copia arquivos para deploy do monitoramento
cp --recursive --verbose ./tmp/monitoramento/* .

# Gambiarra: a senha atual de acesso ao DB SEI tem um caractere que precisa ser decodificado
export DB_SEI_PWD=`echo ${DB_SEI_PWD}|sed 's/%40/@/g'|sed 's/%23/#/g'`

# Build e deploy
docker compose \
    -f docker-compose-prod.yaml \
    -p sei_ia \
    up --build \
    exporter_agent_monitor cadvisor_agent_monitor \
    -d --force-recreate

echo "`date` Deploy do monitoramento realizado com sucesso!"

exit 0
