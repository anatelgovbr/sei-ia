from __future__ import annotations

import logging
import os
import re
import tempfile
import uuid
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import requests
from requests.exceptions import HTTPError

from ._base import _decode_json_body
from .exceptions import SeiApiError

if TYPE_CHECKING:
    from ._protocol import _ClientInternals

    _Base = _ClientInternals
else:
    _Base = object

logger = logging.getLogger(__name__)

_REQUEST_ERROR_PREFIX = "Falha na requisição à API SEI: "


def _sanitize_filename(raw_filename: str, doc_extension: str) -> str:
    """Return a filesystem-safe filename with ``doc_extension`` guaranteed."""
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", raw_filename)
    sanitized = re.sub(r"<[^>]+>", "", sanitized)
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    sanitized = re.sub(r"\s+", " ", sanitized.strip())
    if not sanitized or len(sanitized) < 3:
        return f"{uuid.uuid4()}.{doc_extension}"
    if not sanitized.endswith(f".{doc_extension}"):
        sanitized = f"{sanitized}.{doc_extension}"
    return sanitized


def _parse_ids(id_documentos: str | int) -> set[int]:
    """Convert a single int or CSV string of ints to a set of ints."""
    if isinstance(id_documentos, int):
        return {id_documentos}
    return {int(x.strip()) for x in str(id_documentos).split(",") if x.strip()}


def _raise_for_status(response: requests.Response) -> None:
    """Mapeia 4xx para ``SeiApiError`` com o token anonimizado.

    Os 5xx já são retentados e mapeados dentro de ``_run_with_retry``; aqui só
    chega o sucesso ou um 4xx que não deve ser retentado. Espelha o tratamento
    de status de ``_request_json`` para os endpoints binários (download/remoção).
    """
    try:
        response.raise_for_status()
    except HTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        sei_exc = SeiApiError.from_source_exc(
            exc, status_code=status or 500, prefix=_REQUEST_ERROR_PREFIX
        )
        logger.exception(sei_exc.detail)
        raise sei_exc from exc


