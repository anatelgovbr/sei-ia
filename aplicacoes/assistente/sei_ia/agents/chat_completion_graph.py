"""Module for chat completion workflow graph implementation."""

import asyncio
import contextlib
import inspect
import logging
from datetime import datetime

import httpx
import litellm
import openai
from fastapi import HTTPException
from httpx._exceptions import ReadTimeout
from langgraph.config import get_stream_writer
from langgraph.errors import GraphRecursionError
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
from sei_ia.agents.websearch.deep_research_agent import DeepResearchAgent
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.etl.concatenate_documents import (
    concatenate_documents,
    initialize_document_processing_state,
)
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.benchmark_metrics import current_collector
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException403,
    HTTPException408,
    HTTPException413,
    HTTPException429,
    HTTPException500,
    HTTPException503,
)
from sei_ia.services.llm_models.chat_workflow import chat_gpt
from sei_ia.services.llm_models.get_model import AGENT_TAG_TO_TIER, get_llm_model

setup_logging()
logger = logging.getLogger(__name__)

# Tasks de busca web em background, indexadas por id_request.
# web_search_node cria a task e retorna imediatamente; merge_web_search aguarda.
_web_search_tasks: dict[str, asyncio.Task] = {}

# Sentinel: documentos presentes — task adiada até prepare_doc_websearch_node.
_DEFERRED_WEB_SEARCH = object()


async def build_chat_completion_graph() -> CompiledStateGraph:  # NOSONAR
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
    def start_parallel_flow(_state: UserState) -> dict:
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
        "merge_web_search": merge_web_search_node,
        "prepare_doc_websearch": prepare_doc_websearch_node,
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
    def check_context_no_docs(state: UserState) -> dict:
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

    # Fluxo normal: concatenate -> prepare_doc_websearch -> detect_intent -> handlers
    # prepare_doc_websearch é no-op quando use_websearch=False; garante que a busca web
    # inicie com brief derivado dos documentos antes de detect_intent.
    workflow.add_edge("concatenate_docs", "prepare_doc_websearch")
    workflow.add_edge("prepare_doc_websearch", "detect_intent")
    workflow.add_conditional_edges(
        "detect_intent",
        route_condition,
        {
            "summarize": "handle_summarization",
            "grammar": "handle_grammar_correction",
            "question": "handle_question",
        },
    )

    # ========== FLUXO SEQUENCIAL: handlers → merge_web_search → merge_disclaimer → generate_response ==========
    # classify_disclaimer executa em paralelo, mas NÃO bloqueia o fluxo principal.
    # merge_web_search aguarda a task de busca web iniciada em background (no-op se não há task).

    workflow.add_edge("handle_summarization", "merge_web_search")
    workflow.add_edge("handle_question", "merge_web_search")
    workflow.add_edge("handle_grammar_correction", "merge_web_search")
    workflow.add_edge("check_context_no_docs", "merge_web_search")

    workflow.add_edge("merge_web_search", "merge_disclaimer")

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


async def _perform_web_search(
    state: UserState, enriched_request: str | None = None
) -> list:
    """Executa a busca web (roda como asyncio.Task em background).

    Se enriched_request for fornecido (caso com documentos), usa-o diretamente.
    Caso contrário, monta o request a partir do user_request original.
    """
    _stream_writer = None
    try:
        _stream_writer = get_stream_writer()
        _stream_writer({"_status": "Pesquisando na Internet"})
    except Exception:
        logger.debug("Stream writer indisponível, ignorando")

    _ctx_len_map = {
        "standard": settings.CTX_LEN_STANDARD_MODEL,
        "mini": settings.CTX_LEN_MINI_MODEL,
        "nano": settings.CTX_LEN_NANO_MODEL,
    }
    agent = DeepResearchAgent(
        searx_base_url=settings.SEARX_BASE_URL,
        fastcrw_base_url=settings.FASTCRW_BASE_URL,
        byparr_base_url=settings.BYPARR_BASE_URL,
        llm=get_llm_model(agent_tag=state["agent_tag"]),
        # explorador/classificador: default do compress_llm/extract_llm
        # compartilhado com o DeepResearchAgent. _classify_search_mode rebind
        # pra triagem_busca na hora certa (ver deep_research_agent.py).
        compress_llm=get_llm_model(agent_tag="explorador"),
        extract_llm=get_llm_model(agent_tag="classificador"),
        max_pages=12,
        max_rounds=6,
        llm_ctx_len=_ctx_len_map.get(
            AGENT_TAG_TO_TIER.get(state["agent_tag"], "standard"),
            settings.CTX_LEN_STANDARD_MODEL,
        ),
        compress_llm_ctx_len=settings.CTX_LEN_NANO_MODEL,
    )
    if enriched_request is None:
        today = datetime.now().strftime("%d/%m/%Y")
        enriched_request = (
            f"{state['user_request']}\n\n"
            "Instruções adicionais:\n"
            f" - Considerar fontes mais recentes sabendo que a data de hoje é {today}.\n"
            "- Necessariamente use a ferramenta de websearch para buscar na internet fontes para sua resposta.\n"
        )
    benchmark_tools = current_collector()
    benchmark_run_id = (
        benchmark_tools.start_external_tool("deep_research_search")
        if benchmark_tools is not None
        else None
    )
    try:
        result = await agent._arun(enriched_request)
    except Exception:
        if benchmark_tools is not None and benchmark_run_id is not None:
            benchmark_tools.fail_external_tool(benchmark_run_id)
        raise
    if benchmark_tools is not None and benchmark_run_id is not None:
        benchmark_tools.finish_external_tool(benchmark_run_id, result)

    if _stream_writer is not None:
        with contextlib.suppress(Exception):
            _stream_writer({"_status": "Pesquisa na Internet concluída"})

    if not result:
        result = [
            {
                "content": "Não foi necessário buscar na web.",
                "query": "",
                "references": [],
            }
        ]

    for i, item in enumerate(result, 1):
        item.setdefault("idx", i)
        item.setdefault("node", "web_search_node")

    logger.info(f"Busca web concluída. {len(result)} resultados armazenados")
    return result


