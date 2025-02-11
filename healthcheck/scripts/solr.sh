#!/bin/bash
curl --fail http://localhost:8983/solr/${SOLR_MLT_PROCESS_CORE}/select && curl --fail http://localhost:8983/solr/${SOLR_MLT_JURISPRUDENCE_CORE}/select
  
  
