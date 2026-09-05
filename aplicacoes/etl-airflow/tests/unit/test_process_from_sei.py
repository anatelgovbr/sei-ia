import unittest
from unittest.mock import Mock, patch

import pandas as pd

from jobs.dags.preprocessing.process_from_sei import ProcessFromSEI


class TestGetFormattedRelatedProcesses(unittest.TestCase):
    def test_empty_df_returns_empty_string(self):
        df = pd.DataFrame()
        self.assertEqual(ProcessFromSEI.get_formatted_related_processes(df), "")

    def test_missing_column_returns_empty_string(self):
        df = pd.DataFrame([{"outra_coluna": "x"}])
        self.assertEqual(ProcessFromSEI.get_formatted_related_processes(df), "")

    def test_none_value_returns_empty_string(self):
        df = pd.DataFrame([{"processos_relacionados_1": None}])
        self.assertEqual(ProcessFromSEI.get_formatted_related_processes(df), "")

    def test_extracts_sorted_unique_numbers(self):
        df = pd.DataFrame(
            [{"processos_relacionados_1": "processo 20 e processo 10 e 20 de novo"}]
        )
        self.assertEqual(
            ProcessFromSEI.get_formatted_related_processes(df), "10,20"
        )


class TestListDocuments(unittest.TestCase):
    def test_empty_df_returns_empty_list(self):
        self.assertEqual(ProcessFromSEI.list_documents(pd.DataFrame()), [])

    def test_drops_nan_ids(self):
        df = pd.DataFrame(
            {"id_protocolo_documento": [1, None, 3]}
        )
        self.assertEqual(ProcessFromSEI.list_documents(df), [1, 3])


class TestGetFormatsStr(unittest.TestCase):
    @patch("jobs.dags.preprocessing.process_from_sei.FORMATS", ["pdf", "docx"])
    def test_joins_formats_quoted(self):
        self.assertEqual(ProcessFromSEI.get_formats_str(), "'pdf','docx'")


class TestGetIdDocumentsAllowed(unittest.TestCase):
    def test_empty_processes_str_short_circuits(self):
        self.assertEqual(ProcessFromSEI.get_id_documents_allowed(""), "")
        self.assertEqual(ProcessFromSEI.get_id_documents_allowed("   "), "")

    @patch("jobs.dags.preprocessing.process_from_sei.sei_client")
    def test_delegates_to_sei_client(self, mock_sei_client):
        mock_sei_client.md_ia_lista_documentos_elegiveis_processos_similares.return_value = [
            1,
            2,
            3,
        ]

        result = ProcessFromSEI.get_id_documents_allowed("123,456")

        self.assertEqual(result, "1,2,3")


class TestGetProcessAndSubprocessesStr(unittest.TestCase):
    @patch("jobs.dags.preprocessing.process_from_sei.sei_client")
    def test_without_subprocesses(self, mock_sei_client):
        result = ProcessFromSEI.get_process_and_subprocesses_str(
            "123", subprocesses=False
        )

        self.assertEqual(result, "123")
        mock_sei_client.get_subprocessos_id_protocolo.assert_not_called()

    @patch("jobs.dags.preprocessing.process_from_sei.sei_client")
    def test_with_subprocesses_found(self, mock_sei_client):
        mock_sei_client.get_subprocessos_id_protocolo.return_value = pd.DataFrame(
            [{"id_protocolo_2": 456}, {"id_protocolo_2": 789}]
        )

        result = ProcessFromSEI.get_process_and_subprocesses_str(
            "123", subprocesses=True
        )

        self.assertEqual(result, "123,456,789")

    @patch("jobs.dags.preprocessing.process_from_sei.sei_client")
    def test_with_subprocesses_none_found(self, mock_sei_client):
        mock_sei_client.get_subprocessos_id_protocolo.return_value = pd.DataFrame()

        result = ProcessFromSEI.get_process_and_subprocesses_str(
            "123", subprocesses=True
        )

        self.assertEqual(result, "123")


class TestGetProcessMetadata(unittest.TestCase):
    @patch("jobs.dags.preprocessing.process_from_sei.sei_client")
    def test_empty_metadata_returns_empty_df(self, mock_sei_client):
        mock_sei_client.md_ia_consulta_processo_metadados.return_value = pd.DataFrame()

        result = ProcessFromSEI.get_process_metadata("123")

        self.assertTrue(result.empty)

    @patch("jobs.dags.preprocessing.process_from_sei.sei_client")
    def test_groups_metadata_by_protocolo(self, mock_sei_client):
        mock_sei_client.md_ia_consulta_processo_metadados.return_value = pd.DataFrame(
            [
                {
                    "id_protocolo": "123",
                    "protocolo_formatado": "00000.000000/0000-00",
                    "processo_especificacao": "Especificacao",
                    "interessado": "Empresa A",
                    "processos_relacionados_1": "456",
                    "processos_relacionados_2": "",
                    "id_type_process": 1,
                    "id_unit_process_generator": 10,
                    "name_id_type_process": "Tipo Teste",
                }
            ]
        )

        result = ProcessFromSEI.get_process_metadata("123")

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["id_protocolo"], "123")


class TestGetInfoRelatedProcesses(unittest.TestCase):
    @patch("jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.get_id_documents_allowed")
    def test_returns_empty_columns_df_without_matching_docs(self, mock_get_ids):
        mock_get_ids.return_value = ""

        result = ProcessFromSEI.get_info_related_processes("456")

        self.assertTrue(result.empty)
        self.assertIn("id_protocolo", result.columns)

    @patch("jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.agg_related_process_query")
    @patch("jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.get_id_documents_allowed")
    def test_aggregates_when_docs_found(self, mock_get_ids, mock_agg):
        mock_get_ids.return_value = "1,2"
        mock_agg.return_value = pd.DataFrame([{"id_protocolo": "456"}])

        result = ProcessFromSEI.get_info_related_processes("456")

        mock_agg.assert_called_once_with("1,2")
        self.assertEqual(result.iloc[0]["id_protocolo"], "456")


