FROM python:3.9-alpine
LABEL Description="AutoDeployer"

RUN apk update
RUN apk add jq git curl openssh docker docker-cli-compose dcron logrotate su-exec

ADD . /app

ARG NB_USER
ARG NB_UID
ARG GID_DOCKER

# Corrigindo as interpolações para usar corretamente as variáveis
RUN addgroup -g "${GID_DOCKER}" docker_host
RUN adduser -D -u "${NB_UID}" "${NB_USER}"
RUN addgroup "${NB_USER}" docker_host

RUN mkdir -p /home/${NB_USER}/.ssh
RUN chown -R ${NB_USER} /home/${NB_USER}/.ssh
RUN chmod 700 /home/${NB_USER}/.ssh

RUN chmod -R 777 /app/
RUN chown -R ${NB_USER} /app

# Criando pastas para o log do autodeployer
RUN mkdir -p /var/log/autodeployer
RUN chown ${NB_USER} /var/log/autodeployer

# Cria a configuração do logrotate para rotacionar o autodeployer.log
RUN echo -e "/var/log/autodeployer/autodeployer.log {\n\
    weekly\n\
    missingok\n\
    rotate 4\n\
    compress\n\
    delaycompress\n\
    create 0640 ${NB_USER} root\n\
}\n" > /etc/logrotate.d/autodeployer

# Ativa o suid bit
RUN chmod u+s /sbin/su-exec

USER ${NB_USER}

WORKDIR /app
RUN python -m pip install --upgrade pip && pip install -e .

CMD su-exec root crond -L /var/log/cron.log && umask 000 && python3 -m app_monitor
