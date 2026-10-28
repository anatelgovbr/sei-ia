"""Cliente unificado da API do SEI, configurado a partir do ``settings`` do assistente.

Substitui o antigo fork ``sei_db_handlers.SEIDBHandler``. A lib ``sei_api`` é a
fonte única do transporte HTTP, retry e parsing; este adapter só injeta a
configuração do assistente e recompõe o que era específico do app:

- ``timeout_exc_factory`` levanta ``HTTPException412SeiApiTimeout`` no esgotamento
  de timeout (o router converte em HTTP 412), preservando o contrato do fork.
- ``content_extractor`` extrai texto dos anexos de e-mail (``sei_extraction`` +
  OCR), espelhando o caminho do fork e do adapter do etl.
- ``consulta_historico_topico_com_tokens`` re-acrescenta a coluna ``total_tokens``
  (que o fork computava via ``token_counter``); a lib devolve só o histórico.

``SeiApiError`` é re-exportado como ``SeiDBAPIError`` para manter o contrato
(``.status_code``, ``.from_source_exc``) nos call sites com diff mínimo.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sei_api import SeiApiClient, SeiApiConfig, SeiApiError as SeiDBAPIError
from sei_extraction.config import ExtractionConfig
from sei_extraction.exceptions import UnsupportedFormatError
from sei_extraction.extract import extract_document
from sei_extraction.ocr.client import OpenAIVisionOCRClient

from sei_ia.configs.settings_config import settings
from sei_ia.services.counter import token_counter
from sei_ia.services.exceptions.http_exceptions import HTTPException412SeiApiTimeout

__all__ = [
    "SeiDBAPIError",
    "consulta_historico_topico_com_tokens",
    "extraction_config",
    "ocr_client",
    "sei_client",
]


def build_extraction_pipeline() -> tuple[ExtractionConfig, OpenAIVisionOCRClient]:
    """Monta o par (ExtractionConfig, OpenAIVisionOCRClient) a partir do settings.

    Fonte única dos três builders quase-idênticos que existiam no adapter, em
    external.py e em uploads.py. Só os escalares de OCR vêm do settings; o
    comportamento de planilha (``spreadsheet_format=csv`` + limites 1000/10) é o
    padrão do ``ExtractionConfig`` da lib, compartilhado com o etl — não se
    sobrescreve aqui, pra o padrão viver num lugar só.
    """
    config = ExtractionConfig(
        ocr_enabled=settings.OCR_ENABLED,
        ocr_model=settings.OCR_MODEL,
        ocr_min_text_threshold=settings.OCR_MIN_TEXT_THRESHOLD,
        ocr_dpi=settings.OCR_DPI,
        ocr_max_concurrent_pages=settings.OCR_MAX_CONCURRENT_PAGES,
    )
    ocr_client = OpenAIVisionOCRClient(
        base_url=settings.LITELLM_PROXY_URL,
        api_key=settings.LITELLM_PROXY_API_KEY or "not-needed",
    )
    return config, ocr_client


# Pipeline de extração único do processo. O OpenAIVisionOCRClient embrulha um
# openai.OpenAI síncrono (pool de conexão reaproveitável) e não tem estado por
# chamada, então uma instância só é compartilhada por todos os caminhos de
# extração (anexo de e-mail aqui, download direto em external.py, upload em
# uploads.py) em vez de reconstruir o cliente — e o pool — a cada documento.
extraction_config, ocr_client = build_extraction_pipeline()


def _extract_anexo(path: str, extension: str) -> str:
    """``content_extractor`` do cliente: extrai texto de um anexo de e-mail.

    Espelha o caminho do fork: tenta ``extract_document`` (com OCR) e cai para
    leitura crua do arquivo em ``UnsupportedFormatError``.
    """
    try:
        return extract_document(path, extension, extraction_config, ocr_client)
    except UnsupportedFormatError:
        with Path(path).open("r", encoding="utf-8", errors="ignore") as f:
            return f.read()


sei_client = SeiApiClient(
    SeiApiConfig(
        base_url=settings.SEI_API_DB_ADDRESS,
        sigla_sistema=settings.SEI_API_DB_USER,
        identificacao_servico=settings.SEI_API_DB_IDENTIFIER_SERVICE,
        verify_ssl=settings.VERIFY_SSL,
        timeout_s=int(settings.SEI_API_DB_TIMEOUT),
        chunk_size=settings.SEI_API_DB_CHUNK_SIZE,
        max_retries=settings.SEI_API_MAX_RETRIES,
        backoff_initial_wait=settings.BACKOFF_INITIAL_WAIT,
        retry_backoff_factor=settings.RETRY_BACKOFF_FACTOR,
        max_concurrency=settings.SEI_API_SEMAPHORE,
    ),
    timeout_exc_factory=lambda document_id: HTTPException412SeiApiTimeout(
        document_id=document_id
    ),
    content_extractor=_extract_anexo,
)


def consulta_historico_topico_com_tokens(id_topico: str) -> pd.DataFrame:
    """Histórico do tópico com a coluna ``total_tokens`` recomposta.

    A lib devolve ``pergunta``/``resposta``/``dth_cadastro``. O assistente filtra
    o histórico por orçamento de tokens (``conversation.py``), então ``total_tokens``
    é computado aqui via ``token_counter``, o mesmo cálculo que o fork fazia no
    parse de cada linha. Mantém o nome ``total_tokens`` que os consumidores esperam.
    """
    df = sei_client.md_ia_consulta_historico_topico(id_topico)
    if df.empty:
        return df.assign(total_tokens=pd.Series(dtype="int64"))
    df = df.copy()
    df["total_tokens"] = df.apply(
        lambda row: token_counter(row["pergunta"]) + token_counter(row["resposta"]),
        axis=1,
    )
    return df
