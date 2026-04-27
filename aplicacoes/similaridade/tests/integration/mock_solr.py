
import json


SOLR_RESPONSES = [{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/mlt?q=id_protocolo:422762&fl=id_protocolo,score&mlt.maxqt=1024&mlt.fl=metadata_name_id_type_process&mlt.mintf=1&mlt.mindf=1&wt=json&mlt.interesting_terms=details&mlt.boost=true",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 2}, "match": {"numFound": 1, "start": 0, "maxScore": 0.7002023, "numFoundExact": true, "docs": [{"id_protocolo": "422762", "score": 0.7002023}]}, "response": {"numFound": 3, "start": 0, "maxScore": 0.49104476, "numFoundExact": true, "docs": []}, "interesting_terms": ["metadata_name_id_type_process:regulamentaca", 1.0, "metadata_name_id_type_process:tecnic", 1.1844571, "metadata_name_id_type_process:condica", 1.4444346, "metadata_name_id_type_process:radiofrequenci", 1.4444346, "metadata_name_id_type_process:respectiv", 1.4444346, "metadata_name_id_type_process:faix", 1.4444346, "metadata_name_id_type_process:destinaca", 1.4444346, "metadata_name_id_type_process:servic", 1.4444346, "metadata_name_id_type_process:traz", 1.4444346, "metadata_name_id_type_process:determinad", 1.4444346, "metadata_name_id_type_process:uso", 2.8888693]}'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/mlt?q=id_protocolo%3A422762&fl=id_protocolo%2Cscore&mlt.maxqt=1024&mlt.fl=metadata_name_id_type_process&mlt.mintf=1&mlt.mindf=1&wt=json&mlt.interesting_terms=details&mlt.boost=true&start=0&rows=0",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 2}, "match": {"numFound": 1, "start": 0, "maxScore": 0.7002023, "numFoundExact": true, "docs": [{"id_protocolo": "422762", "score": 0.7002023}]}, "response": {"numFound": 3, "start": 0, "maxScore": 0.49104476, "numFoundExact": true, "docs": []}, "interesting_terms": ["metadata_name_id_type_process:regulamentaca", 1.0, "metadata_name_id_type_process:tecnic", 1.1844571, "metadata_name_id_type_process:condica", 1.4444346, "metadata_name_id_type_process:radiofrequenci", 1.4444346, "metadata_name_id_type_process:respectiv", 1.4444346, "metadata_name_id_type_process:faix", 1.4444346, "metadata_name_id_type_process:destinaca", 1.4444346, "metadata_name_id_type_process:servic", 1.4444346, "metadata_name_id_type_process:traz", 1.4444346, "metadata_name_id_type_process:determinad", 1.4444346, "metadata_name_id_type_process:uso", 2.8888693]}'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=*:*&rows=1&fl=numdocs()",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"q": "*:*", "fl": "numdocs()", "rows": "1"} }, "response": {"numFound": 6, "start": 0, "numFoundExact": true, "docs": [{"numdocs()": 6}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=%2A%3A%2A&fl=numdocs%28%29&start=0&rows=1",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"q": "*:*", "fl": "numdocs()", "rows": "1"} }, "response": {"numFound": 6, "start": 0, "numFoundExact": true, "docs": [{"numdocs()": 6}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?fl=id_protocolo%2Cscore&indent=true&q.op=OR&q=metadata_name_id_type_process%3Auso+metadata_name_id_type_process%3Acondica+metadata_name_id_type_process%3Aradiofrequenci+metadata_name_id_type_process%3Arespectiv+metadata_name_id_type_process%3Afaix+metadata_name_id_type_process%3Adestinaca+metadata_name_id_type_process%3Aservic+metadata_name_id_type_process%3Atraz+metadata_name_id_type_process%3Adeterminad+metadata_name_id_type_process%3Atecnic+metadata_name_id_type_process%3Aregulamentaca&fq=id_protocolo%3A422762&start=0&rows=1",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 1, "params": {"q": "metadata_name_id_type_process:uso metadata_name_id_type_process:condica metadata_name_id_type_process:radiofrequenci metadata_name_id_type_process:respectiv metadata_name_id_type_process:faix metadata_name_id_type_process:destinaca metadata_name_id_type_process:servic metadata_name_id_type_process:traz metadata_name_id_type_process:determinad metadata_name_id_type_process:tecnic metadata_name_id_type_process:regulamentaca", "indent": "true", "fl": "id_protocolo,score", "q.op": "OR", "fq": "id_protocolo:422762", "rows": "1"} }, "response": {"numFound": 1, "start": 0, "maxScore": 7.3871775, "numFoundExact": true, "docs": [{"id_protocolo": "422762", "score": 7.3871775}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?fl=id_protocolo,score&indent=true&q.op=OR&q=metadata_name_id_type_process:uso metadata_name_id_type_process:condica metadata_name_id_type_process:radiofrequenci metadata_name_id_type_process:respectiv metadata_name_id_type_process:faix metadata_name_id_type_process:destinaca metadata_name_id_type_process:servic metadata_name_id_type_process:traz metadata_name_id_type_process:determinad metadata_name_id_type_process:tecnic metadata_name_id_type_process:regulamentaca&rows=1&fq=id_protocolo:422762",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 1, "params": {"q": "metadata_name_id_type_process:uso metadata_name_id_type_process:condica metadata_name_id_type_process:radiofrequenci metadata_name_id_type_process:respectiv metadata_name_id_type_process:faix metadata_name_id_type_process:destinaca metadata_name_id_type_process:servic metadata_name_id_type_process:traz metadata_name_id_type_process:determinad metadata_name_id_type_process:tecnic metadata_name_id_type_process:regulamentaca", "indent": "true", "fl": "id_protocolo,score", "q.op": "OR", "fq": "id_protocolo:422762", "rows": "1"} }, "response": {"numFound": 1, "start": 0, "maxScore": 7.3871775, "numFoundExact": true, "docs": [{"id_protocolo": "422762", "score": 7.3871775}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=id_protocolo:422762&rows=1&fl=*",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"q": "id_protocolo:422762", "fl": "*", "rows": "1"} }, "response": {"numFound": 1, "start": 0, "numFoundExact": true, "docs": [{"id_protocolo": "422762", "protocolo_formatado": "53500029606201032", "metadata_name_id_type_process": "Regulamentação: Uso de Radiofrequências,Traz a destinação de faixa a um determinado serviço, com as respectivas condições técnicas de uso.", "_version_": 1778028670705729536}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=id_protocolo%3A422762&fl=%2A&start=0&rows=1",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"q": "id_protocolo:422762", "fl": "*", "rows": "1"} }, "response": {"numFound": 1, "start": 0, "numFoundExact": true, "docs": [{"id_protocolo": "422762", "protocolo_formatado": "53500029606201032", "metadata_name_id_type_process": "Regulamentação: Uso de Radiofrequências,Traz a destinação de faixa a um determinado serviço, com as respectivas condições técnicas de uso.", "_version_": 1778028670705729536}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=metadata_name_id_type_doc_7:*&rows=0",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 1, "params": {"q": "metadata_name_id_type_doc_7:*", "rows": "0"} }, "response": {"numFound": 3635, "start": 0, "numFoundExact": true, "docs": []} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=*:*&fl=sumtotaltermfreq(metadata_name_id_type_doc_7)&rows=1",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 82, "params": {"q": "*:*", "fl": "sumtotaltermfreq(metadata_name_id_type_doc_7)", "rows": "1"} }, "response": {"numFound": 140783, "start": 0, "numFoundExact": true, "docs": [{"sumtotaltermfreq(metadata_name_id_type_doc_7)": 4062}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=metadata_name_id_type_doc_8:*&rows=0",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 1, "params": {"q": "metadata_name_id_type_doc_8:*", "rows": "0"} }, "response": {"numFound": 3759, "start": 0, "numFoundExact": true, "docs": []} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=*:*&fl=sumtotaltermfreq(metadata_name_id_type_doc_8)&rows=1",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 90, "params": {"q": "*:*", "fl": "sumtotaltermfreq(metadata_name_id_type_doc_8)", "rows": "1"} }, "response": {"numFound": 140783, "start": 0, "numFoundExact": true, "docs": [{"sumtotaltermfreq(metadata_name_id_type_doc_8)": 4206}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=metadata_name_id_type_doc_11:*&rows=0",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 2, "params": {"q": "metadata_name_id_type_doc_11:*", "rows": "0"} }, "response": {"numFound": 17824, "start": 0, "numFoundExact": true, "docs": []} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=*:*&fl=sumtotaltermfreq(metadata_name_id_type_doc_11)&rows=1",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 82, "params": {"q": "*:*", "fl": "sumtotaltermfreq(metadata_name_id_type_doc_11)", "rows": "1"} }, "response": {"numFound": 140783, "start": 0, "numFoundExact": true, "docs": [{"sumtotaltermfreq(metadata_name_id_type_doc_11)": 27361}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=metadata_name_id_type_doc_16:*&rows=0",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 1, "params": {"q": "metadata_name_id_type_doc_16:*", "rows": "0"} }, "response": {"numFound": 16601, "start": 0, "numFoundExact": true, "docs": []} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=*:*&fl=sumtotaltermfreq(metadata_name_id_type_doc_16)&rows=1",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"q": "*:*", "fl": "sumtotaltermfreq(metadata_name_id_type_doc_16)", "rows": "1"} }, "response": {"numFound": 140783, "start": 0, "numFoundExact": true, "docs": [{"sumtotaltermfreq(metadata_name_id_type_doc_16)": 25784}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=*:*&rows=1&fl=numdocs()",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"q": "*:*", "fl": "numdocs()", "rows": "1"} }, "response": {"numFound": 140783, "start": 0, "numFoundExact": true, "docs": [{"numdocs()": 140783}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=metadata_name_id_type_doc_7:*&rows=0",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 1, "params": {"q": "metadata_name_id_type_doc_7:*", "rows": "0"} }, "response": {"numFound": 3635, "start": 0, "numFoundExact": true, "docs": []} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=*:*&fl=sumtotaltermfreq(metadata_name_id_type_doc_7)&rows=1",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"q": "*:*", "fl": "sumtotaltermfreq(metadata_name_id_type_doc_7)", "rows": "1"} }, "response": {"numFound": 140783, "start": 0, "numFoundExact": true, "docs": [{"sumtotaltermfreq(metadata_name_id_type_doc_7)": 4062}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=metadata_name_id_type_doc_8:*&rows=0",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 86, "params": {"q": "metadata_name_id_type_doc_8:*", "rows": "0"} }, "response": {"numFound": 3759, "start": 0, "numFoundExact": true, "docs": []} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=*:*&fl=sumtotaltermfreq(metadata_name_id_type_doc_8)&rows=1",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 78, "params": {"q": "*:*", "fl": "sumtotaltermfreq(metadata_name_id_type_doc_8)", "rows": "1"} }, "response": {"numFound": 140783, "start": 0, "numFoundExact": true, "docs": [{"sumtotaltermfreq(metadata_name_id_type_doc_8)": 4206}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=metadata_name_id_type_doc_11:*&rows=0",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"q": "metadata_name_id_type_doc_11:*", "rows": "0"} }, "response": {"numFound": 17824, "start": 0, "numFoundExact": true, "docs": []} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=*:*&fl=sumtotaltermfreq(metadata_name_id_type_doc_11)&rows=1",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"q": "*:*", "fl": "sumtotaltermfreq(metadata_name_id_type_doc_11)", "rows": "1"} }, "response": {"numFound": 140783, "start": 0, "numFoundExact": true, "docs": [{"sumtotaltermfreq(metadata_name_id_type_doc_11)": 27361}]} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=metadata_name_id_type_doc_16:*&rows=0",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 67, "params": {"q": "metadata_name_id_type_doc_16:*", "rows": "0"} }, "response": {"numFound": 16601, "start": 0, "numFoundExact": true, "docs": []} }'
},
{
    "status_code":200,
    "url": "http://fakehost:0000/solr/process/select?q=*:*&fl=sumtotaltermfreq(metadata_name_id_type_doc_16)&rows=1",
    "params":{},
    "payload": {"params":{}},
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"q": "*:*", "fl": "sumtotaltermfreq(metadata_name_id_type_doc_16)", "rows": "1"} }, "response": {"numFound": 140783, "start": 0, "numFoundExact": true, "docs": [{"sumtotaltermfreq(metadata_name_id_type_doc_16)": 25784}]} }'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/process/select",
    "params":{},
    "payload": {'params': {'fl': "docfreq(metadata_name_id_type_doc_7,'analis')", 'rows': 1, 'q': '*:*'} },
    "text": '{"responseHeader": {"status": 0, "QTime": 4, "params": {"json": "{\\"params\\": {\\"fl\\": \\"docfreq(metadata_name_id_type_doc_7,\'analis\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"} }"} }, "response": {"numFound": 140813, "start": 0, "numFoundExact": true, "docs": [{"docfreq(metadata_name_id_type_doc_7,\'analis\')": 5392}]} }'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/process/select",
    "params":{},
    "payload": {"params": {"fl": "docfreq(metadata_name_id_type_doc_8,'acorda')", "rows": 1, "q": "*:*"} },
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"json": "{\\"params\\": {\\"fl\\": \\"docfreq(metadata_name_id_type_doc_8,\'acorda\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"} }"} }, "response": {"numFound": 140813, "start": 0, "numFoundExact": true, "docs": [{"docfreq(metadata_name_id_type_doc_8,\'acorda\')": 5518}]} }'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/process/select",
    "params":{},
    "payload": {"params": {"fl": "docfreq(metadata_name_id_type_doc_11,'ofici')", "rows": 1, "q": "*:*"} },
    "text": '{"responseHeader": {"status": 0, "QTime": 5, "params": {"json": "{\\"params\\": {\\"fl\\": \\"docfreq(metadata_name_id_type_doc_11,\'ofici\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"} }"} }, "response": {"numFound": 140813, "start": 0, "numFoundExact": true, "docs": [{"docfreq(metadata_name_id_type_doc_11,\'ofici\')": 31902}]} }'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/process/select",
    "params":{},
    "payload": {"params": {"fl": "docfreq(metadata_name_id_type_doc_16,'inform')", "rows": 1, "q": "*:*"} },
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"json": "{\\"params\\": {\\"fl\\": \\"docfreq(metadata_name_id_type_doc_16,\'inform\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"} }"} }, "response": {"numFound": 140813, "start": 0, "numFoundExact": true, "docs": [{"docfreq(metadata_name_id_type_doc_16,\'inform\')": 29712}]} }'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/process/select",
    "params":{},
    "payload": {"params": {"fl": "docfreq(metadata_name_id_type_doc_7,'analis')", "rows": 1, "q": "*:*"} },
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"json": "{\\"params\\": {\\"fl\\": \\"docfreq(metadata_name_id_type_doc_7,\'analis\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"} }"} }, "response": {"numFound": 140813, "start": 0, "numFoundExact": true, "docs": [{"docfreq(metadata_name_id_type_doc_7,\'analis\')": 5394}]} }'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/process/select",
    "params":{},
    "payload": {"params": {"fl": "docfreq(metadata_name_id_type_doc_8,'acorda')", "rows": 1, "q": "*:*"} },
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"json": "{\\"params\\": {\\"fl\\": \\"docfreq(metadata_name_id_type_doc_8,\'acorda\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"} }"} }, "response": {"numFound": 140813, "start": 0, "numFoundExact": true, "docs": [{"docfreq(metadata_name_id_type_doc_8,\'acorda\')": 5520}]} }'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/process/select",
    "params":{},
    "payload": {"params": {"fl": "docfreq(metadata_name_id_type_doc_11,'ofici')", "rows": 1, "q": "*:*"} },
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"json": "{\\"params\\": {\\"fl\\": \\"docfreq(metadata_name_id_type_doc_11,\'ofici\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"} }"} }, "response": {"numFound": 140813, "start": 0, "numFoundExact": true, "docs": [{"docfreq(metadata_name_id_type_doc_11,\'ofici\')": 31902}]} }'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/process/select",
    "params":{},
    "payload": {"params": {"fl": "docfreq(metadata_name_id_type_doc_16,'inform')", "rows": 1, "q": "*:*"} },
    "text": '{"responseHeader": {"status": 0, "QTime": 0, "params": {"json": "{\\"params\\": {\\"fl\\": \\"docfreq(metadata_name_id_type_doc_16,\'inform\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"} }"} }, "response": {"numFound": 140813, "start": 0, "numFoundExact": true, "docs": [{"docfreq(metadata_name_id_type_doc_16,\'inform\')": 29712}]} }'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/mlt",
    "params": {"q": f"id_document:111111", "debug_query": "on", "wt": "json", "mlt.interesting_terms": "details", "rows": 0, "fl": "id_document,score,id_type_document", "mlt.mindf": 1, "mlt.mintf": 1},
    "payload": {"params":{}},
    "text": '{\n  "responseHeader":{\n    "status":0,\n    "QTime":0},\n  "match":{"numFound":0,"start":0,"numFoundExact":true,"docs":[]\n  },\n  "response":null,\n  "exception_during_debug":"java.lang.NullPointerException: Cannot invoke \\\"Object.getClass()\\\" because \\\"query\\\" is null"}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'fl': 'id_document', 'q.op': 'OR', 'q': 'id_document:(111111)'},
    "payload": {"params":{}},
    "text": '{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"id_protocolo:111111",\n      "indent":"true",\n      "q.op":"OR"} },\n  "response":{"numFound":0,"start":0,"numFoundExact":true,"docs":[]\n  } }\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'q': 'content:sampl^0.5000 content:text^0.5000', 'fl': 'id_document,score,id_type_document', 'fq': 'id_type_document:( 7 8 94 ) AND id_document:* AND -id_document:( 111111 )', 'rows': '1'},
    "payload": {"params":{}},
    "text": '{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"content:sampl^0.5000 content:text^0.5000",\n      "indent":"true",\n      "fl":"id_document,score,id_type_document",\n      "q.op":"OR",\n      "rows":"1"} },\n  "response":{"numFound":5282,"start":0,"maxScore":1.7418953,"numFoundExact":true,"docs":[\n      {\n        "id_document":"5743209",\n        "id_type_document":"94",\n        "score":1.7418953}]\n  } }\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'q': 'content:sampl^0.5000 content:text^0.5000', 'fl': 'id_document,score,id_type_document', 'fq': 'id_type_document:( 7 8 94 ) AND id_document:*', 'rows': '1'},
    "payload": {"params":{}},
    "text": '{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"content:sampl^0.5000 content:text^0.5000",\n      "indent":"true",\n      "fl":"id_document,score,id_type_document",\n      "q.op":"OR",\n      "rows":"1"} },\n  "response":{"numFound":5282,"start":0,"maxScore":1.7418953,"numFoundExact":true,"docs":[\n      {\n        "id_document":"5743209",\n        "id_type_document":"94",\n        "score":1.7418953}]\n  } }\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'q': 'content:sampl content:text', 'fl': 'id_document,score,id_type_document', 'fq': 'id_type_document:( 7 8 94 ) AND id_document:* AND -id_document:( 111111 )', 'rows': '1'},
    "payload": {"params":{}},
    "text": '{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"content:sampl content:text",\n      "indent":"true",\n      "fl":"id_document,score,id_type_document",\n      "q.op":"OR",\n      "rows":"1"} },\n  "response":{"numFound":5282,"start":0,"maxScore":3.4837906,"numFoundExact":true,"docs":[\n      {\n        "id_document":"5743209",\n        "id_type_document":"94",\n        "score":3.4837906}]\n  } }\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'q': 'content:sampl content:text', 'fl': 'id_document,score,id_type_document', 'fq': 'id_type_document:( 7 8 94 ) AND id_document:*', 'rows': '1'},
    "payload": {"params":{}},
    "text": '{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"content:sampl content:text",\n      "indent":"true",\n      "fl":"id_document,score,id_type_document",\n      "q.op":"OR",\n      "rows":"1"} },\n  "response":{"numFound":5282,"start":0,"maxScore":3.4837906,"numFoundExact":true,"docs":[\n      {\n        "id_document":"5743209",\n        "id_type_document":"94",\n        "score":3.4837906}]\n  } }\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params":{'fl': 'id_document', 'q.op': 'OR', 'q': 'id_document:(1596887 3256530)'},
    "payload": {"params":{}},
    "text": '{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"id_document:(1596887 3256530)",\n      "fl":"id_document",\n      "q.op":"OR"}},\n  "response":{"numFound":2,"start":0,"numFoundExact":true,"docs":[\n      {\n        "id_document":"1596887"},\n      {\n        "id_document":"3256530"}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params":{'fl': 'id_document', 'q.op': 'OR', 'q': 'id_document:(1234567)'},
    "payload": {"params":{}},
    "text": '{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"id_document:(1234567)",\n      "fl":"id_document",\n      "q.op":"OR"}},\n  "response":{"numFound":2,"start":0,"numFoundExact":true,"docs":[\n      {\n        "id_document":"1234567"}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/mlt",
    "params":{'q': 'id_document:3256530', 'debug_query': 'on', 'wt': 'json', 'mlt.interesting_terms': 'details', 'rows': 0, 'fl': 'id_document,score,id_type_document', 'mlt.mindf': 1, 'mlt.mintf': 1},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":4},\n  "match":{"numFound":1,"start":0,"maxScore":5.597987,"numFoundExact":true,"docs":[\n      {\n        "id_document":"3256530",\n        "id_type_document":"11",\n        "score":5.597987}]\n  },\n  "response":{"numFound":115160,"start":0,"maxScore":55.144234,"numFoundExact":true,"docs":[]\n  },\n  "interesting_terms":[\n    "content:atenca",1.0,\n    "content:setor",1.0,\n    "content:pgf",1.0,\n    "content:agu",1.0,\n    "content:disposica",1.0,\n    "content:demal",1.0,\n    "content:encaminhament",1.0,\n    "content:apreciaca",1.0,\n    "content:senhor",1.0,\n    "content:esclareciment",1.0,\n    "content:equip",1.0,\n    "content:procurador",1.0,\n    "content:atualizad",1.0,\n    "content:stel",1.0,\n    "content:colocam",1.0,\n    "content:fizerem",1.0,\n    "content:ativ",1.0,\n    "content:cobranc",1.0,\n    "content:inscrica",1.0,\n    "content:divid",1.0,\n    "content:ana",1.0,\n    "content:reencaminh",1.0,\n    "content:enac",1.0,\n    "content:chang",1.0,\n    "content:jalil",1.0],\n  "debug":{\n    "rawquerystring":"id_document:3256530",\n    "querystring":"id_document:3256530",\n    "parsedquery":"content:atenca content:setor content:pgf content:agu content:disposica content:demal content:encaminhament content:apreciaca content:senhor content:esclareciment content:equip content:procurador content:atualizad content:stel content:colocam content:fizerem content:ativ content:cobranc content:inscrica content:divid content:ana content:reencaminh content:enac content:chang content:jalil",\n    "parsedquery_toString":"content:atenca content:setor content:pgf content:agu content:disposica content:demal content:encaminhament content:apreciaca content:senhor content:esclareciment content:equip content:procurador content:atualizad content:stel content:colocam content:fizerem content:ativ content:cobranc content:inscrica content:divid content:ana content:reencaminh content:enac content:chang content:jalil",\n    "explain":{}}}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/mlt",
    "params": {'q': 'id_document:1596887', 'debug_query': 'on', 'wt': 'json', 'mlt.interesting_terms': 'details', 'rows': 0, 'fl': 'id_document,score,id_type_document', 'mlt.mindf': 1, 'mlt.mintf': 1},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":4},\n  "match":{"numFound":1,"start":0,"maxScore":5.597987,"numFoundExact":true,"docs":[\n      {\n        "id_document":"1596887",\n        "id_type_document":"11",\n        "score":5.597987}]\n  },\n  "response":{"numFound":179867,"start":0,"maxScore":36.05705,"numFoundExact":true,"docs":[]\n  },\n  "interesting_terms":[\n    "content:respond",1.0,\n    "content:interpost",1.0,\n    "content:administrativ",1.0,\n    "content:proferid",1.0,\n    "content:nº",1.0,\n    "content:centr",1.0,\n    "content:sp",1.0,\n    "content:competent",1.0,\n    "content:despach",1.0,\n    "content:anex",1.0,\n    "content:referenci",1.0,\n    "content:voss",1.0,\n    "content:autoridad",1.0,\n    "content:senhori",1.0,\n    "content:teor",1.0,\n    "content:senhor",1.0,\n    "content:notificam",1.0,\n    "content:recurs",1.0,\n    "content:analisar",1.0,\n    "content:inteir",1.0,\n    "content:rodrig",1.0,\n    "content:coronel",1.0,\n    "content:marcelin",1.0,\n    "content:lobat",1.0,\n    "content:paraibun",1.0],\n  "debug":{\n    "rawquerystring":"id_document:1596887",\n    "querystring":"id_document:1596887",\n    "parsedquery":"content:respond content:interpost content:administrativ content:proferid content:nº content:centr content:sp content:competent content:despach content:anex content:referenci content:voss content:autoridad content:senhori content:teor content:senhor content:notificam content:recurs content:analisar content:inteir content:rodrig content:coronel content:marcelin content:lobat content:paraibun",\n    "parsedquery_toString":"content:respond content:interpost content:administrativ content:proferid content:nº content:centr content:sp content:competent content:despach content:anex content:referenci content:voss content:autoridad content:senhori content:teor content:senhor content:notificam content:recurs content:analisar content:inteir content:rodrig content:coronel content:marcelin content:lobat content:paraibun",\n    "explain":{}}}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/mlt",
    "params": {'q': 'id_document:1234567', 'debug_query': 'on', 'wt': 'json', 'mlt.interesting_terms': 'details', 'rows': 0, 'fl': 'id_document,score,id_type_document', 'mlt.mindf': 1, 'mlt.mintf': 1},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":4},\n  "match":{"numFound":1,"start":0,"maxScore":5.597987,"numFoundExact":true,"docs":[\n      {\n        "id_document":"1234567",\n        "id_type_document":"11",\n        "score":5.597987}]\n  },\n  "response":{"numFound":179867,"start":0,"maxScore":36.05705,"numFoundExact":true,"docs":[]\n  },\n  "interesting_terms":[\n    "content:suspensa",1.0],\n  "debug":{\n    "rawquerystring":"id_document:1234567",\n    "querystring":"id_document:1234567",\n    "parsedquery":"content:suspensa",\n    "explain":{}}}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'fl': 'id_document,content', 'q.op': 'OR', 'q': 'id_document:(3256530 1596887)'},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"id_document:(3256530 1596887)",\n      "fl":"id_document,content",\n      "q.op":"OR"}},\n  "response":{"numFound":2,"start":0,"numFoundExact":true,"docs":[\n      {\n        "id_document":"1596887",\n        "content":"ao senhor rodrigo lobato rua coronel marcelino, 197 - centro cep: 12260-000 - paraibuna/sp assunto: recurso administrativo referência: caso responda este ofício, indicar expressamente o processo nº 53504.010968/2012-81. prezado senhor, notificamos vossa senhoria do inteiro teor do despacho proferido pela autoridade competente (cópia anexa) ao analisar o recurso administrativo interposto nos autos do processo em referência. atenciosamente, anexos: i - despacho decisório nº 8997, de 8 de julho de 2015(sei nº 1342488) "},\n      {\n        "id_document":"3256530",\n        "content":"à senhora ana jalis chang procuradora federal equipe nacional de cobrança - enac setor de inscrição em dívida ativa - anatel assunto: encaminhamento de processo administrativo. senhora procuradora, em atenção ao despacho nº 00473/2018/da-anatel/enac/pgf/agu, informamos que o endereço do interessado foi atualizado no stel. dessa forma, reencaminha-se o processo para apreciação e análise com vistas à inscrição da entidade em dívida ativa e demais procedimentos de cobrança. colocamo-nos à disposição para esclarecimentos se fizerem necessários. atenciosamente, "}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'fl': 'id_document,content', 'q.op': 'OR', 'q': 'id_document:(1234567)'},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"id_document:(1234567)",\n      "fl":"id_document,content",\n      "q.op":"OR"}},\n  "response":{"numFound":2,"start":0,"numFoundExact":true,"docs":[\n      {\n        "id_document":"1234567",\n        "content":"suspensão "}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select?q=content:*&rows=0",
    "params":{},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"content:*",\n      "rows":"0"}},\n  "response":{"numFound":184741,"start":0,"numFoundExact":true,"docs":[]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select?q=*:*&fl=sumtotaltermfreq(content)&rows=1",
    "params":{},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"*:*",\n      "fl":"sumtotaltermfreq(content)",\n      "rows":"1"}},\n  "response":{"numFound":334241,"start":0,"numFoundExact":true,"docs":[\n      {\n        "sumtotaltermfreq(content)":67974685}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params":{},
    "payload": {'params': {'fl': "docfreq(content,'atenca'),docfreq(content,'setor'),docfreq(content,'pgf'),docfreq(content,'agu'),docfreq(content,'disposica'),docfreq(content,'demal'),docfreq(content,'encaminhament'),docfreq(content,'apreciaca'),docfreq(content,'senhor'),docfreq(content,'esclareciment'),docfreq(content,'equip'),docfreq(content,'procurador'),docfreq(content,'atualizad'),docfreq(content,'stel'),docfreq(content,'colocam'),docfreq(content,'fizerem'),docfreq(content,'ativ'),docfreq(content,'cobranc'),docfreq(content,'inscrica'),docfreq(content,'divid'),docfreq(content,'ana'),docfreq(content,'reencaminh'),docfreq(content,'enac'),docfreq(content,'chang'),docfreq(content,'jalil'),docfreq(content,'respond'),docfreq(content,'interpost'),docfreq(content,'administrativ'),docfreq(content,'proferid'),docfreq(content,'nº'),docfreq(content,'centr'),docfreq(content,'sp'),docfreq(content,'competent'),docfreq(content,'despach'),docfreq(content,'anex'),docfreq(content,'referenci'),docfreq(content,'voss'),docfreq(content,'autoridad'),docfreq(content,'senhori'),docfreq(content,'teor'),docfreq(content,'senhor'),docfreq(content,'notificam'),docfreq(content,'recurs'),docfreq(content,'analisar'),docfreq(content,'inteir'),docfreq(content,'rodrig'),docfreq(content,'coronel'),docfreq(content,'marcelin'),docfreq(content,'lobat'),docfreq(content,'paraibun'),docfreq(content,'obrigaca'),docfreq(content,'pado'),docfreq(content,'descumpriment')", 'rows': 1, 'q': '*:*'}},
    "text": '{\n  "responseHeader":{\n    "status":0,\n    "QTime":58,\n    "params":{\n      "json":"{\\"params\\": {\\"fl\\": \\"docfreq(content,\'atenca\'),docfreq(content,\'setor\'),docfreq(content,\'pgf\'),docfreq(content,\'agu\'),docfreq(content,\'disposica\'),docfreq(content,\'demal\'),docfreq(content,\'encaminhament\'),docfreq(content,\'apreciaca\'),docfreq(content,\'senhor\'),docfreq(content,\'esclareciment\'),docfreq(content,\'equip\'),docfreq(content,\'procurador\'),docfreq(content,\'atualizad\'),docfreq(content,\'stel\'),docfreq(content,\'colocam\'),docfreq(content,\'fizerem\'),docfreq(content,\'ativ\'),docfreq(content,\'cobranc\'),docfreq(content,\'inscrica\'),docfreq(content,\'divid\'),docfreq(content,\'ana\'),docfreq(content,\'reencaminh\'),docfreq(content,\'enac\'),docfreq(content,\'chang\'),docfreq(content,\'jalil\'),docfreq(content,\'respond\'),docfreq(content,\'interpost\'),docfreq(content,\'administrativ\'),docfreq(content,\'proferid\'),docfreq(content,\'n\\\\u00ba\'),docfreq(content,\'centr\'),docfreq(content,\'sp\'),docfreq(content,\'competent\'),docfreq(content,\'despach\'),docfreq(content,\'anex\'),docfreq(content,\'referenci\'),docfreq(content,\'voss\'),docfreq(content,\'autoridad\'),docfreq(content,\'senhori\'),docfreq(content,\'teor\'),docfreq(content,\'senhor\'),docfreq(content,\'notificam\'),docfreq(content,\'recurs\'),docfreq(content,\'analisar\'),docfreq(content,\'inteir\'),docfreq(content,\'rodrig\'),docfreq(content,\'coronel\'),docfreq(content,\'marcelin\'),docfreq(content,\'lobat\'),docfreq(content,\'paraibun\'),docfreq(content,\'obrigaca\'),docfreq(content,\'pado\'),docfreq(content,\'descumpriment\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"}}"}},\n  "response":{"numFound":334241,"start":0,"numFoundExact":true,"docs":[\n      {\n        "docfreq(content,\'atenca\')":25704,\n        "docfreq(content,\'setor\')":21950,\n        "docfreq(content,\'pgf\')":19237,\n        "docfreq(content,\'agu\')":16512,\n        "docfreq(content,\'disposica\')":15579,\n        "docfreq(content,\'demal\')":14934,\n        "docfreq(content,\'encaminhament\')":11257,\n        "docfreq(content,\'apreciaca\')":8183,\n        "docfreq(content,\'senhor\')":62983,\n        "docfreq(content,\'esclareciment\')":7712,\n        "docfreq(content,\'equip\')":6951,\n        "docfreq(content,\'procurador\')":42245,\n        "docfreq(content,\'atualizad\')":3135,\n        "docfreq(content,\'stel\')":1679,\n        "docfreq(content,\'colocam\')":1386,\n        "docfreq(content,\'fizerem\')":846,\n        "docfreq(content,\'ativ\')":19205,\n        "docfreq(content,\'cobranc\')":19095,\n        "docfreq(content,\'inscrica\')":18968,\n        "docfreq(content,\'divid\')":18028,\n        "docfreq(content,\'ana\')":614,\n        "docfreq(content,\'reencaminh\')":36,\n        "docfreq(content,\'enac\')":3822,\n        "docfreq(content,\'chang\')":26,\n        "docfreq(content,\'jalil\')":21,\n        "docfreq(content,\'respond\')":31758,\n        "docfreq(content,\'interpost\')":24445,\n        "docfreq(content,\'administrativ\')":105409,\n        "docfreq(content,\'proferid\')":21520,\n        "docfreq(content,\'nº\')":173716,\n        "docfreq(content,\'centr\')":18632,\n        "docfreq(content,\'sp\')":15688,\n        "docfreq(content,\'competent\')":14597,\n        "docfreq(content,\'despach\')":83199,\n        "docfreq(content,\'anex\')":78755,\n        "docfreq(content,\'referenci\')":77218,\n        "docfreq(content,\'voss\')":10667,\n        "docfreq(content,\'autoridad\')":10222,\n        "docfreq(content,\'senhori\')":9798,\n        "docfreq(content,\'teor\')":8910,\n        "docfreq(content,\'notificam\')":7645,\n        "docfreq(content,\'recurs\')":56633,\n        "docfreq(content,\'analisar\')":5087,\n        "docfreq(content,\'inteir\')":1923,\n        "docfreq(content,\'rodrig\')":1452,\n        "docfreq(content,\'coronel\')":849,\n        "docfreq(content,\'marcelin\')":176,\n        "docfreq(content,\'lobat\')":135,\n        "docfreq(content,\'paraibun\')":16,\n        "docfreq(content,\'obrigaca\')":98373,\n        "docfreq(content,\'pado\')":103069,\n        "docfreq(content,\'descumpriment\')":85641}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params":{},
    "payload": {'params': {'fl': "docfreq(content,'atenca'),docfreq(content,'setor'),docfreq(content,'pgf'),docfreq(content,'agu'),docfreq(content,'disposica'),docfreq(content,'demal'),docfreq(content,'encaminhament'),docfreq(content,'apreciaca'),docfreq(content,'senhor'),docfreq(content,'esclareciment'),docfreq(content,'equip'),docfreq(content,'procurador'),docfreq(content,'atualizad'),docfreq(content,'stel'),docfreq(content,'colocam'),docfreq(content,'fizerem'),docfreq(content,'ativ'),docfreq(content,'cobranc'),docfreq(content,'inscrica'),docfreq(content,'divid'),docfreq(content,'ana'),docfreq(content,'reencaminh'),docfreq(content,'enac'),docfreq(content,'chang'),docfreq(content,'jalil'),docfreq(content,'respond'),docfreq(content,'interpost'),docfreq(content,'administrativ'),docfreq(content,'proferid'),docfreq(content,'nº'),docfreq(content,'centr'),docfreq(content,'sp'),docfreq(content,'competent'),docfreq(content,'despach'),docfreq(content,'anex'),docfreq(content,'referenci'),docfreq(content,'voss'),docfreq(content,'autoridad'),docfreq(content,'senhori'),docfreq(content,'teor'),docfreq(content,'senhor'),docfreq(content,'notificam'),docfreq(content,'recurs'),docfreq(content,'analisar'),docfreq(content,'inteir'),docfreq(content,'rodrig'),docfreq(content,'coronel'),docfreq(content,'marcelin'),docfreq(content,'lobat'),docfreq(content,'paraibun')", 'rows': 1, 'q': '*:*'}},
    "text": '{\n  "responseHeader":{\n    "status":0,\n    "QTime":58,\n    "params":{\n      "json":"{\\"params\\": {\\"fl\\": \\"docfreq(content,\'atenca\'),docfreq(content,\'setor\'),docfreq(content,\'pgf\'),docfreq(content,\'agu\'),docfreq(content,\'disposica\'),docfreq(content,\'demal\'),docfreq(content,\'encaminhament\'),docfreq(content,\'apreciaca\'),docfreq(content,\'senhor\'),docfreq(content,\'esclareciment\'),docfreq(content,\'equip\'),docfreq(content,\'procurador\'),docfreq(content,\'atualizad\'),docfreq(content,\'stel\'),docfreq(content,\'colocam\'),docfreq(content,\'fizerem\'),docfreq(content,\'ativ\'),docfreq(content,\'cobranc\'),docfreq(content,\'inscrica\'),docfreq(content,\'divid\'),docfreq(content,\'ana\'),docfreq(content,\'reencaminh\'),docfreq(content,\'enac\'),docfreq(content,\'chang\'),docfreq(content,\'jalil\'),docfreq(content,\'respond\'),docfreq(content,\'interpost\'),docfreq(content,\'administrativ\'),docfreq(content,\'proferid\'),docfreq(content,\'n\\\\u00ba\'),docfreq(content,\'centr\'),docfreq(content,\'sp\'),docfreq(content,\'competent\'),docfreq(content,\'despach\'),docfreq(content,\'anex\'),docfreq(content,\'referenci\'),docfreq(content,\'voss\'),docfreq(content,\'autoridad\'),docfreq(content,\'senhori\'),docfreq(content,\'teor\'),docfreq(content,\'senhor\'),docfreq(content,\'notificam\'),docfreq(content,\'recurs\'),docfreq(content,\'analisar\'),docfreq(content,\'inteir\'),docfreq(content,\'rodrig\'),docfreq(content,\'coronel\'),docfreq(content,\'marcelin\'),docfreq(content,\'lobat\'),docfreq(content,\'paraibun\'),docfreq(content,\'obrigaca\'),docfreq(content,\'pado\'),docfreq(content,\'descumpriment\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"}}"}},\n  "response":{"numFound":334241,"start":0,"numFoundExact":true,"docs":[\n      {\n        "docfreq(content,\'atenca\')":25704,\n        "docfreq(content,\'setor\')":21950,\n        "docfreq(content,\'pgf\')":19237,\n        "docfreq(content,\'agu\')":16512,\n        "docfreq(content,\'disposica\')":15579,\n        "docfreq(content,\'demal\')":14934,\n        "docfreq(content,\'encaminhament\')":11257,\n        "docfreq(content,\'apreciaca\')":8183,\n        "docfreq(content,\'senhor\')":62983,\n        "docfreq(content,\'esclareciment\')":7712,\n        "docfreq(content,\'equip\')":6951,\n        "docfreq(content,\'procurador\')":42245,\n        "docfreq(content,\'atualizad\')":3135,\n        "docfreq(content,\'stel\')":1679,\n        "docfreq(content,\'colocam\')":1386,\n        "docfreq(content,\'fizerem\')":846,\n        "docfreq(content,\'ativ\')":19205,\n        "docfreq(content,\'cobranc\')":19095,\n        "docfreq(content,\'inscrica\')":18968,\n        "docfreq(content,\'divid\')":18028,\n        "docfreq(content,\'ana\')":614,\n        "docfreq(content,\'reencaminh\')":36,\n        "docfreq(content,\'enac\')":3822,\n        "docfreq(content,\'chang\')":26,\n        "docfreq(content,\'jalil\')":21,\n        "docfreq(content,\'respond\')":31758,\n        "docfreq(content,\'interpost\')":24445,\n        "docfreq(content,\'administrativ\')":105409,\n        "docfreq(content,\'proferid\')":21520,\n        "docfreq(content,\'nº\')":173716,\n        "docfreq(content,\'centr\')":18632,\n        "docfreq(content,\'sp\')":15688,\n        "docfreq(content,\'competent\')":14597,\n        "docfreq(content,\'despach\')":83199,\n        "docfreq(content,\'anex\')":78755,\n        "docfreq(content,\'referenci\')":77218,\n        "docfreq(content,\'voss\')":10667,\n        "docfreq(content,\'autoridad\')":10222,\n        "docfreq(content,\'senhori\')":9798,\n        "docfreq(content,\'teor\')":8910,\n        "docfreq(content,\'notificam\')":7645,\n        "docfreq(content,\'recurs\')":56633,\n        "docfreq(content,\'analisar\')":5087,\n        "docfreq(content,\'inteir\')":1923,\n        "docfreq(content,\'rodrig\')":1452,\n        "docfreq(content,\'coronel\')":849,\n        "docfreq(content,\'marcelin\')":176,\n        "docfreq(content,\'lobat\')":135,\n        "docfreq(content,\'paraibun\')":16}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params":{},
    "payload": {'params': {'fl': "docfreq(content,'suspensa'),docfreq(content,'pado')", 'rows': 1, 'q': '*:*'}},
    "text": '{\n  "responseHeader":{\n    "status":0,\n    "QTime":58,\n    "params":{\n      "json":"{\\"params\\": {\\"fl\\": \\"docfreq(content,\'suspensa\'),docfreq(content,\'pado\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"}}"}},\n  "response":{"numFound":334241,"start":0,"numFoundExact":true,"docs":[\n      {\n        "docfreq(content,\'suspensa\')":10425,\n        "docfreq(content,\'pado\')":103069}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'q': 'content:atenca^0.5000 content:setor^0.5000 content:pgf^0.5000 content:agu^0.5000 content:disposica^0.5000 content:demal^0.5000 content:encaminhament^0.5000 content:apreciaca^0.5000 content:senhor^0.5000 content:esclareciment^0.5000 content:equip^0.5000 content:procurador^0.5000 content:atualizad^0.5000 content:stel^0.5000 content:colocam^0.5000 content:fizerem^0.5000 content:ativ^0.5000 content:cobranc^0.5000 content:inscrica^0.5000 content:divid^0.5000 content:ana^0.5000 content:reencaminh^0.5000 content:enac^0.5000 content:chang^0.5000 content:jalil^0.5000 content:respond^0.5000 content:interpost^0.5000 content:administrativ^0.5000 content:proferid^0.5000 content:nº^0.5000 content:centr^0.5000 content:sp^0.5000 content:competent^0.5000 content:despach^0.5000 content:anex^0.5000 content:referenci^0.5000 content:voss^0.5000 content:autoridad^0.5000 content:senhori^0.5000 content:teor^0.5000 content:senhor^0.5000 content:notificam^0.5000 content:recurs^0.5000 content:analisar^0.5000 content:inteir^0.5000 content:rodrig^0.5000 content:coronel^0.5000 content:marcelin^0.5000 content:lobat^0.5000 content:paraibun^0.5000 content:obrigaca^0.5000 content:pado^0.5000 content:descumpriment^0.5000', 'fl': 'id_document,score,id_type_document', 'fq': 'id_type_document:( 7 8 94 ) AND id_document:* AND -id_document:( 1596887 3256530 )', 'rows': '1'},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":79,\n    "params":{\n      "q":"content:atenca^0.5000 content:setor^0.5000 content:pgf^0.5000 content:agu^0.5000 content:disposica^0.5000 content:demal^0.5000 content:encaminhament^0.5000 content:apreciaca^0.5000 content:senhor^0.5000 content:esclareciment^0.5000 content:equip^0.5000 content:procurador^0.5000 content:atualizad^0.5000 content:stel^0.5000 content:colocam^0.5000 content:fizerem^0.5000 content:ativ^0.5000 content:cobranc^0.5000 content:inscrica^0.5000 content:divid^0.5000 content:ana^0.5000 content:reencaminh^0.5000 content:enac^0.5000 content:chang^0.5000 content:jalil^0.5000 content:respond^0.5000 content:interpost^0.5000 content:administrativ^0.5000 content:proferid^0.5000 content:nº^0.5000 content:centr^0.5000 content:sp^0.5000 content:competent^0.5000 content:despach^0.5000 content:anex^0.5000 content:referenci^0.5000 content:voss^0.5000 content:autoridad^0.5000 content:senhori^0.5000 content:teor^0.5000 content:senhor^0.5000 content:notificam^0.5000 content:recurs^0.5000 content:analisar^0.5000 content:inteir^0.5000 content:rodrig^0.5000 content:coronel^0.5000 content:marcelin^0.5000 content:lobat^0.5000 content:paraibun^0.5000 content:obrigaca^0.5000 content:pado^0.5000 content:descumpriment^0.5000",\n      "fl":"id_document,score,id_type_document",\n      "fq":"id_type_document:( 7 8 94 ) AND id_document:* AND -id_document:( 1596887 3256530 )",\n      "rows":"1"}},\n  "response":{"numFound":5630,"start":0,"maxScore":10.106607,"numFoundExact":true,"docs":[\n      {\n        "id_document":"9461606",\n        "id_type_document":"7",\n        "score":10.106607}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'q': 'content:pado^0.5000 content:suspensa^0.5000', 'fl': 'id_document,score,id_type_document', 'fq': 'id_type_document:( 7 8 94 ) AND id_document:* AND -id_document:( 1234567 )', 'rows': '1'},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":79,\n    "params":{\n      "q":"content:pado^0.5000 content:suspensa^0.5000",\n      "fl":"id_document,score,id_type_document",\n      "fq":"id_type_document:( 7 8 94 ) AND id_document:* AND -id_document:( 1234567 )",\n      "rows":"1"}},\n  "response":{"numFound":5630,"start":0,"maxScore":10.106607,"numFoundExact":true,"docs":[\n      {\n        "id_document":"9461606",\n        "id_type_document":"7",\n        "score":10.106607}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'q': 'content:atenca content:setor content:pgf content:agu content:disposica content:demal content:encaminhament content:apreciaca content:senhor content:esclareciment content:equip content:procurador content:atualizad content:stel content:colocam content:fizerem content:ativ content:cobranc content:inscrica content:divid content:ana content:reencaminh content:enac content:chang content:jalil content:respond content:interpost content:administrativ content:proferid content:nº content:centr content:sp content:competent content:despach content:anex content:referenci content:voss content:autoridad content:senhori content:teor content:senhor content:notificam content:recurs content:analisar content:inteir content:rodrig content:coronel content:marcelin content:lobat content:paraibun', 'fl': 'id_document,score,id_type_document', 'fq': 'id_type_document:( 7 8 94 ) AND id_document:( string ) AND -id_document:( 1596887 3256530 )', 'rows': '1'},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":1,\n    "params":{\n      "q":"content:atenca content:setor content:pgf content:agu content:disposica content:demal content:encaminhament content:apreciaca content:senhor content:esclareciment content:equip content:procurador content:atualizad content:stel content:colocam content:fizerem content:ativ content:cobranc content:inscrica content:divid content:ana content:reencaminh content:enac content:chang content:jalil content:respond content:interpost content:administrativ content:proferid content:nº content:centr content:sp content:competent content:despach content:anex content:referenci content:voss content:autoridad content:senhori content:teor content:senhor content:notificam content:recurs content:analisar content:inteir content:rodrig content:coronel content:marcelin content:lobat content:paraibun",\n      "fl":"id_document,score,id_type_document",\n      "fq":"id_type_document:( 7 8 94 ) AND id_document:( string ) AND -id_document:( 1596887 3256530 )",\n      "rows":"1"}},\n  "response":{"numFound":0,"start":0,"maxScore":0.0,"numFoundExact":true,"docs":[]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select?q=content:*&rows=0",
    "params": {},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"content:*",\n      "rows":"0"}},\n  "response":{"numFound":184741,"start":0,"numFoundExact":true,"docs":[]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select?q=*:*&fl=sumtotaltermfreq(content)&rows=1",
    "params": {},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"*:*",\n      "fl":"sumtotaltermfreq(content)",\n      "rows":"1"}},\n  "response":{"numFound":334241,"start":0,"numFoundExact":true,"docs":[\n      {\n        "sumtotaltermfreq(content)":67974685}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {},
    "payload": {'params': {'fl': "docfreq(content,'pado')", 'rows': 1, 'q': '*:*'}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "json":"{\\"params\\": {\\"fl\\": \\"docfreq(content,\'pado\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"}}"}},\n  "response":{"numFound":334241,"start":0,"numFoundExact":true,"docs":[\n      {\n        "docfreq(content,\'pado\')":103069}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'q': 'content:pado', 'fl': 'id_document,score,id_type_document', 'fq': 'id_type_document:( 7 8 94 ) AND id_document:( 6783080 )', 'rows': '1'},
    "payload": {"params":{}},
    "text": '{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"content:pado",\n      "fl":"id_document,score,id_type_document",\n      "fq":"id_type_document:( 7 8 94 ) AND id_document:( 6783080 )",\n      "rows":"1"}},\n  "response":{"numFound":1,"start":0,"maxScore":0.516033,"numFoundExact":true,"docs":[\n      {\n        "id_document":"6783080",\n        "id_type_document":"7",\n        "score":0.516033}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select?q=content:*&rows=0",
    "params": {},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"content:*",\n      "rows":"0"}},\n  "response":{"numFound":184741,"start":0,"numFoundExact":true,"docs":[]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select?q=*:*&fl=sumtotaltermfreq(content)&rows=1",
    "params": {},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "q":"*:*",\n      "fl":"sumtotaltermfreq(content)",\n      "rows":"1"}},\n  "response":{"numFound":334241,"start":0,"numFoundExact":true,"docs":[\n      {\n        "sumtotaltermfreq(content)":67974685}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {},
    "payload": {'params': {'fl': "docfreq(content,'suspensa')", 'rows': 1, 'q': '*:*'}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":0,\n    "params":{\n      "json":"{\\"params\\": {\\"fl\\": \\"docfreq(content,\'suspensa\')\\", \\"rows\\": 1, \\"q\\": \\"*:*\\"}}"}},\n  "response":{"numFound":334241,"start":0,"numFoundExact":true,"docs":[\n      {\n        "docfreq(content,\'suspensa\')":10425}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'q': 'content:suspensa', 'fl': 'id_document,score,id_type_document', 'fq': 'id_type_document:( 7 8 94 ) AND id_document:( 6783080 )', 'rows': '1'},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":1,\n    "params":{\n      "q":"content:suspensa",\n      "fl":"id_document,score,id_type_document",\n      "fq":"id_type_document:( 7 8 94 ) AND id_document:( 6783080 )",\n      "rows":"1"}},\n  "response":{"numFound":1,"start":0,"maxScore":0.6667254,"numFoundExact":true,"docs":[\n      {\n        "id_document":"6783080",\n        "id_type_document":"7",\n        "score":0.6667254}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'fl': 'id_document,score,id_type_document', 'fq': 'id_type_document:( 7 8 94 ) AND id_document:( 6783080 ) AND -id_document:( 1234567 )', 'q': 'content:suspensa^0.5000 content:pado^0.5000', 'rows': '1'},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":1,\n    "params":{\n      "q":"content:suspensa^0.5000 content:pado^0.5000",\n      "fl":"id_document,score,id_type_document",\n      "fq":"id_type_document:( 7 8 94 ) AND id_document:( 6783080 )",\n      "rows":"1"}},\n  "response":{"numFound":1,"start":0,"maxScore":0.59137917,"numFoundExact":true,"docs":[\n      {\n        "id_document":"6783080",\n        "id_type_document":"7",\n        "score":0.59137917}]\n  }}\n'
},
{
    "status_code":200,
    "url":"http://fakehost:0000/solr/documentos_bm25/select",
    "params": {'fl': 'id_document,score,id_type_document', 'fq': 'id_type_document:( 7 8 94 ) AND id_document:( 6783080 ) AND -id_document:( 1234567 )', 'q': 'content:suspensa^0.9000 content:pado^0.1000', 'rows': '1'},
    "payload": {"params":{}},
    "text":'{\n  "responseHeader":{\n    "status":0,\n    "QTime":1,\n    "params":{\n      "q":"content:suspensa^0.9000 content:pado^0.1000",\n      "fl":"id_document,score,id_type_document",\n      "fq":"id_type_document:( 7 8 94 ) AND id_document:( 6783080 )",\n      "rows":"1"}},\n  "response":{"numFound":1,"start":0,"maxScore":0.65165627,"numFoundExact":true,"docs":[\n      {\n        "id_document":"6783080",\n        "id_type_document":"7",\n        "score":0.65165627}]\n  }}\n'
}]


class MockResponse:

    def __init__(self,text,status_code):
        self.text = text
        self.status_code = status_code

    def json(self):
        return json.loads(self.text)


def compare_params(params1,params2):
    for k in params2.keys():
        if k == "q":
            v = params1.get("q")
            if v:
                cond = (set(v.split()) == set(params2["q"].split()))
            else:
                cond = False
        elif k == "fl":
            v = params1.get("fl")
            if v:
                cond = (set(v.split(",")) == set(params2["fl"].split(",")))
            else:
                cond = False
        else:
            cond = (params1.get(k) == params2[k])
        if not cond:
            return False
    return True


def mock_requests_post(url, json, timeout):
    matches = [obj for obj in SOLR_RESPONSES if (obj["url"]==url and compare_params(obj["payload"]["params"],json["params"]))]
    return MockResponse(matches[0]["text"], matches[0]["status_code"])


def mock_requests_get(url,**kwargs):
    params = kwargs.get("params")
    if not params:
        i = ([obj["url"] for obj in SOLR_RESPONSES]).index(url)
        return MockResponse(SOLR_RESPONSES[i]["text"], SOLR_RESPONSES[i]["status_code"])
    else:
        matches = [obj for obj in SOLR_RESPONSES if (obj["url"]==url and compare_params(obj["params"],params))]
        return MockResponse(matches[0]["text"], matches[0]["status_code"])

