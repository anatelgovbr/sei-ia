#!/bin/bash

export AIRFLOW_HOME=/home/lx.giovani.colab/airflow-jobs-2.6.3

export AIRFLOW__CORE__DAGS_FOLDER=/home/lx.giovani.colab/projects/jobs/jobs/dags/dag_objects

export AIRFLOW__CORE__LOAD_EXAMPLES=False

export SOLR_ADDRESS="http://localhost:8997"

export SOLR_MLT_PROCESS_CORE=process

# export MYSQL_CONFIG=/mnt/sei_similaridade/lucas/api_sei_similaridade/config_prod.ini
export MYSQL_CONFIG=/home/$USER/projects/api/config.ini

# export SOLR_MLT_PROCESS_CORE=processos_bm25

#export MLT_PROCESS_CONFIGSET=/home/giovani.colab@anatel.gov.br/api-sei/sei-similaridade/api_sei/configs/solr_core_configs

#export VALIDATION_PROCESSES=/home/giovani.colab@anatel.gov.br/api-sei/sei-similaridade/api_sei/configs/validation_processes.csv

#export FIELDS_PER_PROCESS_TYPE=/home/giovani.colab@anatel.gov.br/api-sei/sei-similaridade/api_sei/configs/doc_por_proc_2.json

#export CONFIG_MLT_FIELDS_WEIGHTS_PATH=/home/giovani.colab@anatel.gov.br/api-sei/sei-similaridade/api_sei/configs/conf_mlt_fields_weights.json

export FAISS_ADDRESS="http://localhost:8083"

export SOLR_MLT_JURISPRUDENCE_CORE="documentos_bm25"

export CONN_STRING_APP_DB="postgresql+psycopg2://sei:seisimilaridade@localhost:8089/sei_similaridade"

export MLT_JURISPRUDENCE_CONFIGSET=/var/solr/configsets/jurisprudence
