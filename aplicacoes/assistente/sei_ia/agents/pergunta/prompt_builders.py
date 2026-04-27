"""Construtores de prompt para documentos completos e chunks agrupados."""

import inspect
import logging

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException500,
)

setup_logging()
logger = logging.getLogger(__name__)


def build_prompt_with_complete_documents(
    document_ids: set[str], document_scores: dict[str, float], user_state: UserState
) -> str:
    """
    Constrói prompt com documentos completos ordenados por relevância.

    Os documentos já têm o content formatado com tags via INTERMEDIATE_COMPLETATION_WITH_DOC.

    Args:
        document_ids: Set de IDs de documentos a incluir
        document_scores: Dict com scores de relevância por documento
        user_state: Estado com documentos e configurações
    Returns:
        Prompt formatado com documentos completos
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug(f"Construindo prompt com {len(document_ids)} documentos completos")

    documents_with_scores = []
    for proc in user_state.get("id_procedimentos", []):
        for doc in proc.id_documentos if hasattr(proc, "id_documentos") else []:
            if doc.id_documento in document_ids:
                score = document_scores.get(doc.id_documento, 0)

                if hasattr(doc, "content") and doc.content:
                    doc_id_for_marker = doc.id_documento
                    documents_with_scores.append(
                        (
                            score,
                            doc.content,
                            doc_id_for_marker,
                            doc.id_documento_formatado,
                            getattr(doc, "metadata", "") or "",
                        )
                    )
                    logger.debug(
                        f"Documento {doc.id_documento}: score {score:.3f}, tamanho: {len(doc.content)} chars"
                    )
                else:
                    logger.warning(f"Documento {doc.id_documento} sem content")

    # Ordenar por score decrescente (mais relevantes primeiro)
    documents_with_scores.sort(key=lambda x: x[0], reverse=True)

    # Armazenar contagem de documentos para processamento posterior
    user_state["rag_documents_count"] = len(documents_with_scores)

    logger.debug(
        f"Documentos encontrados para incluir no prompt: {len(documents_with_scores)}"
    )
    if not documents_with_scores:
        HTTPException500(detail="Problema durante o RAG. Nenhum documento encontrado")

    # Criar mapeamento de id_documento para id_documento_formatado para uso posterior
    id_to_formatted = {}
    docs_content = []
    for score, content, doc_id, doc_id_formatado, meta in documents_with_scores:
        # O conteúdo já vem formatado com delimitadores do template INTERMEDIATE_COMPLETATION_WITH_DOC
        inner = f"{meta}\n{content}" if meta else content
        marked_content = f"<doc_{doc_id}>\n{inner}\n</doc_{doc_id}>"
        docs_content.append(marked_content)
        id_to_formatted[doc_id] = doc_id_formatado
        logger.debug(
            f"Adicionado documento {doc_id} (formatado: {doc_id_formatado}) com score {score:.3f}"
        )

    # Armazenar mapeamento no user_state para uso em replace_doc_markers_with_tooltips
    user_state["id_to_formatted_map"] = id_to_formatted

    prompt = f"""
    [DOCUMENTOS RELEVANTES]
    {"".join(docs_content)}
    [/DOCUMENTOS RELEVANTES]

    [INSTRUÇÕES PARA CITAÇÕES]
    Quando referenciar informações dos documentos acima, use os marcadores <doc_ID></doc_ID> que aparecem antes de cada documento.
    Por exemplo: "Conforme indicado no documento <doc_12345></doc_12345>, o processo deve..."
    IMPORTANTE: Use os marcadores exatamente como mostrado, SEM adicionar parênteses, colchetes ou outros caracteres ao redor.
    Correto: texto <doc_12345></doc_12345> mais texto
    Incorreto: texto (<doc_12345></doc_12345>) mais texto
    Incorreto: texto [<doc_12345></doc_12345>] mais texto
    Estes marcadores serão convertidos automaticamente em referências formatadas para o usuário final.
    Use os marcadores se maneira razoável, e de preferência uma vez , onde ele de fato foi utilizado como base argumentativa.
    [/INSTRUÇÕES PARA CITAÇÕES]

    Pergunta do usuário: {user_state["user_request"]}
    """

    logger.info(
        f"Prompt montado com {len(docs_content)} documentos completos ordenados por relevância"
    )
    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")

    return prompt


def build_prompt_with_grouped_chunks(chunks: list[dict], user_state: UserState) -> str:
    """
    Constrói prompt agrupando chunks por documento com metadados.

    Args:
        chunks: Lista de chunks ordenados por relevância
        user_state: Estado com documentos e metadados

    Returns:
        Prompt formatado com chunks agrupados por documento
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug(f"Construindo prompt com {len(chunks)} chunks")

    # Agrupar chunks por documento
    chunks_by_doc = {}
    for chunk in chunks:
        doc_id = chunk.get("id_documento")
        if doc_id not in chunks_by_doc:
            chunks_by_doc[doc_id] = []
        chunks_by_doc[doc_id].append(chunk)

    logger.debug(f"Chunks agrupados em {len(chunks_by_doc)} documentos")

    # Buscar metadados para cada documento e construir seções
    formatted_sections = []
    id_para_formatado = {}

    for doc_id, doc_chunks in chunks_by_doc.items():
        # Buscar metadados do documento no user_state
        doc_metadata_str = "Não disponível"
        proc_metadata_str = "Não disponível"

        for proc in user_state["id_procedimentos"]:
            for doc in proc.id_documentos:
                if doc.id_documento == doc_id:
                    id_para_formatado[doc_id] = doc.id_documento_formatado
                    id_doc_formatado = doc.id_documento_formatado
                    # Se metadata for string, usar diretamente; se for dict, formatar
                    if hasattr(doc, "metadata") and doc.metadata:
                        if isinstance(doc.metadata, str):
                            doc_metadata_str = doc.metadata
                        else:
                            doc_metadata_str = _format_metadata_dict(doc.metadata)

                    # Mesmo para procedimento
                    if hasattr(proc, "metadata") and proc.metadata:
                        if isinstance(proc.metadata, str):
                            proc_metadata_str = proc.metadata
                        else:
                            proc_metadata_str = _format_metadata_dict(proc.metadata)
                    break
            if doc_metadata_str != "Não disponível":
                break

        # Formatar seção do documento com chunks
        section = f"""
                    -------
                    # Trechos relevantes do documento #{id_doc_formatado}
                    [metadados---]
                    Processo: {proc_metadata_str}
                    Documento: {doc_metadata_str}
                    [\\metadados---]
                    [chunks_doc_{id_doc_formatado}---]
                    """

        # Adicionar chunks do documento ordenados por relevância
        doc_chunks_sorted = sorted(
            doc_chunks, key=lambda x: x.get("similarity_score", 0), reverse=True
        )

        for i, chunk in enumerate(doc_chunks_sorted, 1):
            chunk_text = chunk.get("text", "")
            similarity_score = chunk.get("similarity_score", 0)
            # Alinhar ao padrão oficial de marcadores de chunks: <doc_{doc_id}_{chunk_idx}></doc_{doc_id}_{chunk_idx}>
            section += f"\n<doc_{id_doc_formatado}_{i}></doc_{id_doc_formatado}_{i}>\nTrecho {i} (relevância: {similarity_score:.3f}):\n{chunk_text}\n"

        section += f"[\\chunks_doc_{id_doc_formatado}---]\n"
        formatted_sections.append(section)

        logger.debug(
            f"Documento {id_doc_formatado}: {len(doc_chunks_sorted)} chunks formatados"
        )

    # Montar prompt final com instruções para uso dos marcadores
    prompt = f"""
            [TRECHOS RELEVANTES DOS DOCUMENTOS]
            {"".join(formatted_sections)}
            [/TRECHOS RELEVANTES DOS DOCUMENTOS]

            [INSTRUÇÕES PARA CITAÇÕES]
            Quando referenciar informações dos trechos acima, use os marcadores de reserva de memória
            <doc_{id_doc_formatado}_{i}></doc_{id_doc_formatado}_{i}> exatamente como aparecem no texto.
            Por exemplo: "Conforme indicado <doc_12345_1></doc_12345_1>, o processo deve..."

            Estes marcadores serão convertidos automaticamente em tooltips informativos para o usuário final.
            [/INSTRUÇÕES PARA CITAÇÕES]

            Pergunta do usuário: {user_state["user_request"]}
            """

    # Armazenar dados dos chunks no user_state para processamento posterior das fontes
    chunks_with_metadata = []
    for chunk in chunks:
        chunk_with_metadata = chunk.copy()
        chunk_with_metadata["id_documento_formatado"] = id_para_formatado[
            chunk["id_documento"]
        ]
        chunk_with_metadata["chunk_index"] = None  # Será definido dinamicamente
        chunks_with_metadata.append(chunk_with_metadata)

    user_state["rag_chunks_data"] = chunks_with_metadata
    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")

    return prompt


def _format_metadata_dict(metadata: dict) -> str:
    """
    Formata dicionário de metadados como string legível.

    Args:
        metadata: Dicionário com metadados

    Returns:
        String formatada com os metadados
    """
    if not metadata:
        return "Não disponível"

    # Converter valores para string e filtrar vazios
    formatted_items = []
    for key, value in metadata.items():
        if value is not None and str(value).strip():
            formatted_items.append(f"{key}: {value}")

    return ", ".join(formatted_items) if formatted_items else "Não disponível"
