"""Lida com solicitações solr para banco de dados."""

import asyncio
import inspect
import logging
import re
import sys
import traceback
from typing import Any

import httpx
import nest_asyncio
import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import ConnectionError, JSONDecodeError, Timeout

from api_sei.envs import LOG_LEVEL, SEI_API_DB_TIMEOUT, SOLR_ADDRESS, VERIFY_SSL, auth
from api_sei.exception_handling.exceptions import (
    FieldInURLError,
    JsonFieldException,
    RowsNotFoundError,
    SolrException,
)
from api_sei.utils import add_param_on_url_if_not_exists

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)
nest_asyncio.apply()


async def async_solr_requests(
    queries: list[str],
    timeout: int = SEI_API_DB_TIMEOUT,
    auth: HTTPBasicAuth | None = None,
) -> list[Any]:
    """Executa solicitações assíncronas para o Solr.

    Parameters:
        queries (List[str]): Lista de URLs de consulta ao Solr.
        timeout (int, opcional): Tempo limite para as requisições. O padrão é 120 segundos.

    Returns:
        List[Any]: Lista de respostas das requisições.
    """
    async with httpx.AsyncClient(
        timeout=timeout, auth=auth, verify=VERIFY_SSL
    ) as client:
        tasks = [client.get(q) for q in queries]
        return await asyncio.gather(*tasks, return_exceptions=True)


