"""solr_handlers module."""

from collections.abc import Callable
from typing import Any

import pandas as pd
import requests
from requests.exceptions import ConnectionError, JSONDecodeError, Timeout

from jobs.dags.database.create_solr_core import create_solr_core
from jobs.dags.logger import logger
from jobs.envs import (
    DEFAULT_REQUEST_TIMEOUT,
    MLT_DOCUMENTS_CONFIGSET,
    MLT_PROCESS_CONFIGSET,
    VERIFY_SSL,
)
from jobs.exception_handling.exceptions import (
    FieldInURLException,
    JsonFieldException,
    RowsNotFoundException,
    SolrException,
)
from jobs.utils.funcs import add_param_on_url_if_not_exists


class SolrHandlers:
    """Class for Solr handlers."""

    @staticmethod
    def query_pagination(
        solr_url: str,
        solr_core: str,
        parameters: dict[str, Any],
        process_result_callback: Callable[[list], pd.DataFrame],
        auth: tuple[str, str] | None = None,
    ) -> pd.DataFrame:
        """Queries Solr and processes the results using a callback function.

        Args:
            solr_url (str): URL of the Solr instance.
            solr_core (str): Solr core to query.
            parameters (dict): Parameters for the Solr query.
            process_result_callback (function): Callback function to process the results.

        Returns:
            pd.DataFrame: A pandas DataFrame with the processed results.
        """
        df_result = pd.DataFrame([], columns=parameters["fl"].split(", "))
        start = 0
        num_found = SolrHandlers.count(
            solr_core=solr_core, solr_url=solr_url, auth=auth
        )
        while start <= num_found and num_found != 0:
            parameters["start"] = start
            response = requests.get(
                f"{solr_url}/solr/{solr_core}/select",
                params=parameters,
                auth=auth,
                verify=VERIFY_SSL,
                timeout=DEFAULT_REQUEST_TIMEOUT,
            ).json()
            docs = response.get("response", {}).get("docs", [])
            df_result = pd.concat(
                [df_result, process_result_callback(docs)], axis=0, ignore_index=True
            )
            start += parameters["rows"]
        return df_result

    @staticmethod
    def process_indexed(
        solr_url: str,
        solr_core: str,
        batch_size: int,
        auth: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        create_solr_core(solr_url, solr_core, MLT_PROCESS_CONFIGSET, auth=auth)
        parameters = {
            "fl": "id_protocolo, list_documents, id_type_process",
            "indent": "true",
            "q.op": "OR",
            "q": "*:*",
            "rows": batch_size,
        }
        result = SolrHandlers.query_pagination(
            solr_url,
            solr_core,
            parameters,
            lambda docs: (
                pd.DataFrame(docs)
                .explode("list_documents")
                .rename({"list_documents": "id_document"}, axis=1)
                .assign(
                    id_protocolo=lambda df: df["id_protocolo"].fillna(0).astype(int),
                    id_type_process=lambda df: (
                        df["id_type_process"].fillna(0).astype(int)
                    ),
                    id_document=lambda df: df["id_document"].fillna(0).astype(int),
                )
                .drop_duplicates(subset=["id_protocolo", "id_document"])
            ),
            auth=auth,
        )
        return result.drop("list_documents", axis=1).to_dict(orient="records")

    @staticmethod
    def jurisprudence_indexed(
        solr_url: str,
        solr_core: str,
        batch_size: int,
        auth: tuple[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        create_solr_core(solr_url, solr_core, MLT_DOCUMENTS_CONFIGSET, auth=auth)
        parameters = {
            "fl": "id_document",
            "indent": "true",
            "q.op": "OR",
            "q": "*:*",
            "rows": batch_size,
        }
        return SolrHandlers.query_pagination(
            solr_url,
            solr_core,
            parameters,
            lambda docs: pd.DataFrame(docs).assign(
                id_document=lambda df: df["id_document"].astype(int)
            ),
            auth=auth,
        ).to_dict(orient="records")

    @staticmethod
    def drop_by_field(
        id_values: list[Any],
        solr_url: str,
        solr_core: str,
        field: str = "id_protocolo",
        auth: tuple[str, str] | None = None,
    ) -> None:
        """Remove processes from Solr by a list of id_values."""
        if not isinstance(id_values, list):
            id_values = [id_values]

        str_id_values = (
            "<delete> "
            + "".join([f"<query>{field}:{id_value}</query>" for id_value in id_values])
            + "</delete>"
        )
        response = requests.post(
            f"{solr_url}/solr/{solr_core}/update?commit=true",
            headers={"Content-Type": "text/xml"},
            data=str_id_values,
            auth=auth,
            verify=VERIFY_SSL,
            timeout=DEFAULT_REQUEST_TIMEOUT,
        )

        if response.status_code == requests.codes.ok:
            logger.info("Registros removidos do Solr")
        else:
            logger.error(
                f"Falha ao remover Registros no Solr, \
                            status code: {response.status_code} \
                        response: {response.text}"
            )

    @staticmethod
    def count(
        solr_url: str, solr_core: str, auth: tuple[str, str] | None = None
    ) -> int:
        params = {"fl": "*", "indent": "true", "q": "*:*", "rows": 0}
        response = requests.get(
            f"{solr_url}/solr/{solr_core}" + "/select",
            params=params,
            auth=auth,
            verify=VERIFY_SSL,
            timeout=DEFAULT_REQUEST_TIMEOUT,
        )
        if response.status_code != requests.codes.ok:
            logger.error(
                f"Falha na contagem de numero de processos no Solr, \
                            status code: {response.status_code} \
                        response: {response.text}"
            )
        return response.json()["response"]["numFound"]

    @staticmethod
    def check_solr_service(solr_url: str, auth: tuple[str, str] | None = None) -> bool:
        try:
            response = requests.get(solr_url, timeout=10, auth=auth, verify=VERIFY_SSL)
            return (
                response.status_code == requests.codes.ok
                and "Apache SOLR" in response.text
            )
        except Exception:
            return False

    @staticmethod
    def check_core_exists(
        solr_url: str, core_name: str, auth: tuple[str, str] | None = None
    ) -> bool:
        core_status_url = f"{solr_url}/solr/{core_name}/admin/ping"
        try:
            response = requests.get(
                core_status_url, auth=auth, verify=VERIFY_SSL, timeout=30
            )
        except Exception:
            return False
        return response.status_code == requests.codes.ok

    @staticmethod
    def post(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        nested_fields: list[str] | None = None,
        auth: tuple[str, str] | None = None,
        timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> Any:
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
                verify=VERIFY_SSL,
            )
        except ConnectionError as exc:
            raise SolrException(status_code=503, detail=str(exc)) from exc
        except Timeout as exc:
            raise SolrException(status_code=504, detail=str(exc)) from exc
        return SolrHandlers.retrieve_response(http_response, nested_fields)

    @staticmethod
    def get(
        url: str,
        nested_fields: list[str] | None = None,
        timeout: int = DEFAULT_REQUEST_TIMEOUT,
        params: dict[str, Any] | None = None,
        start: int | None = None,
        rows: int | None = None,
        auth: tuple[str, str] | None = None,
    ) -> Any:
        if nested_fields is None:
            nested_fields = []
        if not rows:
            raise RowsNotFoundException("Numero de rows nao definido")

        if "rows" in url:
            raise FieldInURLException(
                "O campo 'rows' deve ser usado como paramentro do metodo"
            )

        if "start" in url:
            raise FieldInURLException(
                "O campo 'start' deve ser usado como paramentro do metodo"
            )

        if not start:
            start = 0
        url = add_param_on_url_if_not_exists(
            url=url, param_name="rows", param_value=rows
        )
        url = add_param_on_url_if_not_exists(
            url=url, param_name="start", param_value=start
        )
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

        return SolrHandlers.retrieve_response(http_response, nested_fields)

    @staticmethod
    def select(
        url: str,
        nested_fields: list[str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: int = DEFAULT_REQUEST_TIMEOUT,
        k_results: int | None = None,
        batch_size: int = 700,
        auth: tuple[str, str] | None = None,
    ) -> Any:
        if nested_fields is None:
            nested_fields = []
        numFound = SolrHandlers.get(
            url=url, nested_fields=["response", "numFound"], start=0, rows=1, auth=auth
        )
        http_response = []
        for start in range(0, numFound, batch_size):
            if k_results and len(http_response) >= k_results:
                break
            batch_response = SolrHandlers.get(
                url=url,
                nested_fields=nested_fields,
                params=params,
                timeout=DEFAULT_REQUEST_TIMEOUT,
                start=start,
                rows=batch_size,
                auth=auth,
            )
            http_response.extend(batch_response)
        if k_results:
            return http_response[:k_results]

        return http_response

    @staticmethod
    def delete(url: str, auth: tuple[str, str] | None = None) -> Any:
        try:
            http_response = requests.get(
                url, auth=auth, verify=VERIFY_SSL, timeout=DEFAULT_REQUEST_TIMEOUT
            )
        except ConnectionError as exc:
            raise SolrException(status_code=503, detail=str(exc)) from exc
        except Timeout as exc:
            raise SolrException(status_code=504, detail=str(exc)) from exc
        return SolrHandlers.retrieve_response(http_response, [])

    @staticmethod
    def retrieve_response(
        http_response: requests.Response, nested_fields: list[str]
    ) -> Any:
        if isinstance(http_response, Exception):
            raise SolrException(
                status_code=503, detail=str(http_response)
            ) from http_response

        if not (
            hasattr(http_response, "status_code") and hasattr(http_response, "text")
        ):
            raise SolrException(
                status_code=500,
                detail="http_response must have the attributes: status_code and text",
            )

        if not (hasattr(http_response, "json") and callable(http_response.json)):
            raise SolrException(
                status_code=500, detail="http_response must have the method json()"
            )

        if http_response.status_code == requests.codes.not_found:
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
                    status_code=requests.codes.bad_gateway, field=field
                ) from exc

        return ret
