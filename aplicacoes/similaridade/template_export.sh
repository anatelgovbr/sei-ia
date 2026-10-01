#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

: "${CONN_STRING_APP_DB:?Defina CONN_STRING_APP_DB antes de carregar este arquivo}"

export CONN_STRING_APP_DB
export SOLR_ADDRESS="${SOLR_ADDRESS:-http://localhost:8084}"
export SOLR_MLT_PROCESS_CORE="${SOLR_MLT_PROCESS_CORE:-processos_bm25}"
export SOLR_MLT_JURISPRUDENCE_CORE="${SOLR_MLT_JURISPRUDENCE_CORE:-documentos_bm25}"
export CONFIG_MLT_FIELDS_WEIGHTS_PATH="${CONFIG_MLT_FIELDS_WEIGHTS_PATH:-${SCRIPT_DIR}/api_sei/configs/conf_mlt_fields_weights.json}"
export JOBS_API_ADDRESS="${JOBS_API_ADDRESS:-http://etl-airflow-api:8642}"
