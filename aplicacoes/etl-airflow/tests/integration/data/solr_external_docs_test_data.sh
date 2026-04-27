#!/bin/bash

curl "http://rhseislpdin01.anatel.gov.br:8983/solr/sei-protocolos/select?q=prot_proc:53500.039847/2021-42&q.op=OR&wt=json" -o myresponse.json