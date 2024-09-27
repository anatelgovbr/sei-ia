#!/bin/bash

if [ "$#" -ne 3 ]; then
    echo "Uso: $0 <nome_container> <nome_volume> <nome_arquivo_backup>"
    exit 1
fi

nome_container="$1"
nome_volume="$2"
nome_arquivo_backup="$3"

docker stop "$nome_container"
if [ $? -eq 0 ]; then
    echo "Container $nome_container parado com sucesso."
else
    echo "Falha ao parar o container $nome_container."
    exit 1
fi

docker run -v "$nome_volume:/volume" \
    --rm --log-driver none anatel/volume-backup backup > "$nome_arquivo_backup"

if [ $? -eq 0 ]; then
    echo "Backup realizado com sucesso!"
else
    echo "Falha ao realizar o backup."
    exit 1
fi

docker start "$nome_container"
if [ $? -eq 0 ]; then
    echo "Container $nome_container iniciado com sucesso."
else
    echo "Falha ao iniciar o container $nome_container."
    exit 1
fi

exit 0
