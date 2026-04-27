from unittest.mock import patch

import numpy as np
import pymysql
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from mock_solr import mock_requests_get, mock_requests_post

from api_sei.db_models.get_content_lazy import get_proc_content_lazy
from api_sei.db_models.jurisprudence import SolrJurisprudence
from api_sei.main import app
from api_sei.pydantic_models.jurisprudence import FoundIdsDocs
from api_sei.resources.bm25 import bm25_tfidf
from api_sei.services.jurisprudence import doc2doc_search

client = TestClient(app)


@pytest.mark.parametrize("list_id_doc",[[111111],[]])
@patch('api_sei.db_models.jurisprudence.BASE_URL_JURISPRUDENCE_MLT',"http://fakehost:0000/solr/documentos_bm25/mlt")
@patch('api_sei.db_models.jurisprudence.BASE_URL_JURISPRUDENCE_SELECT',"http://fakehost:0000/solr/documentos_bm25/select")
@patch('api_sei.services.jurisprudence.get_tokenized_docs')
@patch('api_sei.db_models.solr_select.requests.get',mock_requests_get)
def test_doc2doc_search_no_parsedquery(mock_get_tokenized_docs,list_id_doc):

    mock_get_tokenized_docs.return_value = []    

    test_data = {
        "text": "",
        "list_id_doc": list_id_doc,
        "list_type_id_doc": [7, 8, 94],
        "rows": 1,
        "id_user": 1234
    }

    response = client.get(
        "/document-recommenders/mlt-recommender/recommendations",
        params=test_data,
    )

    assert response.status_code == 400

    response_json = response.json()

    assert response_json["detail"] == "Os documentos selecionados estão vazios." if len(list_id_doc) else \
        "list_id_doc ou text não podem ser ambos vazios"


@pytest.mark.parametrize("list_id_doc",[[111111],[]])
@patch('api_sei.db_models.jurisprudence.BASE_URL_JURISPRUDENCE_MLT',"http://fakehost:0000/solr/documentos_bm25/mlt")
@patch('api_sei.db_models.jurisprudence.BASE_URL_JURISPRUDENCE_SELECT',"http://fakehost:0000/solr/documentos_bm25/select")
@patch('api_sei.services.jurisprudence.get_tokenized_docs')
@patch('api_sei.db_models.solr_select.requests.get',mock_requests_get)
def test_doc2doc_search_only_text(mock_get_tokenized_docs,list_id_doc):

    mock_get_tokenized_docs.return_value = []    

    test_data = {
        "text": "sample text",
        "list_id_doc": list_id_doc,
        "list_type_id_doc": [7, 8, 94],
        "rows": 1,
        "id_user": 1234
    }

    response = client.get(
        "/document-recommenders/mlt-recommender/recommendations",
        params=test_data,
    )

    assert response.status_code == 200

    response_json = response.json()

    assert response_json["recommendation"][0] == {'id_document': '5743209', 'id_type_document': '94', 'score': 3.4837906}

# pado descumprimento de obrigação

# 1596887
# "ao senhor rodrigo lobato rua coronel marcelino, 197 - centro cep: 12260-000 - paraibuna/sp assunto: recurso administrativo referência: caso responda este ofício, indicar expressamente o processo nº 53504.010968/2012-81. prezado senhor, notificamos vossa senhoria do inteiro teor do despacho proferido pela autoridade competente (cópia anexa) ao analisar o recurso administrativo interposto nos autos do processo em referência. atenciosamente, anexos: i - despacho decisório nº 8997, de 8 de julho de 2015(sei nº 1342488) "

# 3256530
# "à senhora ana jalis chang procuradora federal equipe nacional de cobrança - enac setor de inscrição em dívida ativa - anatel assunto: encaminhamento de processo administrativo. senhora procuradora, em atenção ao despacho nº 00473/2018/da-anatel/enac/pgf/agu, informamos que o endereço do interessado foi atualizado no stel. dessa forma, reencaminha-se o processo para apreciação e análise com vistas à inscrição da entidade em dívida ativa e demais procedimentos de cobrança. colocamo-nos à disposição para esclarecimentos se fizerem necessários. atenciosamente, "

