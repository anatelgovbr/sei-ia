from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import pandas as pd
import requests

from .config import SeiApiConfig


class _ClientInternals(Protocol):
    config: SeiApiConfig
    _timeout_exc_factory: Callable[[str], BaseException]
    _content_extractor: Callable[[str, str], str] | None

    def _build_api_url(self, service_endpoint: str) -> str: ...

    def _build_params(
        self, service_endpoint: str, extra_params: dict | None = None
    ) -> dict: ...

    def _do_request(
        self,
        method: str,
        url: str,
        params: dict,
        headers: dict | None = None,
    ) -> requests.Response: ...

    def _run_with_retry(
        self,
        request_fn: Callable[[], requests.Response],
        document_id_hint: str,
    ) -> requests.Response: ...

    def _request_raw(
        self,
        service_endpoint: str,
        *,
        extra_params: dict | None = None,
        document_id_hint: str = "unknown",
    ) -> requests.Response: ...

    def _request_json(
        self,
        service_endpoint: str,
        *,
        extra_params: dict | None = None,
        document_id_hint: str = "unknown",
        empty_statuses: tuple[int, ...] = (),
    ) -> dict: ...

    def _parse_records(
        self,
        payload: dict,
        columns: list[Any],
        parse_single: Callable[[dict], dict],
    ) -> pd.DataFrame: ...

    def run_async(self, coro: Any, timeout: float | None = None) -> Any: ...

    def md_ia_download_arquivo_documento_externo(
        self,
        id_documento: str,
        doc_extension: str,
        id_anexo: int | None = None,
    ) -> str: ...

    def md_ia_consulta_documento(
        self,
        id_documentos: str,
        sin_filtra_documentos_relevantes: str = "N",
        sin_filtra_bloqueados: str = "N",
        sin_filtra_ativos: str = "N",
    ) -> pd.DataFrame: ...

    async def md_ia_consulta_documento_async(
        self,
        id_documentos: str,
        sin_filtra_documentos_relevantes: str = "N",
        sin_filtra_bloqueados: str = "N",
        sin_filtra_ativos: str = "N",
    ) -> pd.DataFrame: ...

    async def md_ia_consulta_conteudo_documento_async(
        self,
        id_documento: str,
    ) -> dict: ...
