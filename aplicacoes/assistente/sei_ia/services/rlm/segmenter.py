"""Segmentador de documentos para o loop RLM.

Responsável por dividir documentos grandes em seções navegáveis.

Estratégia de segmentação:
    1. Detecção de estrutura legal (Art., Cláusula, CAPÍTULO, Seção, §)
    2. Fallback: chunking por tamanho fixo (~4k tokens) com overlap
    3. Seções estruturais muito grandes são subdivididas por tamanho

Compatível com documentos governamentais brasileiros do SEI.
"""

from __future__ import annotations

import logging
import re

import tiktoken

from sei_ia.services.rlm.config import RLMConfig
from sei_ia.services.rlm.state import DocumentSection

logger = logging.getLogger(__name__)

# ==============================================================================
# CONTAGEM DE TOKENS (standalone, sem dependência do projeto pai)
# ==============================================================================

_ENCODING_NAME = "o200k_base"
_encoding: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    """Retorna instância singleton do encoding tiktoken."""
    global _encoding  # noqa: PLW0603
    if _encoding is None:
        _encoding = tiktoken.get_encoding(_ENCODING_NAME)
    return _encoding


def count_tokens(text: str) -> int:
    """Conta tokens de um texto usando tiktoken (o200k_base).

    Encoding compatível com os modelos usados pelo projeto principal
    (SUMMARIZE_ENCODING_NAME em settings_config.py).
    """
    if not text:
        return 0
    return len(_get_encoding().encode(text))


# ==============================================================================
# PATTERNS PARA ESTRUTURA LEGAL DE DOCUMENTOS GOVERNAMENTAIS
# ==============================================================================

# Cada tupla: (regex, tipo_secao, nível_hierárquico)
# Nível menor = maior hierarquia: Capítulo(1) > Seção(2) > Artigo/Cláusula(3) > §(4)
_STRUCTURAL_PATTERNS: list[tuple[str, str, int]] = [
    (r"CAP[ÍI]TULO\s+[IVXivx\d]+[^\n]*", "capitulo", 1),
    (r"(?:Seção|SEÇÃO)\s+[IVXivx\d]+[^\n]*", "secao", 2),
    (r"Art\.\s*\d+[^\n]*", "artigo", 3),
    (r"(?:Cláusula|CLÁUSULA)\s+\w+[^\n]*", "clausula", 3),
    (r"§\s*\d+[^\n]*", "paragrafo", 4),
]

# Mínimo de marcadores para usar segmentação estrutural
_MIN_STRUCTURAL_MARKERS = 3

# Limite de proximidade (caracteres) para considerar marcadores como duplicatas
_DEDUP_PROXIMITY = 10


# ==============================================================================
# DETECÇÃO DE MARCADORES ESTRUTURAIS
# ==============================================================================


def _find_structural_boundaries(
    content: str,
) -> list[tuple[int, str, str, int]]:
    """Encontra marcadores estruturais e suas posições no texto.

    Retorna:
        Lista de (posição, título, tipo_secao, nível_hierárquico),
        ordenada por posição no texto e desduplicada.
    """
    boundaries: list[tuple[int, str, str, int]] = []

    for pattern, tipo, nivel in _STRUCTURAL_PATTERNS:
        for match in re.finditer(pattern, content):
            title = match.group().strip()
            if len(title) > 120:
                title = title[:120] + "..."
            boundaries.append((match.start(), title, tipo, nivel))

    boundaries.sort(key=lambda x: x[0])

    # Remover duplicatas por proximidade (manter maior hierarquia)
    filtered: list[tuple[int, str, str, int]] = []
    for pos, title, tipo, nivel in boundaries:
        if filtered and abs(pos - filtered[-1][0]) < _DEDUP_PROXIMITY:
            if nivel < filtered[-1][3]:
                filtered[-1] = (pos, title, tipo, nivel)
            continue
        filtered.append((pos, title, tipo, nivel))

    return filtered


# ==============================================================================
# SEGMENTAÇÃO PRINCIPAL
# ==============================================================================


def segment_document(
    content: str,
    doc_id: str,
    doc_id_formatado: str,
    config: RLMConfig | None = None,
    use_sei_section_ids: bool = False,
) -> list[DocumentSection]:
    """Segmenta um documento em seções para navegação pelo RLM.

    Tenta primeiro detectar estrutura legal (artigos, cláusulas, capítulos).
    Se não encontrar marcadores suficientes, faz chunking por tamanho fixo
    com overlap.

    Args:
        content: Texto completo do documento.
        doc_id: ID original do documento no SEI.
        doc_id_formatado: ID formatado para citações.
        config: Configuração do RLM (usa defaults se None).
        use_sei_section_ids: Se True, section IDs usam formato
            ``sec_{doc_id_formatado}_{NNN}`` em vez de ``doc_{doc_id}_sec_{NNN}``.

    Retorna:
        Lista de DocumentSection com offsets no conteúdo original.
    """
    if not content or not content.strip():
        return []

    if config is None:
        config = RLMConfig()

    boundaries = _find_structural_boundaries(content)

    if len(boundaries) >= _MIN_STRUCTURAL_MARKERS:
        logger.info(
            "Documento %s: %d marcadores estruturais encontrados, "
            "usando segmentação por estrutura.",
            doc_id_formatado,
            len(boundaries),
        )
        sections = _segment_by_structure(
            content,
            doc_id,
            doc_id_formatado,
            boundaries,
            config,
            use_sei_section_ids=use_sei_section_ids,
        )
    else:
        logger.info(
            "Documento %s: poucos marcadores estruturais (%d), "
            "usando segmentação por tamanho.",
            doc_id_formatado,
            len(boundaries),
        )
        sections = _segment_by_size(
            content,
            doc_id,
            doc_id_formatado,
            config,
            use_sei_section_ids=use_sei_section_ids,
        )

    logger.info(
        "Documento %s segmentado em %d seções.", doc_id_formatado, len(sections)
    )
    return sections


