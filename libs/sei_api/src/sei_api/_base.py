from __future__ import annotations

import json
import logging
from collections.abc import Callable

import pandas as pd
import requests
from requests.exceptions import HTTPError, JSONDecodeError, RequestException, Timeout
from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .config import SeiApiConfig
from .exceptions import SeiApiError, SeiApiTimeoutError

logger = logging.getLogger(__name__)

_REQUEST_ERROR_PREFIX = "Falha na requisição à API SEI: "


def _is_retryable(exc: BaseException, *, include_json: bool = False) -> bool:
    """Política de retry do transporte: timeout e 5xx/conn repetem."""
    if isinstance(exc, Timeout):
        return True
    if isinstance(exc, (JSONDecodeError, json.JSONDecodeError)):
        return include_json
    if isinstance(exc, HTTPError):
        status = getattr(exc.response, "status_code", None)
        return status is not None and 500 <= status < 600
    if isinstance(exc, RequestException):
        return getattr(exc, "response", None) is None
    return False


def _decode_json_body(content: bytes) -> dict:
    """Decodifica um corpo JSON da API SEI tolerando encodings Windows/Latin.

    Fallback deliberado: a API do SEI às vezes responde JSON que não é UTF-8
    (ex.: byte 0xf5 = "õ"). Cascata:

    1. ``json.loads`` direto nos bytes — a stdlib detecta UTF-8 e remove BOM
       (corpos ``\xef\xbb\xbf{...}`` de origem .NET parseiam);
    2. cp1252 — pontuação Windows (aspas curvas 0x93/0x94, travessão) vira o
       Unicode correto em vez de caracteres de controle C1 invisíveis;
    3. Latin-1 — decode total, nunca falha.

    JSON realmente inválido levanta ``json.JSONDecodeError`` em todos os
    caminhos, preservando o contrato dos chamadores.
    """
    try:
        return json.loads(content)
    except UnicodeDecodeError:
        pass  # corpo não é UTF-8 (SEI legado); tenta encodings Windows/Latin
    try:
        return json.loads(content.decode("cp1252"))
    except UnicodeDecodeError:
        return json.loads(content.decode("latin-1"))


