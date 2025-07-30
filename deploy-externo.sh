#!/bin/bash

set -e # Se algum comando falhar, o script para


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
export ASSISTENTE_USE_LANGFUSE="false"
export ENABLE_OTEL_METRICS="false"
export DOCKER_REGISTRY="anatelgovbr/"

# suprimir mensagens de warning durante docker-compose up
echo 'export GIT_TOKEN=""
export LANGFUSE_SECRET_SALT=""
export LANGFUSE_NEXTAUTH_SECRET=""
export LANGFUSE_URL=""
export LANGFUSE_PUBLIC_KEY=""
export LANGFUSE_SECRET_KEY=""
' >> .env



if [ ! -d $VOL_SEIIA_DIR ]
then
    echo "`date`    ERRO: Pasta de volumes do SEI IA não está criada"
    echo "É obrigatório que a pasta $VOL_SEIIA_DIR exista e esteja devidamente configurada!"
    echo "Você pode usar os seguintes comandos:"
    echo "sudo mkdir --parents --mode=750 $VOL_SEIIA_DIR && sudo chown seiia:docker $VOL_SEIIA_DIR"
    echo ""
    echo "============================================="
    echo "ATENÇÃO: o deploy do SEI IA foi interrompido!"
    echo "============================================="
    exit 2
fi

echo "`date`    INFO: Analisando necessidade de criação de pastas para os volumes nomeados do SEI IA."
SEIIA_VOLS="backup_seiia_vol pgvector_all_vol solr_pd_vol"
SEIIA_VOLS="$SEIIA_VOLS airflow_postgres_vol airflow_logs_vol airflow_jobs_vol"
for vol in $(echo $SEIIA_VOLS)
do
    [ ! -d $VOL_SEIIA_DIR/$vol ] && mkdir --mode=777 $VOL_SEIIA_DIR/$vol
done

echo "*** `date`: Deploy do SEI IA em andamento..."
docker compose --profile externo \
  -f docker-compose-prod.yaml \
  -f docker-compose-ext.yaml \
  -p $PROJECT_NAME \
  up \
  --no-build -d


CONTAINER_NAME=$PROJECT_NAME-"airflow-webserver-pd-1"
echo "*** `date`: Verificando o estado do container $CONTAINER_NAME..."
# Loop para esperar até que o container esteja saudável
sleep 15
MAX_ATTEMPTS=60  # Número máximo de tentativas
SLEEP_INTERVAL=2 # Intervalo entre tentativas (em segundos)
attempt=1

while [ $attempt -le $MAX_ATTEMPTS ]; do
  HEALTH=$(docker inspect --format='{{json .State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null | tr -d '"')
  
  if [ "$HEALTH" == "healthy" ]; then
    echo "*** `date`: Container $CONTAINER_NAME está saudável. Prosseguindo..."
    break
  elif [ -z "$HEALTH" ]; then
    echo "*** `date`: Container $CONTAINER_NAME não encontrado ou sem healthcheck configurado."
    exit 1
  else
    sleep $SLEEP_INTERVAL
    ((attempt++))
  fi
done

# Verifica se o limite de tentativas foi atingido
if [ $attempt -gt $MAX_ATTEMPTS ]; then
  echo "*** `date`: Tempo limite atingido. O container $CONTAINER_NAME não ficou saudável."
  exit 1
fi

echo "*** `date`: Ativando as DAGs do SEI IA no Airflow..."
docker compose -f docker-compose-prod.yaml  -p $PROJECT_NAME exec \
  airflow-webserver-pd /bin/bash -c "airflow dags unpause --yes --treat-dag-id-as-regex '.*'"




echo "*** `date`:Rodando o healthchecker..."
docker compose --profile externo \
  -f docker-compose-healthchecker.yml \
  -p $PROJECT_NAME \
  up \
  --build

rm .env
echo "*** `date`:Finalizado o Deploy do Servidor de Soluções do SEI-IA. "