@patch('api_sei.services.jurisprudence.BASE_URL_JURISPRUDENCE',"http://fakehost:0000/solr/documentos_bm25")
@patch('api_sei.db_models.jurisprudence.BASE_URL_JURISPRUDENCE_MLT',"http://fakehost:0000/solr/documentos_bm25/mlt")
@patch('api_sei.db_models.jurisprudence.BASE_URL_JURISPRUDENCE_SELECT',"http://fakehost:0000/solr/documentos_bm25/select")
@patch('api_sei.db_models.solr_select.requests.get',mock_requests_get)
@patch('api_sei.db_models.solr_select.requests.post',mock_requests_post)
def test_doc2doc_search_complete():

    test_data = {
        "text": "pado descumprimento de obrigação",
        "list_id_doc": [1596887, 3256530],
        "list_type_id_doc": [7, 8, 94],
        "rows": 1,
        "normalized": True,
        "id_user": 1234
    }

    response = client.get(
        "/document-recommenders/mlt-recommender/recommendations",
        params=test_data,
    )

    assert response.status_code == 200

    response_json = response.json()

    assert response_json["recommendation"][0] == {'id_document': '9461606', 'id_type_document': '7', 'score': 0.1905835201394886}


@pytest.mark.parametrize("text",["","sample text"])
@pytest.mark.parametrize("list_id_doc",[[1596887, 3256530],[]])
@patch('api_sei.db_models.jurisprudence.BASE_URL_JURISPRUDENCE_MLT',"http://fakehost:0000/solr/documentos_bm25/mlt")
@patch('api_sei.db_models.jurisprudence.BASE_URL_JURISPRUDENCE_SELECT',"http://fakehost:0000/solr/documentos_bm25/select")
@patch('api_sei.db_models.solr_select.requests.get',mock_requests_get)
@patch('api_sei.services.jurisprudence.get_tokenized_docs')
@patch('api_sei.services.jurisprudence.solr_jurisprudence')
def test_doc2doc_search_text_weight(mock_solr_jurisprudence,mock_get_tokenized_docs,list_id_doc,text):

    mock_solr_jurisprudence.check_has_id_documents = SolrJurisprudence().check_has_id_documents
    
    mock_solr_jurisprudence.get_solr_using_debug_query = SolrJurisprudence().get_solr_using_debug_query

    mock_get_tokenized_docs.return_value = []    

    doc2doc_search(
        list_id_doc=list_id_doc,
        list_type_id_doc=[7,8,94],
        rows=1,
        text=text,
        include_citations=False,
        text_weight=0.4,
        normalized=False, 
        fq=None,
        id_user=1234)

    args,kwargs = mock_solr_jurisprudence.get_solr_parsedquery.call_args

    text_parsedquery = "content:sampl content:text"

    docs_parsedquery = "content:atenca content:setor content:pgf content:agu content:disposica content:demal content:encaminhament content:apreciaca content:senhor content:esclareciment content:equip content:procurador content:atualizad content:stel content:colocam content:fizerem content:ativ content:cobranc content:inscrica content:divid content:ana content:reencaminh content:enac content:chang content:jalil content:respond content:interpost content:administrativ content:proferid content:nº content:centr content:sp content:competent content:despach content:anex content:referenci content:voss content:autoridad content:senhori content:teor content:senhor content:notificam content:recurs content:analisar content:inteir content:rodrig content:coronel content:marcelin content:lobat content:paraibun"

    # print(kwargs["parsedquery"])

    if text == "" and list_id_doc == []:
        expected_parsedquery = ""
    elif text == "" and list_id_doc != []:
        expected_parsedquery = docs_parsedquery
    elif text != "" and list_id_doc == []:
        expected_parsedquery = text_parsedquery
    elif text != "" and list_id_doc != []:
        expected_parsedquery = "^0.4000 ".join(text_parsedquery.split()) + "^0.4000 " + "^0.6000 ".join(docs_parsedquery.split())  + "^0.6000"

    assert set(kwargs["parsedquery"].split()) == set(expected_parsedquery.split())



