"""Módulo para processar intenção 'pergunta' com novo fluxo otimizado."""

import inspect
import logging

from sei_ia.agents.pergunta.auto_indexing import (
    auto_index_missing_documents,
    should_auto_index,
    verify_indexation_after_auto_index,
)
from sei_ia.agents.pergunta.document_decision import (
    calculate_max_chunks,
    check_if_complete_documents_fit,
)
from sei_ia.agents.pergunta.document_validation import check_all_documents_indexed
from sei_ia.agents.pergunta.multi_search_rag import search_with_multiple_questions
from sei_ia.agents.pergunta.prompt_builders import (
    build_prompt_with_complete_documents,
    build_prompt_with_grouped_chunks,
)
from sei_ia.agents.pergunta.question_generator import generate_multiple_questions
from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.exceptions.rag_exceptions import (
    DocumentsNotIndexedException,
    EmbeddingVerificationException,
)

setup_logging()
logger = logging.getLogger(__name__)


async def process_question_intent(user_state: UserState) -> UserState:
    """Processa intenção 'pergunta' com novo fluxo otimizado.

    Args:
        user_state: Estado do usuário com documentos e requisição

    Returns:
        UserState atualizado com prompt montado
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug(
        f"Tokens totais: {user_state['all_tokens_counter']}, "
        f"Limite contexto: {user_state['general_max_ctx_len']}"
    )

    # Verificação inicial de tamanho
    if check_initial_size(user_state):
        logger.debug("Usando caminho direto (documentos cabem no contexto)")
        user_state = build_direct_prompt(user_state)
    else:
        logger.debug("Usando caminho RAG (documentos excedem contexto)")

        # VERIFICAÇÃO OBRIGATÓRIA: Todos os documentos devem estar indexados para RAG
        logger.debug(
            "Verificando se todos os documentos estão indexados no banco vetorial..."
        )
        indexation_result = await check_all_documents_indexed(user_state)

        if not indexation_result["all_indexed"]:
            missing_docs = indexation_result["missing_documents"]
            total_docs = indexation_result["total_documents"]

            # Verificar se houve erro na verificação
            if "error" in indexation_result:
                raise EmbeddingVerificationException(indexation_result["error"])

            # Tentar indexação automática
            if should_auto_index(len(missing_docs), total_docs):
                logger.debug(
                    f"Executando indexação automática para {len(missing_docs)} documentos faltantes..."
                )

                try:
                    await auto_index_missing_documents(missing_docs, user_state)

                    # Verificar se indexação foi bem-sucedida
                    indexation_success = await verify_indexation_after_auto_index(
                        missing_docs, user_state
                    )

                    if not indexation_success:
                        logger.error("Indexação automática falhou")
                        raise DocumentsNotIndexedException(missing_docs, total_docs)

                    logger.debug("✓ Indexação automática concluída com sucesso")

                except Exception as e:
                    logger.error(f"Erro na indexação automática: {e}")
                    # Se indexação falhar, lançar erro original
                    raise DocumentsNotIndexedException(missing_docs, total_docs) from e
            else:
                logger.warning("Indexação automática não recomendada para este caso")
                raise DocumentsNotIndexedException(missing_docs, total_docs)

        logger.debug(
            f"✓ Todos os {indexation_result.get('total_documents', 'documentos')} documentos estão indexados"
        )
        user_state = await make_prompt_with_rag_enhanced(user_state)

    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
    return user_state


def check_initial_size(user_state: UserState) -> bool:
    """Verifica se documentos cabem no contexto sem RAG.

    Args:
        user_state: Estado do usuário

    Returns:
        True se documentos cabem no contexto, False caso contrário
    """
    return user_state["all_tokens_counter"] <= user_state["general_max_ctx_len"]


def build_direct_prompt(user_state: UserState) -> UserState:
    """Monta prompt direto com todos os documentos.

    Args:
        user_state: Estado do usuário

    Returns:
        UserState com prompt montado
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    # Concatenar todos os documentos com marcadores
    all_docs_content = []
    doc_count = 0
    id_to_formatted = {}

    for proc in user_state["id_procedimentos"]:
        for doc in proc.id_documentos:
            if hasattr(doc, "content") and doc.content:
                doc_count += 1
                doc_id_for_marker = doc.id_documento
                meta = getattr(doc, "metadata", "") or ""
                inner = f"{meta}\n{doc.content}" if meta else doc.content
                marked_content = (
                    f"<doc_{doc_id_for_marker}>\n{inner}\n</doc_{doc_id_for_marker}>"
                )
                all_docs_content.append(marked_content)
                # Armazenar mapeamento de id_documento -> id_documento_formatado
                if hasattr(doc, "id_documento_formatado"):
                    id_to_formatted[doc.id_documento] = doc.id_documento_formatado
                    logger.debug(
                        f"Mapeamento criado: {doc.id_documento} -> {doc.id_documento_formatado}"
                    )
                else:
                    logger.warning(
                        f"Documento {doc.id_documento} sem id_documento_formatado"
                    )

    # Armazenar contagem e mapeamento para processamento posterior
    user_state["rag_documents_count"] = doc_count
    user_state["id_to_formatted_map"] = id_to_formatted

    # Montar prompt final
    if all_docs_content:
        docs_text = "\n\n".join(all_docs_content)
        prompt = f"""
{docs_text}

[INSTRUÇÕES PARA CITAÇÕES]
Quando referenciar informações dos documentos acima, use os marcadores <doc_ID></doc_ID> que aparecem antes de cada documento.
Por exemplo: "Conforme indicado no documento <doc_12345></doc_12345>, o processo deve..."
IMPORTANTE: Use os marcadores exatamente como mostrado, SEM adicionar parênteses, colchetes ou outros caracteres ao redor.
Correto: texto <doc_12345></doc_12345> mais texto
Incorreto: texto (<doc_12345></doc_12345>) mais texto
Incorreto: texto [<doc_12345></doc_12345>] mais texto
Estes marcadores serão convertidos automaticamente em referências formatadas para o usuário final
Use os marcadores se maneira razoável, e de preferência uma vez , onde ele de fato foi utilizado como base argumentativa.
[/INSTRUÇÕES PARA CITAÇÕES]

{user_state["user_request"]}
"""
    else:
        prompt = user_state["user_request"]

    user_state["last_prompt"] = prompt
    user_state["doc_rag"] = False

    logger.debug(f"Prompt montado com {len(all_docs_content)} documentos")
    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")

    return user_state


