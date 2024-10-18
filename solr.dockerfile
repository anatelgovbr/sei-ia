FROM solr:9.0.0

# Copiar os arquivos de configuração para dentro do container
COPY tmp/jobs/jobs/configs/solr_core_configs/configsets /var/solr/configsets
COPY tmp/jobs/jobs/configs/solr_core_configs/log4j2.xml /var/solr/log4j2.xml
COPY tmp/jobs/jobs/configs/solr_core_configs/solr.xml /opt/solr/server/solr/solr.xml

# Mudar as permissões dos arquivos e diretórios
USER root
RUN apt-get update && apt-get install -y cron
RUN chown -R 8983:8983 /var/solr && \
    chown 8983:8983 /opt/solr-9.0.0/server/solr/solr.xml

