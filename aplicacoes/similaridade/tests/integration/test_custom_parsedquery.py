
import time
import math
import os
import unittest
from collections import Counter
from unittest import mock
import re
import numpy as np
import pandas as pd
import pytest
# from test_solr import delete_solr, setup_solr, populate_solr_core
from api_sei.resources.custom_parsedquery import FasterCustomParsedQuery
from api_sei.resources.bm25 import bm25_tfidf
from mock_solr import mock_requests_get




def find_weights(expression):
    return list(map(float, re.findall(r"\^([^\s]+)\s", " {} ".format(expression))))

DOCS = [
    {
        "id_protocolo":"422762",
        "protocolo_formatado":"53500029606201032",
        "metadata_name_id_type_process":"Regulamentação: Uso de Radiofrequências,Traz a destinação de faixa a um determinado serviço, com as respectivas condições técnicas de uso.",
        "metadata_name_id_type_process_tokens":["regulamentaca","uso","radiofrequenci","traz","destinaca","faix","determinad","servic","respectiv","condica","tecnic","uso"]
    },
    {
        "id_protocolo":"243264",
        "protocolo_formatado":"53500000801201676",
        "metadata_name_id_type_process":"PADO: Atendimento - SCM,",
        "metadata_name_id_type_process_tokens":["pado","atendiment","scm"]
    },
    {
        "id_protocolo":"7924921",
        "protocolo_formatado":"53500039847202142",
        "metadata_name_id_type_process":"Demanda Externa: Senador,Atender solicitações parlamentares, como pedidos de informação, consulta a processos, agenda com presidente ou demais gestores do Órgão e visita técnica.",
        "metadata_name_id_type_process_tokens":["demand","extern","senador","atender","solicitaca","parlamentar","pedid","informaca","consult","process","agend","president","gestor","orga","visit","tecnic"]
    },
    {
        "id_protocolo":"397413",
        "protocolo_formatado":"53500005769201615",
        "metadata_name_id_type_process":"Regulamentação: Proposição de Ato Normativo,Proposição de expedição ou alteração de ato normativo e de proposta de adequação legislativa.",
        "metadata_name_id_type_process_tokens":["regulamentaca","proposica","ato","normativ","proposica","expedica","alteraca","ato","normativ","propost","adequaca","legislativ"]
    },
    {
        "id_protocolo":"3839143",
        "protocolo_formatado":"53500046380201891",
        "metadata_name_id_type_process":"Regulamentação: Proposição de Ato Normativo,Proposição de expedição ou alteração de ato normativo e de proposta de adequação legislativa.",
        "metadata_name_id_type_process_tokens":["regulamentaca","proposica","ato","normativ","proposica","expedica","alteraca","ato","normativ","propost","adequaca","legislativ"]
    },
    {
        "id_protocolo":"433260",
        "protocolo_formatado":"53500006606201650",
        "metadata_name_id_type_process":"Universalização/Ampliação do Acesso: Estudos,Desenvolvimento de metodologias e análises econômico-financeiras para definir planos, programas e politicas públicas voltadas para universalização e ampliação do acesso.",
        "metadata_name_id_type_process_tokens":["universalizaca","ampliaca","acess","estud","desenvolviment","metodologi","analis","economic","financeir","definir","plan","program","politic","public","voltad","universalizaca","ampliaca","acess"]
    }
]

FIELDS = {"metadata_name_id_type_process":dict()}

for field in FIELDS.keys():

    for i in range(len(DOCS)):
        DOCS[i][f"{field}_termvector"] = dict(Counter(DOCS[i][f"{field}_tokens"]))
        DOCS[i][f"{field}_dl"] = len(DOCS[i][f"{field}_tokens"])

    FIELDS[field]["N"] = sum([bool(d.get(field)) for d in DOCS])
    FIELDS[field]["avgdl"] = sum([len(d[f"{field}_tokens"]) for d in DOCS])/FIELDS[field]["N"]
    FIELDS[field]["doc_freq"] = dict(Counter([t for d in DOCS for t in list(set(d[f"{field}_tokens"])) ]))


