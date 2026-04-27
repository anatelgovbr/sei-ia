#!/bin/sh
set -eu

CONFIG_FILE="/etc/gitlab-runner/config.toml"

VOL_SEIIA_DIR="$(grep '^VOL_SEIIA_DIR=' "$DEPLOY_REPO_PATH/default.env" | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]')"

required_vars="CI_SERVER_URL RUNNER_DESCRIPTION RUNNER_TOKEN ENVIRONMENT TARGET_BRANCH DEPLOY_REPO_PATH RUNNER_NETWORK_NAME RUNNER_DNS_SERVERS RUNNER_JOB_IMAGE"
for var_name in $required_vars; do
  eval "var_value=\${$var_name:-}"
  if [ -z "$var_value" ]; then
    echo "Missing required variable: $var_name" >&2
    exit 1
  fi
done

dns_json="$(printf '%s' "$RUNNER_DNS_SERVERS" | awk -F',' '
  BEGIN { printf "[" }
  {
    for (i = 1; i <= NF; i++) {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $i)
      if ($i != "") {
        if (printed++) {
          printf ", "
        }
        printf "\"%s\"", $i
      }
    }
  }
  END { printf "]" }
')"

cat > "$CONFIG_FILE" <<EOF
concurrent = 1
check_interval = 0
shutdown_timeout = 0

[session_server]
  session_timeout = 1800

[[runners]]
  name = "${RUNNER_DESCRIPTION}"
  url = "${CI_SERVER_URL}"
  token = "${RUNNER_TOKEN}"
  executor = "docker"
  environment = ["ENVIRONMENT=${ENVIRONMENT}", "TARGET_BRANCH=${TARGET_BRANCH}", "DEPLOY_REPO_PATH=${DEPLOY_REPO_PATH}", "DEPLOY_GIT_TOKEN=${DEPLOY_GIT_TOKEN:-}"]
  [runners.cache]
    MaxUploadedArchiveSize = 0
    [runners.cache.s3]
    [runners.cache.gcs]
    [runners.cache.azure]
  [runners.docker]
    tls_verify = false
    image = "${RUNNER_JOB_IMAGE}"
    privileged = false
    disable_entrypoint_overwrite = false
    oom_kill_disable = false
    disable_cache = false
    volumes = ["/cache", "/var/run/docker.sock:/var/run/docker.sock", "${DEPLOY_REPO_PATH}:${DEPLOY_REPO_PATH}", "${VOL_SEIIA_DIR}:${VOL_SEIIA_DIR}"]
    shm_size = 268435456
    network_mtu = 0
    dns = ${dns_json}
    network_mode = "${RUNNER_NETWORK_NAME}"
EOF

exec gitlab-runner run --user=gitlab-runner --config "$CONFIG_FILE"