async def make_prompt_with_rag_enhanced(user_state: UserState) -> UserState:
    """
    RAG Enhanced com múltiplas perguntas - IMPLEMENTAÇÃO COMPLETA.

    1. Gera múltiplas perguntas usando LLM
    2. Busca chunks para cada pergunta
    3. Decide entre documentos completos ou chunks
    4. Monta prompt final com formatação apropriada

    Args:
        user_state: Estado do usuário

    Returns:
        UserState com prompt montado via RAG enhanced
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    try:
        # PASSO 1: Gerar múltiplas perguntas
        logger.debug("Passo 1: Gerando múltiplas perguntas")
        questions = generate_multiple_questions(user_state)
        logger.info(f"Geradas {len(questions)} perguntas para busca")

        # Validar perguntas geradas
        if not questions:
            logger.error("Nenhuma pergunta foi gerada para busca RAG")
            # Fallback: usar a pergunta original
            questions = [user_state.get("user_request", "")]
            logger.info("Usando pergunta original como fallback")

        # PASSO 2: Buscar com todas as perguntas
        logger.debug(
            "Passo 2: Executando busca com múltiplas perguntas de forma assíncrona"
        )
        logger.debug(f"Perguntas para busca: {questions}")

        search_results = await search_with_multiple_questions(questions, user_state)

        chunks = search_results.get("chunks", [])
        document_ids = search_results.get("document_ids", set())
        document_scores = search_results.get("document_scores", {})

        # Validar resultados da busca
        if not chunks and not document_ids:
            logger.warning("RAG não encontrou nenhum documento ou chunk relevante")
            # Montar prompt sem documentos
            prompt = f"""
    [DOCUMENTOS RELEVANTES]

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
            user_state["last_prompt"] = prompt
            user_state["doc_rag"] = True
            user_state["rag_method"] = "no_results"
            user_state["rag_documents_count"] = 0
            user_state["rag_chunks_count"] = 0
            return user_state

        # PASSO 3: Decidir entre documentos completos ou chunks
        logger.debug("Passo 3: Decidindo entre documentos completos vs chunks")
        docs_fit, total_tokens = check_if_complete_documents_fit(
            document_ids, user_state
        )

        # PASSO 4: Construir prompt apropriado
        if docs_fit:
            logger.info("Usando documentos completos (cabem no contexto)")
            prompt = build_prompt_with_complete_documents(
                document_ids, document_scores, user_state
            )
            user_state["rag_method"] = "complete_documents"
        else:
            logger.info(
                f"Usando chunks agrupados ({total_tokens} tokens excedem limite)"
            )
            # Limitar chunks ao que cabe no contexto
            max_chunks = calculate_max_chunks(chunks, user_state)
            limited_chunks = chunks[:max_chunks]

            prompt = build_prompt_with_grouped_chunks(limited_chunks, user_state)
            user_state["rag_method"] = "grouped_chunks"

        user_state["last_prompt"] = prompt
        user_state["doc_rag"] = True
        user_state["rag_documents_count"] = len(document_ids)
        user_state["rag_chunks_count"] = len(chunks)

        logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
        return user_state

    except Exception as e:
        error_msg = f"ERRO CRÍTICO no RAG enhanced: {e}"
        logger.error(error_msg)
        logger.error("Stack trace:", exc_info=True)
        # NÃO usar fallback - deixar o erro aparecer
        raise RuntimeError(error_msg) from e


def generate_reference_tooltip(used_documents: list[str]) -> str:
    """Gera tooltip de referências dos documentos.

    Args:
        used_documents: Lista de IDs dos documentos utilizados

    Returns:
        String formatada com referências
    """
    if not used_documents:
        return ""

    # Formatar como "Docs: 1, 3, 7, 12"
    doc_numbers = [str(i) for i in range(1, len(used_documents) + 1)]
    return f"Docs: {', '.join(doc_numbers)}"
