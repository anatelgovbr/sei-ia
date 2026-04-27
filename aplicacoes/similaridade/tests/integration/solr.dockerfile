FROM solr:9.0.0

COPY --chown=8983:8983 solr_core_configs /var/solr/