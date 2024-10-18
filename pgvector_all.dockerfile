FROM pgvector/pgvector:pg16

# variáveis não são mais usadas em tempo de build - Tarefa Taiga 896
# ARG POSTGRES_USER
# ARG POSTGRES_DB
# ARG POSTGRES_DB_SIMILARIDADE

# Instale cron e outros pacotes necessários
RUN apt-get update && apt-get install -y cron tzdata gettext

# Configure o timezone
RUN echo "America/Sao_Paulo" > /etc/timezone \
    && ln -sf /usr/share/zoneinfo/America/Sao_Paulo /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata

# Copie os arquivos necessários
COPY ./database_init/conf/init_pgvector.sql /docker-entrypoint-initdb.d/init_pgvector.sql.template
COPY ./backup/volumes/backup_project.sh /backup.sh

# Crie o entrypoint customizado para inicializar o cron e o PostgreSQL
RUN \
    cd /usr/local/bin && \
    echo "#!/usr/bin/env bash" > sei_ia-entrypoint.sh && \
    echo "echo '`date` LOG: Gerando arquivo /docker-entrypoint-initdb.d/init_pgvector.sql'" >> sei_ia-entrypoint.sh && \
    echo "envsubst '\${POSTGRES_USER} \${POSTGRES_DB} \${POSTGRES_DB_SIMILARIDADE} \${POSTGRES_DB_ASSISTENTE_SCHEMA}' \
                < /docker-entrypoint-initdb.d/init_pgvector.sql.template \
                > /docker-entrypoint-initdb.d/init_pgvector.sql" \
         >> sei_ia-entrypoint.sh && \
    echo "echo '`date` LOG: Iniciando o serviço cron'" >> sei_ia-entrypoint.sh && \
    echo "cron" >> sei_ia-entrypoint.sh && \
    echo "echo '`date` LOG: Executando entrypoint original da imagem pgvector/pgvector:pg16'" >> sei_ia-entrypoint.sh && \
    echo "docker-entrypoint.sh postgres" >> sei_ia-entrypoint.sh && \
    chmod +x sei_ia-entrypoint.sh

# Crie o wrapper script para garantir que as variáveis de ambiente sejam passadas corretamente ao cron
RUN echo '#!/bin/bash' > /run_backup_assistente.sh && \
    echo '. /etc/custom_env_vars_assistente.sh' >> /run_backup_assistente.sh && \
    echo '/backup.sh' >> /run_backup_assistente.sh && \
    chmod +x /run_backup_assistente.sh

RUN echo '#!/bin/bash' > /run_backup_sei_similaridade.sh && \
    echo '. /etc/custom_env_vars_similaridade.sh' >> /run_backup_sei_similaridade.sh && \
    echo '/backup.sh' >> /run_backup_sei_similaridade.sh && \
    chmod +x /run_backup_sei_similaridade.sh

# Permissões para o script de backup
RUN chmod +x /backup.sh

# Adiciona os cron jobs ao crontab
RUN (crontab -l 2>/dev/null; echo '05 23 * * * . /etc/custom_env_vars_assistente.sh && /run_backup_assistente.sh >> /var/log/backup.log 2>&1') | crontab - \
    && (crontab -l 2>/dev/null; echo '55 23 * * * . /etc/custom_env_vars_similaridade.sh && /run_backup_sei_similaridade.sh >> /var/log/backup.log 2>&1') | crontab -

# Exponha a porta do PostgreSQL
EXPOSE 5432