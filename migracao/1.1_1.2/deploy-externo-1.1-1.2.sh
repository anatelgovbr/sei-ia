#!/bin/bash
#
# Script de migração do SEI IA da versão 1.1.x para 1.2.x
#
# Este script realiza:
# 1. Para os containers existentes
# 2. Remove volumes obsoletos (airflow_jobs_vol não é mais usado)
# 3. Cria novos volumes necessários
# 4. Sobe os novos containers
# 5. Ativa as DAGs do Airflow
# 6. Executa o healthchecker
#
# Uso:
#   ./deploy-externo-1.1-1.2.sh
#

set -e # Se algum comando falhar, o script para

echo "=============================================================="
echo "  MIGRAÇÃO SEI IA: Versão 1.1.x -> 1.2.x"
echo "=============================================================="
echo ""
echo "*** $(date): Iniciando migração..."

# Verificar se estamos no diretório correto
if [ ! -f "docker-compose-prod.yaml" ]; then
    echo "Erro: Execute este script a partir do diretório de deploy do SEI IA."
    exit 1
fi

echo "*** $(date): Carregando variáveis de ambiente..."
# Carregar variáveis de ambiente
source env_files/default.env
source env_files/prod.env
source env_files/security.env

# Gerar AIRFLOW__WEBSERVER__SECRET_KEY automaticamente se não definida
if [ -z "$AIRFLOW__WEBSERVER__SECRET_KEY" ]; then
    echo "*** $(date): AIRFLOW__WEBSERVER__SECRET_KEY não encontrada. Gerando nova chave automaticamente..."
    NEW_AIRFLOW_SECRET_KEY=$(openssl rand -base64 32)
    export AIRFLOW__WEBSERVER__SECRET_KEY="$NEW_AIRFLOW_SECRET_KEY"
    echo "export AIRFLOW__WEBSERVER__SECRET_KEY=\"$NEW_AIRFLOW_SECRET_KEY\"" >> env_files/security.env
    echo "*** $(date): Chave salva em env_files/security.env para reutilização futura."
fi

# Carregar variáveis de ambiente específicas de acordo com o argumento
cat env_files/default.env > .env
cat env_files/prod.env >> .env
cat env_files/security.env >> .env

# Suprimir mensagens de warning durante docker-compose up
echo 'export GIT_TOKEN=""
export LANGFUSE_SECRET_SALT=""
export LANGFUSE_NEXTAUTH_SECRET=""
export LANGFUSE_URL=""
export LANGFUSE_HOST=""
export LANGFUSE_PUBLIC_KEY=""
export LANGFUSE_SECRET_KEY=""
export REDIS_PASSWORD=""
' >> .env

echo "*** $(date): Configurando variáveis de ambiente para instalação do SEI IA..."
export PROJECT_NAME="${PROJECT_NAME:-sei_ia}"
export ASSISTENTE_USE_LANGFUSE="${ASSISTENTE_USE_LANGFUSE:-false}"
export ENABLE_OTEL_METRICS="${ENABLE_OTEL_METRICS:-false}"
export DOCKER_REGISTRY="${DOCKER_REGISTRY:-anatelgovbr/}"

echo ""
echo "*** $(date): Parando containers existentes..."
docker compose --profile externo \
  -f docker-compose-prod.yaml \
  -f docker-compose-ext.yaml \
  -p $PROJECT_NAME \
  down --remove-orphans || true

echo ""
echo "*** $(date): Verificando e removendo volumes obsoletos..."

# Lista de volumes que não são mais necessários ou precisam ser recriados
VOLUMES_TO_CHECK=(
  "${PROJECT_NAME}_airflow-jobs-volume"
  "${PROJECT_NAME}_airflow_jobs_vol"
)

