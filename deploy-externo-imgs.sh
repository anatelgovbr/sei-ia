#!/bin/bash

set -e # Se algum comando falhar, o script para

string_secao_nao_essencial="NAO ESSENCIAIS NO MOMENTO DA INSTALACAO"
linha_secao_nao_essencial=`grep -n "$string_secao_nao_essencial" env_files/security.env|cut -f1 -d:`

if [ `head -$linha_secao_nao_essencial env_files/security.env|grep --count '\*\*\*\*'` -gt 0 ]; then
  echo "==========================================="
  echo "ATENÇÃO: Deploy Servidor de Soluções do SEI-IA foi interrompido!"
  echo "==========================================="
  echo "A seção de configurações ESSENCIAIS do arquivo env_files/security.env não está adequadamente preenchida!"
  echo "O deploy do Servidor de Soluções do SEI-IA depende da configuração de todas as variáveis dessa seção do arquivo!"
  echo "(para mais detalhes sobre o correto preenchimento do arquivo env_files/security.env, leia o arquivo docs/INSTALL.md)"
  exit 1
fi

if [ `tail -n +$linha_secao_nao_essencial env_files/security.env|grep --count '\*\*\*\*'` -gt 0 ]; then
  echo "==============================================="
  echo "ATENÇÃO: o deploy do Servidor de Soluções do SEI-IA pode ter problemas!"
  echo "==============================================="
  echo "A seção de configurações NÃO ESSENCIAIS do arquivo env_files/security.env não está totalmente preenchida!"
  echo "Embora nem todas as varíaveis dessa seção sejam de preenchimento obrigatório, é importante notar que" \
       "o deploy do Servidor de Soluções do SEI-IA pode dar errado dependendo do que não foi configurado nessa seção do arquivo!"
  echo "(para mais detalhes sobre o correto preenchimento do arquivo env_files/security.env, leia o arquivo docs/INSTALL.md)"
fi

echo "*** `date`: Carregando variáveis de ambiente..."
# Carregar variáveis de ambiente
source env_files/prod.env
source env_files/default.env
source env_files/security.env

# Carregar variáveis de ambiente específicas de acordo com o argumento
cat env_files/prod.env > .env
cat env_files/default.env >> .env
cat env_files/security.env >> .env

echo "*** `date`: Criando pasta de storage para o SEI-IA caso não exista..."
[ -d $STORAGE_PROJ_DIR ] && chmod 777 $STORAGE_PROJ_DIR || mkdir --mode 777 $STORAGE_PROJ_DIR

echo "*** `date`: Configurando variáveis de ambiente para instalação do Servidor de Soluções do SEI-IA..."
export PROJECT_NAME=sei_ia

export API_SEI_IMAGE="0.3-RC"
export API_ASSISTENTE_VERSION="0.3-RC"
export NGINX_ASSISTENTE_VERSION="0.3-RC"
export AIRFLOW_IMAGE_NAME="0.3-RC"
export APP_API="0.3-RC"
export SOLR_CONTAINER="0.3-RC"
export POSTGRES_IMAGE="0.3-RC"

export DOCKER_REGISTRY="anatelgovbr/"

echo "*** `date`: Deploy do Servidor de Soluções do SEI-IA em andamento..."
docker compose --profile externo \
  -f docker-compose-prod.yaml \
  -p $PROJECT_NAME \
  up \
  --no-build -d

echo "*** `date`:Ativando as DAGs do Servidor de Soluções do SEI-IA no Airflow..."
docker compose -f docker-compose-prod.yaml -p $PROJECT_NAME exec airflow-webserver-pd /bin/bash -c "airflow dags list | awk '{print \$1}' | grep -v 'DAG_ID' | xargs -I {} airflow dags unpause {}; exit 0"

#adicionar registro na tabela version_register no banco sei_similaridade
sh insert_row_version_register.sh

echo "*** `date`:Finalizado o Deploy do Servidor de Soluções do SEI-IA. "
