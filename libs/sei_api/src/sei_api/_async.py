from __future__ import annotations

import asyncio
import json
import logging
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree.ElementTree import ParseError as XMLParseError

import defusedxml.ElementTree as defusedET
import httpx
import pandas as pd
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from sei_extraction.formatting import format_email_with_attachments

from ._base import _decode_json_body
from .exceptions import SeiApiError

if TYPE_CHECKING:
    from ._protocol import _ClientInternals

    _Base = _ClientInternals
else:
    _Base = object

logger = logging.getLogger(__name__)

_REQUEST_ERROR_PREFIX = "Falha na requisição à API SEI: "
_ACCEPT_JSON = {"accept": "application/json"}

_CONTENT_ENDPOINT_EXCLUDE: frozenset[str] = frozenset(
    {"ConteudoDocumento", "IdAnexos", "TipoConteudo"}
)
_METADATA_ENDPOINT_EXCLUDE: frozenset[str] = frozenset(
    {
        "IdProcedimento",
        "IdTipoDocumento",
        "IdDocumento",
        "StaTipoDocumento",
        "SinArmazenarCache",
    }
)


def _is_retryable_async(exc: BaseException, *, include_json: bool = False) -> bool:
    """Política de retry assíncrona: Timeout e 5xx/conn repetem; 4xx não."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, json.JSONDecodeError):
        return include_json
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or 500 <= status < 600
    if isinstance(exc, httpx.HTTPError):
        return getattr(exc, "response", None) is None
    return False


def _sanitize_html_field(value: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", text).strip()


class AsyncMixin(_Base):
    """Async HTTP layer for the SEI API client.

    Composes with ``BaseSeiClient`` via multiple inheritance.
    Reads ``self.config``, ``self._build_api_url``, ``self._build_params``,
    ``self._timeout_exc_factory``, ``self._content_extractor``, and
    ``self._parse_records`` from the base.
    """

    # ------------------------------------------------------------------
    # Sync→async bridge
    # ------------------------------------------------------------------

    def run_async(self, coro, timeout: float | None = None):
        """Run ``coro`` regardless of whether a loop is already running.

        No running loop (Airflow, scripts): delegates to ``asyncio.run()``.
        Running loop present (FastAPI endpoints): spawns a ``ThreadPoolExecutor``
        so the coroutine gets its own loop in a fresh thread.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(coro)).result(timeout)

    # ------------------------------------------------------------------
    # Async HTTP transport
    # ------------------------------------------------------------------

    def _async_client(self) -> httpx.AsyncClient:
        """Create a configured ``httpx.AsyncClient`` from ``self.config``."""
        cfg = self.config
        limits = httpx.Limits(
            max_connections=cfg.max_concurrency,
            max_keepalive_connections=cfg.max_concurrency,
        )
        return httpx.AsyncClient(
            limits=limits,
            verify=cfg.verify_ssl,
            timeout=cfg.timeout_s,
        )

    async def _do_get_async(self, url: str, params: dict) -> httpx.Response:
        async with self._async_client() as client:
            response = await client.get(url, params=params, headers=_ACCEPT_JSON)
        if response.status_code == 429 or 500 <= response.status_code < 600:
            response.raise_for_status()
        return response

    async def _request_raw_async(
        self,
        endpoint: str,
        *,
        extra_params: dict | None = None,
        document_id_hint: str = "unknown",
    ) -> httpx.Response:
        """GET with retry (Timeout/5xx/conn). Returns the ``Response`` without raising on 4xx."""
        url = self._build_api_url(endpoint)
        params = self._build_params(endpoint, extra_params)
        return await self._run_with_retry_async(
            self._do_get_async,
            url,
            params,
            document_id_hint=document_id_hint,
        )

    async def _run_with_retry_async(
        self,
        request_fn,
        url: str,
        params: dict,
        *,
        document_id_hint: str,
        include_json: bool = False,
    ):
        cfg = self.config
        retryer = AsyncRetrying(
            stop=stop_after_attempt(max(cfg.max_retries, 1)),
            wait=wait_exponential(
                multiplier=cfg.backoff_initial_wait, exp_base=cfg.retry_backoff_factor
            ),
            retry=retry_if_exception(
                lambda exc: _is_retryable_async(exc, include_json=include_json)
            ),
            reraise=True,
        )
        try:
            return await retryer(request_fn, url, params)
        except httpx.TimeoutException as timeout_exc:
            logger.exception(
                "Timeout da API SEI ao consultar %s após %d tentativas",
                document_id_hint,
                cfg.max_retries,
            )
            raise self._timeout_exc_factory(document_id_hint) from timeout_exc
        except httpx.HTTPError as http_exc:
            status = getattr(getattr(http_exc, "response", None), "status_code", None)
            sei_exc = SeiApiError.from_source_exc(
                http_exc, status_code=status or 500, prefix=_REQUEST_ERROR_PREFIX
            )
            logger.exception(sei_exc.detail)
            raise sei_exc from http_exc

    async def _request_json_async(
        self,
        endpoint: str,
        *,
        extra_params: dict | None = None,
        document_id_hint: str = "unknown",
        empty_statuses: tuple[int, ...] = (),
    ) -> dict:
        """GET + retry, validating status and decoding JSON.

        ``empty_statuses`` returns ``{"data": []}`` on those codes instead of
        raising, preserving retry on real error paths.
        """

        async def request_and_decode(url: str, params: dict) -> dict:
            response = await self._do_get_async(url, params)
            if response.status_code in empty_statuses:
                return {"data": []}
            response.raise_for_status()
            return _decode_json_body(response.content)

        try:
            return await self._run_with_retry_async(
                request_and_decode,
                self._build_api_url(endpoint),
                self._build_params(endpoint, extra_params),
                document_id_hint=document_id_hint,
                include_json=True,
            )
        except httpx.HTTPStatusError as http_exc:
            status = http_exc.response.status_code
            sei_exc = SeiApiError.from_source_exc(
                http_exc, status_code=status, prefix=_REQUEST_ERROR_PREFIX
            )
            logger.exception(sei_exc.detail)
            raise sei_exc from http_exc
        except json.JSONDecodeError as json_exc:
            msg = f"Resposta inválida da API SEI (JSON mal formado): {json_exc}"
            logger.exception(msg)
            raise SeiApiError(status_code=502, detail=msg) from json_exc

    # ------------------------------------------------------------------
    # md_ia_consulta_conteudo_documento_async
    # ------------------------------------------------------------------

    async def md_ia_consulta_conteudo_documento_async(
        self,
        id_documento: str,
    ) -> dict:
        """Fetch raw content for a single document, with retry and email attachment support.

        Returns a dict with keys:
          ``id_documento``, ``tipo_conteudo``, ``content_doc``, ``extra_metadata``.

        404 returns ``{"id_documento": …, "content_doc": None}`` without raising.
        Retry is delegated to ``_request_raw_async`` (Timeout/5xx/429).
        """
        response = await self._request_raw_async(
            "md_ia_consulta_conteudo_documento",
            extra_params={"IdDocumento": id_documento},
            document_id_hint=id_documento,
        )

        if response.status_code == 404:
            logger.warning(
                "Conteúdo do documento %s não encontrado (404)", id_documento
            )
            return {"id_documento": id_documento, "content_doc": None}

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as http_exc:
            status = http_exc.response.status_code
            sei_exc = SeiApiError.from_source_exc(
                http_exc, status_code=status, prefix=_REQUEST_ERROR_PREFIX
            )
            logger.exception(sei_exc.detail)
            raise sei_exc from http_exc

        if not response.content:
            return {"id_documento": id_documento, "content_doc": None}

        try:
            api_response = _decode_json_body(response.content)
        except Exception as json_exc:
            msg = f"Resposta inválida da API SEI (JSON mal formado): {json_exc}"
            logger.exception(msg)
            raise SeiApiError(status_code=502, detail=msg) from json_exc
        data = api_response.get("data", {})

        content_doc = data.get("ConteudoDocumento")
        extra_metadata = {
            k: _sanitize_html_field(str(v)) if isinstance(v, str) else str(v)
            for k, v in data.items()
            if k not in _CONTENT_ENDPOINT_EXCLUDE and v is not None
        }

        if data.get("IdAnexos"):
            if self._content_extractor is None:
                raise SeiApiError(
                    status_code=500,
                    detail=(
                        f"Documento {id_documento} possui anexos mas nenhum "
                        "content_extractor foi injetado no cliente. "
                        "Passe content_extractor=(path, ext) -> str ao construir SeiApiClient."
                    ),
                )

            try:
                root = defusedET.fromstring(content_doc or "")
                anexos = root.findall(".//atributo[@nome='Anexos']/valores/valor")
                anexo_map = {
                    val.get("id"): val.text
                    for val in anexos
                    if val.get("id") and val.text
                }
            except (XMLParseError, ET.ParseError) as xml_exc:
                logger.warning(
                    "Erro ao parsear XML para anexos do documento %s: %s",
                    id_documento,
                    xml_exc,
                )
                anexo_map = {}

            attachments: list[tuple[int, str, str | None]] = []
            for idx, id_anexo in enumerate(data["IdAnexos"], start=1):
                filename = anexo_map.get(str(id_anexo), f"anexo_{id_anexo}.unknown")
                extension = Path(filename).suffix.lstrip(".").lower()
                try:
                    save_path = self.md_ia_download_arquivo_documento_externo(
                        id_documento, extension, id_anexo
                    )
                    anexo_text = self._content_extractor(save_path, extension)
                    attachments.append((idx, filename, anexo_text))
                    Path(save_path).unlink(missing_ok=True)
                except Exception:
                    logger.exception(
                        "Erro ao processar anexo %s do documento %s",
                        id_anexo,
                        id_documento,
                    )

            content_doc = format_email_with_attachments(content_doc, attachments)

        return {
            "id_documento": id_documento,
            "tipo_conteudo": data.get("TipoConteudo"),
            "content_doc": content_doc,
            "extra_metadata": extra_metadata,
        }

    # ------------------------------------------------------------------
    # md_ia_consulta_documento_async
    # ------------------------------------------------------------------

    async def md_ia_consulta_documento_async(
        self,
        id_documentos: str,
        sin_filtra_documentos_relevantes: str = "N",
        sin_filtra_bloqueados: str = "N",
        sin_filtra_ativos: str = "N",
    ) -> pd.DataFrame:
        """Async fetch of document metadata for one or more document IDs.

        Mirrors the sync ``md_ia_consulta_documento`` column set.
        """
        import html as html_lib  # noqa: PLC0415

        service_endpoint = "md_ia_consulta_documento"
        columns = [
            "id_protocolo",
            "num_doc",
            "documento_especificacao",
            "id_type_document",
            "content_doc",
            "formato_arquivo",
            "dta_inclusao",
            "name_id_type_doc",
            "id_protocolo_documento",
            "type_doc",
            "num_proc",
            "sin_armazena_cache",
            "extra_metadata",
        ]

        def parse(doc: dict) -> dict:
            extra_metadata = {
                k: html_lib.unescape(_sanitize_html_field(str(v)))
                if k == "Assinaturas"
                else (_sanitize_html_field(str(v)) if isinstance(v, str) else str(v))
                for k, v in doc.items()
                if k not in _METADATA_ENDPOINT_EXCLUDE and v is not None and v != ""
            }
            return {
                "id_protocolo": int(doc["IdProcedimento"]),
                "num_doc": doc["NumeroDocumento"],
                "documento_especificacao": doc.get("EspecificacaoDocumento", ""),
                "id_type_document": int(doc["IdTipoDocumento"]),
                # Espelha o sync md_ia_consulta_documento: content_doc em branco
                # (este endpoint só traz metadado). Mantém o shape idêntico entre
                # os dois siblings — a coluna já consta em `columns` acima.
                "content_doc": "",
                "formato_arquivo": doc["NomeArquivo"],
                "dta_inclusao": pd.to_datetime(doc["DataInclusao"], dayfirst=True),
                "name_id_type_doc": doc.get("NomeTipoDocumento", ""),
                "id_protocolo_documento": int(doc["IdDocumento"]),
                "type_doc": doc["StaTipoDocumento"],
                "num_proc": doc["NumeroProcesso"],
                "sin_armazena_cache": doc.get("SinArmazenarCache", "S"),
                "extra_metadata": extra_metadata,
            }

        payload = await self._request_json_async(
            service_endpoint,
            extra_params={
                "SinFiltraDocumentosRelevantes": sin_filtra_documentos_relevantes,
                "SinFiltraBloqueados": sin_filtra_bloqueados,
                "SinFiltraAtivos": sin_filtra_ativos,
                "IdDocumentos": id_documentos,
            },
            document_id_hint=id_documentos,
        )
        return self._parse_records(payload, columns, parse)

    # ------------------------------------------------------------------
    # md_ia_consulta_processo_async
    # ------------------------------------------------------------------

    async def md_ia_consulta_processo_async(
        self,
        id_procedimentos: str,
    ) -> pd.DataFrame:
        """Async fetch of process metadata for one or more procedure IDs."""
        service_endpoint = "md_ia_consulta_processo"
        payload = await self._request_json_async(
            service_endpoint,
            extra_params={
                "SinFiltraAtivos": "N",
                "SinFiltraBloqueados": "N",
                "SinFiltraDocumentosRelevantes": "N",
                "IdProcedimentos": id_procedimentos,
            },
            document_id_hint=id_procedimentos,
        )
        data_list = payload.get("data", [])

        data_list_to_parse: list[dict] = []
        for data in data_list:
            protocolo_formatado = data.get("NumeroProcesso") or ""
            processo_especificacao = data.get("EspecificacaoProcesso") or ""
            nome_id_tipo_processo = data.get("TipoProcesso") or ""
            sigla_unid = data.get("SiglaUnidadeGeradoraProcesso") or ""
            desc_unid = data.get("DescricaoUnidadeGeradoraProcesso") or ""

            processos_pai = data.get("ProcessosPaiRelacionado") or []
            processos_filho = data.get("ProcessosFilhoRelacionado") or []

            base = {
                "id_procedimento": data.get("IdProcedimento"),
                "id_protocolo_formatado": protocolo_formatado,
                "processo_especificacao": processo_especificacao,
                "nome_id_tipo_processo": nome_id_tipo_processo,
                "sigla_unid": sigla_unid,
                "desc_unid": desc_unid,
            }

            if processos_pai and processos_filho:
                for pai in processos_pai:
                    for filho in processos_filho:
                        data_list_to_parse.append(
                            {
                                **base,
                                "rp1p_descricao": pai.get("Especificacao", ""),
                                "rp2p_descricao": filho.get("Especificacao", ""),
                                "rp1u_sigla": pai.get(
                                    "SiglaUnidadeGeradoraProcesso", ""
                                ),
                                "rp2u_sigla": filho.get(
                                    "SiglaUnidadeGeradoraProcesso", ""
                                ),
                            }
                        )
            elif processos_pai:
                for pai in processos_pai:
                    data_list_to_parse.append(
                        {
                            **base,
                            "rp1p_descricao": pai.get("Especificacao") or "",
                            "rp2p_descricao": "",
                            "rp1u_sigla": pai.get("SiglaUnidadeGeradoraProcesso") or "",
                            "rp2u_sigla": "",
                        }
                    )
            elif processos_filho:
                for filho in processos_filho:
                    data_list_to_parse.append(
                        {
                            **base,
                            "rp1p_descricao": "",
                            "rp2p_descricao": filho.get("Especificacao") or "",
                            "rp1u_sigla": "",
                            "rp2u_sigla": filho.get("SiglaUnidadeGeradoraProcesso")
                            or "",
                        }
                    )
            else:
                data_list_to_parse.append(
                    {
                        **base,
                        "rp1p_descricao": "",
                        "rp2p_descricao": "",
                        "rp1u_sigla": "",
                        "rp2u_sigla": "",
                    }
                )

        return pd.DataFrame(data_list_to_parse)

    # ------------------------------------------------------------------
    # md_ia_consulta_processo_batch
    # ------------------------------------------------------------------

    async def md_ia_consulta_processo_batch(
        self,
        id_procedimentos: list[str],
        batch_size: int = 100,
    ) -> pd.DataFrame:
        """Fetch process metadata for a list of IDs, chunked by ``batch_size``."""
        if not id_procedimentos:
            return pd.DataFrame()

        chunk_size = max(1, min(batch_size, self.config.chunk_size))
        chunks = [
            id_procedimentos[i : i + chunk_size]
            for i in range(0, len(id_procedimentos), chunk_size)
        ]

        if len(chunks) == 1:
            id_proc_str = ",".join(str(p) for p in chunks[0])
            return await self.md_ia_consulta_processo_async(id_proc_str)

        async def _fetch_chunk(chunk: list[str]) -> pd.DataFrame:
            return await self.md_ia_consulta_processo_async(
                ",".join(str(p) for p in chunk)
            )

        results = await asyncio.gather(
            *(_fetch_chunk(c) for c in chunks), return_exceptions=True
        )
        dfs = [df for df in results if isinstance(df, pd.DataFrame) and not df.empty]
        if not dfs:
            return pd.DataFrame()
        return pd.concat(dfs, ignore_index=True)

    # ------------------------------------------------------------------
    # md_ia_atualiza_documentos_vetorizaveis_async
    # ------------------------------------------------------------------

    async def md_ia_atualiza_documentos_vetorizaveis_async(
        self,
        id_documento: int,
    ) -> bool:
        """Signal SEI that ``id_documento`` has been vectorised.

        Returns ``True`` on HTTP 200, ``False`` on any ``httpx.HTTPError``.
        """
        endpoint = "md_ia_atualiza_documentos_vetorizaveis"
        url = self._build_api_url(endpoint)
        params = self._build_params(endpoint, {"IdDocumento": id_documento})
        try:
            async with httpx.AsyncClient(
                verify=self.config.verify_ssl, timeout=self.config.timeout_s
            ) as client:
                response = await client.put(url, params=params)
                response.raise_for_status()
                return response.status_code == 200
        except httpx.HTTPError:
            logger.exception("Erro ao atualizar documento %s", id_documento)
            return False

    # ------------------------------------------------------------------
    # fetch_documents_content_async
    # ------------------------------------------------------------------

    async def fetch_documents_content_async(
        self,
        document_ids: list[str],
        limit: int | None = None,
    ) -> tuple[dict, dict]:
        """Fetch content for many documents concurrently with semaphore control.

        ``limit`` defaults to ``self.config.max_concurrency``.

        Returns:
            ``(content_map, extra_meta_map)`` — each maps
            ``str(id_documento) → value``.
        """
        effective_limit = limit if limit is not None else self.config.max_concurrency
        sem = asyncio.Semaphore(effective_limit)

        async def _bound_fetch(_id: str) -> dict:
            async with sem:
                try:
                    return await self.md_ia_consulta_conteudo_documento_async(
                        id_documento=_id
                    )
                except SeiApiError:
                    return {"id_documento": _id, "content_doc": None}

        results = await asyncio.gather(*(_bound_fetch(_id) for _id in document_ids))

        content_map = {
            str(res.get("id_documento")): res.get("content_doc")
            for res in results
            if res
        }
        extra_meta_map = {
            str(res.get("id_documento")): res.get("extra_metadata", {})
            for res in results
            if res
        }
        return content_map, extra_meta_map
