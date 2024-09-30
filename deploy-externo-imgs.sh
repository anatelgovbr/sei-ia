#!/bin/bash

set -e # Se algum comando falhar, o script para

# if [ `grep --count "\*\*\*\*" env_files/security.env` -gt 0 ]; then
#   echo "================================="
#   echo "ATENÇÃO: Deploy foi interrompido!"
#   echo "================================="
#   echo "O arquivo env_files/security.env não está adequadamente configurado!"
#   echo "O deploy do SEI IA depende da configuração desse arquivo!"
#   echo "(para mais detalhes, leia o arquivo README.md)"
#   exit 1
# fi

echo "*** `date`: Carregando variáveis de ambiente..."
# Carregar variáveis de ambiente
source env_files/prod.env
source env_files/default.env
source env_files/security.env

# Carregar variáveis de ambiente específicas de acordo com o argumento
cat env_files/prod.env > .env
cat env_files/default.env >> .env
cat env_files/security.env >> .env

echo "*** `date`: Criando pasta de storage para o SEI IA caso não exista..."
[ -d $STORAGE_PROJ_DIR ] && chmod 777 $STORAGE_PROJ_DIR || mkdir --mode 777 $STORAGE_PROJ_DIR

echo "*** `date`: Configurando variáveis de ambiente para instalação do SEI IA..."
export PROJECT_NAME=sei_ia

export API_SEI_IMAGE="0.2-RC"
export API_ASSISTENTE_VERSION="0.2-RC"
export NGINX_ASSISTENTE_VERSION="0.2-RC"
export AIRFLOW_IMAGE_NAME="0.2-RC"
export APP_API="0.2-RC"
export SOLR_CONTAINER="0.2-RC"
export POSTGRES_IMAGE="0.2-RC"

export DOCKER_REGISTRY="anatelgovbr/"

echo "*** `date`: Deploy do SEI IA em andamento..."
docker compose --profile externo \
  -f docker-compose-prod.yaml \
  -f docker-compose-dev.yaml \
  -p $PROJECT_NAME \
  up \
  --no-build -d

echo "*** `date`:Ativando as DAGs do SEI IA no Airflow..."
docker compose -f docker-compose-prod.yaml -p $PROJECT_NAME exec airflow-webserver-pd /bin/bash -c "airflow dags list | awk '{print \$1}' | grep -v 'DAG_ID' | xargs -I {} airflow dags unpause {}; exit 0"