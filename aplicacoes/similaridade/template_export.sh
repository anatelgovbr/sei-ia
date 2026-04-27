#!/bin/bash
 
export SOLR_ADDRESS="http://localhost:8084"
 
# export MYSQL_CONFIG=/home/$USER/config_homol.ini
export MYSQL_CONFIG=/home/$USER/config_prod.ini
 
export SOLR_MLT_PROCESS_CORE=processos_bm25
 
export CONFIG_MLT_FIELDS_WEIGHTS_PATH=/home/$USER/projects/api/api_sei/configs/conf_mlt_fields_weights.json
 
export FAISS_ADDRESS="http://localhost:8083"
 
export FAISS_INDEX_PATH="/home/airflow/app/faiss_index/paraphrase-multilingual-mpnet-base-v2_300_truncation_weighted.index"
 
export SOLR_MLT_JURISPRUDENCE_CORE="documentos_bm25"
 
export CONN_STRING_APP_DB="postgresql+psycopg2://sei:seisimilaridade@localhost:8089/sei_similaridade"
 
export JOBS_API_ADDRESS="http://jobs_api:8642"
