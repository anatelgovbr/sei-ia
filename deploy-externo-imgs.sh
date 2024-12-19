#!/bin/bash

set -e # Se algum comando falhar, o script para

string_secao_nao_essencial="NAO ESSENCIAIS NO MOMENTO DA INSTALACAO"
linha_secao_nao_essencial=`grep -n "$string_secao_nao_essencial" env_files/security.env|cut -f1 -d:`

if [ `head -$linha_secao_nao_essencial env_files/security.env|grep --count '\*\*\*\*'` -gt 0 ]; then
  echo "==========================================="
  echo "ATENÇÃO: Deploy do SEI IA foi interrompido!"
  echo "==========================================="
  echo "A seção de configurações ESSENCIAIS do arquivo env_files/security.env não está adequadamente preenchida!"
  echo "O deploy do SEI IA depende da configuração de todas as variáveis dessa seção do arquivo!"
  echo "(para mais detalhes sobre o correto preenchimento do arquivo env_files/security.env, leia o arquivo README.md)"
  exit 1
fi

if [ `tail -n +$linha_secao_nao_essencial env_files/security.env|grep --count '\*\*\*\*'` -gt 0 ]; then
  echo "==============================================="
  echo "ATENÇÃO: o deploy do SEI IA pode ter problemas!"
  echo "==============================================="
  echo "A seção de configurações NÃO ESSENCIAIS do arquivo env_files/security.env não está totalmente preenchida!"
  echo "Embora nem todas as varíaveis dessa seção sejam de preenchimento obrigatório, é importante notar que" \
       "o deploy do SEI IA pode dar errado dependendo do que não foi configurado nessa seção do arquivo!"
  echo "(para mais detalhes sobre o correto preenchimento do arquivo env_files/security.env, leia o arquivo README.md)"
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

echo "*** `date`: Configurando variáveis de ambiente para instalação do SEI IA..."
export PROJECT_NAME=sei_ia

export API_SEI_IMAGE="1.0.2-RC"
export API_ASSISTENTE_VERSION="1.0.2-RC"
export NGINX_ASSISTENTE_VERSION="1.0.2-RC"
export AIRFLOW_IMAGE_NAME="1.0.2-RC"
export APP_API="1.0.2-RC"
export SOLR_CONTAINER="1.0.2-RC"
export POSTGRES_IMAGE="1.0.2-RC"

export DOCKER_REGISTRY="anatelgovbr/"

echo "*** `date`: Deploy do SEI IA em andamento..."
docker compose --profile externo \
  -f docker-compose-ext.yaml \
  -p $PROJECT_NAME \
  up \
  --no-build -d

echo "*** `date`:Ativando as DAGs do SEI IA no Airflow..."
docker compose -f docker-compose-ext.yaml -p $PROJECT_NAME exec airflow-webserver-pd /bin/bash -c "
airflow dags list | awk 'NR > 2 {print \$1}' > /tmp/dags_list.txt;
cat /tmp/dags_list.txt || echo 'Nenhuma DAG encontrada.';
while read -r dag; do
    echo 'Tentando despausar DAG:' \$dag;

    # Verifica se a DAG já está pausada
    is_paused=\$(airflow dags list | grep \"^\$dag\" | awk '{print \$2}')
    
    if [ \"\$dag\" == \"dag_embeddings_start\" ]; then
        echo 'Pausando dag_embeddings_start...';
        airflow dags pause dag_embeddings_start || echo 'Falha ao pausar dag_embeddings_start';
    else
        echo \"Despausando DAG: \$dag...\"
        airflow dags unpause \"\$dag\" || echo 'Falha ao despausar \$dag';
    fi
done < /tmp/dags_list.txt
"


#adicionar registro na tabela version_register no banco sei_similaridade
sh insert_row_version_register.sh

echo "*** `date`:Rodando o healthchecker..."
docker compose -f docker-compose-healthchecker.yml \
  -p $PROJECT_NAME up --build

echo "*** `date`:Finalizado o Deploy do Servidor de Soluções do SEI-IA. "
