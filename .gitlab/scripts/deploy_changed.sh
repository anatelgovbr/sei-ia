#!/usr/bin/env bash
set -euo pipefail

DEPLOY_BRANCH="${DEPLOY_BRANCH:-${TARGET_BRANCH:-dev}}"
DEPLOY_REPO_PATH="${DEPLOY_REPO_PATH:?DEPLOY_REPO_PATH is required}"
COMPOSE_FILES="${COMPOSE_FILES:-}"
COMPOSE_ENV_FILES="${COMPOSE_ENV_FILES:-default.env security.env}"
DEPLOY_DRY_RUN="${DEPLOY_DRY_RUN:-0}"
CHANGED_FILES_OVERRIDE="${CHANGED_FILES_OVERRIDE:-}"
BUILDX_BUILDER_NAME="${BUILDX_BUILDER_NAME:-seiia-bridge}"

export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
export COMPOSE_DOCKER_CLI_BUILD="${COMPOSE_DOCKER_CLI_BUILD:-1}"
export BUILDX_BUILDER="${BUILDX_BUILDER:-$BUILDX_BUILDER_NAME}"

declare -a CHANGED_FILES=()
declare -a BUILD_SERVICES=()
declare -a ROLLOUT_SERVICES=()
declare -a ETL_ROLLOUT_SERVICES=()
declare -a MANUAL_FILES=()
declare -a UNSUPPORTED_FILES=()
declare -a IGNORED_FILES=()
declare -a COMPOSE_ARGS=()

STACK_REFRESH_REQUIRED="${FORCE_STACK_REFRESH:-0}"
ETL_INIT_REQUIRED=0
OLD_SHA=""
NEW_SHA=""
IMAGE_RELEASE_TAG=""
PHASE_START_TS=0
OVERALL_START_TS=0

log() {
  printf '[deploy] %s\n' "$*"
}

fail() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

timestamp_now() {
  date +%s
}

format_duration() {
  local total_seconds="$1"
  local minutes=$((total_seconds / 60))
  local seconds=$((total_seconds % 60))
  printf '%02dm%02ds' "$minutes" "$seconds"
}

sanitize_fragment() {
  local value="$1"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  value="$(printf '%s' "$value" | sed 's/[^a-z0-9_.-]/-/g')"
  value="$(printf '%s' "$value" | sed 's/--*/-/g; s/^-//; s/-$//')"
  printf '%s' "${value:-unknown}"
}

compute_image_release_tag() {
  local env_name commit_ref short_sha
  env_name="$(sanitize_fragment "${ENVIRONMENT:-unknown}")"
  commit_ref="${CI_COMMIT_SHA:-${NEW_SHA:-}}"

  if printf '%s' "$commit_ref" | grep -Eq '^[0-9a-fA-F]{7,40}$'; then
    short_sha="$(printf '%.12s' "$commit_ref" | tr '[:upper:]' '[:lower:]')"
  else
    short_sha="$(sanitize_fragment "${commit_ref:-manual}")"
  fi

  IMAGE_RELEASE_TAG="${env_name}-${short_sha}"
}

start_phase() {
  local phase_name="$1"
  PHASE_START_TS="$(timestamp_now)"
  log "Starting ${phase_name}"
}

finish_phase() {
  local phase_name="$1"
  local now_ts elapsed
  now_ts="$(timestamp_now)"
  elapsed=$((now_ts - PHASE_START_TS))
  log "Finished ${phase_name} in $(format_duration "$elapsed")"
}

guard_target_branch() {
  if [ -n "${TARGET_BRANCH:-}" ] && [ -n "${CI_COMMIT_BRANCH:-}" ] && [ "$CI_COMMIT_BRANCH" != "$TARGET_BRANCH" ]; then
    log "Skipping branch ${CI_COMMIT_BRANCH}; runner is configured for ${TARGET_BRANCH} (${ENVIRONMENT:-unknown})"
    exit 0
  fi
}

contains() {
  local needle="$1"
  shift || true
  local item
  for item in "$@"; do
    if [ "$item" = "$needle" ]; then
      return 0
    fi
  done
  return 1
}

