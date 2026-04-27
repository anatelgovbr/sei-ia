#!/usr/bin/env bash
# Gera security.env e litellm_config.yaml a partir das variaveis de CI/CD do GitLab.
#
# Variaveis necessarias no GitLab (Settings > CI/CD > Variables):
#
# --- security.env ---
# GID_DOCKER, DB_SEIIA_USER, DB_SEIIA_PWD,   (ENVIRONMENT e derivado automaticamente do branch)
# SOLR_USER, SOLR_PASSWORD,
# AIRFLOW_POSTGRES_DB, AIRFLOW_POSTGRES_USER, AIRFLOW_AMQP_USER,
# _AIRFLOW_WWW_USER_USERNAME, _AIRFLOW_WWW_USER_PASSWORD,
# AIRFLOW_POSTGRES_PASSWORD, AIRFLOW_AMQP_PASSWORD, AIRFLOW__WEBSERVER__SECRET_KEY,
# OPENAI_API_VERSION, ASSISTENTE_LITELLM_PROXY_API_KEY,
# ASSISTENTE_LITELLM_STANDARD_MODEL_NAME, ASSISTENTE_LITELLM_MINI_MODEL_NAME,
# ASSISTENTE_LITELLM_NANO_MODEL_NAME, ASSISTENTE_LITELLM_THINK_MODEL_NAME,
# ASSISTENTE_LITELLM_EMBEDDING_MODEL_NAME, ASSISTENTE_LITELLM_STT_MODEL_NAME,
# ASSISTENTE_OCR_MODEL,
# LITELLM_STANDARD_MODEL, LITELLM_MINI_MODEL, LITELLM_NANO_MODEL,
# SEI_API_DB_IDENTIFIER_SERVICE, SEI_ADDRESS,
# PROJECT_ENDPOINT, AZURE_TENANT_ID, AZURE_WEB_AGENT_ID,
# AZURE_CLIENT_SECRET, AZURE_CLIENT_ID, BING_CONNECTION_NAME, MODEL_DEPLOYMENT_NAME,
# LANGFUSE_URL, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY,
# LANGFUSE_SECRET_SALT, LANGFUSE_NEXTAUTH_SECRET  (opcionais)
#
# --- litellm_config.yaml (via litellm_config.template.yaml) ---
# Os modelos devem incluir o prefixo do provedor:
#   Conexao direta com Azure:  LITELLM_STANDARD_MODEL=azure/gpt-5.4
#   Via LiteLLM proxy central: LITELLM_STANDARD_MODEL=openai/seiia-ds
# LITELLM_STANDARD_MODEL, LITELLM_MINI_MODEL, LITELLM_NANO_MODEL,
# LITELLM_STANDARD_API_BASE, LITELLM_STANDARD_API_KEY, LITELLM_STANDARD_API_VERSION,
# LITELLM_THINK_MAX_TOKENS,
# LITELLM_EMBEDDING_MODEL, LITELLM_EMBEDDING_API_BASE, LITELLM_EMBEDDING_API_KEY, LITELLM_EMBEDDING_API_VERSION,
# LITELLM_STT_MODEL, LITELLM_STT_API_BASE, LITELLM_STT_API_KEY, LITELLM_STT_API_VERSION
set -euo pipefail

DEPLOY_REPO_PATH="${DEPLOY_REPO_PATH:?DEPLOY_REPO_PATH is required}"

log() { printf '[generate-config] %s\n' "$*"; }

# Deriva o valor de ENVIRONMENT a partir do branch/environment do CI.
# Evita ter que cadastrar essa variavel manualmente no GitLab.
resolve_environment() {
  # CI_ENVIRONMENT_NAME e injetado pelo GitLab quando o job declara 'environment:'
  case "${CI_ENVIRONMENT_NAME:-}" in
    development) printf 'dev'  ; return ;;
    homologacao) printf 'homol'; return ;;
    production)  printf 'prod' ; return ;;
  esac
  # Fallback: deriva do nome do branch
  case "${CI_COMMIT_BRANCH:-}" in
    dev|develop|desenvolvimento) printf 'dev'  ; return ;;
    hm|homolog|homologacao)      printf 'homol'; return ;;
    pd|prod|producao|main|master) printf 'prod' ; return ;;
  esac
  # Ultimo recurso: usa a variavel manual se existir
  printf '%s' "${ENVIRONMENT:-dev}"
}

