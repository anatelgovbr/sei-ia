
import unittest
from unittest import mock
import pytest
from api_sei.resources.custom_parsedquery import ManualExtractCustomParsedQuery, read_mlt_fields_weights
from mock_solr import mock_requests_get
from mock_solr import mock_requests_post


class TestCustomParsedQuery(unittest.TestCase):
    """test CustomParsedQuery"""

    @mock.patch(
        "api_sei.db_models.solr_select.requests.post", mock_requests_post
    )
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
    @mock.patch(
        'api_sei.db_models.get_content_lazy.get_proc_content_lazy',
    )
    @pytest.mark.integration
    def test_process_text_similarity_field_negative_weight(self,mock_get_proc_content_lazy):
        # 5,6,17,81,332,374 not in (4,7,8,11,16,41,42,80,94,111,160,293,330,497,498,499)
        mock_get_proc_content_lazy.return_value = {
            # "metadata_name_id_type_doc_5":"Despacho Ordinatório",
            # "metadata_name_id_type_doc_6":"Despacho Ordinatório de Instauração",
            "metadata_name_id_type_doc_7":"Análise",
            "metadata_name_id_type_doc_8":"Acórdão",
            "metadata_name_id_type_doc_11":"Ofício",
            "metadata_name_id_type_doc_16":"Informe",
            # "metadata_name_id_type_doc_17":"Matéria para Apreciação do Conselho Diretor",
            # "metadata_name_id_type_doc_81":"Certidão",
            # "metadata_name_id_type_doc_332":"Recibo Eletrônico de Protocolo",
            # "metadata_name_id_type_doc_374":"Despacho Ordinatório de Encerramento",
        }
        
        id_protocolo = "3619868"
        manualExtractCustomParsedQuery = ManualExtractCustomParsedQuery(id_protocolo)
        parsedquery = manualExtractCustomParsedQuery.get_parsedquery()

        # print(manualExtractCustomParsedQuery.all_fields)
        # print(manualExtractCustomParsedQuery.per_field_terms)
        # print(manualExtractCustomParsedQuery.boolean_fields_data)
        # print(read_mlt_fields_weights(manualExtractCustomParsedQuery.all_fields))

        # for field_name in manualExtractCustomParsedQuery.all_fields:
        #     interesting_terms = manualExtractCustomParsedQuery.per_field_terms[field_name]
        #     preprocessed_parsedquery = " ".join([f"{field_name}:{t}" for t in interesting_terms])
        #     ref_score = manualExtractCustomParsedQuery.get_self_score(preprocessed_parsedquery)
        #     print(ref_score)

        # print(parsedquery)
        self.assertTrue("^-" not in parsedquery)

if __name__ == '__main__':

    unittest.main()