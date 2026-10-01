"""Modulo para extracao e manipulacao de citações - suporte a chunks e documentos completos."""

import logging
import re
from re import Match

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.llm_models.citation_sources import (
    _collect_web_reference_entries,
    build_web_references_section,
    create_chunk_tooltip,
    create_doc_tooltip,
    create_web_search_tooltip,
    find_chunk_metadata,
    find_web_search_metadata,
    get_document_count,
)

setup_logging()
logger = logging.getLogger(__name__)

# Padrões de citação
PATTERN_CHUNK_MARKER = (
    r"<doc_(\d+)_(\d+)></doc_\1_\2>"  # Padrão chunks: <doc_5630621_1></doc_5630621_1>
)
PATTERN_DOC_MARKER = (
    r"<doc_(\d+)></doc_\1>"  # Padrão documentos: <doc_12345></doc_12345>
)
PATTERN_WEB_SEARCH_MARKER = (
    r"<web_(\d+)>"  # Padrão web search simplificado: <web_1> (sem fechamento)
)


def escape_newlines_in_strings(json_str: str) -> str:
    r"""Substitui quebras de linha literais dentro de strings JSON por \\n."""

    def replace(match: Match[str]) -> str:
        return match.group(0).replace("\n", "\\n")

    string_pattern = r'"(?:\\.|[^"\\])*"'
    return re.sub(string_pattern, replace, json_str)


def remove_final_escapes_in_strings(json_str: str) -> str:
    r"""Remove caracteres de escape solitários (\) no final de linhas em strings JSON."""
    return json_str.replace("\\\n", "\n")


def extract_chunk_markers(response_text: str) -> list[tuple[str, str, str]]:
    """Extrai marcadores de chunks do texto de resposta.

    Args:
        response_text: Texto da resposta com marcadores

    Returns:
        Lista de tuplas (marker_completo, doc_id, chunk_index)
    """

    markers = []
    matches = re.findall(PATTERN_CHUNK_MARKER, response_text)

    for match in matches:
        doc_id = match[0]
        chunk_index = match[1]
        full_marker = f"<doc_{doc_id}_{chunk_index}></doc_{doc_id}_{chunk_index}>"
        markers.append((full_marker, doc_id, chunk_index))

    return markers


def replace_chunk_markers_with_tooltips(
    response_text: str, user_state: UserState, start_number: int = 1
) -> tuple[str, int]:
    """Substitui marcadores de chunks por tooltips HTML com numeração sequencial.

    Args:
        response_text: Texto com marcadores <{i}_{doc_id}></{i}_{doc_id}>
        user_state: Estado com metadados dos chunks
        start_number: Número inicial para a numeração sequencial

    Returns:
        Tupla (texto_processado, próximo_número_disponível)
    """
    markers = extract_chunk_markers(response_text)
    processed_text = response_text

    # Mapear chunks para numeração sequencial (baseado na ordem de aparição no texto)
    chunk_sequential_map = {}
    sequential_number = start_number

    # Primeiro, mapear todas as tags na ordem que aparecem no texto
    for full_marker, doc_id, chunk_index in markers:  # noqa: B007
        chunk_key = (doc_id, chunk_index)
        if chunk_key not in chunk_sequential_map:
            chunk_sequential_map[chunk_key] = sequential_number
            sequential_number += 1

    # Processar marcadores em ordem reversa para não afetar posições
    for full_marker, doc_id, chunk_index in reversed(markers):
        chunk_key = (doc_id, chunk_index)
        current_number = chunk_sequential_map[chunk_key]

        chunk_metadata = find_chunk_metadata(chunk_index, doc_id, user_state)
        if chunk_metadata is None:
            logger.warning(
                f"Metadados não encontrados para chunk doc_id={doc_id}, chunk_index={chunk_index}"
            )
            processed_text = processed_text.replace(full_marker, "", 1)
        else:
            tooltip = create_chunk_tooltip(chunk_metadata, current_number)
            processed_text = processed_text.replace(full_marker, tooltip, 1)

    return processed_text, sequential_number


def extract_doc_markers(response_text: str) -> list[tuple[str, str]]:
    """Extrai marcadores de documentos do texto de resposta.

    Args:
        response_text: Texto da resposta com marcadores

    Returns:
        Lista de tuplas (marker_completo, doc_id)
    """

    markers = []
    matches = re.findall(PATTERN_DOC_MARKER, response_text)

    for doc_id in matches:
        full_marker = f"<doc_{doc_id}></doc_{doc_id}>"
        markers.append((full_marker, doc_id))

    return markers


