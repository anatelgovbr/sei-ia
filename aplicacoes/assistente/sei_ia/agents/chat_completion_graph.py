"""Module for chat completion workflow graph implementation."""

import contextlib
import inspect
import logging
from datetime import datetime

import httpx
import litellm
import openai
from fastapi import HTTPException
from httpx._exceptions import ReadTimeout
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import StreamWriter

from sei_ia.agents.disclaimer import (
    classify_disclaimer_need,
    prepare_disclaimer_for_response,
)
from sei_ia.agents.grammar_checker import make_prompt_with_doc_grammar_correction
from sei_ia.agents.intent_selector_agent import intent_selector_agent
from sei_ia.agents.pergunta import process_question_intent
from sei_ia.agents.rag.sources import transform_response_sources_enhanced
from sei_ia.agents.summarize.prompt_with_doc_summarization import (
    make_prompt_with_doc_summarization,
)
from sei_ia.agents.websearch.azure_web_search_tool import BingGroundingAgent
from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.etl.concatenate_documents import (
    concatenate_documents,
    initialize_document_processing_state,
)
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException204,
    HTTPException403,
    HTTPException404,
    HTTPException408,
    HTTPException413,
    HTTPException429,
    HTTPException500,
)
from sei_ia.services.llm_models.chat_workflow import chat_gpt

setup_logging()
logger = logging.getLogger(__name__)


async def build_chat_completion_graph() -> CompiledStateGraph:
    """
    Build the chat completion workflow graph com observabilidade Langfuse v3.

    Estrutura otimizada com execução paralela:
    - classify_disclaimer_need executa em paralelo com detect_document
    - classify_disclaimer preenche disclaimer_case no state (não bloqueia fluxo)
    - merge_disclaimer usa o disclaimer_case para preparar disclaimer_text
    - generate_response adiciona o disclaimer e gera a resposta
    - Ganho estimado: ~1.5 segundos por requisição

    Fluxo:
    1. START → start_parallel → [detect_document || classify_disclaimer] (paralelo)
    2. classify_disclaimer preenche disclaimer_case e termina (sem bloquear)
    3. detect_document → concatenate_docs → detect_intent → handlers (sequencial)
    4. handlers → merge_disclaimer (usa disclaimer_case do state)
    5. merge_disclaimer → generate_response (adiciona disclaimer)
    6. generate_response → END
    """

    # Aplicar wrapper a todas as funções de nó
    async def start_parallel_flow(state: UserState) -> dict:
        """Node de entrada que inicia o fluxo paralelo de detect_document e classify_disclaimer."""
        logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
        # Retorna dict vazio - este node não modifica nada, apenas dispara o fanout
        return {}

    nodes = {
        "start_workflow": start_parallel_flow,
        "start_workflow_with_web_search": start_parallel_flow,
        "detect_document": initialize_document_processing_state,
        "web_search": web_search_node,
        "concatenate_docs": concatenate_documents,
        "detect_intent": intent_selector_agent,
        "handle_question": handle_question,
        "handle_summarization": make_prompt_with_doc_summarization,
        "handle_grammar_correction": make_prompt_with_doc_grammar_correction,
        "generate_response": handle_response,
        "classify_disclaimer": classify_disclaimer_need,
        "merge_disclaimer": prepare_disclaimer_for_response,
    }
    workflow = StateGraph(UserState)
    # Adicionar nós ao workflow
    for name, func in nodes.items():
        workflow.add_node(name, func)

    # Criar node de entrada que dispara execução paralela

    # Adicionar edges iniciais
    workflow.add_conditional_edges(
        START,
        websearch_condition,
        {
            "use_web_search": "start_workflow_with_web_search",
            "skip_web_search": "start_workflow",
        },
    )

    # ========== OTIMIZAÇÃO: EXECUÇÃO PARALELA - INÍCIO DO FLUXO ==========

    # Início do fluxo sem web search
    workflow.add_edge("start_workflow", "detect_document")
    workflow.add_edge("start_workflow", "classify_disclaimer")

    # Início do fluxo com web search
    workflow.add_edge("start_workflow_with_web_search", "detect_document")
    workflow.add_edge("start_workflow_with_web_search", "classify_disclaimer")
    workflow.add_edge("start_workflow_with_web_search", "web_search")

    # Criar node intermediário para verificação de contexto quando não há documentos
    async def check_context_no_docs(state: UserState) -> dict:
        """Verifica limite de tokens quando não há documentos.

        Este node é ativado quando não há documentos para processar.

        Importante: Realiza verificação de limite de tokens antes de prosseguir,
        já que este fluxo bypassa concatenate_docs e detect_intent.
        """
        from sei_ia.agents.intent_selector_agent import check_length_context
        from sei_ia.services.exceptions.http_exceptions import HTTPException413

        # Verificação de limite de tokens (necessária neste fluxo sem documentos)
        if not check_length_context(state):
            logger.debug(">> check_context_no_docs: atingiu o limite de tokens.")
            msg = (
                f"Tamanho do contexto excedido ({state['all_tokens_counter']} tokens)."
            )
            raise HTTPException413(detail=msg)

        # Retorna dict vazio - este node apenas valida, não modifica state
        return {}

    workflow.add_node("check_context_no_docs", check_context_no_docs)

    # Rotas após detect_document
    workflow.add_conditional_edges(
        "detect_document",
        detect_document_condition,
        {"refer_docs": "concatenate_docs", "dont_refer_docs": "check_context_no_docs"},
    )

    # Fluxo normal: concatenate -> detect_intent -> handlers
    workflow.add_edge("concatenate_docs", "detect_intent")
    workflow.add_conditional_edges(
        "detect_intent",
        route_condition,
        {
            "summarize": "handle_summarization",
            "grammar": "handle_grammar_correction",
            "question": "handle_question",
        },
    )

    # ========== FLUXO SEQUENCIAL: handlers → merge_disclaimer → generate_response ==========
    # classify_disclaimer executa em paralelo, mas NÃO bloqueia o fluxo principal
    # Ele apenas preenche disclaimer_case no state

    # Handlers vão para merge_disclaimer (que usa o disclaimer_case já preenchido)
    workflow.add_edge("handle_summarization", "merge_disclaimer")
    workflow.add_edge("handle_question", "merge_disclaimer")
    workflow.add_edge("handle_grammar_correction", "merge_disclaimer")
    workflow.add_edge("check_context_no_docs", "merge_disclaimer")

    # merge_disclaimer → generate_response (ponto final)
    workflow.add_edge("merge_disclaimer", "generate_response")

    # generate_response → END
    workflow.add_edge("generate_response", END)

    return workflow.compile()


