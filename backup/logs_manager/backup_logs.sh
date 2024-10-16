#!/bin/bash

if [ $# -eq 0 ]; then
    echo "Uso: $0 <diretorio_destino>"
    exit 1
fi

dest_dir="$1"

script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

log_dir="$script_dir/logs"

tar -czf "$dest_dir/logs_$(date +'%Y-%m-%d_%H-%M-%S').tar.gz" -C "$log_dir" .

rm -rf "$log_dir"/*

echo "Logs comprimidos e enviados para: $dest_dir"