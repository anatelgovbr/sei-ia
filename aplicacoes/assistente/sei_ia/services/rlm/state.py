"""Modelos de dados para o RLM (Recursive Language Model).

Define as estruturas de dados usadas durante a segmentação
de documentos grandes para o engine REPL.

Compatível com os modelos do projeto principal (sei_ia.data.pydantic_models).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ==============================================================================
# MODELO DE SEÇÃO DE DOCUMENTO
# ==============================================================================


class DocumentSection(BaseModel):
    """Seção de um documento segmentado.

    Cada documento grande é dividido em seções menores para
    navegação pelo Root LM no REPL.

    Atributos:
        section_id: Identificador único da seção (ex: "sec_15125948_001").
        doc_id: ID original do documento no SEI.
        doc_id_formatado: ID formatado (SEI number) para citações.
        title: Título detectado ou gerado (ex: "Cláusula 3 - Valor do Contrato").
        gist: Resumo curto da seção (não usado pelo engine REPL).
        offset_start: Posição de início no conteúdo original do documento.
        offset_end: Posição de fim no conteúdo original do documento.
        token_count: Quantidade de tokens da seção completa.
        metadata: Metadados adicionais (tipo_secao, hierarquia, etc.).
    """

    section_id: str
    doc_id: str
    doc_id_formatado: str
    title: str
    gist: str = ""
    offset_start: int
    offset_end: int
    token_count: int = 0
    metadata: dict = Field(default_factory=dict)
