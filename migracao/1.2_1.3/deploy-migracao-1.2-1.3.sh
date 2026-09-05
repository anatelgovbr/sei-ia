#!/usr/bin/env bash
# Migra uma instalação preservada do Servidor SEI IA 1.2.x para um checkout 1.3.x.
# O script nunca usa `down -v`, não modifica a árvore 1.2 e falha se qualquer gate falhar.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_MIGRATION="$SCRIPT_DIR/migracao_1.2_1.3.py"

SOURCE_DIR=""
DEPLOY_DIR=""
OVERRIDES=""
OLD_CERTS_DIR=""
BACKUP_DIR=""
MODE=""
COMPLETION_MARKER=""

usage() {
  cat <<'EOF'
Uso:
  deploy-migracao-1.2-1.3.sh \
    --source-dir /caminho/servidor-1.2 \
    --deploy-dir /caminho/servidor-1.3 \
    --overrides /caminho/migracao-overrides.env \
    --old-certs-dir /caminho/volumes-1.2/certificado \
    --check|--apply

  deploy-migracao-1.2-1.3.sh \
    --from-backup /caminho/backup-1.2 \
    --check|--apply

--check valida origem, contrato, LiteLLM, conflitos e TLS sem escrever ou parar serviços.
--apply para a stack 1.2 sem remover volumes, grava a configuração validada e executa
make up e make check no deploy 1.3.
EOF
}

die() {
  printf 'ERRO: %s\n' "$*" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-dir|--deploy-dir|--overrides|--old-certs-dir|--from-backup)
      [ "$#" -ge 2 ] || die "falta valor para $1"
      option="$1"
      value="$2"
      case "$option" in
        --source-dir) SOURCE_DIR="$value" ;;
        --deploy-dir) DEPLOY_DIR="$value" ;;
        --overrides) OVERRIDES="$value" ;;
        --old-certs-dir) OLD_CERTS_DIR="$value" ;;
        --from-backup) BACKUP_DIR="$value" ;;
      esac
      shift 2
      ;;
    --check|--dry-run)
      [ -z "$MODE" ] || die "informe apenas um modo"
      MODE="check"
      shift
      ;;
    --apply)
      [ -z "$MODE" ] || die "informe apenas um modo"
      MODE="apply"
      shift
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

if [ -n "$BACKUP_DIR" ]; then
  BACKUP_DIR="$(cd "$BACKUP_DIR" && pwd -P)"
  [ -z "$SOURCE_DIR" ] || die "não combine --from-backup com --source-dir"
  SOURCE_DIR="$BACKUP_DIR"
  [ -n "$OVERRIDES" ] || OVERRIDES="$BACKUP_DIR/migration-overrides.env"
  [ -n "$OLD_CERTS_DIR" ] || OLD_CERTS_DIR="$BACKUP_DIR/certificado"
fi
[ -n "$DEPLOY_DIR" ] || DEPLOY_DIR="$(cd "$SCRIPT_DIR/../.." && pwd -P)"

[ -n "$SOURCE_DIR" ] || die "--source-dir é obrigatório"
[ -n "$DEPLOY_DIR" ] || die "--deploy-dir é obrigatório"
[ -n "$OVERRIDES" ] || die "--overrides é obrigatório"
[ -n "$OLD_CERTS_DIR" ] || die "--old-certs-dir é obrigatório"
[ -n "$MODE" ] || die "--check ou --apply é obrigatório"

[ -d "$SOURCE_DIR" ] || die "origem 1.2 inexistente: $SOURCE_DIR"
[ -d "$DEPLOY_DIR" ] || die "destino 1.3 inexistente: $DEPLOY_DIR"
SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd -P)"
DEPLOY_DIR="$(cd "$DEPLOY_DIR" && pwd -P)"
OVERRIDES="$(cd "$(dirname "$OVERRIDES")" && pwd -P)/$(basename "$OVERRIDES")"
OLD_CERTS_DIR="$(cd "$OLD_CERTS_DIR" && pwd -P)"
COMPLETION_MARKER="$DEPLOY_DIR/.runtime/migration-1.2-1.3.complete"

for path in \
  "$SOURCE_DIR/docker-compose-prod.yaml" \
  "$SOURCE_DIR/docker-compose-ext.yaml" \
  "$SOURCE_DIR/airflow.env" \
  "$SOURCE_DIR/.env" \
  "$SOURCE_DIR/env_files/prod.env" \
  "$SOURCE_DIR/env_files/default.env" \
  "$SOURCE_DIR/env_files/security.env" \
  "$DEPLOY_DIR/docker-compose.yml" \
  "$DEPLOY_DIR/Makefile"; do
  [ -f "$path" ] || die "arquivo obrigatório ausente: $path"
done

printf '[migracao 1.2->1.3] Executando preflight sem alterações.\n'
preflight_output="$({
  python3 "$PYTHON_MIGRATION" \
    --source-dir "$SOURCE_DIR" \
    --deploy-dir "$DEPLOY_DIR" \
    --overrides "$OVERRIDES" \
    --old-certs-dir "$OLD_CERTS_DIR" \
    --check
} 2>&1)" || {
  printf '%s\n' "$preflight_output" >&2
  exit 2
}
printf '%s\n' "$preflight_output"

if [ "$MODE" = "check" ]; then
  exit 0
fi

if printf '%s\n' "$preflight_output" | grep -qx 'MIGRATION_STATUS=already-migrated'; then
  if [ -f "$COMPLETION_MARKER" ]; then
    printf '[migracao 1.2->1.3] Destino já migrado e ativado; nenhuma ação executada.\n'
    exit 0
  fi
  printf '[migracao 1.2->1.3] Configuração já gravada, mas ativação não concluída; retomando make up e make check.\n'
else
  rm -f "$COMPLETION_MARKER"
fi

printf '[migracao 1.2->1.3] Parando somente a stack 1.2; volumes serão preservados.\n'
docker compose \
  --profile '*' \
  --env-file "$SOURCE_DIR/env_files/prod.env" \
  --env-file "$SOURCE_DIR/env_files/default.env" \
  --env-file "$SOURCE_DIR/env_files/security.env" \
  -f "$SOURCE_DIR/docker-compose-prod.yaml" \
  -f "$SOURCE_DIR/docker-compose-ext.yaml" \
  -p sei_ia \
  down --remove-orphans

printf '[migracao 1.2->1.3] Gravando configuração e certificado validados.\n'
python3 "$PYTHON_MIGRATION" \
  --source-dir "$SOURCE_DIR" \
  --deploy-dir "$DEPLOY_DIR" \
  --overrides "$OVERRIDES" \
  --old-certs-dir "$OLD_CERTS_DIR" \
  --apply

printf '[migracao 1.2->1.3] Validando e iniciando a stack 1.3.\n'
make --directory "$DEPLOY_DIR" up
make --directory "$DEPLOY_DIR" check

umask 077
marker_tmp="$(mktemp "$DEPLOY_DIR/.runtime/.migration-1.2-1.3.complete.XXXXXX")"
printf 'MIGRATION_STATUS=complete\n' > "$marker_tmp"
mv -f "$marker_tmp" "$COMPLETION_MARKER"

printf '[migracao 1.2->1.3] Migração concluída com todos os gates aprovados.\n'