def _sample_doc_chunks(
    content: str, chunk_size: int, max_chunks: int
) -> list[tuple[int, str]]:
    natural = [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]
    n = len(natural)
    if n <= max_chunks:
        indices = list(range(n))
    else:
        indices = sorted(
            {int(i * (n - 1) / (max_chunks - 1)) for i in range(max_chunks)}
        )
    return [(idx, natural[idx]) for idx in indices]


def _collect_all_chunks(
    state: UserState, chunk_size: int, max_chunks: int
) -> list[tuple[str, int, str]]:
    result: list[tuple[str, int, str]] = []
    for proc in state.get("id_procedimentos") or []:
        for doc in proc.id_documentos:
            content = getattr(doc, "content", None) or ""
            if not content.strip():
                continue
            doc_id = getattr(doc, "id_documento_formatado", "") or getattr(
                doc, "id_documento", ""
            )
            for idx, text in _sample_doc_chunks(content, chunk_size, max_chunks):
                result.append((doc_id, idx, text))
    return result


async def _extract_doc_search_brief(state: UserState) -> str:
    """Lê o(s) documento(s) em chunks paralelos e sintetiza o que buscar na web.

    Algoritmo em duas fases (inspirado no DeepResearchAgent):
      Fase 1 — Extração paralela: divide cada documento em chunks de CHUNK_SIZE chars,
               amostra até MAX_CHUNKS_PER_DOC chunks distribuídos uniformemente pelo
               documento e chama o nano em paralelo (semáforo MAX_CONCURRENT) para
               identificar o que cada trecho indica que deve ser pesquisado externamente.
               Chunks sem informação relevante respondem "IRRELEVANTE" e são descartados.
      Fase 2 — Síntese: o mini consolida todas as extrações relevantes em um brief
               coerente que guia o agente de busca web.

    Retorna o user_request original se nenhum documento tiver conteúdo ou se ambas
    as fases falharem.
    """
    CHUNK_SIZE = 10_000
    MAX_CHUNKS_PER_DOC = 20
    MAX_CONCURRENT = 8

    all_chunks = _collect_all_chunks(state, CHUNK_SIZE, MAX_CHUNKS_PER_DOC)
    if not all_chunks:
        return state["user_request"]

    nano_llm = get_llm_model(agent_tag="explorador")
    mini_llm = get_llm_model(agent_tag="busca_web")
    user_request = state["user_request"]

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def _extract_chunk(doc_id: str, chunk_idx: int, text: str) -> str:
        prompt = (
            f"Documento {doc_id} — trecho {chunk_idx + 1}\n\n"
            f"PERGUNTA DO USUÁRIO:\n{user_request}\n\n"
            f"TRECHO DO DOCUMENTO:\n{text}\n\n"
            "Liste em até 5 tópicos CURTOS quais informações externas (da internet) "
            "são necessárias para responder à pergunta com base EXCLUSIVAMENTE neste trecho. "
            "Inclua: normas citadas, entidades mencionadas, dados que precisam de "
            "atualização ou comparação externa.\n"
            "Se este trecho NÃO contiver informações relevantes para a pergunta, "
            "responda apenas a palavra: IRRELEVANTE"
        )
        async with semaphore:
            try:
                resp = await nano_llm.ainvoke(prompt)
                result = (
                    resp.content if hasattr(resp, "content") else str(resp)
                ).strip()
                return "" if result.upper().startswith("IRRELEVANTE") else result
            except Exception:
                return ""

    extractions: list[str] = await asyncio.gather(
        *[_extract_chunk(doc_id, idx, text) for doc_id, idx, text in all_chunks],
        return_exceptions=False,
    )

    relevant = [e for e in extractions if e.strip()]
    logger.debug(
        f"[doc_brief] {len(relevant)}/{len(all_chunks)} chunks relevantes extraídos"
    )

    if not relevant:
        return user_request

    # ── Fase 2: síntese pelo mini ─────────────────────────────────────────────
    today = datetime.now().strftime("%d/%m/%Y")
    aggregated = "\n\n---\n\n".join(relevant)
    synth_prompt = (
        f"PERGUNTA DO USUÁRIO:\n{user_request}\n\n"
        "Abaixo estão extrações de vários trechos de documentos institucionais "
        "indicando o que precisa ser pesquisado na internet para complementar a resposta:\n\n"
        f"{aggregated}\n\n"
        "Consolide as extrações acima em um guia de pesquisa web de 3 a 5 parágrafos, "
        "sem repetições, priorizando os pontos mais relevantes para a pergunta do usuário. "
        "Inclua normas, entidades, conceitos técnicos e dados externos identificados."
    )
    try:
        resp = await mini_llm.ainvoke(synth_prompt)
        brief = (resp.content if hasattr(resp, "content") else str(resp)).strip()
    except Exception:
        logger.warning("Falha na síntese do brief — usando extrações brutas")
        brief = aggregated[:4_000]

    if not brief:
        return user_request

    return (
        f"{user_request}\n\n"
        f"Contexto extraído dos documentos para guiar a busca:\n{brief}\n\n"
        "Instruções adicionais:\n"
        f" - Considerar fontes mais recentes sabendo que a data de hoje é {today}.\n"
        "- Necessariamente use a ferramenta de websearch para buscar na internet fontes para sua resposta.\n"
    )


