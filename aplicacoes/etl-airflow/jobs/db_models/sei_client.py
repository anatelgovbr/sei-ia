"""Cliente unificado da API do SEI, configurado a partir do env do ETL.

Substitui o antigo fork ``sei_db_handlers.SEIDBHandler``. A lib ``sei_api``
separou metadados de conteúdo, devolve ``dta_inclusao`` como datetime e expõe
``formato_arquivo`` (nome completo do arquivo) no lugar de ``content_type``.
Este adapter recompõe o que o ETL espera: a coluna ``content_type`` derivada da
extensão, ``dta_inclusao`` formatada como string e ``content_doc`` preenchido sob
demanda via ``fetch_documents_content_async``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sei_api import SeiApiClient, SeiApiConfig
from sei_extraction.config import ExtractionConfig
from sei_extraction.exceptions import UnsupportedFormatError
from sei_extraction.extract import extract_document
from sei_extraction.ocr.client import OpenAIVisionOCRClient

from jobs.envs import (
    LITELLM_PROXY_API_KEY,
    LITELLM_PROXY_URL,
    OCR_DPI,
    OCR_ENABLED,
    OCR_MAX_CONCURRENT_PAGES,
    OCR_MIN_TEXT_THRESHOLD,
    OCR_MODEL,
    SEI_API_DB_ADDRESS,
    SEI_API_DB_CHUNK_SIZE,
    SEI_API_DB_IDENTIFIER_SERVICE,
    SEI_API_DB_TIMEOUT,
    SEI_API_DB_USER,
    SEI_API_MAX_CONCURRENCY,
    SEI_API_MAX_RETRIES,
    VERIFY_SSL,
)

_DTA_INCLUSAO_FORMAT = "%Y-%m-%d %H:%M:%S"

_extraction_config = ExtractionConfig(
    ocr_enabled=OCR_ENABLED,
    ocr_model=OCR_MODEL,
    ocr_min_text_threshold=OCR_MIN_TEXT_THRESHOLD,
    ocr_dpi=OCR_DPI,
    ocr_max_concurrent_pages=OCR_MAX_CONCURRENT_PAGES,
)
_ocr_client = OpenAIVisionOCRClient(
    base_url=LITELLM_PROXY_URL,
    api_key=LITELLM_PROXY_API_KEY or "not-needed",
)


def _extract_anexo(path: str, extension: str) -> str:
    """``content_extractor`` do cliente: extrai texto de um anexo de e-mail.

    Espelha o caminho do fork: tenta ``extract_document`` (com OCR) e cai para
    leitura crua do arquivo em ``UnsupportedFormatError``.
    """
    try:
        return extract_document(path, extension, _extraction_config, _ocr_client)
    except UnsupportedFormatError:
        with Path(path).open("r", encoding="utf-8", errors="ignore") as f:
            return f.read()


sei_client = SeiApiClient(
    SeiApiConfig(
        base_url=SEI_API_DB_ADDRESS,
        sigla_sistema=SEI_API_DB_USER,
        identificacao_servico=SEI_API_DB_IDENTIFIER_SERVICE,
        verify_ssl=VERIFY_SSL,
        timeout_s=SEI_API_DB_TIMEOUT,
        chunk_size=SEI_API_DB_CHUNK_SIZE,
        max_retries=SEI_API_MAX_RETRIES,
        max_concurrency=SEI_API_MAX_CONCURRENCY,
    ),
    content_extractor=_extract_anexo,
)


def _content_type_from_formato(formato_arquivo: object) -> str:
    """Deriva a extensão do arquivo (ou ``html``) do nome completo.

    O fork expunha ``content_type``; a lib devolve ``formato_arquivo``
    (``NomeArquivo`` completo). Recria a regra do fork: extensão após o último
    ponto, ``html`` quando não há ponto.
    """
    nome = str(formato_arquivo or "")
    return nome.rsplit(".", 1)[-1] if "." in nome else "html"


def _enrich_documento_df(df: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta ``content_type`` e formata ``dta_inclusao`` como o ETL espera."""
    df = df.copy()
    df["content_type"] = df["formato_arquivo"].map(_content_type_from_formato)
    if not df.empty:
        df["dta_inclusao"] = pd.to_datetime(df["dta_inclusao"]).dt.strftime(
            _DTA_INCLUSAO_FORMAT
        )
    return df


def consulta_documentos(id_documentos: str, **filtros: str) -> pd.DataFrame:
    """Metadados dos documentos no schema do ETL (``content_type`` + ``dta_inclusao`` string).

    Substitui ``SEIDBHandler.md_ia_consulta_documento(..., conteudo=False)``.
    """
    return _enrich_documento_df(
        sei_client.md_ia_consulta_documento(id_documentos, **filtros)
    )


def consulta_documentos_com_conteudo(
    id_documentos: str, **filtros: str
) -> pd.DataFrame:
    """Metadados com a coluna ``content_doc`` preenchida.

    Recria ``SEIDBHandler.md_ia_consulta_documento(conteudo=True)``: busca os
    metadados e funde o conteúdo obtido via ``fetch_documents_content_async``.
    """
    df = consulta_documentos(id_documentos, **filtros)
    if df.empty:
        return df
    ids = df["id_protocolo_documento"].astype(str).tolist()
    content_map, _ = sei_client.run_async(sei_client.fetch_documents_content_async(ids))
    df["content_doc"] = df["id_protocolo_documento"].astype(str).map(content_map)
    return df
