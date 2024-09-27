#!/bin/bash
set -e # Se algum comando falhar , o script para


# Verifica se o ambiente é dev, homol ou prod
if [ "$ENVIRONMENT" != "dev" ] && [ "$ENVIRONMENT" != "homol" ] && [ "$ENVIRONMENT" != "prod" ]; then
    echo "Erro: não foi possível identificar ambiente válido."
    exit 1
fi


# Identifica branch conforme ambiente
if [ "$ENVIRONMENT" = "dev" ]; then
    branch_deploy='desenvolvimento'
    branch_jobs='desenvolvimento'
    
fi
if [ "$ENVIRONMENT" = "homol" ]; then
    branch_deploy='homologacao'
    branch_jobs='homologacao'

fi
if [ "$ENVIRONMENT" = "prod" ]; then
    branch_deploy='master'
    branch_jobs='main'

fi
echo Branch de ambiente definida: $branch


# Ajusta pwd e paths
cd /app/

rm -rf tmp/api_deployer

# Clonar o repositório do DEPLOY
git clone -b $branch_deploy --single-branch --depth 1 https://oauth2:$GIT_TOKEN@$GIT_BASE_URL/deploy.git tmp/api_deployer/sei_similaridade_deploy
echo "Repo deploy cloned ("$branch_deploy")"

cat tmp/api_deployer/sei_similaridade_deploy/env_files/default.env > .env
echo "" >> .env
cat tmp/api_deployer/sei_similaridade_deploy/env_files/$ENVIRONMENT.env >> .env
echo "" >> .env
cat ./security.env >> .env

cp .env /app/tmp/api_deployer/sei_similaridade_deploy/.env
source .env



# Ajusta pwd
cd /app/tmp/api_deployer/sei_similaridade_deploy/


git clone -b $branch_jobs --single-branch --depth 1 https://oauth2:$GIT_TOKEN@$GIT_BASE_URL/jobs.git tmp/jobs

echo "Repo api cloned ("$branch_jobs")"

# Copia dockerfile do jobs
cp ./tmp/jobs/airflow.dockerfile /app/tmp/api_deployer/sei_similaridade_deploy/airflow.dockerfile
cp ./tmp/jobs/jobs_api.dockerfile /app/tmp/api_deployer/sei_similaridade_deploy/jobs_api.dockerfile




# Inicia os serviços Docker Compose
docker compose -f docker-compose-prod.yaml build --build-arg CACHEBUST=$(date +%s) airflow-webserver-pd
docker compose -f docker-compose-prod.yaml build --build-arg CACHEBUST=$(date +%s) jobs_api

#docker compose --profile all up -d --force-recreate
docker compose -f docker-compose-prod.yaml -p $PROJECT_NAME --profile airflow up -d --force-recreate
docker compose -f docker-compose-prod.yaml -p $PROJECT_NAME --profile airflow up jobs_api -d --force-recreate

echo "success"
docker compose -f docker-compose-prod.yaml -p $PROJECT_NAME exec airflow-webserver-pd /bin/bash -c "airflow dags list | awk '{print \$1}' | grep -v 'DAG_ID' | xargs -I {} airflow dags unpause {}; exit 0"
exit 0
# Despausa todos as Dags do Airflow



#rm -rf tmp/jobs