async def prepare_doc_websearch_node(state: UserState) -> dict:
    """Inicia busca web com brief derivado do conteúdo dos documentos.

    Executado após concatenate_docs. Substitui o sentinel _DEFERRED_WEB_SEARCH
    pelo asyncio.Task real, enriquecido com contexto do documento via nano.
    No-op se use_websearch=False ou se a task já foi iniciada.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    if not state.get("use_websearch"):
        return {}
    task_key = str(state.get("id_request", ""))
    if _web_search_tasks.get(task_key) is not _DEFERRED_WEB_SEARCH:
        return {}

    enriched = await _extract_doc_search_brief(state)
    _web_search_tasks[task_key] = asyncio.create_task(  # type: ignore[assignment]
        _perform_web_search(state, enriched)
    )
    logger.debug(f">> busca web iniciada com brief de documento (key={task_key})")
    return {}


async def web_search_node(state: UserState) -> dict:  # NOSONAR
    """Inicia busca web como task em background e retorna imediatamente.

    Se documentos estiverem presentes na requisição, adia a task: o brief
    será gerado pelo nano após concatenate_docs em prepare_doc_websearch_node.
    Sem documentos, inicia imediatamente com o user_request original.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    task_key = str(state.get("id_request", id(state)))
    has_docs = bool(state.get("id_procedimentos") or state.get("arquivos_avulsos"))
    if has_docs:
        _web_search_tasks[task_key] = _DEFERRED_WEB_SEARCH  # type: ignore[assignment]
        logger.debug(f">> busca web adiada (documentos presentes, key={task_key})")
    else:
        # create_task agenda a coroutine no event loop atual e herda o contexto (ContextVar)
        _web_search_tasks[task_key] = asyncio.create_task(_perform_web_search(state))
        logger.debug(f">> busca web iniciada em background (key={task_key})")
    return {}


async def merge_web_search_node(state: UserState) -> dict:
    """Aguarda resultado da busca web em background (no-op se não há task pendente).

    Inserido entre handlers e merge_disclaimer para coletar o resultado da task
    iniciada em web_search_node. Neste ponto o pipeline de documentos já executou,
    então a busca web provavelmente já terminou ou está próxima de terminar.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    task_key = str(state.get("id_request", ""))
    task = _web_search_tasks.pop(task_key, None)

    if task is None or task is _DEFERRED_WEB_SEARCH:
        return {}

    try:
        tool_web_search = await task
    except Exception:
        logger.exception("Erro na busca web em background")
        tool_web_search = [
            {"content": "Erro na busca web.", "query": "", "references": []}
        ]

    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
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
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    state = await process_question_intent(state)
    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
    return state


async def handle_response(  # noqa: PLR0912, PLR0915, C901  # NOSONAR
    state: UserState, writer: StreamWriter | None = None
) -> UserState:
    """Wrapper para chat_gpt com tratamento de erros e aplicação de disclaimer."""
    try:
        logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

        # Obtém o stream writer do contexto (None se não estiver em modo streaming)
        with contextlib.suppress(Exception):
            writer = get_stream_writer()

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
            f"conexão interrompida durante streaming. Erro: {type(exc).__name__}"
        )
        raise HTTPException500 from exc
    except GraphRecursionError as exc:
        logger.warning(
            f"{inspect.currentframe().f_code.co_name}: agente ReAct atingiu limite de recursão"
        )
        raise HTTPException503 from exc
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
