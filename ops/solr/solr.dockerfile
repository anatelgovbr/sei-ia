# syntax=docker/dockerfile:1.7

FROM solr:9.0.0

ARG SOLR_USER
ARG SOLR_PASSWORD

COPY aplicacoes/etl-airflow/jobs/configs/solr_core_configs/configsets /var/solr/configsets
COPY aplicacoes/etl-airflow/jobs/configs/solr_core_configs/log4j2.xml /var/solr/log4j2.xml
COPY aplicacoes/etl-airflow/jobs/configs/solr_core_configs/solr.xml /opt/solr/server/solr/solr.xml

USER root

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y cron gettext pwgen vim-common curl

COPY ops/solr/create_hash.sh /tmp/create_hash.sh
RUN chmod +x /tmp/create_hash.sh

# Copia o template do arquivo de segurança
COPY ops/solr/security.json.template /tmp/security.json.template

RUN chown -R 8983:8983 /var/solr && \
    chown 8983:8983 /opt/solr-9.0.0/server/solr/solr.xml

COPY ops/solr/entrypoint.sh /opt/solr/entrypoint.sh
RUN chmod +x /opt/solr/entrypoint.sh

ENTRYPOINT ["/opt/solr/entrypoint.sh"]