generate_security_env() {
  local out="$DEPLOY_REPO_PATH/security.env"

  if [ -z "${GID_DOCKER:-}" ] && [ -z "${DB_SEIIA_USER:-}" ]; then
    log "Variaveis de security.env nao configuradas no GitLab; pulando geracao de $out"
    return 0
  fi

  local app_environment
  app_environment="$(resolve_environment)"
  log "ENVIRONMENT resolvido automaticamente: ${app_environment}"

  log "Gerando $out"
  {
    printf '%s=%s\n' "GID_DOCKER"                        "${GID_DOCKER:-}"
    printf '%s=%s\n' "ENVIRONMENT"                       "${app_environment}"
    printf '%s=%s\n' "DB_SEIIA_USER"                     "${DB_SEIIA_USER:-}"
    printf '%s=%s\n' "DB_SEIIA_PWD"                      "${DB_SEIIA_PWD:-}"
    printf '%s=%s\n' "SOLR_USER"                         "${SOLR_USER:-}"
    printf '%s=%s\n' "SOLR_PASSWORD"                     "${SOLR_PASSWORD:-}"
    printf '%s=%s\n' "AIRFLOW_POSTGRES_DB"               "${AIRFLOW_POSTGRES_DB:-}"
    printf '%s=%s\n' "AIRFLOW_POSTGRES_USER"             "${AIRFLOW_POSTGRES_USER:-}"
    printf '%s=%s\n' "AIRFLOW_AMQP_USER"                 "${AIRFLOW_AMQP_USER:-}"
    printf '%s=%s\n' "_AIRFLOW_WWW_USER_USERNAME"        "${_AIRFLOW_WWW_USER_USERNAME:-}"
    printf '%s=%s\n' "_AIRFLOW_WWW_USER_PASSWORD"        "${_AIRFLOW_WWW_USER_PASSWORD:-}"
    printf '%s=%s\n' "AIRFLOW_POSTGRES_PASSWORD"         "${AIRFLOW_POSTGRES_PASSWORD:-}"
    printf '%s=%s\n' "AIRFLOW_AMQP_PASSWORD"             "${AIRFLOW_AMQP_PASSWORD:-}"
    printf '%s=%s\n' "AIRFLOW__WEBSERVER__SECRET_KEY"    "${AIRFLOW__WEBSERVER__SECRET_KEY:-}"
    printf '%s=%s\n' "OPENAI_API_VERSION"                        "${OPENAI_API_VERSION:-}"
    printf '%s=%s\n' "ASSISTENTE_LITELLM_PROXY_API_KEY"          "${ASSISTENTE_LITELLM_PROXY_API_KEY:-}"
    printf '%s=%s\n' "ASSISTENTE_LITELLM_STANDARD_MODEL_NAME"    "${ASSISTENTE_LITELLM_STANDARD_MODEL_NAME:-standard}"
    printf '%s=%s\n' "ASSISTENTE_LITELLM_MINI_MODEL_NAME"        "${ASSISTENTE_LITELLM_MINI_MODEL_NAME:-mini}"
    printf '%s=%s\n' "ASSISTENTE_LITELLM_NANO_MODEL_NAME"        "${ASSISTENTE_LITELLM_NANO_MODEL_NAME:-nano}"
    printf '%s=%s\n' "ASSISTENTE_LITELLM_THINK_MODEL_NAME"       "${ASSISTENTE_LITELLM_THINK_MODEL_NAME:-think}"
    printf '%s=%s\n' "ASSISTENTE_LITELLM_EMBEDDING_MODEL_NAME"  "${ASSISTENTE_LITELLM_EMBEDDING_MODEL_NAME:-embedding}"
    printf '%s=%s\n' "ASSISTENTE_LITELLM_STT_MODEL_NAME"        "${ASSISTENTE_LITELLM_STT_MODEL_NAME:-speech-to-text}"
    printf '%s=%s\n' "ASSISTENTE_OCR_MODEL"                     "${ASSISTENTE_OCR_MODEL:-nano}"
    printf '%s=%s\n' "LITELLM_STANDARD_MODEL"                    "${LITELLM_STANDARD_MODEL:-}"
    printf '%s=%s\n' "LITELLM_MINI_MODEL"                        "${LITELLM_MINI_MODEL:-}"
    printf '%s=%s\n' "LITELLM_NANO_MODEL"                        "${LITELLM_NANO_MODEL:-}"
    printf '%s=%s\n' "SEI_API_DB_IDENTIFIER_SERVICE"             "${SEI_API_DB_IDENTIFIER_SERVICE:-}"
    printf '%s=%s\n' "SEI_ADDRESS"                       "${SEI_ADDRESS:-}"
    printf '%s=%s\n' "PROJECT_ENDPOINT"                  "${PROJECT_ENDPOINT:-}"
    printf '%s=%s\n' "AZURE_TENANT_ID"                   "${AZURE_TENANT_ID:-}"
    printf '%s=%s\n' "AZURE_WEB_AGENT_ID"                "${AZURE_WEB_AGENT_ID:-}"
    printf '%s=%s\n' "AZURE_CLIENT_SECRET"               "${AZURE_CLIENT_SECRET:-}"
    printf '%s=%s\n' "AZURE_CLIENT_ID"                   "${AZURE_CLIENT_ID:-}"
    printf '%s=%s\n' "BING_CONNECTION_NAME"              "${BING_CONNECTION_NAME:-}"
    printf '%s=%s\n' "MODEL_DEPLOYMENT_NAME"             "${MODEL_DEPLOYMENT_NAME:-}"
    printf '%s=%s\n' "LANGFUSE_URL"                      "${LANGFUSE_URL:-}"
    printf '%s=%s\n' "LANGFUSE_PUBLIC_KEY"               "${LANGFUSE_PUBLIC_KEY:-}"
    printf '%s=%s\n' "LANGFUSE_SECRET_KEY"               "${LANGFUSE_SECRET_KEY:-}"
    printf '%s=%s\n' "LANGFUSE_SECRET_SALT"              "${LANGFUSE_SECRET_SALT:-}"
    printf '%s=%s\n' "LANGFUSE_NEXTAUTH_SECRET"          "${LANGFUSE_NEXTAUTH_SECRET:-}"
  } > "$out"
  log "security.env gerado com sucesso"
}

