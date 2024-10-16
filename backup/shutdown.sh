#!/bin/bash

# Parar todos os containers com nomes que começam com "sei_"
# exceto para a instância do node_exporter (Taiga 690) - 27/05/2024
# retirar o jobs da rotina que para o ambiente para execução do backup (Taiga 787) - 25/07/2024
docker ps --filter "name=sei_" --format "{{.ID}} {{.Names}}" \
    | egrep -v "sei_ia-(exporter|cadvisor)_agent_monitor-" \
    | egrep -v "sei_ia-api_assistente-" \
    | egrep -v "sei_similaridade_deploy-(airflow|rabbitmq|jobs_api)-" \
    | awk '{print $1}' \
    | xargs -r docker stop