append_unique() {
  local array_name="$1"
  local value="$2"
  declare -n array_ref="$array_name"
  if ! contains "$value" "${array_ref[@]:-}"; then
    array_ref+=("$value")
  fi
}

check_volumes() {
  local vol_seiia_dir=""
  local default_env="$DEPLOY_REPO_PATH/default.env"

  if [ -f "$default_env" ]; then
    vol_seiia_dir="$(grep '^VOL_SEIIA_DIR=' "$default_env" | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]')"
  fi
  vol_seiia_dir="${vol_seiia_dir:-/var/seiia/volumes}"

  if [ ! -d "$vol_seiia_dir" ]; then
    log "ERRO: Diretório base de volumes $vol_seiia_dir não existe."
    log "Execute os seguintes comandos para criá-lo:"
    printf '  sudo mkdir --parents --mode=750 %s\n' "$vol_seiia_dir" >&2
    printf '  sudo chown seiia:docker %s\n' "$vol_seiia_dir" >&2
    exit 1
  fi

  local -a volume_specs=(
    "airflow_logs_vol:50000:0:750"
    "airflow_postgres_vol:999:999:700"
    "pgvector_all_vol:999:999:700"
    "solr_pd_vol:8983:8983:750"
  )

  local problems=0
  local -a fix_commands=()

  for spec in "${volume_specs[@]}"; do
    IFS=':' read -r vol_name uid gid mode <<< "$spec"
    local vol_path="$vol_seiia_dir/$vol_name"

    if [ ! -d "$vol_path" ]; then
      fix_commands+=("sudo mkdir --mode=$mode $vol_path && sudo chown $uid:$gid $vol_path")
      problems=1
    else
      local current_owner
      current_owner="$(stat -c '%u:%g' "$vol_path")"
      if [ "$current_owner" != "$uid:$gid" ]; then
        fix_commands+=("sudo chown $uid:$gid $vol_path  # atual: $current_owner, esperado: $uid:$gid")
        problems=1
      fi
    fi
  done

  if [ "$problems" -eq 1 ]; then
    log "ERRO: Problemas detectados nos diretórios de volumes."
    log "Execute os seguintes comandos para corrigir:"
    for cmd in "${fix_commands[@]}"; do
      printf '  %s\n' "$cmd" >&2
    done
    exit 1
  fi

  log "Diretórios de volumes verificados"
}

setup_repo() {
  [ -d "$DEPLOY_REPO_PATH/.git" ] || fail "Repository not found at ${DEPLOY_REPO_PATH}"
  git config --global --add safe.directory "$DEPLOY_REPO_PATH"

  if [ -n "$(git -C "$DEPLOY_REPO_PATH" status --porcelain --untracked-files=no)" ]; then
    fail "Local tracked changes detected in ${DEPLOY_REPO_PATH}. Refusing to deploy over a dirty checkout."
  fi

  local current_branch
  current_branch="$(git -C "$DEPLOY_REPO_PATH" branch --show-current)"
  if [ "$current_branch" != "$DEPLOY_BRANCH" ]; then
    log "Switching checkout from ${current_branch} to ${DEPLOY_BRANCH}"
    git -C "$DEPLOY_REPO_PATH" switch "$DEPLOY_BRANCH"
  fi
}

build_pull_source() {
  if [ -n "${DEPLOY_GIT_TOKEN:-}" ] && [ -n "${CI_SERVER_URL:-}" ] && [ -n "${CI_PROJECT_PATH:-}" ]; then
    printf '%s/%s.git' "${CI_SERVER_URL%/}" "${CI_PROJECT_PATH}" | \
      sed "s#^https://#https://oauth2:${DEPLOY_GIT_TOKEN}@#"
    return 0
  fi

  printf 'origin'
}