# Funções auxiliares (mantém lógica original)
def detect_document_condition(state: UserState) -> str:
    """Condição para decidir o próximo nó após detect_document."""
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    if len(state["all_documents"]) > 0:
        return "refer_docs"
    return "dont_refer_docs"


def websearch_condition(state: UserState) -> str:
    """Condição para decidir se deve executar busca web."""
    if state.get("use_websearch", False):
        return "use_web_search"
    return "skip_web_search"


async def web_search_node(state: UserState) -> dict:
    """Executa busca web e armazena resultado em web_content."""
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    _stream_writer = None
    try:
        _stream_writer = get_stream_writer()
        _stream_writer({"_status": "Pesquisando na Internet"})
    except Exception:
        pass

    agent = BingGroundingAgent()
    today = datetime.now().strftime("%d/%m/%Y")
    enriched_system = (
        f"{state['user_request']}\n\n"
        "Instruções adicionais:\n"
        f" - Considerar fontes mais recentes sabendo que a data de hoje é {today}.\n"
        "- Necessariamente use a ferramenta de websearch para buscar na internet fontes para sua resposta.\n"
    )
    result = await agent.process_user_prompt(enriched_system)

    if _stream_writer is not None:
        with contextlib.suppress(Exception):
            _stream_writer({"_status": "Pesquisa na Internet concluída"})

    # Estrutura das mensagens: AIMessage(tool_calls) -> ToolMessage(resultado)
    tool_call_map = {}  # {tool_call_id: query}
    for msg in result.get("messages", []):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_name = tool_call.get("name", "")
                if tool_name.startswith("bing_grounding"):
                    tool_call_id = tool_call.get("id", "")
                    query = tool_call.get("args", {}).get("query", "")
                    if tool_call_id and query:
                        tool_call_map[tool_call_id] = query

    # Extrair ToolMessages e associar com sua chamada de ToolCall
    tool_web_search = []
    idx = 1
    for msg in result.get("messages", []):
        if isinstance(msg, ToolMessage):
            tool_call_id = getattr(msg, "tool_call_id", "")
            query = tool_call_map.get(tool_call_id, "")
            content = getattr(msg, "content", "")

            if content:
                tool_web_search.append(
                    {
                        "content": content,
                        "query": query,
                        "node": "web_search_node",
                        "idx": idx,
                        "references": [],
                    }
                )
                idx += 1

    if not tool_web_search:
        tool_web_search = [
            {
                "content": "Não foi necessário buscar na web.",
                "query": "",
                "references": [],
            }
        ]

    logger.info(f"Busca web concluída. {len(tool_web_search)} resultados armazenados")

    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
    # Retorna apenas os campos modificados para suportar execução paralela
    return {"tool_web_search": tool_web_search}


