#!/usr/bin/env bash
# Preserva os insumos mínimos de uma instalação 1.2.x antes de atualizar o checkout.
set -euo pipefail

SOURCE_DIR="$(pwd -P)"
BACKUP_DIR=""
CERTS_DIR=""

usage() {
  cat <<'EOF'
Uso:
  prepare-upgrade-1.3.sh \
    [--source-dir /caminho/servidor-1.2] \
    --backup-dir /caminho/backup-1.2 \
    [--certs-dir /caminho/certificado]

Cria um snapshot privado mínimo para executar a migração depois da atualização do
mesmo checkout para a versão 1.3. Não copia bancos nem volumes persistentes.
EOF
}

die() {
  printf 'ERRO: %s\n' "$*" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-dir|--backup-dir|--certs-dir)
      [ "$#" -ge 2 ] || die "falta valor para $1"
      case "$1" in
        --source-dir) SOURCE_DIR="$2" ;;
        --backup-dir) BACKUP_DIR="$2" ;;
        --certs-dir) CERTS_DIR="$2" ;;
      esac
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "argumento desconhecido: $1"
      ;;
  esac
done

[ -n "$BACKUP_DIR" ] || die "--backup-dir é obrigatório"
[ -d "$SOURCE_DIR" ] || die "origem 1.2 inexistente: $SOURCE_DIR"
SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd -P)"

required_files=(
  docker-compose-prod.yaml
  docker-compose-ext.yaml
  airflow.env
  .env
  env_files/prod.env
  env_files/default.env
  env_files/security.env
  llm_config/litellm_config.yaml
)
for relative_path in "${required_files[@]}"; do
  [ -f "$SOURCE_DIR/$relative_path" ] || \
    die "arquivo obrigatório ausente: $SOURCE_DIR/$relative_path"
done

mapfile -t source_metadata < <(
  python3 - "$SOURCE_DIR/env_files/default.env" <<'PY'
import ast
import re
import sys
from pathlib import Path

assignment = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
values = {}
for raw_line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    match = assignment.match(raw_line.strip())
    if not match:
        continue
    name, raw_value = match.groups()
    value = raw_value.split(" #", maxsplit=1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = ast.literal_eval(value)
    values[name] = value
print(values.get("TAG_ESCAPED", ""))
print(values.get("VOL_SEIIA_DIR", ""))
PY
)
[ "${#source_metadata[@]}" -eq 2 ] || die "não foi possível ler a origem 1.2"
SOURCE_VERSION="${source_metadata[0]}"
VOLUME_ROOT="${source_metadata[1]}"
[[ "$SOURCE_VERSION" =~ ^v?1\.2([.]|$) ]] || \
  die "origem não identificada como Servidor SEI IA 1.2.x"
[ -n "$VOLUME_ROOT" ] || die "VOL_SEIIA_DIR ausente na origem 1.2"

[ -n "$CERTS_DIR" ] || CERTS_DIR="$VOLUME_ROOT/certificado"
[ -d "$CERTS_DIR" ] || die "diretório TLS inexistente: $CERTS_DIR"
CERTS_DIR="$(cd "$CERTS_DIR" && pwd -P)"
for filename in seiia.cert.pem seiia.cert.key; do
  [ -f "$CERTS_DIR/$filename" ] || die "material TLS ausente: $CERTS_DIR/$filename"
done

BACKUP_PARENT="$(dirname "$BACKUP_DIR")"
BACKUP_NAME="$(basename "$BACKUP_DIR")"
mkdir -p "$BACKUP_PARENT"
BACKUP_PARENT="$(cd "$BACKUP_PARENT" && pwd -P)"
BACKUP_DIR="$BACKUP_PARENT/$BACKUP_NAME"
[ ! -e "$BACKUP_DIR" ] || die "backup já existe: $BACKUP_DIR"

umask 077
TEMP_DIR="$(mktemp -d "$BACKUP_PARENT/.${BACKUP_NAME}.tmp.XXXXXX")"
cleanup() {
  rm -rf -- "$TEMP_DIR"
}
trap cleanup EXIT

for relative_path in \
  docker-compose-prod.yaml docker-compose-ext.yaml airflow.env \
  env_files/prod.env env_files/default.env; do
  install -D -m 0644 "$SOURCE_DIR/$relative_path" "$TEMP_DIR/$relative_path"
done
install -m 0600 "$SOURCE_DIR/.env" "$TEMP_DIR/.env"
install -D -m 0600 \
  "$SOURCE_DIR/env_files/security.env" "$TEMP_DIR/env_files/security.env"
install -D -m 0600 \
  "$SOURCE_DIR/llm_config/litellm_config.yaml" \
  "$TEMP_DIR/llm_config/litellm_config.yaml"
install -D -m 0644 "$CERTS_DIR/seiia.cert.pem" "$TEMP_DIR/certificado/seiia.cert.pem"
install -D -m 0600 "$CERTS_DIR/seiia.cert.key" "$TEMP_DIR/certificado/seiia.cert.key"

SOURCE_COMMIT="$(git -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null || true)"
[ -n "$SOURCE_COMMIT" ] || SOURCE_COMMIT="indisponivel"
cat > "$TEMP_DIR/migration-source.env" <<EOF
SOURCE_VERSION=$SOURCE_VERSION
SOURCE_COMMIT=$SOURCE_COMMIT
VOL_SEIIA_DIR=$VOLUME_ROOT
EOF
chmod 0600 "$TEMP_DIR/migration-source.env"

SEARXNG_SECRET_KEY="$(openssl rand -hex 32)"
cat > "$TEMP_DIR/migration-overrides.env" <<EOF
# Preencha os valores sem equivalente inequívoco na versão 1.2.
LITELLM_NANO_MODEL=
LITELLM_NANO_API_BASE=
LITELLM_NANO_API_KEY=
LITELLM_NANO_API_VERSION=
LITELLM_STT_MODEL=
LITELLM_STT_API_BASE=
LITELLM_STT_API_KEY=
LITELLM_STT_API_VERSION=
SEIIA_GATEWAY_HOST=
SEIIA_CERT_DNS=
SEARXNG_SECRET_KEY=$SEARXNG_SECRET_KEY
EOF
chmod 0600 "$TEMP_DIR/migration-overrides.env"

mv "$TEMP_DIR" "$BACKUP_DIR"
trap - EXIT
printf 'BACKUP_DIR=%s\n' "$BACKUP_DIR"
printf 'SOURCE_VERSION=%s\n' "$SOURCE_VERSION"
printf 'STATUS=prepared\n'