class SolrRequests:
    """Classe para solicitações ao Solr."""

    @staticmethod
    def check_solr_service(solr_url: str, auth: HTTPBasicAuth | None = None) -> bool:
        """Verifica se o serviço Solr está disponível.

        Parameters:
            solr_url (str): A URL do servidor Solr.

        Returns:
            bool: True se o Solr estiver disponível, False caso contrário.
        """
        try:
            response = requests.get(solr_url, timeout=10, auth=auth, verify=VERIFY_SSL)
            return bool(response.status_code == requests.codes.ok) and bool(
                "Apache SOLR" in response.text
            )
        except Exception:
            return False

    @staticmethod
    def check_core_exists(
        solr_url: str, core_name: str, auth: HTTPBasicAuth | None = None
    ) -> bool:
        """Verifica se o core do Solr existe.

        Parameters:
            solr_url (str): A URL do servidor Solr.
            core_name (str): O nome do core Solr.

        Returns:
            bool: True se o core existir, False caso contrário.
        """
        core_status_url = f"{solr_url}/solr/{core_name}/admin/ping"
        try:
            response = requests.get(
                core_status_url, timeout=10, auth=auth, verify=VERIFY_SSL
            )
        except Exception:
            return False
        return response.status_code == requests.codes.ok

    @staticmethod
    def check_query_core_exists(url: str, auth: HTTPBasicAuth | None) -> None:
        """Verifica a existência de um core no Solr baseado na URL e na resposta HTTP.

        Parameters:
            url (str): URL da requisição original.
            auth: Credenciais de autenticação para o Solr.

        Raises:
            SolrException: Se o core ou a comunicação com o Solr falharem.
        """
        core_name = None
        pattern = r"/solr/([^/]+)/"
        match = re.search(pattern, url)
        if match:
            core_name = match.group(1)

        if not core_name:
            raise SolrException(
                status_code=requests.codes.not_found,
                detail="O core mencionado nao foi encontrado",
            )

        status_url = f"{SOLR_ADDRESS}/solr/admin/cores?action=STATUS&core={core_name}"
        try:
            response = requests.get(
                status_url, auth=auth, timeout=20, verify=VERIFY_SSL
            )

            try:
                data = response.json()
            except ValueError:
                raise SolrException(  # noqa: B904
                    status_code=requests.codes.internal_server_error,
                    detail="Erro ao processar a resposta JSON do Solr",
                )

            has_core = bool(data.get("status", {}).get(core_name, None))
            if not has_core:
                raise SolrException(
                    status_code=requests.codes.not_found,
                    detail="Core da query não foi encontrado no Solr",
                )
        except requests.exceptions.RequestException as e:
            raise SolrException(  # noqa: B904
                status_code=requests.codes.service_unavailable,
                detail=f"Erro de comunicação com o Solr: {e!s}",
            )

        raise SolrException(
            status_code=requests.codes.not_found,
            detail="URL de comunicação com o Solr não encontrado",
        )

    @staticmethod
    def post(
        url: str,
        payload: dict[str, Any],
        nested_fields: list[str] | None = None,
        timeout: int = SEI_API_DB_TIMEOUT,
        auth: HTTPBasicAuth | None = None,
    ) -> Any:  # noqa: ANN401
        """Envia uma solicitação POST ao Solr.

        Parameters:
            url (str): A URL de destino.
            payload (dict): O payload JSON a ser enviado.
            nested_fields (List[str], opcional): Lista de campos aninhados para obter da resposta.
            O padrão é uma lista vazia.
            timeout (int, opcional): O tempo limite para a requisição. O padrão é 60 segundos.

        Returns:
            Any: A resposta processada da requisição.
        """
        if nested_fields is None:
            nested_fields = []
        try:
            http_response = requests.post(
                url=url, json=payload, timeout=timeout, auth=auth, verify=VERIFY_SSL
            )
        except ConnectionError as exc:
            raise SolrException(
                status_code=requests.codes.service_unavailable, detail=str(exc)
            ) from exc
        except Timeout as exc:
            raise SolrException(status_code=504, detail=str(exc)) from exc
        return SolrRequests.retrieve_response(http_response, nested_fields)

    @staticmethod
    def select_raw(
        url: str,
        nested_fields: list | None = None,
        timeout: int = SEI_API_DB_TIMEOUT,
        params: dict | None = None,
        auth: HTTPBasicAuth | None = None,
    ) -> Any:  # noqa: ANN401
        """Executa uma solicitação GET ao Solr e retorna a resposta crua.

        Parameters:
            url (str): A URL de destino.
            nested_fields (List[str], opcional): Lista de campos aninhados para obter da resposta.
            timeout (int, opcional): O tempo limite para a requisição. O padrão é 60 segundos.
            params (dict, opcional): Parâmetros adicionais para a requisição.

        Returns:
            Any: A resposta processada da requisição.
        """
        if nested_fields is None:
            nested_fields = []
        try:
            if params:
                http_response = requests.get(
                    url, params=params, timeout=timeout, auth=auth, verify=VERIFY_SSL
                )
            else:
                http_response = requests.get(
                    url, timeout=timeout, auth=auth, verify=VERIFY_SSL
                )
        except ConnectionError as exc:
            raise SolrException(status_code=503, detail=str(exc)) from exc
        except Timeout as exc:
            raise SolrException(status_code=504, detail=str(exc)) from exc

        return SolrRequests.retrieve_response(http_response, nested_fields)

    @staticmethod
    def get(
        url: str,
        nested_fields: list | None = None,
        timeout: int = SEI_API_DB_TIMEOUT,
        params: dict | None = None,
        start: int | None = None,
        rows: int | None = None,
        auth: HTTPBasicAuth | None = None,
    ) -> Any:  # noqa: ANN401
        """Executa uma solicitação GET ao Solr com paginação.

        Parameters:
            url (str): A URL de destino.
            nested_fields (List[str], opcional): Lista de campos aninhados para obter da resposta.
            timeout (int, opcional): O tempo limite para a requisição. O padrão é 60 segundos.
            params (dict, opcional): Parâmetros adicionais para a requisição.
            start (int, opcional): Ponto de início da paginação. O padrão é 0.
            rows (int, opcional): Número de linhas para recuperar.

        Returns:
            Any: A resposta processada da requisição.

        Raises:
            RowsNotFoundError: Se o número de `rows` não for fornecido.
            FieldInURLError: Se os campos 'start' ou 'rows' já estiverem presentes na URL.
        """
        logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

        if nested_fields is None:
            nested_fields = []
        if rows is None:
            raise RowsNotFoundError("Numero de rows nao definido")

        if "&rows=" in url:
            raise FieldInURLError(
                "O campo 'rows' deve ser usado como parametro do metodo"
            )

        if "&start=" in url:
            raise FieldInURLError(
                "O campo 'start' deve ser usado como parametro do metodo"
            )

        if not start:
            start = 0
        url = add_param_on_url_if_not_exists(
            url=url, param_name="start", param_value=start
        )
        url = add_param_on_url_if_not_exists(
            url=url, param_name="rows", param_value=rows
        )
        if params:
            for k, v in params.items():
                url = add_param_on_url_if_not_exists(
                    url=url, param_name=k, param_value=v
                )

        try:
            http_response = requests.get(
                url, timeout=timeout, auth=auth, verify=VERIFY_SSL
            )
        except ConnectionError as exc:
            raise SolrException(status_code=503, detail=str(exc)) from exc
        except Timeout as exc:
            raise SolrException(status_code=504, detail=str(exc)) from exc

        return SolrRequests.retrieve_response(http_response, nested_fields)

    @staticmethod
    def select(
        url: str,
        nested_fields: list | None = None,
        params: dict | None = None,
        rows: dict | None = None,  # noqa: ARG004
        timeout: int = SEI_API_DB_TIMEOUT,
        k_results: int | None = None,
        batch_size: int = 700,
        auth: HTTPBasicAuth | None = None,
    ) -> Any:  # noqa: ANN401
        """Executa uma solicitação GET ao Solr com paginação.

        Parameters:
            url (str): A URL de destino.
            nested_fields (List[str], opcional): Lista de campos aninhados para obter da resposta.
            timeout (int, opcional): O tempo limite para a requisição. O padrão é 60 segundos.
            params (dict, opcional): Parâmetros adicionais para a requisição.
            start (int, opcional): Ponto de início da paginação. O padrão é 0.
            rows (int, opcional): Número de linhas para recuperar.

        Returns:
            Any: A resposta processada da requisição.

        Raises:
            RowsNotFoundError: Se o número de `rows` não for fornecido.
            FieldInURLError: Se os campos 'start' ou 'rows' já estiverem presentes na URL.
        """
        if nested_fields is None:
            nested_fields = []
        num_found = SolrRequests.get(
            url=url,
            params=params,
            nested_fields=["response", "numFound"],
            start=0,
            rows=1,
            auth=auth,
        )
        http_response = []
        for start in range(0, num_found, batch_size):
            if k_results and len(http_response) >= k_results:
                break
            batch_response = SolrRequests.get(
                url=url,
                nested_fields=nested_fields,
                params=params,
                timeout=timeout,
                start=start,
                rows=batch_size,
                auth=auth,
            )
            http_response.extend(batch_response)

        if k_results:
            return http_response[:k_results]

        return http_response

    @staticmethod
    def retrieve_response(http_response: Any, nested_fields: list | None = None) -> Any:  # noqa: ANN401
        """Processa a resposta HTTP e extrai os campos aninhados, se houver.

        Parameters:
            http_response (Any): A resposta HTTP para ser processada.
            nested_fields (List[str]): Lista de campos aninhados para extrair.

        Returns:
            Any: O conteúdo da resposta processada.

        Raises:
            SolrException: Se a resposta HTTP contiver erros.
        """
        if nested_fields is None:
            nested_fields = []
        if isinstance(http_response, Exception):
            _, _, exc_traceback = sys.exc_info()
            trace_info = traceback.extract_tb(exc_traceback)[-1]
            logger.error(f"SolrException: {http_response!s}")
            raise SolrException(
                status_code=503,
                detail=[
                    str(SolrException.__module__),
                    trace_info.lineno,
                    "/home/airflow/app/api_sei/db_models/solr_select.py",
                ],
            ) from http_response

        if not (
            hasattr(http_response, "status_code") and hasattr(http_response, "text")
        ):
            _, _, exc_traceback = sys.exc_info()
            trace_info = traceback.extract_tb(exc_traceback)[-1]
            logger.error(
                "SolrException: http_response must have the attributes: status_code and text"
            )
            raise SolrException(
                status_code=500,
                detail=[
                    str(SolrException.__module__),
                    trace_info.lineno,
                    "/home/airflow/app/api_sei/db_models/solr_select.py",
                ],
            )

        if not (hasattr(http_response, "json") and callable(http_response.json)):
            _, _, exc_traceback = sys.exc_info()
            trace_info = traceback.extract_tb(exc_traceback)[-1]
            logger.error("SolrException: http_response must have the method json()")
            raise SolrException(
                status_code=500,
                detail=[
                    str(SolrException.__module__),
                    trace_info.lineno,
                    "/home/airflow/app/api_sei/db_models/solr_select.py",
                ],
            )

        if http_response.status_code == requests.codes.not_found:
            SolrRequests.check_query_core_exists(http_response.url, auth=auth)
            raise SolrException(
                status_code=requests.codes.not_found,
                detail="URL de comunicacao com o Solr nao encontrado",
            )

        if http_response.status_code != requests.codes.ok:
            raise SolrException(
                status_code=http_response.status_code, detail=http_response.text
            )

        try:
            requests_json = http_response.json()
        except JSONDecodeError as exc:
            raise SolrException(
                status_code=requests.codes.bad_gateway, detail=str(exc)
            ) from exc

        ret = requests_json
        for field in nested_fields:
            try:
                ret = ret[field]
            except (IndexError, KeyError, TypeError) as exc:
                raise JsonFieldException(
                    status_code=requests.codes.bad_request, field=field
                ) from exc

        return ret

    @staticmethod
    def async_select(
        queries: list[str],
        nested_fields: list | None = None,
        auth: HTTPBasicAuth | None = None,
    ) -> list[Any]:
        """Recupera dados do Solr usando paginação.

        Parameters:
            url (str): A URL do Solr.
            nested_fields (List[str], opcional): Lista de campos aninhados para obter da resposta.
            params (dict, opcional): Parâmetros adicionais para a requisição.
            rows (int, opcional): Número de linhas por requisição.
            timeout (int, opcional): Tempo limite para a requisição. O padrão é 120 segundos.
            k_results (int, opcional): Número máximo de resultados a serem recuperados.
            batch_size (int, opcional): Tamanho do lote por requisição. O padrão é 700.

        Returns:
            List[Any]: Lista de dados recuperados.
        """
        if len(queries) == 0:
            return []

        loop = asyncio.get_event_loop()
        response_list = loop.run_until_complete(async_solr_requests(queries, auth=auth))

        return [SolrRequests.retrieve_response(r, nested_fields) for r in response_list]