@pytest.mark.parametrize("list_type_id_doc",[[],[7,8,94]])
@pytest.mark.parametrize("list_id_doc",[[111111],[]])
@pytest.mark.parametrize("fq",[None,[222222]])
@patch('api_sei.services.jurisprudence.solr_jurisprudence')
def test_doc2doc_search_service_fq(mock_solr_jurisprudence,fq,list_id_doc,list_type_id_doc):  

    mock_solr_jurisprudence.check_has_id_documents.return_value = FoundIdsDocs(
        id_docs_found=set(),id_docs_not_found=set())

    doc2doc_search(
        list_id_doc=list_id_doc,
        list_type_id_doc=list_type_id_doc,
        rows=1,
        text="",
        include_citations=False,
        text_weight=0.5,
        normalized=False, 
        fq=fq,
        id_user=1234)

    if list_id_doc != [] and list_type_id_doc == [] and fq is None:
        compound_fq="id_document:* AND -id_document:( 111111 )"
    elif list_id_doc != [] and list_type_id_doc == [] and fq is not None:
        compound_fq="id_document:( 222222 ) AND -id_document:( 111111 )"
    elif list_id_doc != [] and list_type_id_doc != [] and fq is None:
        compound_fq="id_type_document:( 7 8 94 ) AND id_document:* AND -id_document:( 111111 )"
    elif list_id_doc != [] and list_type_id_doc != [] and fq is not None:
        compound_fq="id_type_document:( 7 8 94 ) AND id_document:( 222222 ) AND -id_document:( 111111 )"
    elif list_id_doc == [] and list_type_id_doc == [] and fq is None:
        compound_fq="id_document:*"
    elif list_id_doc == [] and list_type_id_doc == [] and fq is not None:
        compound_fq="id_document:( 222222 )"
    elif list_id_doc == [] and list_type_id_doc != [] and fq is None:
        compound_fq="id_type_document:( 7 8 94 ) AND id_document:*"
    elif list_id_doc == [] and list_type_id_doc != [] and fq is not None:
        compound_fq="id_type_document:( 7 8 94 ) AND id_document:( 222222 )"

    mock_solr_jurisprudence.get_solr_parsedquery.assert_called_with(
        parsedquery="", rows=1, fq=compound_fq, normalize_value=1
    )

@pytest.mark.parametrize("text_weight",[0.5,0.1])
@pytest.mark.parametrize("normalized",[False,True])
@patch('api_sei.services.jurisprudence.BASE_URL_JURISPRUDENCE',"http://fakehost:0000/solr/documentos_bm25")
@patch('api_sei.db_models.jurisprudence.BASE_URL_JURISPRUDENCE_MLT',"http://fakehost:0000/solr/documentos_bm25/mlt")
@patch('api_sei.db_models.jurisprudence.BASE_URL_JURISPRUDENCE_SELECT',"http://fakehost:0000/solr/documentos_bm25/select")
@patch('api_sei.db_models.solr_select.requests.get',mock_requests_get)
@patch('api_sei.db_models.solr_select.requests.post',mock_requests_post)
def test_doc2doc_search_service_normalized(normalized,text_weight):  

    ret = doc2doc_search(
        list_id_doc=[1234567], # fake doc with content "suspensão "
        list_type_id_doc=[7,8,94],
        rows=1,
        text="pado",
        include_citations=False,
        text_weight=text_weight,
        normalized=normalized, 
        fq=[6783080],
        id_user=1234)
    
    N = 184741
    avgdl = 67974685/N
    pado_n = 103069
    pado_freq = 50 # frequência do token pado no documento 6783080
    dl = 2398 # comprimento do documento 6783080

    suspensa_n = 10425
    suspensa_freq = 2 # frequência do token suspensa no documento 6783080

    # pado_return_score,_ = bm25_tfidf(pado_n,N,pado_freq,dl,avgdl)
    pado_return_score = 0.516033
    suspensa_return_score = 0.6667254

    denormalized_score = text_weight * pado_return_score + (1-text_weight) * suspensa_return_score

    pado_ref_score,_ = bm25_tfidf(pado_n,N,1,2,avgdl)
    suspensa_ref_score,_ = bm25_tfidf(suspensa_n,N,1,2,avgdl)

    ref_score = text_weight * pado_ref_score + (1-text_weight) * suspensa_ref_score

    final_score = denormalized_score/ref_score if normalized else denormalized_score

    assert np.allclose(
        final_score,
        ret["recommendation"][0]["score"]
    )

def test_get_proc_content_lazy_raises_operational_error():
    with patch('api_sei.db_models.mysql.Mysql.connect') as mock_connect:
        mock_mysql_instance = Mysql("Nao existe", "Nao Existe")
        mock_mysql_instance.connect()  

        with pytest.raises(HTTPException):
            get_proc_content_lazy(123456)

        mock_connect.assert_called_once()

        with pytest.raises(pymysql.OperationalError) as exc_info:
            mock_mysql_instance.select(None)

        assert isinstance(exc_info.value, pymysql.OperationalError)
        assert "Banco relacional do SEI indisponivel" in str(exc_info.value)
