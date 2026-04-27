#!/usr/bin/env bash
set -euo pipefail

BUILDER_NAME="${BUILDX_BUILDER_NAME:-seiia-bridge}"
BUILDER_NETWORK="${BUILDX_BUILDER_NETWORK:-docker-host-bridge}"
BUILDKIT_CONFIG_PATH="${BUILDKIT_CONFIG_PATH:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/buildkit/buildkitd.toml}"

log() {
  printf '[buildx] %s\n' "$*"
}

if docker buildx inspect "$BUILDER_NAME" >/dev/null 2>&1; then
  log "Using existing builder ${BUILDER_NAME}"
else
  log "Creating builder ${BUILDER_NAME} on network ${BUILDER_NETWORK}"
  docker buildx create \
    --name "$BUILDER_NAME" \
    --driver docker-container \
    --driver-opt "network=${BUILDER_NETWORK}" \
    --config "$BUILDKIT_CONFIG_PATH" \
    --use \
    >/dev/null
fi

docker buildx use "$BUILDER_NAME" >/dev/null
docker buildx inspect --bootstrap "$BUILDER_NAME" >/dev/null

log "Builder ${BUILDER_NAME} is ready"
