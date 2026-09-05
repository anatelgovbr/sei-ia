from __future__ import annotations

import html as html_lib
import logging
import re
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from ._protocol import _ClientInternals

    _Base = _ClientInternals
else:
    _Base = object

logger = logging.getLogger(__name__)

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


def _sanitize_html_field(value: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", text).strip()


def _parse_ids(id_documentos: str | int) -> set[int]:
    """Convert a single int or CSV string of ints to a set of ints."""
    if isinstance(id_documentos, int):
        return {id_documentos}
    return {int(x.strip()) for x in str(id_documentos).split(",") if x.strip()}


class DocumentsMixin(_Base):
    """Sync document/content endpoints for the SEI API client."""

    def _parse_ok_doc_response(self, payload: dict, id_documento: str) -> dict:
        """Parse a non-empty conteudo_documento payload into a result dict.

        When ``IdAnexos`` is present the email attachment composition is
        delegated to the async sibling; here the raw fields are returned and
        the caller is expected to augment them.
        """
        data = payload.get("data", {})
        if not data:
            return {"id_documento": id_documento, "content_doc": None}
        content_doc = data.get("ConteudoDocumento")
        tipo_conteudo = data.get("TipoConteudo")
        id_anexos = data.get("IdAnexos")
        return {
            "id_documento": id_documento,
            "tipo_conteudo": tipo_conteudo,
            "content_doc": content_doc,
            "id_anexos": id_anexos,
        }

    def md_ia_consulta_documento(
        self,
        id_documentos: str,
        sin_filtra_documentos_relevantes: str = "N",
        sin_filtra_bloqueados: str = "N",
        sin_filtra_ativos: str = "N",
    ) -> pd.DataFrame:
        """Fetch document metadata for one or more document IDs.

        Splits ``id_documentos`` into chunks of ``config.chunk_size``,
        deduplicates IDs preserving order, and concatenates per-chunk results.
        When content is needed the caller should follow up with
        ``md_ia_consulta_conteudo_documento`` or the async batch variant.

        Colunas retornadas: ``id_protocolo``, ``num_doc``,
        ``documento_especificacao``, ``id_type_document``, ``content_doc``
        (em branco), ``formato_arquivo``, ``dta_inclusao``,
        ``name_id_type_doc``, ``id_protocolo_documento``, ``type_doc``,
        ``num_proc``, ``sin_armazena_cache``, ``extra_metadata``.
        """
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

        # Deduplicate preserving order to avoid overlong URLs (ETL hardened pattern).
        id_list = list(
            dict.fromkeys(i.strip() for i in str(id_documentos).split(",") if i.strip())
        )
        chunk_size = self.config.chunk_size
        all_dfs: list[pd.DataFrame] = []

        for i in range(0, len(id_list), chunk_size):
            chunk = ",".join(id_list[i : i + chunk_size])
            payload = self._request_json(
                service_endpoint,
                extra_params={
                    "SinFiltraDocumentosRelevantes": sin_filtra_documentos_relevantes,
                    "SinFiltraBloqueados": sin_filtra_bloqueados,
                    "SinFiltraAtivos": sin_filtra_ativos,
                    "IdDocumentos": chunk,
                },
                document_id_hint=chunk,
            )
            df_chunk = self._parse_records(payload, columns, parse)
            if not df_chunk.empty:
                all_dfs.append(df_chunk)

        if not all_dfs:
            return pd.DataFrame(columns=columns)
        return pd.concat(all_dfs, ignore_index=True)

    def md_ia_consulta_documento_batch(
        self,
        id_documentos: list[str],
        batch_size: int = 100,
        sin_filtra_documentos_relevantes: str = "N",
        sin_filtra_bloqueados: str = "N",
        sin_filtra_ativos: str = "N",
    ) -> pd.DataFrame:
        """Fetch document metadata for a list of IDs, chunked by ``batch_size``.

        Sync surface: delegates per-chunk fetches to
        ``self.run_async(self.md_ia_consulta_documento_async(...))`` so the
        async sibling handles concurrency. Falls back to the sync
        ``md_ia_consulta_documento`` for the single-chunk case, avoiding the
        async hop.
        """
        if not id_documentos:
            return pd.DataFrame()

        effective_chunk = max(1, min(batch_size, self.config.chunk_size))
        chunks = [
            id_documentos[i : i + effective_chunk]
            for i in range(0, len(id_documentos), effective_chunk)
        ]

        if len(chunks) == 1:
            id_docs_str = ",".join(str(d) for d in chunks[0])
            return self.md_ia_consulta_documento(
                id_docs_str,
                sin_filtra_documentos_relevantes,
                sin_filtra_bloqueados,
                sin_filtra_ativos,
            )

        all_dfs: list[pd.DataFrame] = []
        for chunk in chunks:
            id_docs_str = ",".join(str(d) for d in chunk)
            df = self.run_async(
                self.md_ia_consulta_documento_async(
                    id_docs_str,
                    sin_filtra_documentos_relevantes,
                    sin_filtra_bloqueados,
                    sin_filtra_ativos,
                )
            )
            if isinstance(df, pd.DataFrame) and not df.empty:
                all_dfs.append(df)

        if not all_dfs:
            return pd.DataFrame()
        return pd.concat(all_dfs, ignore_index=True)

    def md_ia_consulta_conteudo_documento(self, id_documentos: str) -> pd.DataFrame:
        """Fetch raw content payload for a document, including attachment metadata.

        Colunas retornadas: ``tipo_conteudo``, ``content_doc``, ``extra_metadata``.

        When ``IdAnexos`` is present the attachment download and text extraction
        are delegated to ``sei_extraction.extract_document`` (see coupling note
        in the porting report). The ``content_doc`` field in that case will
        carry the raw XML/HTML from the API; callers that need augmented content
        with extracted attachment text must call the async sibling
        ``md_ia_consulta_conteudo_documento_async``.

        Raises:
            SeiApiUnavailableError: propagated from health-check guard.
            SeiApiError: on HTTP or JSON error.
        """
        service_endpoint = "md_ia_consulta_conteudo_documento"

        payload = self._request_json(
            service_endpoint,
            extra_params={"IdDocumento": id_documentos},
            document_id_hint=str(id_documentos),
        )

        api_docs = payload.get("data", {})

        if not api_docs:
            return pd.DataFrame(
                [{"tipo_conteudo": None, "content_doc": None, "extra_metadata": {}}]
            )

        tipo_conteudo = api_docs.get("TipoConteudo")
        content_doc = api_docs.get("ConteudoDocumento")
        id_anexos = api_docs.get("IdAnexos")

        extra_metadata = {
            k: _sanitize_html_field(str(v)) if isinstance(v, str) else str(v)
            for k, v in api_docs.items()
            if k not in _CONTENT_ENDPOINT_EXCLUDE and v is not None
        }

        if id_anexos:
            # Attachment download + text extraction is out of scope for this
            # method. Callers needing augmented content (email body + extracted
            # attachment text) must use md_ia_consulta_conteudo_documento_async,
            # which calls sei_extraction.extract_document for each attachment.
            # The raw content_doc (XML with attachment references) is returned
            # unchanged here so callers can decide how to handle it.
            logger.debug(
                "Documento %s tem %d anexo(s); extração de texto delegada ao "
                "sibling assíncrono ou ao chamador via sei_extraction.",
                id_documentos,
                len(id_anexos),
            )

        return pd.DataFrame(
            [
                {
                    "tipo_conteudo": tipo_conteudo,
                    "content_doc": content_doc,
                    "extra_metadata": extra_metadata,
                }
            ]
        )
