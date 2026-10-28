#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

: "${CONN_STRING_APP_DB:?Defina CONN_STRING_APP_DB antes de carregar este arquivo}"
: "${_AIRFLOW_WWW_USER_PASSWORD:?Defina _AIRFLOW_WWW_USER_PASSWORD antes de carregar este arquivo}"

export AIRFLOW_HOME="${AIRFLOW_HOME:-${REPO_ROOT}/.runtime/airflow}"
export AIRFLOW__CORE__DAGS_FOLDER="${AIRFLOW__CORE__DAGS_FOLDER:-${SCRIPT_DIR}/jobs/dags/dag_objects}"
export AIRFLOW__CORE__LOAD_EXAMPLES="${AIRFLOW__CORE__LOAD_EXAMPLES:-False}"
export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="${AIRFLOW__DATABASE__SQL_ALCHEMY_CONN:-${CONN_STRING_APP_DB}}"
export CONN_STRING_APP_DB
export _AIRFLOW_WWW_USER_PASSWORD
export SOLR_ADDRESS="${SOLR_ADDRESS:-http://localhost:8997}"
export SOLR_MLT_PROCESS_CORE="${SOLR_MLT_PROCESS_CORE:-process}"
export SOLR_MLT_JURISPRUDENCE_CORE="${SOLR_MLT_JURISPRUDENCE_CORE:-documentos_bm25}"
export MLT_PROCESS_CONFIGSET="${MLT_PROCESS_CONFIGSET:-${SCRIPT_DIR}/jobs/configs/solr_core_configs/configsets/process}"
export MLT_JURISPRUDENCE_CONFIGSET="${MLT_JURISPRUDENCE_CONFIGSET:-${SCRIPT_DIR}/jobs/configs/solr_core_configs/configsets/jurisprudence}"