can_use_ci_commit_range() {
  [ -n "${CI_COMMIT_SHA:-}" ] || return 1
  [ -n "${CI_COMMIT_BEFORE_SHA:-}" ] || return 1
  [ "${CI_COMMIT_BEFORE_SHA}" != "0000000000000000000000000000000000000000" ] || return 1

  git -C "$DEPLOY_REPO_PATH" rev-parse --verify "${CI_COMMIT_SHA}^{commit}" >/dev/null 2>&1 || return 1
  git -C "$DEPLOY_REPO_PATH" rev-parse --verify "${CI_COMMIT_BEFORE_SHA}^{commit}" >/dev/null 2>&1 || return 1
}

refresh_checkout() {
  local pull_source diff_range before_sha current_pipeline_sha
  pull_source="$(build_pull_source)"

  OLD_SHA="$(git -C "$DEPLOY_REPO_PATH" rev-parse HEAD)"
  log "Updating ${DEPLOY_BRANCH} in ${DEPLOY_REPO_PATH}"
  git -C "$DEPLOY_REPO_PATH" pull --ff-only "$pull_source" "$DEPLOY_BRANCH"
  NEW_SHA="$(git -C "$DEPLOY_REPO_PATH" rev-parse HEAD)"
  before_sha="${CI_COMMIT_BEFORE_SHA:-}"
  current_pipeline_sha="${CI_COMMIT_SHA:-}"

  if [ "$OLD_SHA" = "$NEW_SHA" ]; then
    if [ -n "$before_sha" ] && [ -n "$current_pipeline_sha" ] && [ "$current_pipeline_sha" = "$NEW_SHA" ] && \
       ! printf '%s' "$before_sha" | grep -Eq '^0+$' && \
       git -C "$DEPLOY_REPO_PATH" cat-file -e "${before_sha}^{commit}" 2>/dev/null; then
      diff_range="${before_sha}..${current_pipeline_sha}"
      log "Checkout already at ${NEW_SHA}; using pipeline diff ${diff_range}"
    else
      if [ "${FORCE_STACK_REFRESH:-0}" = "1" ]; then
        log "No remote changes detected but FORCE_STACK_REFRESH=1; proceeding with stack refresh"
        return 0
      fi
      log "No remote changes detected for ${DEPLOY_BRANCH} (${ENVIRONMENT:-unknown})"
      exit 0
    fi
  else
    diff_range="${OLD_SHA}..${NEW_SHA}"
  fi

  while IFS= read -r changed_file; do
    [ -n "$changed_file" ] && CHANGED_FILES+=("$changed_file")
  done < <(git -C "$DEPLOY_REPO_PATH" diff --name-only "$diff_range")
}

load_changed_files() {
  if [ -n "$CHANGED_FILES_OVERRIDE" ]; then
    OLD_SHA="${OLD_SHA_OVERRIDE:-override-old}"
    NEW_SHA="${NEW_SHA_OVERRIDE:-override-new}"
    while IFS= read -r changed_file; do
      [ -n "$changed_file" ] && CHANGED_FILES+=("$changed_file")
    done < <(printf '%s\n' "$CHANGED_FILES_OVERRIDE")
    return 0
  fi

  setup_repo
  refresh_checkout
}

