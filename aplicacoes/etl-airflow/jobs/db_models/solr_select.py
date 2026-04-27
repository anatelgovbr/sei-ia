"""Solr select module."""

import logging
from typing import Any

import requests
from requests.exceptions import ConnectionError, JSONDecodeError, Timeout

from jobs.envs import DEFAULT_REQUEST_TIMEOUT, VERIFY_SSL
from jobs.exception_handling.exceptions import JsonFieldException, SolrException

logger = logging.getLogger(__name__)


class SolrRequests:
    """Solr requests handler."""

    @staticmethod
    def check_solr_service(solr_url: str, auth: tuple[str, str] | None = None) -> bool:
        try:
            response = requests.get(solr_url, timeout=10, auth=auth, verify=VERIFY_SSL)
            return response.status_code == 200 and "Apache SOLR" in response.text
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
        return response.status_code == 200

    @staticmethod
    def post(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        nested_fields: list[str] | None = None,
        timeout: int = DEFAULT_REQUEST_TIMEOUT,
        auth: tuple[str, str] | None = None,
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
        return SolrRequests.retrieve_response(http_response, nested_fields)

    @staticmethod
    def select(
        url: str,
        nested_fields: list[str] | None = None,
        timeout: int = DEFAULT_REQUEST_TIMEOUT,
        params: dict[str, Any] | None = None,
        auth: tuple[str, str] | None = None,
    ) -> Any:
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
    def retrieve_response(
        http_response: requests.Response, nested_fields: list[str] | None = None
    ) -> Any:
        if nested_fields is None:
            nested_fields = []
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
                status_code=404, detail="URL de comunicacao com o Solr nao encontrado"
            )

        if http_response.status_code != requests.codes.ok:
            raise SolrException(
                status_code=http_response.status_code, detail=http_response.text
            )

        try:
            requests_json = http_response.json()
        except JSONDecodeError as exc:
            raise SolrException(status_code=502, detail=str(exc)) from exc

        ret = requests_json
        for field in nested_fields:
            try:
                ret = ret[field]
            except (IndexError, KeyError, TypeError) as exc:
                raise JsonFieldException(status_code=502, field=field) from exc

        return ret
