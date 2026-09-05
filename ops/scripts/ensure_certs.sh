#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-.}"
CERTS_DIR="$REPO_ROOT/.runtime/certs"
CERT_FILE="$CERTS_DIR/seiia.cert.pem"
KEY_FILE="$CERTS_DIR/seiia.cert.key"
MANAGED_MARKER="$CERTS_DIR/.generated-by-sei-ia"

# Le uma variavel do ambiente; se vazia, cai para security.env e default.env.
read_conf() {
  local name="$1" val f
  val="$(printenv "$name" 2>/dev/null || true)"
  if [ -z "$val" ]; then
    for f in "$REPO_ROOT/security.env" "$REPO_ROOT/default.env"; do
      [ -f "$f" ] || continue
      val="$(grep "^${name}=" "$f" 2>/dev/null | tail -n1 | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]' || true)"
      [ -n "$val" ] && break
    done
  fi
  printf '%s' "$val"
}

valid_dns_name() {
  local name="$1" label
  [ -n "$name" ] && [ "${#name}" -le 253 ] || return 1
  IFS='.' read -ra labels <<< "$name"
  [ "${#labels[@]}" -gt 0 ] || return 1
  for label in "${labels[@]}"; do
    [ -n "$label" ] && [ "${#label}" -le 63 ] || return 1
    printf '%s' "$label" | grep -Eq \
      '^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$' || return 1
  done
}

cert_has_dns() {
  local name="$1" escaped
  escaped="${name//./\\.}"
  printf '%s' "$CURRENT_SAN" | grep -qE "DNS:${escaped}(,|$)"
}

cert_and_key_match() {
  local cert_public key_public
  cert_public="$(openssl x509 -in "$CERT_FILE" -pubkey -noout 2>/dev/null)" || return 1
  key_public="$(openssl pkey -in "$KEY_FILE" -pubout 2>/dev/null)" || return 1
  [ "$cert_public" = "$key_public" ]
}

cert_fingerprint() {
  openssl x509 -in "$CERT_FILE" -noout -fingerprint -sha256 2>/dev/null
}

NB_USER="$(read_conf NB_USER)"
NB_USER="${NB_USER:-seiia}"
SEIIA_GATEWAY_HOST="$(read_conf SEIIA_GATEWAY_HOST)"
SEIIA_CERT_DNS="$(read_conf SEIIA_CERT_DNS)"

if [ -z "$SEIIA_GATEWAY_HOST" ]; then
  echo "$(date)    ERRO: defina SEIIA_GATEWAY_HOST em security.env" >&2
  exit 2
fi
if ! valid_dns_name "$SEIIA_GATEWAY_HOST"; then
  echo "$(date)    ERRO: SEIIA_GATEWAY_HOST contem um nome DNS invalido: '$SEIIA_GATEWAY_HOST'" >&2
  exit 2
fi

# O certificado gerenciado tambem cobre os nomes internos usados pelos healthchecks.
SAN="DNS:$SEIIA_GATEWAY_HOST,DNS:$NB_USER,DNS:localhost,IP:127.0.0.1"
WANT_DNS="$SEIIA_GATEWAY_HOST"
if [ -n "$SEIIA_CERT_DNS" ]; then
  case "$SEIIA_CERT_DNS" in
    ,*|*,|*,,*)
      echo "$(date)    ERRO: SEIIA_CERT_DNS contem uma lista DNS invalida: '$SEIIA_CERT_DNS'" >&2
      exit 2
      ;;
  esac
  IFS=',' read -ra _dns_names <<< "$SEIIA_CERT_DNS"
  for name in "${_dns_names[@]}"; do
    name="$(printf '%s' "$name" | tr -d '[:space:]')"
    [ -z "$name" ] && continue
    if ! valid_dns_name "$name"; then
      echo "$(date)    ERRO: SEIIA_CERT_DNS contem um nome DNS invalido: '$name'" >&2
      exit 2
    fi
    SAN="$SAN,DNS:$name"
    WANT_DNS="$WANT_DNS $name"
  done
fi

mkdir -p "$CERTS_DIR"
chmod 700 "$CERTS_DIR"

for entry in "$CERT_FILE" "$KEY_FILE"; do
  if [ -e "$entry" ] && [ ! -f "$entry" ]; then
    echo "$(date)    ERRO: $entry existe, mas nao e um arquivo regular; corrija o bind mount antes de continuar" >&2
    exit 2
  fi
done

cert_exists=0
key_exists=0
[ -f "$CERT_FILE" ] && cert_exists=1
[ -f "$KEY_FILE" ] && key_exists=1

if [ "$cert_exists" -ne "$key_exists" ]; then
  echo "$(date)    ERRO: certificado e chave devem existir como um par em $CERTS_DIR" >&2
  exit 2
fi

needs_gen=0
validation_error=""
is_managed=0
if [ "$cert_exists" -eq 0 ]; then
  needs_gen=1
else
  if [ -f "$MANAGED_MARKER" ] && [ "$(cat "$MANAGED_MARKER")" = "$(cert_fingerprint || true)" ]; then
    is_managed=1
  fi
  if ! cert_and_key_match; then
    validation_error="o certificado e a chave privada nao formam um par valido"
  elif ! openssl x509 -in "$CERT_FILE" -noout -checkend 0 >/dev/null 2>&1; then
    validation_error="o certificado esta vencido ou invalido"
  else
    CURRENT_SAN="$(openssl x509 -in "$CERT_FILE" -noout -ext subjectAltName 2>/dev/null || true)"
    for name in $WANT_DNS; do
      if ! cert_has_dns "$name"; then
        validation_error="o certificado nao cobre DNS:$name no SAN"
        break
      fi
    done
  fi

  if [ -n "$validation_error" ]; then
    if [ "$is_managed" -eq 1 ]; then
      needs_gen=1
    else
      echo "$(date)    ERRO: certificado fornecido pelo operador: $validation_error" >&2
      echo "$(date)    ERRO: corrija o par $CERT_FILE / $KEY_FILE; ele nao sera sobrescrito automaticamente" >&2
      exit 2
    fi
  fi
fi

if [ "$needs_gen" -eq 1 ]; then
  echo "$(date)    INFO: gerando certificado TLS autoassinado em $CERTS_DIR (SAN: $SAN)"
  openssl req -x509 -newkey rsa:4096 -nodes -days 3650 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -subj "/C=BR/ST=Estado/L=Cidade/O=Organizacao/OU=Unidade/CN=$SEIIA_GATEWAY_HOST" \
    -addext "subjectAltName=$SAN"
  cert_fingerprint > "$MANAGED_MARKER"
  chmod 600 "$MANAGED_MARKER"
else
  echo "$(date)    INFO: certificado em $CERT_FILE valido para $WANT_DNS; mantendo"
fi

chmod 644 "$CERT_FILE"
chmod 600 "$KEY_FILE"
