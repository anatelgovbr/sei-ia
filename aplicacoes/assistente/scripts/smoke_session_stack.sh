#!/usr/bin/env bash
set -euo pipefail

# Smoke do endpoint servido pela stack Docker. A stack deve estar de pé; este
# launcher não executa `make up` nem derruba containers existentes.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_dir="$(cd -- "${script_dir}/.." && pwd)"
repo_root="$(cd -- "${app_dir}/../.." && pwd)"
port="${ASSISTENTE_PORT:-8088}"
base_url="${ASSISTENTE_CONTAINER_URL:-https://localhost:${port}}"
health_url="${base_url%/}/health"

if [[ "${base_url}" == https://* ]]; then
    cert_file="${ASSISTENTE_CONTAINER_CERT:-${repo_root}/.runtime/certs/seiia.cert.pem}"
    if [[ ! -r "${cert_file}" ]]; then
        echo "Certificado da stack ausente: ${cert_file}" >&2
        echo "Suba a stack a partir da raiz deste worktree para gerar .runtime/certs." >&2
        exit 2
    fi
    curl_args=(--cacert "${cert_file}")
    export SSL_CERT_FILE="${cert_file}"
else
    curl_args=()
fi

if ! curl --fail --silent --show-error "${curl_args[@]}" "${health_url}" >/dev/null; then
    echo "Assistente da stack não está saudável em ${health_url}." >&2
    echo "Execute 'make up' na raiz deste worktree e tente novamente." >&2
    exit 1
fi

cd "${app_dir}"
exec uv run python scripts/smoke_session_host.py \
    --url "${base_url%/}/llm_lang/session_stream" \
    --no-serve \
    --no-blob-check \
    "$@"
