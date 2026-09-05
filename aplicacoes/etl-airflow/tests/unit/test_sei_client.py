import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from sei_extraction.exceptions import UnsupportedFormatError

from jobs.db_models import sei_client as sei_client_module
from jobs.db_models.sei_client import (
    _content_type_from_formato,
    _enrich_documento_df,
    _extract_anexo,
    consulta_documentos,
    consulta_documentos_com_conteudo,
)


class TestExtractAnexo(unittest.TestCase):
    @patch("jobs.db_models.sei_client.extract_document")
    def test_extract_anexo_success(self, mock_extract_document):
        mock_extract_document.return_value = "texto extraido"

        result = _extract_anexo("/tmp/anexo.pdf", "pdf")

        self.assertEqual(result, "texto extraido")

    @patch("jobs.db_models.sei_client.extract_document")
    def test_extract_anexo_fallback_on_unsupported_format(self, mock_extract_document):
        mock_extract_document.side_effect = UnsupportedFormatError("nao suportado")

        with tempfile.TemporaryDirectory() as tmp_dir:
            anexo_path = Path(tmp_dir) / "anexo.xyz"
            anexo_path.write_text("conteudo cru", encoding="utf-8")

            result = _extract_anexo(str(anexo_path), "xyz")

        self.assertEqual(result, "conteudo cru")


class TestContentTypeFromFormato(unittest.TestCase):
    def test_with_extension(self):
        self.assertEqual(_content_type_from_formato("documento.pdf"), "pdf")

    def test_without_extension(self):
        self.assertEqual(_content_type_from_formato("documento"), "html")

    def test_with_none(self):
        self.assertEqual(_content_type_from_formato(None), "html")


class TestEnrichDocumentoDf(unittest.TestCase):
    def test_enrich_non_empty_df(self):
        df = pd.DataFrame(
            [
                {
                    "formato_arquivo": "documento.pdf",
                    "dta_inclusao": "2026-01-01 10:00:00",
                }
            ]
        )

        result = _enrich_documento_df(df)

        self.assertEqual(result["content_type"].iloc[0], "pdf")
        self.assertEqual(result["dta_inclusao"].iloc[0], "2026-01-01 10:00:00")

    def test_enrich_empty_df(self):
        df = pd.DataFrame(columns=["formato_arquivo", "dta_inclusao"])

        result = _enrich_documento_df(df)

        self.assertTrue(result.empty)
        self.assertIn("content_type", result.columns)


class TestConsultaDocumentos(unittest.TestCase):
    @patch.object(sei_client_module, "sei_client")
    def test_consulta_documentos_enriches_result(self, mock_client):
        mock_client.md_ia_consulta_documento.return_value = pd.DataFrame(
            [{"formato_arquivo": "doc.txt", "dta_inclusao": "2026-01-01 00:00:00"}]
        )

        result = consulta_documentos("123", id_type_process="1")

        mock_client.md_ia_consulta_documento.assert_called_once_with(
            "123", id_type_process="1"
        )
        self.assertEqual(result["content_type"].iloc[0], "txt")


class TestConsultaDocumentosComConteudo(unittest.TestCase):
    @patch.object(sei_client_module, "sei_client")
    def test_returns_empty_df_without_fetching_content(self, mock_client):
        mock_client.md_ia_consulta_documento.return_value = pd.DataFrame(
            columns=["formato_arquivo", "dta_inclusao"]
        )

        result = consulta_documentos_com_conteudo("123")

        self.assertTrue(result.empty)
        mock_client.run_async.assert_not_called()

    @patch.object(sei_client_module, "sei_client")
    def test_merges_fetched_content(self, mock_client):
        mock_client.md_ia_consulta_documento.return_value = pd.DataFrame(
            [
                {
                    "id_protocolo_documento": 1,
                    "formato_arquivo": "doc.txt",
                    "dta_inclusao": "2026-01-01 00:00:00",
                }
            ]
        )
        mock_client.fetch_documents_content_async.return_value = "coro"
        mock_client.run_async.return_value = ({"1": "conteudo do documento"}, None)

        result = consulta_documentos_com_conteudo("123")

        self.assertEqual(result["content_doc"].iloc[0], "conteudo do documento")


if __name__ == "__main__":
    unittest.main()
