FROM pgvector/pgvector:pg16

ARG POSTGRES_USER
ARG POSTGRES_DB
ARG POSTGRES_DB_SIMILARIDADE

RUN apt-get update && apt-get install -y cron tzdata gettext

RUN echo "America/Sao_Paulo" > /etc/timezone \
    && ln -sf /usr/share/zoneinfo/America/Sao_Paulo /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata

COPY ./database_init/conf/init_pgvector.sql /docker-entrypoint-initdb.d/init_pgvector.sql.template

COPY ./backup/volumes/backup_project.sh /backup.sh

RUN \
    cd /usr/local/bin && \
    echo "#!/usr/bin/env bash" > sei_ia-entrypoint.sh && \
    echo "echo '`date` LOG: Gerando arquivo /docker-entrypoint-initdb.d/init_pgvector.sql'" >> sei_ia-entrypoint.sh && \
    echo "envsubst '\${POSTGRES_USER} \${POSTGRES_DB} \${POSTGRES_DB_SIMILARIDADE}' \
                < /docker-entrypoint-initdb.d/init_pgvector.sql.template \
                > /docker-entrypoint-initdb.d/init_pgvector.sql" \
         >> sei_ia-entrypoint.sh && \
    echo "echo '`date` LOG: Executando entrypoint original da imagem pgvector/pgvector:pg16'" >> sei_ia-entrypoint.sh && \
    echo "docker-entrypoint.sh postgres" >> sei_ia-entrypoint.sh && \
    chmod +x sei_ia-entrypoint.sh


RUN chmod +x /backup.sh

RUN echo '05 23 * * * export POSTGRES_USER=${POSTGRES_USER} POSTGRES_PASSWORD=${POSTGRES_PASSWORD} POSTGRES_DB=${POSTGRES_DB} PGDATA=${PGDATA} && sleep 1 && date >> /var/log/backup.log && /backup.sh >> /var/log/backup.log 2>&1' | crontab -
RUN echo '55 23 * * * export POSTGRES_USER=${POSTGRES_USER} POSTGRES_PASSWORD=${POSTGRES_PASSWORD} POSTGRES_DB=${POSTGRES_DB_SIMILARIDADE} PGDATA=${PGDATA} && sleep 1 && date >> /var/log/backup.log && /backup.sh >> /var/log/backup.log 2>&1' | crontab -

EXPOSE 5432

