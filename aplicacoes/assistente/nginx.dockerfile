FROM nginx:1.27-alpine3.19-perl

# Instalar openssl para gerar certificados
RUN apk add --no-cache openssl

# Criar pastas de destino (se necessário, mas /etc/ssl/certs e /etc/ssl/private já existem no Alpine)
RUN mkdir -p /etc/ssl/certs /etc/ssl/private /etc/nginx/conf.d

# Gerar certificados autoassinados diretamente nos locais corretos, se não existirem
RUN if [ ! -f /etc/ssl/certs/seiia.cert.pem ] || [ ! -f /etc/ssl/private/seiia.cert.key ]; then \
        openssl req -x509 -newkey rsa:4096 -keyout /etc/ssl/private/seiia.cert.key -out /etc/ssl/certs/seiia.cert.pem -days 3650 -nodes -subj "/C=BR/ST=Estado/L=Cidade/O=Organizacao/OU=Unidade/CN=localhost"; \
    fi

# Ajustar permissões para que o usuário nginx possa ler os certificados
RUN chown -R nginx:nginx /etc/ssl/certs /etc/ssl/private && \
    chmod 644 /etc/ssl/certs/seiia.cert.pem && \
    chmod 600 /etc/ssl/private/seiia.cert.key

# Copiar o arquivo de configuração do Nginx a partir da estrutura do monorepo
COPY aplicacoes/assistente/sei_ia/configs/nginx.conf /etc/nginx/conf.d/nginx.conf
