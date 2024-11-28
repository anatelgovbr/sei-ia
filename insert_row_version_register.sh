# Carregar variáveis de ambiente
source ./env_files/security.env
POSTGRES_DB="sei_similaridade"
CONTAINER_NAME="pgvector_all"

# Capturar dados do repositório local com valores padrão
HASH=$(git rev-parse HEAD 2>/dev/null || echo "default-hash")
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "externos")
TAG=$(git tag --points-at HEAD 2>/dev/null || echo "1.0.1")
URL=$(git config --get remote.origin.url 2>/dev/null || echo "EXTERNOS/jobs.git")
CURRENT_TIME=$(date '+%Y-%m-%d %H:%M:%S')

# Função para escapar aspas simples
escape_string() {
    echo "$1" | sed "s/'/''/g"
}

# Escapar variáveis para uso em SQL
HASH_ESCAPED=$(escape_string "$HASH")
BRANCH_ESCAPED=$(escape_string "$BRANCH")
TAG_ESCAPED=$(escape_string "$TAG")
URL_ESCAPED=$(escape_string "${URL}/jobs.git") # /jobs.git é para a dag de indexação do sei_similaridade reconhecer a linha na tabela

# Construir o comando SQL
SQL_COMMAND="INSERT INTO version_register (hash, branch, tag, url, created_at, updated_at) VALUES ('$HASH_ESCAPED', '$BRANCH_ESCAPED', '$TAG_ESCAPED', '$URL_ESCAPED', '$CURRENT_TIME', '$CURRENT_TIME');"

# Obter o ID do container do pgvector_all
CONTAINER_ID=$(docker ps --filter "name=${CONTAINER_NAME}" --format "{{.ID}}")

echo $CONTAINER_ID

if [ -z "$CONTAINER_ID" ]; then
    echo "Container com o nome '${CONTAINER_NAME}' não encontrado."
    exit 1
fi

echo "Executando comando no container ID: $CONTAINER_ID"

# Executar o comando dentro do container
docker exec -i "$CONTAINER_ID" env PGPASSWORD="${POSTGRES_PASSWORD}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "$SQL_COMMAND"

if [ $? -eq 0 ]; then
    echo "Registro inserido com sucesso na tabela version_register."
else
    echo "Erro ao inserir registro no PostgreSQL."
    exit 1
fi