class TestGetDocsFromProcess(unittest.TestCase):
    @patch("jobs.dags.preprocessing.process_from_sei.consulta_documentos_com_conteudo")
    @patch("jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.get_id_documents_allowed")
    def test_drops_duplicate_documents(self, mock_get_ids, mock_consulta):
        mock_get_ids.return_value = "1,1"
        mock_consulta.return_value = pd.DataFrame(
            [
                {"id_protocolo_documento": 1, "conteudo": "a"},
                {"id_protocolo_documento": 1, "conteudo": "a"},
            ]
        )

        result = ProcessFromSEI.get_docs_from_process("123")

        self.assertEqual(len(result), 1)


class TestAggRelatedProcessQuery(unittest.TestCase):
    @patch("jobs.dags.preprocessing.process_from_sei.consulta_documentos")
    def test_empty_docs_returns_empty_columns_df(self, mock_consulta):
        mock_consulta.return_value = pd.DataFrame()

        result = ProcessFromSEI.agg_related_process_query("1,2")

        self.assertTrue(result.empty)
        self.assertIn("documento_especificacao", result.columns)

    @patch("jobs.dags.preprocessing.process_from_sei.sei_client")
    @patch("jobs.dags.preprocessing.process_from_sei.consulta_documentos")
    def test_aggregates_documents_by_process(self, mock_consulta, mock_sei_client):
        mock_consulta.return_value = pd.DataFrame(
            [
                {
                    "id_protocolo": "123",
                    "documento_especificacao": "Despacho",
                    "name_id_type_doc": "Despacho Decisorio",
                }
            ]
        )
        mock_sei_client.md_ia_consulta_processo_metadados.return_value = pd.DataFrame(
            [
                {
                    "protocolo_formatado": "00000.000000/0000-00",
                    "processo_especificacao": "Especificacao",
                    "interessado": "Empresa A",
                    "name_interested": "Empresa A",
                    "id_type_process": 1,
                    "id_unit_process_generator": 10,
                    "name_id_unit_process_generator": "Unidade Teste",
                    "name_id_type_process": "Tipo Teste",
                }
            ]
        )

        result = ProcessFromSEI.agg_related_process_query("1,2")

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["id_protocolo"], "123")

    @patch("jobs.dags.preprocessing.process_from_sei.sei_client")
    @patch("jobs.dags.preprocessing.process_from_sei.consulta_documentos")
    def test_handles_process_without_metadata(self, mock_consulta, mock_sei_client):
        mock_consulta.return_value = pd.DataFrame(
            [
                {
                    "id_protocolo": "123",
                    "documento_especificacao": "Despacho",
                    "name_id_type_doc": "Despacho Decisorio",
                }
            ]
        )
        mock_sei_client.md_ia_consulta_processo_metadados.return_value = pd.DataFrame()

        result = ProcessFromSEI.agg_related_process_query("1,2")

        self.assertEqual(len(result), 1)
        self.assertIsNone(result.iloc[0]["protocolo_formatado"])


class TestProcessFromSEIOrchestration(unittest.TestCase):
    @patch("jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.get_process_metadata")
    def test_stops_early_without_metadata(self, mock_get_metadata):
        mock_get_metadata.return_value = pd.DataFrame()

        process = ProcessFromSEI(
            id_protocolo="123",
            id_type_process=1,
            interested_max=3,
            related_processes_max=3,
        )

        self.assertIsNone(process.process_transformed)

    @patch("jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.get_docs_from_process")
    @patch("jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.get_process_metadata")
    def test_stops_early_without_documents(
        self, mock_get_metadata, mock_get_docs
    ):
        mock_get_metadata.return_value = pd.DataFrame([{"id_protocolo": "123"}])
        mock_get_docs.return_value = pd.DataFrame()

        process = ProcessFromSEI(
            id_protocolo="123",
            id_type_process=1,
            interested_max=3,
            related_processes_max=3,
        )

        self.assertIsNone(process.process_transformed)

    @patch("jobs.dags.preprocessing.process_from_sei.ProcessTransformed")
    @patch(
        "jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.get_info_related_processes"
    )
    @patch(
        "jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.get_formatted_related_processes"
    )
    @patch(
        "jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.get_process_and_subprocesses_str"
    )
    @patch("jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.get_docs_from_process")
    @patch("jobs.dags.preprocessing.process_from_sei.ProcessFromSEI.get_process_metadata")
    def test_builds_process_transformed_on_full_success(
        self,
        mock_get_metadata,
        mock_get_docs,
        mock_get_processes_str,
        mock_get_formatted_related,
        mock_get_info_related,
        mock_process_transformed_cls,
    ):
        mock_get_metadata.return_value = pd.DataFrame([{"id_protocolo": "123"}])
        mock_get_docs.return_value = pd.DataFrame(
            {"id_protocolo_documento": [1, 2]}
        )
        mock_get_processes_str.return_value = "123"
        mock_get_formatted_related.return_value = ""
        mock_get_info_related.return_value = pd.DataFrame()
        mock_process_transformed_cls.return_value = Mock(name="process_transformed")

        process = ProcessFromSEI(
            id_protocolo="123",
            id_type_process=1,
            interested_max=3,
            related_processes_max=3,
        )

        mock_process_transformed_cls.assert_called_once()
        self.assertIsNotNone(process.process_transformed)


if __name__ == "__main__":
    unittest.main()
