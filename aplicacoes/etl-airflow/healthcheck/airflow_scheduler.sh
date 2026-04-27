#!/bin/bash
curl --fail "http://${AIRFLOW_HEALTH_WEBSERVER_HOST:-etl-airflow-webserver}:8080/health"
  