def route_condition(state: UserState) -> str:
    """Determine which path to take based on state."""
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    if state["intent"] == "reescrever":
        return "grammar"
    if state["intent"] in ("multi_pergunta", "analise", "pergunta"):
        # Novo fluxo para intenção "pergunta" - sem false_rag
        return "question"
    return "summarize"


async def handle_question(state: UserState) -> UserState:
    """Handle question intent with new optimized flow."""
    try:
        logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
        state = await process_question_intent(state)

    except (HTTPException204, HTTPException404, HTTPException408) as e:
        raise e from e
    else:
        # Não definir doc_rag aqui pois é definido internamente no process_question_intent
        logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
        return state


async def handle_response(
    state: UserState, writer: StreamWriter | None = None
) -> UserState:
    """Wrapper para chat_gpt com tratamento de erros e aplicação de disclaimer."""
    try:
        logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

        # Obtém o stream writer do contexto (None se não estiver em modo streaming)
        try:
            writer = get_stream_writer()
        except Exception:
            writer = None

        # Verifica se há disclaimer preparado e faz streaming dele primeiro
        disclaimer_text = state.get("disclaimer_text")
        if disclaimer_text and writer is not None:
            # Faz streaming do disclaimer antes da resposta do LLM
            writer(disclaimer_text)

        response = await chat_gpt(state, writer=writer)
    except (ReadTimeout, openai.APITimeoutError) as exc:
        logger.exception(f"{inspect.currentframe().f_code.co_name}: Timeout error")
        raise HTTPException408 from exc
    except openai.BadRequestError as exc:
        logger.exception(
            f"{inspect.currentframe().f_code.co_name}: Context length exceeded"
        )
        error_json = None
        if hasattr(exc, "response") and hasattr(exc.response, "json"):
            try:
                error_json = exc.response.json()
            except (ValueError, TypeError, AttributeError):
                error_json = None
        if error_json:
            error_code = error_json.get("error", {}).get("code")
            inner_code = error_json.get("error", {}).get("innererror", {}).get("code")
            if (
                error_code == "content_filter"
                and inner_code == "ResponsibleAIPolicyViolation"
            ):
                msg = (
                    "Seu prompt foi bloqueado pela política de uso da OpenAI/Azure. "
                    "Por favor, revise o conteúdo e tente novamente."
                )
                raise HTTPException403(detail=msg) from exc
        msg = f"Tamanho do contexto excedido ({state.get('all_tokens_counter', 'N/A')} tokens)."
        raise HTTPException413(detail=msg) from exc
    except openai.RateLimitError as exc:
        logger.exception(f"{inspect.currentframe().f_code.co_name}: Rate limit error")
        raise HTTPException429 from exc
    except (httpx.RemoteProtocolError, litellm.exceptions.APIConnectionError) as exc:
        # Erros de conexão/streaming que não foram recuperados pelos retries
        logger.exception(
            f"{inspect.currentframe().f_code.co_name}: Erro de conexão com Azure OpenAI - "
            f"conexão interrompida durante streaming. Erro: {type(exc).__name__}: {exc}"
        )
        raise HTTPException500 from exc
    except Exception as ex:
        # Converte ChatError (que possui status_code e detail) em HTTPException
        status_code = getattr(ex, "status_code", None)
        detail = getattr(ex, "detail", None)
        if isinstance(status_code, int) and detail:
            logger.exception(
                f"{inspect.currentframe().f_code.co_name}: Erro tratado com status {status_code}"
            )
            raise HTTPException(status_code=status_code, detail=detail) from ex
        logger.exception(f"{inspect.currentframe().f_code.co_name}: Erro inesperado")
        logger.info(f"Type: {type(ex)}, Exception: {ex}")
        raise HTTPException500 from ex

    # Processar marcadores para RAG e  web search
    has_web_marker = response.get("response", "").find("<web_") != -1
    if (
        state.get("doc_rag", False)
        or response.get("response", "").find("<doc_") != -1
        or has_web_marker
    ):
        logger.debug("Processando tooltips e fontes na resposta")
        processed_response = transform_response_sources_enhanced(response, state)
        state["response"] = processed_response
    else:
        state["response"] = response

    # Adicionar disclaimer no começo da resposta se foi preparado
    disclaimer_text = state.get("disclaimer_text")
    if disclaimer_text and not state["response"]["response"].startswith("⚠️"):
        state["response"]["response"] = disclaimer_text + state["response"]["response"]
        logger.debug("Disclaimer adicionado no começo da resposta")

    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
    return state
