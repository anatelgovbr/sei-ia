"""Cliente unificado da API do SEI, configurado a partir do env do app.

Substitui o antigo fork ``sei_db_handlers.SEIDBHandler``. A lib ``sei_api``
separou metadados de conteúdo; ``consulta_documentos_com_conteudo`` recompõe o
antigo comportamento ``md_ia_consulta_documento(conteudo=True)`` no nível do app.
"""

from __future__ import annotations

import pandas as pd
from sei_api import SeiApiClient, SeiApiConfig

from api_sei.envs import (
    SEI_API_DB_ADDRESS,
    SEI_API_DB_CHUNK_SIZE,
    SEI_API_DB_IDENTIFIER_SERVICE,
    SEI_API_DB_TIMEOUT,
    SEI_API_DB_USER,
    VERIFY_SSL,
)

sei_client = SeiApiClient(
    SeiApiConfig(
        base_url=SEI_API_DB_ADDRESS,
        sigla_sistema=SEI_API_DB_USER,
        identificacao_servico=SEI_API_DB_IDENTIFIER_SERVICE,
        verify_ssl=VERIFY_SSL,
        timeout_s=SEI_API_DB_TIMEOUT,
        chunk_size=SEI_API_DB_CHUNK_SIZE,
    )
)


def consulta_documentos_com_conteudo(
    id_documentos: str, **filtros: str
) -> pd.DataFrame:
    """Metadados dos documentos com a coluna ``content_doc`` preenchida.

    Recria o antigo ``md_ia_consulta_documento(conteudo=True)``: busca os
    metadados e funde o conteúdo obtido via ``fetch_documents_content_async``.
    """
    df = sei_client.md_ia_consulta_documento(id_documentos, **filtros)
    if df.empty:
        return df
    ids = df["id_protocolo_documento"].astype(str).tolist()
    content_map, _ = sei_client.run_async(sei_client.fetch_documents_content_async(ids))
    df["content_doc"] = df["id_protocolo_documento"].astype(str).map(content_map)
    return df