for volume in "${VOLUMES_TO_CHECK[@]}"; do
  if docker volume ls -q | grep -q "^${volume}$"; then
    echo "  - Verificando containers usando o volume: $volume"
    CONTAINERS=$(docker ps -a --filter "volume=$volume" -q)
    if [ -n "$CONTAINERS" ]; then
      echo "    Parando e removendo containers associados..."
      docker stop $CONTAINERS 2>/dev/null || true
      docker rm -f $CONTAINERS 2>/dev/null || true
    fi
    echo "  - Removendo volume obsoleto: $volume"
    docker volume rm -f "$volume" 2>/dev/null || echo "    Volume $volume não encontrado ou já removido"
  fi
done

echo ""
echo "*** $(date): Criando diretórios de volumes se necessário..."

# Verificar se VOL_SEIIA_DIR está definido
if [ -z "$VOL_SEIIA_DIR" ]; then
  VOL_SEIIA_DIR="/var/seiia/volumes"
  echo "  - Usando padrão: VOL_SEIIA_DIR  $VOL_SEIIA_DIR"
fi

# Criar diretórios necessários para os volumes
VOLUME_DIRS=(
  "airflow_logs_vol"
  "airflow_postgres_vol"
  "solr_pd_vol"
  "pgvector_all_vol"
  "backup_seiia_vol"
)

for dir in "${VOLUME_DIRS[@]}"; do
  if [ ! -d "$VOL_SEIIA_DIR/$dir" ]; then
    echo "  - Criando diretório: $VOL_SEIIA_DIR/$dir"
    mkdir -p "$VOL_SEIIA_DIR/$dir"
    chmod 777 "$VOL_SEIIA_DIR/$dir"
  fi
done

echo ""
echo "*** $(date): Iniciando deploy do SEI IA 1.2..."
docker compose --profile externo \
  -f docker-compose-prod.yaml \
  -f docker-compose-ext.yaml \
  -p $PROJECT_NAME \
  up \
  --no-build -d

# Aguardar containers iniciarem
CONTAINER_NAME="${PROJECT_NAME}-airflow-webserver-pd-1"
echo ""
echo "*** $(date): Aguardando container $CONTAINER_NAME ficar saudável..."

sleep 15
MAX_ATTEMPTS=60
SLEEP_INTERVAL=5
attempt=1

while [ $attempt -le $MAX_ATTEMPTS ]; do
  HEALTH=$(docker inspect --format='{{json .State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null | tr -d '"')

  if [ "$HEALTH" == "healthy" ]; then
    echo "*** $(date): Container $CONTAINER_NAME está saudável!"
    break
  elif [ -z "$HEALTH" ]; then
    echo "*** $(date): Container $CONTAINER_NAME não encontrado ou sem healthcheck configurado."
    echo "    Tentando novamente em ${SLEEP_INTERVAL}s... (tentativa $attempt/$MAX_ATTEMPTS)"
  else
    echo "    Status: $HEALTH - Aguardando... (tentativa $attempt/$MAX_ATTEMPTS)"
  fi

  sleep $SLEEP_INTERVAL
  ((attempt++))
done

if [ $attempt -gt $MAX_ATTEMPTS ]; then
  echo ""
  echo "*** $(date): AVISO: Tempo limite atingido aguardando container ficar saudável."
  echo "    Verifique os logs com: docker logs $CONTAINER_NAME"
  echo ""
  read -p "Deseja continuar mesmo assim? (s/N): " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Ss]$ ]]; then
    echo "Migração cancelada."
    exit 1
  fi
fi

echo ""
echo "*** $(date): Ativando as DAGs do SEI IA no Airflow..."
docker compose -f docker-compose-prod.yaml -f docker-compose-ext.yaml -p $PROJECT_NAME exec \
  airflow-webserver-pd /bin/bash -c "airflow dags unpause --yes --treat-dag-id-as-regex '.*'" || {
    echo "Aviso: Não foi possível ativar as DAGs automaticamente."
    echo "       Ative manualmente via interface do Airflow."
  }

echo ""
echo "*** $(date): Executando healthchecker..."
docker compose --profile externo \
  -f docker-compose-healthchecker.yml \
  -p $PROJECT_NAME \
  up \
  --build

echo ""
echo "=============================================================="
echo "  MIGRAÇÃO CONCLUÍDA"
echo "=============================================================="