# ==============================================================================
# SEGMENTAÇÃO POR ESTRUTURA LEGAL
# ==============================================================================


def _segment_by_structure(
    content: str,
    doc_id: str,
    doc_id_formatado: str,
    boundaries: list[tuple[int, str, str, int]],
    config: RLMConfig,
    use_sei_section_ids: bool = False,
) -> list[DocumentSection]:
    """Segmenta usando marcadores estruturais detectados.

    Seções muito grandes (>2x o alvo) são subdivididas por tamanho.
    Conteúdo antes do primeiro marcador é incluído como "Preâmbulo".
    """
    sections: list[DocumentSection] = []

    # Incluir preâmbulo se houver conteúdo antes do primeiro marcador
    first_marker_pos = boundaries[0][0]
    if first_marker_pos > 0:
        preambulo_text = content[:first_marker_pos]
        preambulo_tokens = count_tokens(preambulo_text)
        if preambulo_tokens > 50:
            sections.append(
                DocumentSection(
                    section_id="",  # renumerado depois
                    doc_id=doc_id,
                    doc_id_formatado=doc_id_formatado,
                    title="Preâmbulo",
                    offset_start=0,
                    offset_end=first_marker_pos,
                    token_count=preambulo_tokens,
                    metadata={"tipo_secao": "preambulo", "nivel_hierarquico": 0},
                )
            )

    # Criar seções a partir dos marcadores
    for i, (pos, title, tipo, nivel) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(content)
        section_text = content[pos:end]
        tokens = count_tokens(section_text)

        if tokens > config.section_target_tokens * 2:
            # Seção muito grande: subdividir por tamanho
            sub_sections = _segment_by_size(
                section_text,
                doc_id,
                doc_id_formatado,
                config,
                offset_base=pos,
                title_prefix=title,
                use_sei_section_ids=use_sei_section_ids,
            )
            sections.extend(sub_sections)
        else:
            sections.append(
                DocumentSection(
                    section_id="",  # renumerado depois
                    doc_id=doc_id,
                    doc_id_formatado=doc_id_formatado,
                    title=title,
                    offset_start=pos,
                    offset_end=end,
                    token_count=tokens,
                    metadata={"tipo_secao": tipo, "nivel_hierarquico": nivel},
                )
            )

    # Renumerar section_ids sequencialmente
    for i, sec in enumerate(sections):
        if use_sei_section_ids:
            sec.section_id = f"sec_{doc_id_formatado}_{i + 1:03d}"
        else:
            sec.section_id = f"doc_{doc_id}_sec_{i + 1:03d}"

    return sections


# ==============================================================================
# SEGMENTAÇÃO POR TAMANHO (FALLBACK)
# ==============================================================================


def _segment_by_size(
    content: str,
    doc_id: str,
    doc_id_formatado: str,
    config: RLMConfig,
    offset_base: int = 0,
    title_prefix: str = "",
    use_sei_section_ids: bool = False,
) -> list[DocumentSection]:
    """Segmenta por tamanho fixo com overlap entre seções.

    Usado como fallback quando não há marcadores estruturais,
    ou para subdividir seções estruturais muito grandes.

    Args:
        content: Texto a segmentar.
        doc_id: ID do documento.
        doc_id_formatado: ID formatado.
        config: Configuração com section_target_tokens e section_overlap_tokens.
        offset_base: Offset base para ajustar posições ao conteúdo original.
        title_prefix: Prefixo para títulos (ex: nome da seção estrutural pai).
        use_sei_section_ids: Se True, usa formato ``sec_{doc_id_formatado}_{NNN}``.
    """
    encoding = _get_encoding()
    all_tokens = encoding.encode(content)
    total_tokens = len(all_tokens)

    if total_tokens == 0:
        return []

    target = config.section_target_tokens
    overlap = config.section_overlap_tokens
    step = max(target - overlap, 1)

    sections: list[DocumentSection] = []
    token_pos = 0
    char_offset = 0

    while token_pos < total_tokens:
        token_end = min(token_pos + target, total_tokens)
        chunk_tokens = all_tokens[token_pos:token_end]
        chunk_text = encoding.decode(chunk_tokens)

        sec_num = len(sections) + 1
        if title_prefix:
            title = (
                title_prefix if sec_num == 1 else f"{title_prefix} (parte {sec_num})"
            )
        else:
            title = f"Seção {sec_num}"

        if use_sei_section_ids:
            sid = f"sec_{doc_id_formatado}_{sec_num:03d}"
        else:
            sid = f"doc_{doc_id}_sec_{sec_num:03d}"

        sections.append(
            DocumentSection(
                section_id=sid,
                doc_id=doc_id,
                doc_id_formatado=doc_id_formatado,
                title=title,
                offset_start=offset_base + char_offset,
                offset_end=offset_base + char_offset + len(chunk_text),
                token_count=len(chunk_tokens),
                metadata={"tipo_secao": "chunk", "nivel_hierarquico": 99},
            )
        )

        if token_end >= total_tokens:
            break

        # Avançar pelo passo (target - overlap) e atualizar offset de caracteres
        advance_tokens = all_tokens[token_pos : token_pos + step]
        advance_text = encoding.decode(advance_tokens)
        char_offset += len(advance_text)
        token_pos += step

    return sections
