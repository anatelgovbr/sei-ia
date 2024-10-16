#!/bin/bash

VOLUME_PATH="/var/solr"

BACKUP_DIR="/backup"

BACKUP_FILE="$BACKUP_DIR/solr_backup.tar.gz"

# Cria o diretório de backup, se não existir
mkdir -p $BACKUP_DIR

# Remove qualquer backup anterior no diretório
rm -f $BACKUP_FILE

start_time=$(date +%s)

# Gera o arquivo de backup excluindo o próprio arquivo de backup do processo
tar --exclude=$BACKUP_FILE -czf $BACKUP_FILE -C $VOLUME_PATH . --warning=no-file-changed

if [ $? -eq 0 ]; then
    end_time=$(date +%s)
    elapsed_time=$((end_time - start_time))
    echo "Backup realizado com sucesso! Tempo de execução: $elapsed_time segundos"
else
    echo "Falha ao realizar o backup."
fi
