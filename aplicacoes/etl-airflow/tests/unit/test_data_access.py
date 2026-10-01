import unittest
from unittest.mock import patch

import pandas as pd

from jobs.configs.parameters.data_access import DataAccess


class TestDataAccess(unittest.TestCase):
    @patch("jobs.configs.parameters.data_access.sei_client")
    def test_fetch_docs_weights(self, mock_client):
        mock_client.md_ia_lista_segmentos_documentos_relevantes.return_value = (
            pd.DataFrame([{"segmento": "a"}])
        )

        result = DataAccess.fetch_docs_weights()

        self.assertEqual(result.iloc[0]["segmento"], "a")

    @patch("jobs.configs.parameters.data_access.sei_client")
    def test_fetch_series(self, mock_client):
        mock_client.md_ia_lista_tipo_documento.return_value = pd.DataFrame(
            [{"tipo": "despacho"}]
        )

        result = DataAccess.fetch_series()

        self.assertEqual(result.iloc[0]["tipo"], "despacho")

    @patch("jobs.configs.parameters.data_access.sei_client")
    def test_fetch_metadados_weights(self, mock_client):
        mock_client.md_ia_lista_percentual_relevancia_metadados.return_value = (
            pd.DataFrame([{"metadado": "x", "peso": 1}])
        )

        result = DataAccess.fetch_metadados_weights()

        self.assertEqual(result.iloc[0]["peso"], 1)


if __name__ == "__main__":
    unittest.main()