classify_changes() {
  local changed_file
  for changed_file in "${CHANGED_FILES[@]}"; do
    case "$changed_file" in
      litellm_config.template.yaml)
        STACK_REFRESH_REQUIRED=1
        ;;
      aplicacoes/etl-airflow/jobs/configs/solr_core_configs/*)
        append_unique BUILD_SERVICES "etl-airflow-webserver"
        append_unique BUILD_SERVICES "etl-airflow-api"
        append_unique BUILD_SERVICES "infra-solr"
        append_unique ETL_ROLLOUT_SERVICES "etl-airflow-webserver"
        append_unique ETL_ROLLOUT_SERVICES "etl-airflow-scheduler"
        append_unique ETL_ROLLOUT_SERVICES "etl-airflow-worker"
        append_unique ETL_ROLLOUT_SERVICES "etl-airflow-triggerer"
        append_unique ETL_ROLLOUT_SERVICES "etl-airflow-api"
        append_unique ROLLOUT_SERVICES "infra-solr"
        ETL_INIT_REQUIRED=1
        ;;
      aplicacoes/assistente/nginx.dockerfile|aplicacoes/assistente/sei_ia/configs/nginx.conf)
        append_unique BUILD_SERVICES "assistente-nginx"
        append_unique ROLLOUT_SERVICES "assistente-nginx"
        ;;
      aplicacoes/assistente/*)
        append_unique BUILD_SERVICES "assistente"
        append_unique ROLLOUT_SERVICES "assistente"
        append_unique ROLLOUT_SERVICES "assistente-nginx"
        ;;
      aplicacoes/similaridade/*)
        append_unique BUILD_SERVICES "similaridade"
        append_unique ROLLOUT_SERVICES "similaridade"
        append_unique ROLLOUT_SERVICES "similaridade-feedback"
        ;;
      aplicacoes/etl-airflow/*)
        append_unique BUILD_SERVICES "etl-airflow-webserver"
        append_unique BUILD_SERVICES "etl-airflow-api"
        append_unique ETL_ROLLOUT_SERVICES "etl-airflow-webserver"
        append_unique ETL_ROLLOUT_SERVICES "etl-airflow-scheduler"
        append_unique ETL_ROLLOUT_SERVICES "etl-airflow-worker"
        append_unique ETL_ROLLOUT_SERVICES "etl-airflow-triggerer"
        append_unique ETL_ROLLOUT_SERVICES "etl-airflow-api"
        ETL_INIT_REQUIRED=1
        ;;
      ops/solr/*)
        append_unique BUILD_SERVICES "infra-solr"
        append_unique ROLLOUT_SERVICES "infra-solr"
        ;;
      docker-compose.yml|docker-compose.override.yml|default.env|security.env|llm_config.yaml|litellm_config.yaml)
        STACK_REFRESH_REQUIRED=1
        ;;
      ops/database/ddl.sql|ops/database/conf/init_pgvector.sql)
        append_unique MANUAL_FILES "$changed_file"
        ;;
      .gitignore|.gitlab-ci.yml|.gitlab/*|README.md|CLAUDE.md|docs/*|tests/*|security_example.env|ops/database/conf/postgresql.conf|ops/database/pgvector_all.dockerfile)
        append_unique IGNORED_FILES "$changed_file"
        ;;
      *)
        append_unique UNSUPPORTED_FILES "$changed_file"
        ;;
    esac
  done

  local etl_service
  for etl_service in "${ETL_ROLLOUT_SERVICES[@]}"; do
    append_unique ROLLOUT_SERVICES "$etl_service"
  done
}

print_summary() {
  log "Environment: ${ENVIRONMENT:-unknown}"
  log "Previous SHA: ${OLD_SHA}"
  log "Current SHA: ${NEW_SHA}"
  if [ "${#CHANGED_FILES[@]}" -gt 0 ]; then
    printf '[deploy] Changed files:\n'
    printf '  - %s\n' "${CHANGED_FILES[@]}"
  fi

  if [ "${#IGNORED_FILES[@]}" -gt 0 ]; then
    printf '[deploy] Ignored files:\n'
    printf '  - %s\n' "${IGNORED_FILES[@]}"
  fi
  if [ "${#BUILD_SERVICES[@]}" -gt 0 ]; then
    printf '[deploy] Build services:\n'
    printf '  - %s\n' "${BUILD_SERVICES[@]}"
  fi
  if [ "${#ROLLOUT_SERVICES[@]}" -gt 0 ]; then
    printf '[deploy] Rollout services:\n'
    printf '  - %s\n' "${ROLLOUT_SERVICES[@]}"
  fi
  if [ "$STACK_REFRESH_REQUIRED" -eq 1 ]; then
    log "Stack refresh required due to compose/env root changes"
  fi
}

build_compose_args() {
  COMPOSE_ARGS=(--project-directory "$DEPLOY_REPO_PATH")

  local compose_files_value="${COMPOSE_FILES:-}"
  if [ -z "$compose_files_value" ]; then
    compose_files_value="docker-compose.yml"
    case "${ENVIRONMENT:-}" in
      dev|homolog)
        compose_files_value="${compose_files_value} docker-compose.override.yml"
        ;;
    esac
  fi

  local compose_file
  for compose_file in $compose_files_value; do
    COMPOSE_ARGS+=(-f "$DEPLOY_REPO_PATH/$compose_file")
  done

  local env_file
  for env_file in $COMPOSE_ENV_FILES; do
    if [ -f "$DEPLOY_REPO_PATH/$env_file" ]; then
      COMPOSE_ARGS+=(--env-file "$DEPLOY_REPO_PATH/$env_file")
    fi
  done
}

docker_compose() {
  docker compose "${COMPOSE_ARGS[@]}" "$@"
}

image_repo_for_service() {
  case "$1" in
    assistente) printf 'sei-ia/assistente' ;;
    assistente-nginx) printf 'sei-ia/assistente-nginx' ;;
    similaridade) printf 'sei-ia/similaridade' ;;
    etl-airflow-webserver) printf 'sei-ia/etl-airflow' ;;
    etl-airflow-api) printf 'sei-ia/etl-airflow-api' ;;
    infra-solr) printf 'sei-ia/infra-solr' ;;
    *) return 1 ;;
  esac
}

tag_release_images() {
  [ "${#BUILD_SERVICES[@]}" -gt 0 ] || return 0

  compute_image_release_tag
  log "Tagging built images with release tag ${IMAGE_RELEASE_TAG}"

  local service image_repo source_image target_image
  local -a tagged_repos=()
  for service in "${BUILD_SERVICES[@]}"; do
    image_repo="$(image_repo_for_service "$service")" || continue
    if contains "$image_repo" "${tagged_repos[@]:-}"; then
      continue
    fi

    source_image="${image_repo}:local"
    target_image="${image_repo}:${IMAGE_RELEASE_TAG}"
    docker image inspect "$source_image" >/dev/null 2>&1 || fail "Source image not found for tagging: ${source_image}"
    docker tag "$source_image" "$target_image"
    append_unique tagged_repos "$image_repo"
    log "Tagged ${source_image} as ${target_image}"
  done
}

ensure_buildx_builder() {
  if [ "${DOCKER_BUILDKIT}" != "1" ]; then
    return 0
  fi

  log "Ensuring BuildKit builder ${BUILDX_BUILDER} with host DNS"
  bash "$DEPLOY_REPO_PATH/.gitlab/scripts/ensure_buildx_builder.sh"
}

wait_for_container() {
  local service="$1"
  local mode="$2"
  local timeout_seconds="${3:-300}"
  local start_ts now_ts container_id status health exit_code elapsed
  local -a ps_args=()

  start_ts="$(date +%s)"
  while true; do
    now_ts="$(date +%s)"
    ps_args=()
    if [ "$mode" = "oneshot" ]; then
      ps_args+=(-a)
    fi
    container_id="$(docker_compose ps "${ps_args[@]}" -q "$service" | head -n1)"
    if [ -n "$container_id" ]; then
      status="$(docker inspect --format '{{.State.Status}}' "$container_id")"
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"
      exit_code="$(docker inspect --format '{{.State.ExitCode}}' "$container_id")"

      case "$mode" in
        oneshot)
          if [ "$status" = "exited" ] && [ "$exit_code" = "0" ]; then
            elapsed=$((now_ts - start_ts))
            log "${service} completed successfully after $(format_duration "$elapsed")"
            return 0
          fi
          if [ "$status" = "exited" ] && [ "$exit_code" != "0" ]; then
            fail "${service} exited with code ${exit_code}"
          fi
          ;;
        service)
          if [ "$health" = "healthy" ]; then
            elapsed=$((now_ts - start_ts))
            log "${service} is healthy after $(format_duration "$elapsed")"
            return 0
          fi
          if [ "$health" = "unhealthy" ]; then
            fail "${service} became unhealthy"
          fi
          if [ "$health" = "none" ] && [ "$status" = "running" ]; then
            elapsed=$((now_ts - start_ts))
            log "${service} is running after $(format_duration "$elapsed")"
            return 0
          fi
          if [ "$status" = "exited" ]; then
            fail "${service} exited unexpectedly with code ${exit_code}"
          fi
          ;;
        *)
          fail "Unknown wait mode: ${mode}"
          ;;
      esac
    fi

    if [ $((now_ts - start_ts)) -ge "$timeout_seconds" ]; then
      fail "Timed out waiting for ${service} (${mode})"
    fi
    sleep 5
  done
}

run_builds() {
  if [ "${#BUILD_SERVICES[@]}" -eq 0 ]; then
    return 0
  fi

  start_phase "docker compose build"
  log "Building changed services"
  docker_compose build "${BUILD_SERVICES[@]}"
  tag_release_images
  finish_phase "docker compose build"
}

run_etl_init() {
  if [ "$ETL_INIT_REQUIRED" -ne 1 ]; then
    return 0
  fi

  start_phase "etl-airflow-init"
  log "Running etl-airflow-init"
  docker_compose up -d --no-deps etl-airflow-init
  wait_for_container "etl-airflow-init" "oneshot" 600
  finish_phase "etl-airflow-init"
}

run_rollout() {
  if [ "$STACK_REFRESH_REQUIRED" -eq 1 ]; then
    start_phase "compose stack refresh"
    log "Refreshing compose stack without rebuilding unchanged images"
    if ! docker_compose up -d --no-build; then
      log "Stack refresh without build failed; retrying with build to restore missing local images"
      docker_compose up -d --build
    fi
    finish_phase "compose stack refresh"
    return 0
  fi

  if [ "${#ROLLOUT_SERVICES[@]}" -eq 0 ]; then
    log "No services require rollout"
    return 0
  fi

  start_phase "service rollout"
  log "Rolling out changed services"
  docker_compose up -d --no-build --no-deps "${ROLLOUT_SERVICES[@]}"
  finish_phase "service rollout"
}

wait_for_rollout() {
  if [ "$STACK_REFRESH_REQUIRED" -eq 1 ]; then
    log "Waiting for updated services to become healthy"
  fi

  start_phase "health checks"
  local service
  for service in "${ROLLOUT_SERVICES[@]}"; do
    wait_for_container "$service" "service" 600
  done
  finish_phase "health checks"
}

generate_config_files() {
  local generate_script="$DEPLOY_REPO_PATH/.gitlab/scripts/generate_config_files.sh"
  if [ -f "$generate_script" ]; then
    bash "$generate_script"
  else
    log "Script de geracao de configuracoes nao encontrado; pulando"
  fi
}

main() {
  OVERALL_START_TS="$(timestamp_now)"
  guard_target_branch
  check_volumes
  load_changed_files
  generate_config_files

  if [ "${#CHANGED_FILES[@]}" -eq 0 ] && [ "$STACK_REFRESH_REQUIRED" -ne 1 ]; then
    log "No changed files to process"
    exit 0
  fi

  classify_changes
  print_summary

  if [ "${#MANUAL_FILES[@]}" -gt 0 ]; then
    printf '[deploy] Manual intervention required for database initialization files:\n' >&2
    printf '  - %s\n' "${MANUAL_FILES[@]}" >&2
    exit 1
  fi

  if [ "${#UNSUPPORTED_FILES[@]}" -gt 0 ]; then
    printf '[deploy] Unsupported changed files. Update .gitlab/scripts/deploy_changed.sh mapping first:\n' >&2
    printf '  - %s\n' "${UNSUPPORTED_FILES[@]}" >&2
    exit 1
  fi

  if [ "${#BUILD_SERVICES[@]}" -eq 0 ] && [ "${#ROLLOUT_SERVICES[@]}" -eq 0 ] && [ "$STACK_REFRESH_REQUIRED" -eq 0 ]; then
    log "Only ignored files changed. No deploy required."
    exit 0
  fi

  if [ "$DEPLOY_DRY_RUN" = "1" ]; then
    log "Dry-run enabled. Skipping compose validation, build and rollout."
    exit 0
  fi

  build_compose_args
  docker_compose config -q
  ensure_buildx_builder

  run_builds
  run_etl_init
  run_rollout
  wait_for_rollout
  log "Deploy completed successfully in $(format_duration "$(( $(timestamp_now) - OVERALL_START_TS ))")"
}

main "$@"