def search_score(query_terms_per_field,id_protocolo):

    i = [d["id_protocolo"] for d in DOCS].index(id_protocolo)

    scores = []
    debug_strs = []
    for f in query_terms_per_field.keys():
        for t in query_terms_per_field[f]:
            score,debug_str = bm25_tfidf(
                FIELDS[f]["doc_freq"][t],
                FIELDS[f]["N"],
                DOCS[i][f"{f}_termvector"][t],
                DOCS[i][f"{f}_dl"],
                FIELDS[f]["avgdl"]
            )
            scores.append(score)
            debug_strs.append(debug_str.format(f"{f}:{t}"))
    final_score = sum(scores)
    print("{} = sum of:".format(final_score))
    for dbgstr in debug_strs:
        print(dbgstr)

    return final_score


class TestCustomParsedQuery(unittest.TestCase):
    """test CustomParsedQuery"""

    # @classmethod
    # def setUpClass(cls):
    #     # Obs: é importante que seja criado um solr só para os testes desta classe, ou então que
    #     # os testes dessa classe sejam executados logo após a primeira carga inicial de dados no solr,
    #     # antes que sejam feitos quaisquer updates ou deletes de dados, porque updates e deletes 
    #     # vão afetar os valores de certas variáveis, como numdocs e docfreq, no solr.
    #     setup_solr([TEST_SOLR_PROCESS_CORE_NAME])
    #     solr_fields = ["protocolo_formatado","id_protocolo","metadata_name_id_type_process"]
    #     populate_solr_core([{k:v for k,v in d.items() if k in solr_fields} for d in DOCS],TEST_SOLR_PROCESS_CORE_NAME)


    # @classmethod
    # def tearDownClass(cls):
    #     delete_solr()

    @mock.patch(
        "api_sei.db_models.solr_select.requests.get", mock_requests_get
    )
    @mock.patch(
        'api_sei.resources.custom_parsedquery.SOLR_ADDRESS',
        "http://fakehost:0000"
    )
    @mock.patch(
        'api_sei.resources.custom_parsedquery.SOLR_MLT_PROCESS_CORE',
        "process"
    )
    @pytest.mark.integration
    def test_get_parsedquery(self):

        id_protocolo = "422762"
        parsedquery = FasterCustomParsedQuery(id_protocolo).get_parsedquery()
    
        compiled_regex = re.compile(r"metadata_name_id_type_process")
        parsedquery = ' '.join(list(filter(compiled_regex.search, parsedquery.split())))

        stored_weights = find_weights(parsedquery)
        
        i = [d["id_protocolo"] for d in DOCS].index(id_protocolo)
        metadata_name_id_type_process_query_terms = \
            list(set(DOCS[i]["metadata_name_id_type_process_tokens"]))[:25]
        query_terms_per_field = {
            "metadata_name_id_type_process": metadata_name_id_type_process_query_terms
        }
        self_score = search_score(query_terms_per_field,id_protocolo)

        expected_weights = [(0.3 * 0.5)/self_score]*len(metadata_name_id_type_process_query_terms)

        print("expected weight", expected_weights[0], "stored weight", stored_weights[0],)

        self.assertTrue(np.allclose(
            stored_weights,
            expected_weights
        ))

    @mock.patch(
        "api_sei.db_models.solr_select.requests.get", mock_requests_get
    )
    @mock.patch(
        'api_sei.resources.custom_parsedquery.SOLR_ADDRESS',
        "http://fakehost:0000"
    )
    @mock.patch(
        'api_sei.resources.custom_parsedquery.SOLR_MLT_PROCESS_CORE',
        "process"
    )
    @pytest.mark.integration
    def test_process_text_similarity_field_small_weight(self):

        initial_weight = 1e-8
        id_protocolo = "422762"
        field_name = "metadata_name_id_type_process"
        parsedquery = FasterCustomParsedQuery(id_protocolo).process_text_similarity_field(field_name,initial_weight)
        self.assertTrue("e-" not in parsedquery)



if __name__ == '__main__':

    unittest.main()