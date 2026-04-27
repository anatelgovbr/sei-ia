"""Autoteste."""

import json
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_sei.envs import CONFIG_AUTO_TESTS_PATH

# URL_BASE = "http://localhost:8082"


class TestesAutoteste:
    """Classe para testes de autoteste da API."""

    def __init__(self, app: FastAPI) -> None:  # noqa: D107
        self.client = TestClient(app)

    def read_endpoints(self) -> list:
        """Faz a leitura do arquivo de configuração de endpoints.

        Returns:
            list: Uma lista de dicionários contendo os endpoints.
        """
        with Path(CONFIG_AUTO_TESTS_PATH).open() as file:
            return json.load(file)

    def build_url(self, path: str, params: dict, base_url: str | None = None) -> str:
        """Constroi uma URL com base em um caminho e parâmetros.

        Se o parâmetro "id_recommendation" estiver presente, substitui o placeholder
        {id_recommendation} no caminho.

        Os parâmetros com valores em forma de lista (como list_type_id_doc) são
        unidos com vírgulas.

        Retorna a URL completa com o caminho e a string de consulta.
        """
        if not base_url:
            base_url = ""
        if "id_recommendation" in params:
            path = path.format(id_recommendation=params.pop("id_recommendation"))

        query_params = []
        for key, value in params.items():
            if isinstance(value, list):
                query_params.extend((key, v) for v in value)
            else:
                query_params.append((key, value))

        query_string = urlencode(query_params, doseq=True)
        return f"{base_url}{path}?{query_string}"

    def autoteste(self) -> list:
        """Testes múltiplos de rotas para verificar os seus HTTP status codes.

        Parameters:
            app (FastAPI): A instancia da aplicação FastAPI.

        Returns:
            list: Uma lista de dicionários contendo os resultados de HTTP e os status codes.
        """
        results = []

        # Construir URLs e testá-las
        endpoints = self.read_endpoints()
        for endpoint in endpoints:
            test_description = endpoint["test_description"]
            url = self.build_url(path=endpoint["path"], params=endpoint["params"])
            response = self.client.get(url)

            status_code_expected = endpoint["result_expected"].get("status_code")
            endpoint_result = {}
            endpoint_result["test_description"] = test_description
            endpoint_result["url"] = url
            endpoint_result["test_success"] = (
                "SUCCESS" if response.status_code == status_code_expected else "FAIL"
            )
            endpoint_result["status_code"] = response.status_code
            results.append(endpoint_result)

        return results
