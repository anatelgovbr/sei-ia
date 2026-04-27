"""Module for connecting with Solr."""

import logging
import time
from typing import Any, TypeVar

import requests
from fastapi import HTTPException
from requests.auth import HTTPBasicAuth
from requests.exceptions import (
    ConnectionError as ConnectionErrorRequest,
    JSONDecodeError,
    RequestException,
    Timeout,
)

from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings

setup_logging()

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
DEFAULT_ERROR_MSG = "Erro não especificado"
DEFAULT_DETAIL_MSG = "Sem detalhes"
DEFAULT_ACTION_MSG = "Ação não especificada"

T = TypeVar("T")


class ResourceNotFoundException(HTTPException):
    """Exception raised when a Solr index does not contain an ID."""


class JsonFieldException(HTTPException):
    """Exception raised when a Solr index does not contain an ID."""


class SolrExceptionError(Exception):
    """Exceção do Solr."""

    def __init__(
        self, status_code: int | None = None, detail: str | None = None
    ) -> None:
        """Inicializa a exceção do Solr.

        Args:
            status_code: Código de status HTTP.
            detail: Detalhes do erro.
        """
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail or "Erro no Solr")


class RowsNotFoundException(HTTPException):
    """Exception raised when a Solr index does not contain an ID."""


class FieldInURLException(HTTPException):
    """Exception raised when a Solr index does not contain an ID."""


class CoreCreationExceptionError(HTTPException):
    """Exception raised when failing to create a core in Solr."""


def create_solr_core(
    address: str, name: str, auth: HTTPBasicAuth | None, *, force: bool = False
) -> bool:
    """Cria um core no Solr.

    Args:
        address: Endereço do Solr.
        name: Nome do core.
        auth: Autenticação.
        force: Força a criação mesmo se já existir.

    Returns:
        bool: True se criado com sucesso.

    Raises:
        CoreCreationExceptionError: Se falhar ao criar o core.
    """
    logging.debug("Criando core no solr: %s", name)

    def _core_exists_and_working(core_name: str) -> bool:
        """Verifica se o core existe e está funcionando."""
        try:
            # Tenta fazer ping no core para ver se está funcionando
            ping_url = f"{address}/solr/{core_name}/admin/ping"
            ping_response = requests.get(
                ping_url, auth=auth, verify=settings.VERIFY_SSL, timeout=10
            )

            if ping_response.status_code == requests.codes.ok:
                logging.debug("Core %s existe e está funcionando", core_name)
                return True

            # Se ping falhou, verifica status via admin API
            status_url = f"{address}/solr/admin/cores?action=STATUS&core={core_name}&indexInfo=false"
            status_response = requests.get(
                status_url, auth=auth, verify=settings.VERIFY_SSL, timeout=60
            )

            if status_response.status_code == requests.codes.ok:
                response_json = status_response.json()
                core_status = response_json.get("status", {}).get(core_name, {})

                # Verifica se o core realmente existe no status
                if core_status and "instanceDir" in core_status:
                    logging.debug(
                        "Core %s existe na admin API mas ping falhou", core_name
                    )
                    return True

            logging.debug("Core %s não existe ou não está funcionando", core_name)
            return False

        except Exception as e:
            logging.debug("Erro ao verificar core %s: %s", core_name, str(e))
            return False

    try:
        # Verifica se o core já existe e está funcionando
        if _core_exists_and_working(name) and not force:
            logging.debug("Core %s já existe e está funcionando", name)
            return True

        logging.info("Criando core %s no Solr...", name)

        create_url = f"{address}/solr/admin/cores?action=CREATE&name={name}&configSet=/var/solr/configsets/_default"
        create_response = requests.get(
            create_url, auth=auth, verify=settings.VERIFY_SSL, timeout=60
        )

        if create_response.status_code != requests.codes.ok:
            error_msg = f"Erro ao criar core {name}: status {create_response.status_code}, response: {create_response.text}"
            logging.error(error_msg)
            raise CoreCreationExceptionError(status_code=503, detail=error_msg)

        retries = 0
        while retries < MAX_RETRIES:
            if _core_exists_and_working(name):
                logging.info("Core %s criado com sucesso", name)
                return True
            time.sleep(1)
            retries += 1

        error_msg = (
            f"Timeout aguardando criação do core {name} após {MAX_RETRIES} tentativas"
        )
        logging.error(error_msg)
        raise CoreCreationExceptionError(status_code=503, detail=error_msg)

    except CoreCreationExceptionError:
        # Re-levanta exceções do próprio core creation
        raise
    except Exception as e:
        error_msg = f"Erro inesperado ao criar core {name}: {str(e)}"
        logging.exception(error_msg)
        raise CoreCreationExceptionError(status_code=503, detail=error_msg) from e


