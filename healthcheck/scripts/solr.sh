#!/bin/bash
curl --fail -k -u $SOLR_USER:$SOLR_PASSWORD https://localhost:8983/solr/${SOLR_MLT_PROCESS_CORE}/select && curl --fail -k -u $SOLR_USER:$SOLR_PASSWORD https://localhost:8983/solr/${SOLR_MLT_JURISPRUDENCE_CORE}/select