class BaseSeiClient:
    """Núcleo de transporte do cliente SEI. Retry via tenacity, parse em cima.

    ``_request_raw`` aplica o retry e devolve a ``Response`` crua (não levanta em
    4xx). ``_request_json`` valida status e decodifica. Métodos com semântica
    "404 = vazio" passam por ``_request_json(..., empty_statuses=(404,))`` e ainda
    herdam o retry de ``Timeout``/5xx.
    """

    def __init__(
        self,
        config: SeiApiConfig,
        *,
        timeout_exc_factory: Callable[[str], BaseException] | None = None,
        content_extractor: Callable[[str, str], str] | None = None,
    ):
        self.config = config
        self._timeout_exc_factory = timeout_exc_factory or (
            lambda document_id: SeiApiTimeoutError(document_id=document_id)
        )
        self._content_extractor = content_extractor

    def _build_api_url(self, service_endpoint: str) -> str:
        return f"{self.config.base_url}/{service_endpoint}"

    def _build_params(
        self, service_endpoint: str, extra_params: dict | None = None
    ) -> dict:
        params = {
            "servico": service_endpoint,
            "SiglaSistema": self.config.sigla_sistema,
            "IdentificacaoServico": self.config.identificacao_servico,
        }
        if extra_params:
            params.update(extra_params)
        return params

    def _do_request(
        self,
        method: str,
        url: str,
        params: dict,
        headers: dict | None = None,
    ) -> requests.Response:
        """Faz a requisição e levanta só em 5xx, para o retryer pegar.

        4xx volta como ``Response`` para o chamador decidir (``_request_json``
        valida status; os métodos de download levantam via ``raise_for_status``).
        """
        response = requests.request(
            method,
            url,
            params=params,
            headers=headers,
            verify=self.config.verify_ssl,
            timeout=self.config.timeout_s,
        )
        if 500 <= response.status_code < 600:
            response.raise_for_status()
        return response

    def _run_with_retry(
        self,
        request_fn: Callable[[], object],
        document_id_hint: str,
        *,
        include_json: bool = False,
    ) -> object:
        """Aplica a política de retry (Timeout/5xx/conn) sobre ``request_fn``.

        Fonte única do retry + mapeamento de erro: Timeout esgotado vira o erro
        do ``timeout_exc_factory`` (HTTP 412 no app); qualquer outra
        ``RequestException`` vira ``SeiApiError`` com o token anonimizado.
        Tanto ``_request_raw`` quanto os downloads binários passam por aqui.
        """
        cfg = self.config
        retryer = Retrying(
            stop=stop_after_attempt(max(cfg.max_retries, 1)),
            wait=wait_exponential(
                multiplier=cfg.backoff_initial_wait, exp_base=cfg.retry_backoff_factor
            ),
            retry=retry_if_exception(
                lambda exc: _is_retryable(exc, include_json=include_json)
            ),
            reraise=True,
        )
        try:
            return retryer(request_fn)
        except Timeout as timeout_exc:
            logger.exception(
                f"Timeout da API SEI ao consultar {document_id_hint} após "
                f"{cfg.max_retries} tentativas"
            )
            raise self._timeout_exc_factory(document_id_hint) from timeout_exc
        except RequestException as req_exc:
            status = getattr(getattr(req_exc, "response", None), "status_code", None)
            sei_exc = SeiApiError.from_source_exc(
                req_exc, status_code=status or 500, prefix=_REQUEST_ERROR_PREFIX
            )
            logger.exception(sei_exc.detail)
            raise sei_exc from req_exc

    def _request_raw(
        self,
        service_endpoint: str,
        *,
        extra_params: dict | None = None,
        document_id_hint: str = "unknown",
    ) -> requests.Response:
        """GET com retry (Timeout/5xx/conn). Devolve a ``Response`` sem levantar em 4xx."""
        url = self._build_api_url(service_endpoint)
        params = self._build_params(service_endpoint, extra_params)
        return self._run_with_retry(
            lambda: self._do_request("GET", url, params), document_id_hint
        )  # type: ignore[return-value]

    def _request_json(
        self,
        service_endpoint: str,
        *,
        extra_params: dict | None = None,
        document_id_hint: str = "unknown",
        empty_statuses: tuple[int, ...] = (),
    ) -> dict:
        """GET + retry, validando status e decodificando JSON.

        ``empty_statuses`` devolve ``{"data": []}`` nesses códigos em vez de
        levantar (caso "não encontrado = vazio"), preservando o retry no caminho
        de erro real.
        """

        def request_and_decode() -> dict:
            url = self._build_api_url(service_endpoint)
            params = self._build_params(service_endpoint, extra_params)
            response = self._do_request("GET", url, params)
            if response.status_code in empty_statuses:
                return {"data": []}
            response.raise_for_status()
            return _decode_json_body(response.content)

        try:
            return self._run_with_retry(
                request_and_decode,
                document_id_hint,
                include_json=True,
            )  # type: ignore[return-value]
        except HTTPError as http_exc:
            status = getattr(http_exc.response, "status_code", None)
            sei_exc = SeiApiError.from_source_exc(
                http_exc, status_code=status or 500, prefix=_REQUEST_ERROR_PREFIX
            )
            logger.exception(sei_exc.detail)
            raise sei_exc from http_exc
        except json.JSONDecodeError as json_exc:
            msg = f"Resposta inválida da API SEI (JSON mal formado): {json_exc}"
            logger.exception(msg)
            # requests.codes.* é sempre int; o stub de types-requests o tipa como
            # int | None, gerando falso-positivo de arg-type no mypy.
            raise SeiApiError(
                status_code=requests.codes.bad_gateway,  # type: ignore[arg-type]
                detail=msg,
            ) from json_exc

    def _parse_records(
        self, payload: dict, columns: list, parse_single: Callable[[dict], dict]
    ) -> pd.DataFrame:
        api_docs = payload.get("data", [])
        if not api_docs:
            return pd.DataFrame(columns=columns)
        return pd.DataFrame([parse_single(doc) for doc in api_docs])
