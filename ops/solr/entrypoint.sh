#!/bin/bash
set -e

# Adiciona as opções do SSL às opções Java, se necessário
if [[ -n "$SOLR_SSL_OPTS" ]]; then
  SOLR_OPTS="$SOLR_OPTS $SOLR_SSL_OPTS"
fi

# Cria o diretório para os arquivos SSL
mkdir -p /var/solr-ssl

echo "Gerando a chave privada SSL..."
openssl genrsa -out /var/solr-ssl/key.pem 2048

echo "Gerando o certificado SSL autoassinado..."
openssl req -new -x509 \
  -key /var/solr-ssl/key.pem \
  -out /var/solr-ssl/cert.pem \
  -days 365 \
  -subj "/C=BR/ST=Distrito Federal/L=Brasilia/O=Solr/OU=IT Department/CN=${SOLR_HOST}"

chmod 600 /var/solr-ssl/cert.pem /var/solr-ssl/key.pem
chown -R solr:solr /var/solr-ssl

echo "Criando o keystore SSL..."
openssl pkcs12 -export \
  -in /var/solr-ssl/cert.pem \
  -inkey /var/solr-ssl/key.pem \
  -out /var/solr-ssl/keystore.p12 \
  -name solr-ssl \
  -passout pass:12345

if [ ! -f /var/solr-ssl/keystore.p12 ]; then
  echo "Erro ao criar o keystore SSL."
  exit 1
fi

chmod 600 /var/solr-ssl/keystore.p12
chown solr:solr /var/solr-ssl/keystore.p12

export SOLR_SSL_ENABLED=true
export SOLR_SSL_KEY_STORE=/var/solr-ssl/keystore.p12
export SOLR_SSL_KEY_STORE_PASSWORD=12345
export SOLR_SSL_TRUST_STORE=/var/solr-ssl/keystore.p12
export SOLR_SSL_TRUST_STORE_PASSWORD=12345
export SOLR_SSL_NEED_CLIENT_AUTH=false
export SOLR_SSL_WANT_CLIENT_AUTH=false

echo "Certificado SSL gerado e armazenado em /var/solr-ssl/cert.pem"

echo "Gerando o arquivo security.json a partir do template..."
SALT=$(/tmp/create_hash.sh)
HASHED_PASSWORD=$(/tmp/create_hash.sh "$SOLR_PASSWORD")
export HASHED_PASSWORD="${HASHED_PASSWORD}"
export SOLR_USER="${SOLR_USER}"

envsubst < /tmp/security.json.template > /tmp/security.json

chmod 664 /tmp/security.json
chown root:root /tmp/security.json

chown -R 8983:8983 /var/solr

mkdir -p /var/solr/data
chown -R solr:solr /var/solr/data

echo "Configurando o Solr security..."
cp /tmp/security.json /var/solr/data/security.json

runuser -u solr -- solr-precreate default-core

echo "Iniciando o Solr com suporte a SSL..."
exec solr -f -Dsolr.log.level=DEBUG
