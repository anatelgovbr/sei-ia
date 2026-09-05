import unittest
from unittest.mock import Mock, patch

import pandas as pd

from jobs.dags.preprocessing.process_transformed import ProcessTransformed, zero_pad


def _build_process_transformed(**overrides):
    df_process_documents = pd.DataFrame(
        [
            {
                "id_protocolo_documento": 1,
                "id_type_document": "4",
                "content_doc": (
                    "<html><body><p>DECIDE</p>"
                    "<p>Aplicar multa a prestadora pelo descumprimento verificado.</p>"
                    "</body></html>"
                ),
                "content_type": "html",
                "dta_inclusao": "2026-01-01 00:00:00",
                "name_id_type_doc": "Despacho",
                "documento_especificacao": "Despacho Decisorio",
            }
        ]
    )
    df_process_metadata = pd.DataFrame(
        [
            {
                "id_protocolo": "123",
                "protocolo_formatado": "00000.000000/0000-00",
                "id_type_process": 1,
                "name_id_type_process": "Processo Teste",
                "id_unit_process_generator": 10,
                "processo_especificacao": "Especificacao Teste",
                "interessado": "Empresa Teste",
            }
        ]
    )
    df_related_processes = pd.DataFrame(
        columns=[
            "processo_especificacao",
            "name_interested",
            "name_id_unit_process_generator",
            "name_id_type_process",
            "documento_especificacao",
            "name_id_type_doc",
        ]
    )
    kwargs = {
        "id_protocolo": "123",
        "df_process_documents": df_process_documents,
        "df_process_metadata": df_process_metadata,
        "df_related_processes": df_related_processes,
        "interested_max": 3,
        "related_processes_max": 3,
    }
    kwargs.update(overrides)
    return ProcessTransformed(**kwargs)


class TestZeroPad(unittest.TestCase):
    def test_pads_with_zero(self):
        self.assertEqual(zero_pad(["a"], 3, "0"), ["a", "0", "0"])

    def test_truncates_nothing_when_already_long_enough(self):
        self.assertEqual(zero_pad(["a", "b"], 2, "0"), ["a", "b"])


class TestProcessTransformed(unittest.TestCase):
    @patch("jobs.dags.preprocessing.process_transformed.get_app_db")
    def test_fabric_solr_dict_builds_expected_shape(self, mock_get_app_db):
        mock_db = Mock()
        mock_db.execute_query_one.return_value = {"id": 42}
        mock_get_app_db.return_value = mock_db

        process = _build_process_transformed()

        self.assertEqual(process.solr_dict["id_protocolo"], "123")
        self.assertEqual(process.solr_dict["version_manager_id"], 42)
        self.assertEqual(process.solr_dict["list_documents"], [1])
        self.assertIn("content_id_type_doc_4", process.solr_dict)
        self.assertIn("content_id_type_doc_4_decide", process.solr_dict)
        self.assertIn(
            "aplicar multa a prestadora",
            process.solr_dict["content_id_type_doc_4_decide"][0],
        )

    @patch("jobs.dags.preprocessing.process_transformed.get_app_db")
    def test_dt_ref_insert_is_formatted_when_provided(self, mock_get_app_db):
        from datetime import datetime

        mock_db = Mock()
        mock_db.execute_query_one.return_value = {"id": 1}
        mock_get_app_db.return_value = mock_db

        process = _build_process_transformed(
            dt_ref_insert=datetime(2026, 1, 1, 12, 0, 0)
        )

        self.assertEqual(process.solr_dict["dt_ref_insert"], "2026-01-01T12:00:00Z")

    @patch("jobs.dags.preprocessing.process_transformed.get_app_db")
    def test_transform_html_to_text_handles_none_and_plain_text(
        self, mock_get_app_db
    ):
        mock_db = Mock()
        mock_db.execute_query_one.return_value = {"id": 1}
        mock_get_app_db.return_value = mock_db

        result = ProcessTransformed.transform_html_to_text(
            ["texto puro sem html", None], ["txt", "txt"]
        )

        self.assertEqual(result, ["texto puro sem html", ""])


if __name__ == "__main__":
    unittest.main()
