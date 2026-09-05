"""Modulo para extracao e manipulacao de citações - suporte a chunks e documentos completos."""

import logging
import re
from re import Match

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import UserState

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


def clean_chunk_text_for_display(text: str) -> str:
    r"""Remove o cabeçalho técnico do texto do chunk para exibição no tooltip.

    O cabeçalho técnico tem o formato:
    -------
    # o conteúdo do documento #<ID>
    está transcrito abaixo:
    (delimitado por [doc_<ID>---] conteúdo [\doc_<ID>---])
    [doc_<ID>---]
    <conteúdo real>
    [\doc_<ID>---]

    Args:
        text: Texto do chunk com possível cabeçalho técnico

    Returns:
        Texto limpo sem o cabeçalho técnico
    """
    # Remover o cabeçalho completo até (e incluindo) a última ocorrência de [doc_<ID>---]
    # que está em uma linha separada (após a linha de descrição)
    pattern_header = r"^-+\s*\n#\s*o\s+conteúdo\s+do\s+documento\s+#\d+\s*\nestá\s+transcrito\s+abaixo:\s*\n\(delimitado por.*?\)\s*\n\[doc_\d+---\]\s*\n"
    text_without_header = re.sub(
        pattern_header, "", text, flags=re.MULTILINE | re.DOTALL
    )

    # Remover o delimitador de fechamento se existir
    text_without_footer = re.sub(
        r"^\s*\[\\doc_\d+---\]\s*$", "", text_without_header, flags=re.MULTILINE
    )

    return text_without_footer.strip() if text_without_footer else text


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


def find_chunk_metadata(
    chunk_index: str, id_doc_formatado: str, user_state: UserState
) -> dict[str, str]:
    """Busca metadados do chunk específico nos dados do user_state.

    Args:
        chunk_index: Índice do chunk (ex: "1")
        doc_id: ID do documento
        user_state: Estado com dados dos chunks

    Returns:
        Dicionário com metadados do chunk
    """

    # Buscar nos chunks do RAG se estiver disponível
    if user_state.get("rag_chunks_data"):
        # Mapear chunks por documento e índice baseado na ordem
        chunks_by_doc = {}
        for chunk in user_state["rag_chunks_data"]:
            chunk_doc_id = chunk.get("id_documento_formatado")
            if chunk_doc_id not in chunks_by_doc:
                chunks_by_doc[chunk_doc_id] = []
            chunks_by_doc[chunk_doc_id].append(chunk)

        # Buscar chunk específico por documento e índice
        if id_doc_formatado in chunks_by_doc:
            doc_chunks = chunks_by_doc[id_doc_formatado]
            chunk_idx = int(chunk_index) - 1  # Converter para índice 0-based
            if 0 <= chunk_idx < len(doc_chunks):
                chunk = doc_chunks[chunk_idx]
                similarity_score = chunk.get("similarity_score", 0)
                chunk_text = (
                    chunk.get("text", "")[:150] + "..."
                    if len(chunk.get("text", "")) > 150
                    else chunk.get("text", "")
                )

                return {
                    "doc_id": chunk.get("id_documento"),
                    "chunk_index": chunk_index,
                    "similarity_score": f"{similarity_score:.3f}",
                    "preview": chunk_text,
                    "full_text": chunk.get("text", ""),
                    "id_documento_formatado": chunk.get("id_documento_formatado"),
                }


