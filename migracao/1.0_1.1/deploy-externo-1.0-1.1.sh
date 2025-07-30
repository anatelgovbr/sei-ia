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



##### remover volumes antigos
VOLUMES_TO_REMOVE=(
  "${PROJECT_NAME}_airflow-logs-volume"
  "${PROJECT_NAME}_airflow-jobs"
  "${PROJECT_NAME}_airflow-postgres-db-volume"
)

for volume in "${VOLUMES_TO_REMOVE[@]}"; do
  echo "Verificando containers usando o volume: $volume"
  CONTAINERS=$(docker ps -a --filter "volume=$volume" -q)
  if [ -n "$CONTAINERS" ]; then
    echo "Parando e removendo containers associados ao volume $volume"
    docker stop $CONTAINERS
    docker rm -f $CONTAINERS
  fi

  echo "Removendo volume: $volume"
  docker volume rm -f "$volume" || echo "Volume $volume não encontrado ou já removido"
done

echo "*** `date`: Deploy do SEI IA em andamento..."
docker compose --profile externo \
  -f docker-compose-prod.yaml \
  -f migracao/1.0_1.1/docker-compose-vol-override-1.0-1.1.yml \
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
docker compose -f docker-compose-prod.yaml -f docker-compose-ext.yaml  -p $PROJECT_NAME exec \
  airflow-webserver-pd /bin/bash -c "airflow dags unpause --yes --treat-dag-id-as-regex '.*'"

echo "*** `date`:Rodando o healthchecker..."
docker compose --profile externo \
  -f docker-compose-healthchecker.yml \
  -p $PROJECT_NAME \
  up \
  --build

echo "*** `date`:Finalizado o Deploy do Servidor de Soluções do SEI-IA. "