class SolrRequests:
    """Classe para requisições ao Solr."""

    @staticmethod
    def _handle_error(response: requests.Response, **kwargs: dict[str, Any]) -> None:
        """Lida com erros de requisições ao Solr.

        Args:
            response: Resposta da requisição.
            **kwargs: Argumentos adicionais.

        Raises:
            SolrExceptionError: Erro na requisição.
        """
        if response.status_code != requests.codes.ok:
            error = kwargs.get("error", DEFAULT_ERROR_MSG)
            detail = kwargs.get("detail", DEFAULT_DETAIL_MSG)
            action = kwargs.get("action", DEFAULT_ACTION_MSG)
            msg = f"Erro ao {action} no Solr: {error}, Detail: {detail}"
            raise SolrExceptionError(detail=msg)

    @staticmethod
    def check_solr_service(solr_url: str, auth: HTTPBasicAuth | None = None) -> bool:
        """Check if Solr service is available.

        Args:
            solr_url: Solr URL.
            auth: Authentication object.

        Returns:
            True if Solr service is available, False otherwise.
        """
        try:
            response = requests.get(
                solr_url, timeout=10, auth=auth, verify=settings.VERIFY_SSL
            )
        except RequestException as e:
            raise SolrExceptionError(
                status_code=503, detail="Não foi possível criar o core no Solr"
            ) from e
        else:
            return (
                response.status_code == requests.codes.ok
                and "Apache SOLR" in response.text
            )

    @staticmethod
    def check_core_exists(
        solr_url: str, core_name: str, auth: HTTPBasicAuth | None = None
    ) -> bool:
        """Check if the Solr core exists.

        Args:
            solr_url: Solr URL.
            core_name: Name of the core to check.
            auth: Authentication object.

        Returns:
            True if the core exists, False otherwise.
        """
        core_status_url = f"{solr_url}/solr/{core_name}/admin/ping"
        try:
            response = requests.get(
                core_status_url, auth=auth, timeout=10, verify=settings.VERIFY_SSL
            )
        except RequestException:
            return False
        return response.status_code == requests.codes.ok

    @staticmethod
    def post(
        url: str,
        payload: list | dict,
        headers: dict | None = None,
        nested_fields: list[str] | None = None,
        timeout: int = 60,
        auth: HTTPBasicAuth | None = None,
    ) -> dict:
        """Send a POST request to Solr.

        Args:
            url: The URL to send the request to.
            payload: The JSON payload to send.
            headers: The headers to include in the request.
            nested_fields: List of nested fields to retrieve from the response.
            timeout: Timeout for the request.
            auth: Authentication object.

        Returns:
            The parsed JSON response from Solr.
        """
        if headers is None:
            headers = {"Content-Type": "application/json; charset=utf-8"}
        if nested_fields is None:
            nested_fields = []

        try:
            http_response = requests.post(
                url=url,
                json=payload,
                headers=headers,
                timeout=timeout,
                auth=auth,
                verify=settings.VERIFY_SSL,
            )
        except ConnectionErrorRequest as exc:
            raise SolrExceptionError(status_code=503, detail=str(exc)) from exc
        except Timeout as exc:
            raise SolrExceptionError(status_code=504, detail=str(exc)) from exc
        return SolrRequests.retrieve_response(http_response, nested_fields)

    @staticmethod
    def select(
        url: str,
        nested_fields: list[str] | None = None,
        timeout: int = 60,
        params: dict | None = None,
        auth: HTTPBasicAuth | None = None,
    ) -> dict:
        """Send a SELECT request to Solr.

        Args:
            url: The URL to send the request to.
            nested_fields: List of nested fields to retrieve from the response.
            timeout: Timeout for the request.
            params: Query parameters for the request.
            auth: Authentication object.

        Returns:
            The parsed JSON response from Solr.
        """
        if nested_fields is None:
            nested_fields = []

        try:
            if params:
                http_response = requests.get(
                    url,
                    params=params,
                    timeout=timeout,
                    auth=auth,
                    verify=settings.VERIFY_SSL,
                )
            else:
                http_response = requests.get(
                    url, timeout=timeout, auth=auth, verify=settings.VERIFY_SSL
                )
        except ConnectionErrorRequest as exc:
            raise SolrExceptionError(status_code=503, detail=str(exc)) from exc
        except Timeout as exc:
            raise SolrExceptionError(status_code=504, detail=str(exc)) from exc

        return SolrRequests.retrieve_response(http_response, nested_fields)

    @staticmethod
    def retrieve_response(
        http_response: requests.Response, nested_fields: list[str] | None = None
    ) -> dict:
        """Retrieve the response from a Solr request.

        Args:
            http_response: The HTTP response object.
            nested_fields: List of nested fields to retrieve from the response.

        Returns:
            The parsed JSON response from Solr.

        Raises:
            SolrExceptionError: If the response is not valid.
            JsonFieldException: If a nested field is missing.
        """
        if nested_fields is None:
            nested_fields = []

        if isinstance(http_response, Exception):
            raise SolrExceptionError(
                status_code=503, detail=str(http_response)
            ) from http_response

        if not (
            hasattr(http_response, "status_code") and hasattr(http_response, "text")
        ):
            raise SolrExceptionError(
                status_code=500,
                detail="http_response must have the attributes: status_code and text",
            )

        if not (hasattr(http_response, "json") and callable(http_response.json)):
            raise SolrExceptionError(
                status_code=500, detail="http_response must have the method json()"
            )

        if http_response.status_code == requests.codes.not_found:
            raise SolrExceptionError(
                status_code=404,
                detail="URL for communication with Solr not found",
            )

        if http_response.status_code != requests.codes.ok:
            raise SolrExceptionError(
                status_code=http_response.status_code, detail=http_response.text
            )

        try:
            requests_json = http_response.json()
        except JSONDecodeError as exc:
            raise SolrExceptionError(status_code=502, detail=str(exc)) from exc

        ret = requests_json
        for field in nested_fields:
            try:
                ret = ret[field]
            except (IndexError, KeyError, TypeError) as exc:
                raise JsonFieldException(
                    status_code=502, detail=f"Missing field: {field}"
                ) from exc

        return ret

    @staticmethod
    def get_last_insert(url: str, auth: HTTPBasicAuth | None = None) -> dict:
        """Get the last document inserted in Solr.

        Args:
            url: Solr URL.
            auth: Authentication object.

        Returns:
            The last inserted document.
        """
        params = {
            "q": "*:*",
            "sort": "_version_ desc",
            "rows": 1,
        }
        response = SolrRequests.select(url=url, params=params, auth=auth)
        docs = response["response"].get("docs", [])
        return docs[0] if docs else {}