def create_chunk_tooltip(
    chunk_metadata: dict[str, str], sequential_number: int | None = None
) -> str:
    """Gera HTML com tooltip lateral para chunk.

    Args:
        chunk_metadata: Metadados do chunk
        sequential_number: Número sequencial para exibição ao usuário (opcional)

    Returns:
        String HTML com tooltip
    """
    # Usar numeração sequencial se fornecida, caso contrário usar chunk_index original
    display_number = (
        sequential_number
        if sequential_number is not None
        else chunk_metadata.get("chunk_index")
    )

    # Limpar o texto do cabeçalho técnico antes de exibir no tooltip
    full_text = chunk_metadata.get("full_text", "")
    clean_text = clean_chunk_text_for_display(full_text)

    # Escapa o title inteiro — inclui o '|' separador e qualquer '|'/markdown vindo do
    # conteúdo do chunk, que quebrariam a tabela se a citação cair numa célula.
    title = _escape_tooltip_title(
        f"Documento SEI nº {chunk_metadata.get('id_documento_formatado')} | {clean_text}"
    )
    return (
        f'<a href="#" data-toggle="tooltip" data-html="true" '
        f'class="AssistenteSEIIAfonteResposta" title="{title}">[{display_number}]</a>'
    )


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


def create_doc_tooltip(
    doc_id: str,  # noqa: ARG001  # NOSONAR
    doc_id_formatado: str | None,
    relative_index: int,
    doc_count: int,  # noqa: ARG001  # NOSONAR
) -> str:
    """Gera HTML com tooltip para documento (sem conteúdo).

    Args:
        doc_id: ID do documento (numérico)
        doc_id_formatado: ID formatado do documento, quando disponível
        relative_index: Índice relativo do documento (1, 2, 3...)
        doc_count: Número total de documentos usados

    Returns:
        String HTML com tooltip
    """
    visible_number = str(doc_id_formatado or "").strip()
    title_text = (
        f"Documento SEI nº {visible_number}"
        if visible_number
        else "Documento SEI (número não disponível)"
    )
    title = _escape_tooltip_title(title_text)
    return (
        f'<a href="#" data-toggle="tooltip" data-html="true" '
        f'class="AssistenteSEIIAfonteResposta" title="{title}">[{relative_index}]</a>'
    )


def create_upload_tooltip(filename: str, relative_index: int) -> str:
    """Gera HTML com tooltip para um arquivo enviado pelo usuário.

    Args:
        filename: Nome original do arquivo enviado.
        relative_index: Índice global da fonte na resposta.

    Returns:
        String HTML com o nome do arquivo como único conteúdo do tooltip.
    """
    title = _escape_tooltip_title(filename)
    return (
        f'<a href="#" data-toggle="tooltip" data-html="true" '
        f'class="AssistenteSEIIAfonteResposta" title="{title}">[{relative_index}]</a>'
    )


def get_document_count(user_state: UserState) -> int:
    """Conta o número de documentos utilizados na resposta.

    Args:
        user_state: Estado com informações dos documentos

    Returns:
        Número de documentos utilizados
    """
    if user_state is None:
        return 0

    if user_state.get("rag_documents_count"):
        return user_state["rag_documents_count"]

    doc_count = 0
    id_procedimentos = user_state.get("id_procedimentos") or []
    for proc in id_procedimentos:
        doc_count += len(proc.id_documentos)

    return doc_count


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


def _escape_tooltip_title(text: str) -> str:
    """Escapa um texto para uso seguro no atributo title="" de um tooltip de citação.

    Faz duas coisas, ambas via entidades HTML (o navegador decodifica na exibição, então
    o texto que aparece no tooltip não muda):

    1. Escapa os caracteres que quebram o atributo HTML / a tabela GFM:
       ``& " < >`` e o pipe ``|`` (que, cru numa célula, é lido como separador de coluna).

    2. Neutraliza os caracteres estruturais de markdown — backtick, ``[``, ``]`` e ``*``.
       Isso é necessário porque o frontend re-parseia o conteúdo da célula como markdown
       e **também o conteúdo do atributo title**: um ``[texto](url)`` cru dentro do title
       vira ``<a href="url">``, e essas aspas fecham o ``title=""`` no meio, destruindo o
       HTML e a tabela. Encodando ``[`` → ``&#91;`` etc., o parser não forma mais
       link/imagem/código, mas o tooltip continua exibindo o texto original.
    """
    return (
        text.replace("&", "&amp;")  # precisa vir primeiro
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "&#124;")
        .replace("`", "&#96;")
        .replace("[", "&#91;")
        .replace("]", "&#93;")
        .replace("*", "&#42;")
    )