class FilesMixin(_Base):
    """Binary download, avulso removal, history, and internal-doc endpoints."""

    def md_ia_download_arquivo_documento_externo(
        self,
        id_documento: str,
        doc_extension: str,
        id_anexo: int | None = None,
    ) -> str:
        """Download an external document or one of its attachments.

        Returns the path of the file written to a system temp directory.
        Text extraction is out of scope; the caller should use ``sei_extraction``.

        Args:
            id_documento: SEI document ID.
            doc_extension: Expected file extension, e.g. ``"pdf"``.
            id_anexo: Attachment ID; when provided, downloads that attachment.

        Returns:
            Absolute path of the saved temp file.

        Raises:
            SeiApiUnavailableError: propagated from health-check guard.
            SeiApiError: on HTTP error or unexpected failure.
        """
        endpoint = "md_ia_download_arquivo_documento_externo"
        url = self._build_api_url(endpoint)
        params = self._build_params(endpoint, {"IdDocumento": id_documento})
        if id_anexo is not None:
            params["IdAnexo"] = id_anexo

        response = self._run_with_retry(
            lambda: self._do_request("GET", url, params, {"accept": "*/*"}),
            document_id_hint=str(id_documento),
        )
        _raise_for_status(response)

        content_disp = response.headers.get("content-disposition", "")
        logger.debug("Content-Disposition: %s", content_disp)

        match = re.search(r'filename="(.+?)"', content_disp)
        raw_filename = match.group(1) if match else f"{uuid.uuid4()}.{doc_extension}"
        filename = _sanitize_filename(raw_filename, doc_extension)

        extension = Path(filename).suffix
        fd, save_path_str = tempfile.mkstemp(suffix=extension)
        os.close(fd)
        with Path(save_path_str).open("wb") as f:
            f.write(response.content)

        logger.debug(
            "Documento %s (anexo %s) salvo em '%s'",
            id_documento,
            id_anexo,
            save_path_str,
        )
        return save_path_str

    def md_ia_download_arquivo_avulso(
        self,
        id_arquivo_avulso: int,
        doc_extension: str,
    ) -> str:
        """Download a standalone uploaded file (arquivo avulso).

        Returns the path of the file written to a system temp directory.
        Text extraction is out of scope; the caller should use ``sei_extraction``.

        Args:
            id_arquivo_avulso: SEI arquivo avulso ID.
            doc_extension: Expected file extension, e.g. ``"pdf"``.

        Returns:
            Absolute path of the saved temp file.

        Raises:
            SeiApiError: on HTTP error or unexpected failure.
        """
        endpoint = "md_ia_download_arquivo_avulso"
        url = self._build_api_url(endpoint)
        params = self._build_params(endpoint, {"IdArquivoAvulso": id_arquivo_avulso})

        response = self._run_with_retry(
            lambda: self._do_request("GET", url, params, {"accept": "*/*"}),
            document_id_hint=str(id_arquivo_avulso),
        )
        _raise_for_status(response)

        content_disp = response.headers.get("content-disposition", "")
        logger.debug("Content-Disposition: %s", content_disp)

        match = re.search(r'filename="(.+?)"', content_disp)
        raw_filename = match.group(1) if match else f"{uuid.uuid4()}.{doc_extension}"
        filename = _sanitize_filename(raw_filename, doc_extension)

        extension = Path(filename).suffix
        fd, save_path_str = tempfile.mkstemp(suffix=extension)
        os.close(fd)
        with Path(save_path_str).open("wb") as f:
            f.write(response.content)

        logger.debug(
            "Arquivo avulso %s salvo em '%s'", id_arquivo_avulso, save_path_str
        )
        return save_path_str

    def md_ia_remove_arquivos_avulsos(
        self,
        id_arquivos_avulsos: list[int] | set[int],
    ) -> dict[str, Any]:
        """Signal the SEI API that a set of avulso files can be removed.

        Should be called after the caller has locally saved or processed
        the files. Only the first ID in the sorted set is sent per the
        API contract observed in the assist fork.

        Args:
            id_arquivos_avulsos: Collection of avulso file IDs to remove.

        Returns:
            JSON response dict, or ``{"status": "skipped", "data": []}`` when
            the input is empty, or ``{"status": "success", "data": []}`` when
            the response body is not valid JSON.

        Raises:
            SeiApiError: on HTTP error or unexpected failure.
        """
        ids = sorted({int(i) for i in id_arquivos_avulsos})
        if not ids:
            return {"status": "skipped", "data": []}

        endpoint = "md_ia_remove_arquivos_avulsos"
        url = self._build_api_url(endpoint)
        params = self._build_params(endpoint, {"IdArquivoAvulso": ids[0]})

        response = self._run_with_retry(
            lambda: self._do_request(
                "DELETE", url, params, {"accept": "application/json"}
            ),
            document_id_hint=str(ids[0]),
        )
        _raise_for_status(response)

        try:
            return _decode_json_body(response.content)
        except JSONDecodeError:
            return {"status": "success", "data": []}

    def md_ia_consulta_historico_topico(self, id_topico: str) -> pd.DataFrame:
        """Fetch the Q&A history for a topic.

        Returns 404 as an empty DataFrame instead of an error, matching the
        assist fork's ``_handle_historico_topico_errors`` policy.

        Colunas: ``pergunta``, ``resposta``, ``dth_cadastro``.

        Note: ``total_tokens`` was dropped — it depended on
        ``sei_ia.services.counter.token_counter`` (app-coupled). Callers that
        need token counts should compute them after fetching.

        Args:
            id_topico: Topic ID.

        Returns:
            DataFrame with conversation history, or empty on 404.

        Raises:
            SeiApiError: on non-404 HTTP errors or unexpected failures.
        """
        endpoint = "md_ia_consulta_historico_topico"
        columns = ["pergunta", "resposta", "dth_cadastro"]

        def parse(doc: dict) -> dict:
            return {
                "pergunta": doc["Pergunta"],
                "resposta": doc["Resposta"],
                "dth_cadastro": pd.to_datetime(
                    doc.get("DthCadastro", ""), dayfirst=True
                ).strftime("%Y-%m-%d %H:%M:%S"),
            }

        payload = self._request_json(
            endpoint,
            extra_params={"IdTopico": id_topico},
            empty_statuses=(404,),
            document_id_hint=id_topico,
        )
        return self._parse_records(payload, columns, parse)

    def md_ia_consulta_ultimo_id_message(self) -> int | None:
        """Fetch the most recent message ID from the SEI API.

        Returns:
            Integer ID, or ``None`` when the API returns no data.

        Raises:
            SeiApiError: on HTTP or JSON errors.
        """
        payload = self._request_json("md_ia_consulta_ultimo_id_message")
        raw = payload.get("data")
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        return int(raw) if raw is not None else None

    def internal_docs_from_process_api(self, id_documentos: str) -> pd.DataFrame:
        """Fetch internal document metadata, raising when IDs are missing.

        Calls ``self.md_ia_consulta_documento`` and cross-checks that all
        requested IDs were returned. Raises ``SeiApiError(404)`` on mismatch.

        Args:
            id_documentos: Comma-separated document IDs.

        Returns:
            DataFrame from ``md_ia_consulta_documento``, empty on API error.

        Raises:
            SeiApiError: when requested IDs are not found in the response.
        """
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
        ]
        try:
            df = self.md_ia_consulta_documento(id_documentos=id_documentos)
        except SeiApiError:
            logger.exception("documentos internos não encontrados")
            return pd.DataFrame(columns=columns)

        requested = _parse_ids(id_documentos)
        returned = set(df["id_protocolo_documento"].dropna().unique())
        missing = requested - returned
        if requested and missing:
            logger.exception("Documentos internos não encontrados: %s", missing)
            # requests.codes.* é sempre int; o stub de types-requests o tipa como
            # int | None, gerando falso-positivo de arg-type no mypy.
            raise SeiApiError(
                status_code=requests.codes.not_found,  # type: ignore[arg-type]
                detail=f"Documentos internos não encontrados: {missing}",
            )
        return df

    def get_internal_docs_from_process(self, id_documentos: str) -> pd.DataFrame:
        """Fetch internal document metadata and add a ``nr_documento`` alias column.

        Content fetching and text extraction are out of scope for this method.
        In the assist fork, ``get_internal_docs_from_process`` also called
        ``fetch_documents_content_async`` which in turn called
        ``md_ia_consulta_conteudo_documento_async`` with inline PDF/spreadsheet
        extraction (``fitz``, ``_extract_text_from_pdf``, etc.). That chain is
        app-coupled logic belonging to ``sei_extraction``. Callers that need
        content should call ``self.md_ia_consulta_conteudo_documento`` or the
        async sibling after receiving this DataFrame.

        Args:
            id_documentos: Comma-separated document IDs.

        Returns:
            DataFrame with ``nr_documento`` column added (alias for ``num_doc``).
        """
        df = self.internal_docs_from_process_api(id_documentos=id_documentos)
        if df.empty:
            return df
        df = df.rename(columns={"num_doc": "nr_documento"})
        return df
