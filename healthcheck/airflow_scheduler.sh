#!/bin/bash

folder=/mnt/sei_similaridade/sei_similaridade_deploy

function test_healthcheck() {
  local service=$1
  local test=$2

  if ! docker compose -f $folder/docker-compose.yaml ps -q $service > /dev/null; then
    echo "Serviço $service não está rodando"
    return 1
  fi

  docker compose -f $folder/docker-compose.yaml exec -T $service sh -c "$test"
  local rc=$?

  if [ $rc -ne 0 ]; then    
    echo "Falha no healthcheck do serviço $service"
    return $rc
  else
    echo "Healthcheck do serviço $service OK"
  fi
}



test_healthcheck "airflow-scheduler" "sh /home/airflow/app/healthcheck/airflow_scheduler.sh"
  