def _clean_web_excerpt(text: str, max_len: int = 250) -> str:
    """Limpa e trunca o conteúdo de uma página para exibição no tooltip.

    Apenas colapsa espaços/quebras e trunca em max_len. O escape para o atributo
    title="" (inclusive o pipe, que quebraria a tabela markdown) é feito no builder do
    tooltip via _escape_tooltip_title — assim há um único ponto de escape, no limite de
    saída, independente de quem montou o preview.
    """
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip() + "..."
    return cleaned


def build_web_references_section(entries: list[tuple[int, str]]) -> str:
    """Monta a seção "Referências" (HTML) listando [N]: url das fontes web citadas.

    Usa HTML (não markdown) porque '[N]: url' em markdown é interpretado como
    definição de link de referência e não seria renderizado. Deduplica por número
    sequencial e ordena de forma crescente.
    """
    if not entries:
        return ""
    seen: set[int] = set()
    lines: list[str] = []
    for seq, url in sorted(entries, key=lambda e: e[0]):
        if seq in seen or not url:
            continue
        seen.add(seq)
        lines.append(
            f'[{seq}]: <a href="{url}" target="_blank" '
            f'class="AssistenteSEIIAfonteWebSearch">{url}</a>'
        )
    if not lines:
        return ""
    body = "<br>".join(lines)
    return f"\n\n<p><strong>Referências:</strong><br>{body}</p>"


def _collect_web_reference_entries(
    web_sequential_map: dict[str, int], user_state: UserState
) -> list[tuple[int, str]]:
    """Resolve (número sequencial, url) de cada marcador web citado para a seção."""
    entries: list[tuple[int, str]] = []
    for idx, seq in web_sequential_map.items():
        metadata = find_web_search_metadata(idx, user_state)
        if metadata:
            entries.append((seq, metadata.get("url", "")))
    return entries


def find_web_search_metadata(idx: str, user_state: UserState) -> dict[str, str] | None:
    """Busca metadados do resultado de web search pelo índice.

    Args:
        idx: Índice do resultado (ex: "1")
        user_state: Estado com dados de tool_web_search

    Returns:
        Dicionário com url, title e preview (trecho do conteúdo) do resultado,
        ou None se não encontrado
    """
    tool_web_search = user_state.get("tool_web_search", [])
    search_idx = int(idx)

    for result in tool_web_search:
        if result.get("idx") != search_idx:
            continue
        references = result.get("references", [])
        if references:
            ref = references[0]
            # Trecho exibido no tooltip: prioriza o snippet do SearXNG (trecho
            # relevante à query) sobre o content da página crua, cujo início costuma
            # ser navegação/cookies em vez do conteúdo que fundamentou a citação.
            # Fallback para o content quando não há snippet (ex.: páginas sem snippet).
            excerpt_source = ref.get("snippet") or result.get("content") or ""
            return {
                "idx": str(search_idx),
                "url": ref.get("url", ""),
                "title": ref.get("title", ""),
                "preview": _clean_web_excerpt(excerpt_source),
            }

    logger.warning(f"Metadados não encontrados para web_search idx={idx}")
    return None


def create_web_search_tooltip(metadata: dict[str, str], sequential_number: int) -> str:
    """Gera HTML com tooltip para resultado de web search.

    Args:
        metadata: Metadados do resultado (url, title, preview)
        sequential_number: Número sequencial para exibição

    Returns:
        String HTML com link clicável e tooltip mostrando o trecho da página
        usado como fonte (cai para a URL se não houver trecho).
    """
    url = metadata.get("url", "#")
    preview = metadata.get("preview") or url
    title = _escape_tooltip_title(preview)

    return (
        f'<a href="{url}" target="_blank" data-toggle="tooltip" data-html="true" '
        f'class="AssistenteSEIIAfonteWebSearch" title="{title}">[{sequential_number}]</a>'
    )


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
