import unittest
from unittest import mock

import random

import pandas as pd

from jobs.dags.database.sql_templates.external_docs_from_process import (
    EXTERNAL_DOCS_FROM_PROCESS_TEMPLATE,
)
from jobs.dags.database.sql_templates.internal_docs_from_process import (
    INTERNAL_DOCS_FROM_PROCESS_TEMPLATE,
)
from jobs.dags.database.sql_templates.related_processes import (
    RELATED_PROCESSES_TEMPLATE
)
from jobs.dags.database.sql_templates.process_metadata import PROCESS_METADATA_TEMPLATE
from jobs.dags.database.sql_templates.subprocessos import (
    SUBPROCESSOS_ID_PROTOCOLO_TEMPLATE
)
from jobs.dags.preprocessing.process_from_sei import ProcessFromSEI

df = pd.DataFrame(
    {
        "id_protocolo": ["2667442"],
        "protocolo_formatado": ["53500.000554/2018-70"],
        "id_type_process": ["100000686"],
        "name_id_type_process": ["PADO: Home Passed"],
        "id_unit_process_generator": ["110000941"],
        "processo_especificacao": [
            "Descumprimento de obrigação relativas ao Home Passed- pela empresa RCA COMPANY DE TELECOMUNICAÇÕES"
        ],
        "interessado": ["100046724"],
        "processos_relacionados_1": ["122333,3334444"],
        "processos_relacionados_2": ["5555522,1224444"],
        "content_doc": [
            "o gerente de controle de obrigações de universalização e de ampliação do acesso, no uso de suas atribuições legais e regulamentares, em especial a disposta no art. 239, vii, do regimento interno da anatel, aprovado pela resolução nº 612, de 29 de abril de 2013, em razão da competência delegada pelo art. 1º da portaria nº 1.185, de 20 de julho de 2018, examinando os autos do processo em epígrafe; considerando que foram revisados os níveis de acesso dos documentos no sistema sei, em conformidade com o disposto nos incisos iii, iv e vi do art. 9º e nos arts. 25 a 27 da portaria nº 912/2017. declara extinto o processo em epígrafe, procedendo com seu encerramento nesta gerência, em razão dos termos do acórdão nº 659/2020 (sei nº 6289194). "
        ],
        "content_type": ["html"],
        "name_id_type_doc": ["Despacho Ordinatório de Encerramento "],
        "id_type_document": ["374"],
        "dta_inclusao": [pd.Timestamp(2022, 8, 16, 0)],
        "documento_especificacao": ["despacho ordinatório de encerramento"],
        "nr_documento": ["1111111"],
        "id_protocolo_documento": ["1111111"],
        "name_interested": ["RCA COMPANY DE TELECOMUNICAÇÕES"],
        "name_id_unit_process_generator": ["GCOUA"],
    }
)

def mock_get_id_documents_allowed(id_protocolo, external):
    if not external:
        id_documents = df['id_protocolo_documento'].values.tolist()
        formatted_id_documents = ','.join([f"'{x}'" for x in id_documents]) 
        return formatted_id_documents
    else:
        return ""




class TestProcessFromSEI(unittest.TestCase):
    """test ProcessFromSEI"""

    def setUp(self):
        pass

    @mock.patch(
        "jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.get_id_documents_allowed",
        mock_get_id_documents_allowed
    )
    @mock.patch(
        "jobs.dags.preprocessing.process_from_sei.ENVIRONMENT", "test"
    )
    @mock.patch("jobs.dags.preprocessing.process_from_sei.ProcessTransformed")
    def test_process_from_sei(self, mock_process_transformed):
        """
        Tests if ProcessFromSEI calls ProcessTransformed with metadata_in_embd=True
        and embd_on = True, when ProcessFromSEI is called with metadata_in_embd=True
        """

        id_protocolo = df["id_protocolo"].loc[0]
        id_type_process = df["id_type_process"].loc[0]

        process = ProcessFromSEI(id_protocolo=id_protocolo, 
                       id_type_process=id_type_process, 
                       interested_max=2, 
                       related_processes_max=9,
                       subprocesses=False, 
                       dt_ref_insert=None)
        
          
        args, kwargs = mock_process_transformed.call_args

        pd.testing.assert_frame_equal(kwargs['df_process_documents'], process.df_process_documents)
        pd.testing.assert_frame_equal(kwargs['df_process_metadata'], process.df_process_metadata)
        pd.testing.assert_frame_equal(kwargs['df_related_processes'], process.df_related_processes)


    def test_get_formatted_related_processes_usual(self):
        df = pd.DataFrame(
            {"processos_relacionados_1": ["122333,3334444"],
             "processos_relacionados_2": ["5555522,1224444"]}
        )
        rel = ProcessFromSEI.get_formatted_related_processes(df)
        self.assertEqual(rel, "122333,1224444,3334444,5555522")

    def test_get_formatted_related_processes_two_empty(self):
        random.seed(1)
        for _ in range(100):
            df = pd.DataFrame(
                {"processos_relacionados_1": ",".join([str(random.randint(1, 10000000)) for _ in range(random.randint(1, 10))]),
                 "processos_relacionados_2": ['']}
            )
            rel = ProcessFromSEI.get_formatted_related_processes(df)
            self.assertTrue(",," not in rel, f"Bad str: {rel}")

    def test_get_formatted_related_processes_all_empty(self):
        df = pd.DataFrame(
            {"processos_relacionados_1": [""],
             "processos_relacionados_2": [""]}
        )
        rel = ProcessFromSEI.get_formatted_related_processes(df)
        self.assertEqual(rel, "")

    def test_get_formatted_related_processes_empty_dataframe(self):
        """Testa comportamento com DataFrame vazio"""
        df = pd.DataFrame()
        rel = ProcessFromSEI.get_formatted_related_processes(df)
        self.assertEqual(rel, "")

    def test_get_formatted_related_processes_missing_column(self):
        """Testa comportamento quando coluna processos_relacionados_1 não existe"""
        df = pd.DataFrame({"outra_coluna": ["valor"]})
        rel = ProcessFromSEI.get_formatted_related_processes(df)
        self.assertEqual(rel, "")

    def test_get_formatted_related_processes_none_value(self):
        """Testa comportamento quando o valor é None"""
        df = pd.DataFrame({"processos_relacionados_1": [None]})
        rel = ProcessFromSEI.get_formatted_related_processes(df)
        self.assertEqual(rel, "")

    def test_get_formatted_related_processes_non_string_value(self):
        """Testa comportamento quando o valor não é string"""
        df = pd.DataFrame({"processos_relacionados_1": [123]})
        rel = ProcessFromSEI.get_formatted_related_processes(df)
        self.assertEqual(rel, "")


if __name__ == "__main__":
    unittest.main()
