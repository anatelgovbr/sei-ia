#!/bin/bash

# Definindo variáveis locais para o script
BACKUP_DIR="/backup"
BACKUP_FILE="$BACKUP_DIR/${POSTGRES_DB}_backup.sql"

# Criar o diretório de backup, se não existir
echo "Criando diretório de backup em $BACKUP_DIR" >> /var/log/backup.log 2>&1
mkdir -p "$BACKUP_DIR"

# Definindo o comando pg_dump com as variáveis populadas
PG_DUMP_CMD="PGPASSWORD=$POSTGRES_PASSWORD pg_dump -U $POSTGRES_USER -F c -b -v -f \"$BACKUP_FILE\" $POSTGRES_DB"

# Executando o backup e capturando erros
echo "Iniciando o backup do banco de dados $POSTGRES_DB" >> /var/log/backup.log 2>&1
if eval $PG_DUMP_CMD >> /var/log/backup.log 2>&1; then
  echo "Backup do banco de dados $POSTGRES_DB realizado com sucesso em $BACKUP_FILE" >> /var/log/backup.log 2>&1
else
  echo "Falha ao realizar o backup do banco de dados $POSTGRES_DB" >> /var/log/backup.log 2>&1
  echo "Comando executado: $PG_DUMP_CMD" >> /var/log/backup.log 2>&1
fi