generate_litellm_config() {
  local template="$DEPLOY_REPO_PATH/litellm_config.template.yaml"
  local out="$DEPLOY_REPO_PATH/litellm_config.yaml"

  if [ ! -f "$template" ]; then
    log "Template $template nao encontrado; pulando geracao de litellm_config.yaml"
    return 0
  fi

  if [ -z "${LITELLM_STANDARD_API_KEY:-}" ]; then
    log "LITELLM_STANDARD_API_KEY nao configurada no GitLab; pulando geracao de $out"
    return 0
  fi

  log "Gerando $out a partir de $template"
  envsubst '${LITELLM_STANDARD_MODEL}
${LITELLM_MINI_MODEL}
${LITELLM_NANO_MODEL}
${LITELLM_STANDARD_API_BASE}
${LITELLM_STANDARD_API_KEY}
${LITELLM_STANDARD_API_VERSION}
${LITELLM_THINK_MAX_TOKENS}
${LITELLM_EMBEDDING_MODEL}
${LITELLM_EMBEDDING_API_BASE}
${LITELLM_EMBEDDING_API_KEY}
${LITELLM_EMBEDDING_API_VERSION}
${LITELLM_STT_MODEL}
${LITELLM_STT_API_BASE}
${LITELLM_STT_API_KEY}
${LITELLM_STT_API_VERSION}' \
    < "$template" > "$out"
  log "litellm_config.yaml gerado com sucesso"
}

main() {
  log "Iniciando geracao de arquivos de configuracao"
  generate_security_env
  generate_litellm_config
  log "Geracao de arquivos de configuracao concluida"
}

main "$@"
