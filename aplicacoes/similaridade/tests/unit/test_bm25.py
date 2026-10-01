
import unittest
from unittest import mock
from api_sei.resources.bm25 import get_doc_score, bm25_tfidf
import numpy as np


class TestBM25(unittest.TestCase):

    @mock.patch("api_sei.resources.bm25.get_field_terms_statistics")
    def test_get_doc_score(self, mock_field_terms_statistics):

        doc = {"metadata_name_id_type_process":['pado', 'home', 'passed']}
        tokens_freq = {'pado': 1, 'home': 1, 'passed': 1}
        dl = 3

        parsedquery = "metadata_name_id_type_process:home metadata_name_id_type_process:passed metadata_name_id_type_process:pado"

        tokens_n = {'pado': 90, 'home': 8, 'passed': 8}
        N = 102
        avgdl = 3.156862745098039

        mock_field_terms_statistics.return_value = (N, tokens_n, avgdl)

        score = get_doc_score("",parsedquery,doc)

        mock_field_terms_statistics.assert_called_with(
            "","metadata_name_id_type_process",
            [kv.split(":")[-1] for kv in parsedquery.split()])

        expected_scores = []
        for k in tokens_n.keys():
            scr,debug_str = bm25_tfidf(tokens_n[k],N,tokens_freq.get(k,0),dl,avgdl)
            print(debug_str)
            expected_scores.append(scr)
        expected_score = sum(expected_scores)
        self.assertTrue(np.allclose(score, expected_score))

        # http://rhgiadtsin01:8084/solr/processos_bm25_val/select?fl=
        # id_protocolo,score&fq=id_protocolo:3619868&indent=true&q.op=OR&q=
        # metadata_name_id_type_process:home metadata_name_id_type_process:passed metadata_name_id_type_process:pado
        solr_score = 2.3749611
        self.assertTrue(np.allclose(score, solr_score)) 

if __name__ == "__main__":
    unittest.main()