def replace_doc_markers_with_tooltips(
    response_text: str, user_state: UserState, start_number: int = 1
) -> tuple[str, int]:
    """Substitui marcadores de documentos por tooltips HTML.

    Args:
        response_text: Texto com marcadores <doc_{id}></doc_{id}>
        user_state: Estado com metadados dos documentos
        start_number: Número inicial para a numeração sequencial

    Returns:
        Tupla (texto_processado, próximo_número_disponível)
    """
    markers = extract_doc_markers(response_text)
    processed_text = response_text
    doc_count = get_document_count(user_state)

    # Obter mapeamento de id_documento -> id_documento_formatado
    id_to_formatted_map = user_state.get("id_to_formatted_map", {})

    logger.debug(f"Total de documentos: {doc_count}")
    logger.debug(f"Mapeamento id -> formatado: {id_to_formatted_map}")

    # Criar mapeamento baseado na ordem de aparição na resposta
    unique_doc_ids = []
    seen_doc_ids = set()
    sequential_number = start_number

    # Percorrer marcadores na ordem de aparição para mapear índices
    for _, doc_id in markers:
        if doc_id not in seen_doc_ids:
            unique_doc_ids.append(doc_id)
            seen_doc_ids.add(doc_id)

    # Criar mapeamento doc_id -> índice baseado na ordem de aparição (usando numeração global)
    doc_id_to_index = {}
    for doc_id in unique_doc_ids:
        doc_id_to_index[doc_id] = sequential_number
        sequential_number += 1

    logger.debug(f"Ordem de aparição - doc_id -> índice: {doc_id_to_index}")

    # Processar marcadores em ordem reversa para não afetar posições
    for full_marker, doc_id in reversed(markers):
        current_index = doc_id_to_index.get(doc_id, start_number)
        # Buscar o id_documento_formatado do mapeamento
        doc_id_formatado = id_to_formatted_map.get(doc_id)
        if not doc_id_formatado:
            logger.warning(
                "Número SEI não encontrado para a fonte do documento %s", doc_id
            )
        tooltip = create_doc_tooltip(doc_id, doc_id_formatado, current_index, doc_count)
        processed_text = processed_text.replace(full_marker, tooltip, 1)

        logger.debug(
            f"Processado marcador {full_marker} -> [{current_index}] (formatado: {doc_id_formatado})"
        )

    logger.debug(f"Processados {len(markers)} marcadores de documentos")
    return processed_text, sequential_number


# ==================== WEB SEARCH ====================


def extract_web_search_markers(response_text: str) -> list[tuple[str, str]]:
    """Extrai marcadores de web search do texto de resposta.

    Args:
        response_text: Texto da resposta com marcadores

    Returns:
        Lista de tuplas (marker_completo, idx)
    """
    markers = []
    matches = re.findall(PATTERN_WEB_SEARCH_MARKER, response_text)

    for idx in matches:
        full_marker = f"<web_{idx}>"  # Marcador simplificado, sem fechamento
        markers.append((full_marker, idx))

    return markers


def replace_web_search_markers_with_tooltips(
    response_text: str, user_state: UserState, start_number: int = 1
) -> tuple[str, int]:
    """Substitui marcadores <web_N> por tooltips HTML com links clicáveis.

    Args:
        response_text: Texto com marcadores de web search
        user_state: Estado com dados de tool_web_search
        start_number: Número inicial para a numeração sequencial

    Returns:
        Tupla (texto_processado, próximo_número_disponível)
    """
    markers = extract_web_search_markers(response_text)
    processed_text = response_text

    # Mapear para numeração sequencial (baseado na ordem de aparição)
    web_sequential_map = {}
    sequential_number = start_number

    for _, idx in markers:
        if idx not in web_sequential_map:
            web_sequential_map[idx] = sequential_number
            sequential_number += 1

    # Processar em ordem reversa para não afetar posições
    for full_marker, idx in reversed(markers):
        seq_num = web_sequential_map[idx]
        metadata = find_web_search_metadata(idx, user_state)

        if metadata:
            tooltip = create_web_search_tooltip(metadata, seq_num)
            processed_text = processed_text.replace(full_marker, tooltip, 1)
        else:
            # Fallback: remover marcador se não encontrar metadados
            logger.warning(f"Metadados não encontrados para web_search idx={idx}")
            processed_text = processed_text.replace(full_marker, "", 1)

    # Limpar tags de fechamento soltas </web_N> que possam existir
    processed_text = re.sub(r"</web_\d+>", "", processed_text)

    # Anexa a seção "Referências" com [N]: url das fontes web citadas.
    section = build_web_references_section(
        _collect_web_reference_entries(web_sequential_map, user_state)
    )
    if section:
        processed_text += section

    logger.debug(f"Processados {len(markers)} marcadores de web search")
    return processed_text, sequential_number


def transform_response_sources_enhanced(response: dict, user_state: UserState) -> str:
    """Pipeline aprimorado de transformação que suporta chunks, documentos e web search.

    A numeração é global e sequencial, garantindo que não haja números duplicados
    entre diferentes tipos de fontes (chunks, documentos e web search).

    Args:
        response_text: Texto da resposta
        user_state: Estado com dados dos chunks, documentos e web search

    Returns:
        Texto processado com tooltips apropriados
    """
    response_text = response["response"]
    next_number = 1  # Contador global para numeração sequencial

    # Processar marcadores de chunks
    if re.search(PATTERN_CHUNK_MARKER, response_text):
        logger.info("Processando resposta com marcadores de chunks")
        response_text, next_number = replace_chunk_markers_with_tooltips(
            response_text, user_state, next_number
        )

    # Processar marcadores de documentos
    if re.search(PATTERN_DOC_MARKER, response_text):
        logger.info("Processando resposta com marcadores de documentos")
        response_text, next_number = replace_doc_markers_with_tooltips(
            response_text, user_state, next_number
        )

    # Processar marcadores de web search
    if re.search(PATTERN_WEB_SEARCH_MARKER, response_text):
        logger.info("Processando resposta com marcadores de web search")
        response_text, next_number = replace_web_search_markers_with_tooltips(
            response_text, user_state, next_number
        )

    logger.debug(f"Total de fontes processadas: {next_number - 1}")
    response["response"] = response_text
    return response
