#!/bin/bash
set -e # Se algum comando falhar, o script para

# Verificar se o OpenSSL está instalado
if ! command -v openssl &> /dev/null; then
    echo "*** `date` ERRO: OpenSSL não está instalado. Por favor, instale o OpenSSL antes de continuar."
    exit 1
fi

rm -rf .env

echo "*** `date`: Carregando variáveis de ambiente..."
# Carregar variáveis de ambiente
source env_files/prod.env
source env_files/default.env
source env_files/security.env

# Carregar variáveis de ambiente específicas de acordo com o argumento
cat env_files/prod.env > .env
cat env_files/default.env >> .env
cat env_files/security.env >> .env

source ./.env
CERT_DIR=$VOL_SEIIA_DIR/certificado

if [ ! -d $CERT_DIR ]; then
    echo "`date` INFO: Pasta '$CERT_DIR' não encontrada, criando..."
    sudo mkdir -p $CERT_DIR
fi


if [ ! -d "certificado" ]; then
    echo "`date` INFO: Pasta 'certificado' não encontrada, criando..."
    mkdir -p "certificado"
fi

# Verificar se os certificados existem e criar se não existirem
if [ ! -f "certificado/seiia.cert.pem" ] || [ ! -f "certificado/seiia.cert.key" ]; then
    echo "`date` INFO: Certificado não encontrado, criando..."
    openssl req -x509 -newkey rsa:2048 -nodes -batch -out certificado/seiia.cert.pem -keyout certificado/seiia.cert.key -days 36500 -subj "/CN=seiia"
else
    echo "*** `date` INFO: Certificado já existe, continuando..."
fi

echo "*** `date` INFO: Copiando certificados para o diretório de volumes... $CERT_DIR"
sudo cp certificado/seiia.cert.pem $CERT_DIR/seiia.cert.pem
sudo cp certificado/seiia.cert.key $CERT_DIR/seiia.cert.key

echo "*** `date` INFO: Certificados encontrados, ajustando permissões..."
sudo chown -R $NB_UID:$NB_UID $CERT_DIR

echo "*** `date` INFO: Iniciando containers com certificados montados..."
docker compose -f docker-compose-prod.yaml \
  -f certificado_ssl_proprietario/docker-compose-cert-override.yml \
  -f docker-compose-ext.yaml \
  -p "$PROJECT_NAME" \
  --profile certificado \
  stop
docker compose -f docker-compose-prod.yaml \
  -f certificado_ssl_proprietario/docker-compose-cert-override.yml \
  -f docker-compose-ext.yaml \
  -p "$PROJECT_NAME" \
  --profile certificado \
  up -d

rm .env
rm -rf certificado