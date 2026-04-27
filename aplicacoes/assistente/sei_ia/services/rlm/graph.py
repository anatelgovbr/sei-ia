"""LangGraph StateGraph para o RLM v2.

Orquestra 3 fases: Plan → Execute → Synthesize.
Cada fase usa create_react_agent com tools especificas.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from sei_ia.services.rlm.config import RLMConfig
from sei_ia.services.rlm.prompts_repl import (
    EXPLORER_SYSTEM_PROMPT,
    EXPLORER_WEBSEARCH_ADDENDUM,
    PLANNING_SYSTEM_PROMPT,
    PLANNING_WEBSEARCH_ADDENDUM,
    SYNTHESIS_SYSTEM_PROMPT,
    SYNTHESIS_WEBSEARCH_ADDENDUM,
)
from sei_ia.services.rlm.tools import (
    ExplorerResult,
    RLMSharedState,
    make_explorer_tools,
    make_planning_tools,
    make_synthesis_tools,
)

logger = logging.getLogger(__name__)


# ============================================================================
# DAG Topological Sort
# ============================================================================


def _topological_levels(todo_list: list[dict]) -> list[list[dict]]:
    """Agrupa TODOs em niveis topologicos.

    Nivel 0: sem dependencias (rodam em paralelo).
    Nivel 1: dependem apenas de items do nivel 0.
    etc.
    """
    id_to_todo = {t["id"]: t for t in todo_list}
    remaining = set(id_to_todo.keys())
    completed: set[int] = set()
    levels: list[list[dict]] = []

    while remaining:
        # Items cujas deps ja estao completas
        ready = [
            tid
            for tid in remaining
            if all(d in completed for d in id_to_todo[tid].get("deps", []))
        ]
        if not ready:
            # Ciclo — forcar todos restantes no mesmo nivel
            logger.warning("Ciclo detectado no TODO DAG, forcando execucao.")
            ready = list(remaining)
        levels.append([id_to_todo[tid] for tid in ready])
        completed.update(ready)
        remaining -= set(ready)

    return levels


def _extract_tool_calls(messages: list) -> list[dict]:
    """Extrai log de tool calls (input+output) da lista de messages do LangGraph."""
    calls: list[dict] = []
    id_to_call: dict[str, dict] = {}

    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                entry = {
                    "tool": tc["name"],
                    "input": tc.get("args", {}),
                    "output": None,
                }
                calls.append(entry)
                id_to_call[tc["id"]] = entry
        if isinstance(msg, ToolMessage):
            parent = id_to_call.get(msg.tool_call_id)
            if parent:
                content = (
                    msg.content if isinstance(msg.content, str) else str(msg.content)
                )
                parent["output"] = content

    return calls


# ============================================================================
# Runner do Pipeline RLM v2
# ============================================================================


async def run_rlm_v2(
    shared: RLMSharedState,
    root_llm: Any,
    sub_llm: Any,
    config: RLMConfig,
    query: str = "",
    nano_llm: Any | None = None,
    on_step: Callable[[str, dict], None] | None = None,
    use_websearch: bool = False,
) -> str:
    """Executa o pipeline RLM v2 completo: Plan → Execute → Synthesize.

    Args:
        shared: estado compartilhado (context, doc_contents, catalog, etc.)
        root_llm: modelo LLM para o Root LM (standard)
        sub_llm: modelo LLM para Sub-LMs exploradores (mini)
        config: configuracao RLM
        query: pergunta do usuario
        nano_llm: modelo Nano-LM para ask_sub_lm effort=low (nano). Se None, usa sub_llm.
        on_step: callback para eventos de progresso

    Returns:
        Resposta final como string.
    """
    _emit = on_step or (lambda _e, _d: None)
    llm_sem = asyncio.Semaphore(config.llm_concurrency)

    # ----------------------------------------------------------------
    # Bridges: sync wrappers para Sub-LM (mini) e Nano-LM
    # ----------------------------------------------------------------
    async def _async_llm(prompt: str) -> str:
        async with llm_sem:
            resp = await sub_llm.ainvoke(prompt)
            return resp.content if hasattr(resp, "content") else str(resp)

    async def _async_llm_batch(prompts: list[str]) -> list[str]:
        tasks = [_async_llm(p) for p in prompts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [
            r if isinstance(r, str) else f"Erro na chamada LLM: {r}" for r in results
        ]

    _nano = nano_llm or sub_llm  # fallback para mini se nano nao disponivel

    async def _async_nano(prompt: str) -> str:
        async with llm_sem:
            resp = await _nano.ainvoke(prompt)
            return resp.content if hasattr(resp, "content") else str(resp)

    async def _async_nano_batch(prompts: list[str]) -> list[str]:
        tasks = [_async_nano(p) for p in prompts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [
            r if isinstance(r, str) else f"Erro na chamada LLM: {r}" for r in results
        ]

    loop = asyncio.get_running_loop()

    def _sync_llm(prompt: str) -> str:
        future = asyncio.run_coroutine_threadsafe(_async_llm(prompt), loop)
        return future.result(timeout=120)

    def _sync_llm_batch(prompts: list[str]) -> list[str]:
        future = asyncio.run_coroutine_threadsafe(_async_llm_batch(prompts), loop)
        return future.result(timeout=300)

    def _sync_nano(prompt: str) -> str:
        future = asyncio.run_coroutine_threadsafe(_async_nano(prompt), loop)
        return future.result(timeout=120)

    def _sync_nano_batch(prompts: list[str]) -> list[str]:
        future = asyncio.run_coroutine_threadsafe(_async_nano_batch(prompts), loop)
        return future.result(timeout=300)

    # ================================================================
    # FASE 1: PLANNING
    # ================================================================
    t_plan = time.perf_counter()
    logger.info("=== FASE 1: PLANNING ===")
    _emit("planning_start", {})

    planning_tools = make_planning_tools(shared)
    planning_prompt = PLANNING_SYSTEM_PROMPT
    if use_websearch:
        planning_prompt = f"{PLANNING_SYSTEM_PROMPT}\n\n{PLANNING_WEBSEARCH_ADDENDUM}"
    planning_agent = create_react_agent(
        root_llm, planning_tools, prompt=planning_prompt
    )

    planning_input = {
        "messages": [
            HumanMessage(
                content=f"Catalogo de documentos:\n{shared.catalog}\n\n"
                f"Pergunta do usuario: {query}"
            )
        ]
    }
    planning_result = await planning_agent.ainvoke(
        planning_input, config={"recursion_limit": config.planning_recursion_limit}
    )
    planning_calls = _extract_tool_calls(planning_result.get("messages", []))
    _emit("planning_tool_calls", {"calls": planning_calls})

    if not shared.todo_list:
        logger.warning("Root LM nao criou TODO list. Usando fallback de 1 TODO.")
        shared.todo_list = [
            {
                "id": 1,
                "task": "Responder a pergunta do usuario",
                "deps": [],
                "status": "pending",
            }
        ]

    plan_elapsed = time.perf_counter() - t_plan
    _emit(
        "planning_complete",
        {
            "todo_count": len(shared.todo_list),
            "todos": shared.todo_list,
            "elapsed_s": plan_elapsed,
        },
    )
    logger.info("TODO criado: %d tarefas", len(shared.todo_list))

    # ================================================================
    # FASE 2: EXECUTION (DAG com paralelismo)
    # ================================================================
    t_exec = time.perf_counter()
    logger.info("=== FASE 2: EXECUTION ===")
    _emit("execution_start", {"todo_count": len(shared.todo_list)})

    levels = _topological_levels(shared.todo_list)
    todo_sem = asyncio.Semaphore(config.max_parallel_todos)

    for level_idx, level in enumerate(levels):
        logger.info(
            "Nivel %d: %d TODOs (%s)",
            level_idx,
            len(level),
            [t["id"] for t in level],
        )
        tasks = []
        for todo in level:
            tasks.append(
                _run_single_explorer(
                    todo=todo,
                    shared=shared,
                    sub_llm=sub_llm,
                    config=config,
                    sync_llm_fn=_sync_llm,
                    sync_llm_batch_fn=_sync_llm_batch,
                    sync_nano_llm_fn=_sync_nano,
                    sync_nano_llm_batch_fn=_sync_nano_batch,
                    todo_sem=todo_sem,
                    emit=_emit,
                    enable_websearch=use_websearch,
                )
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                tid = level[i]["id"]
                logger.error("TODO %d falhou: %s", tid, r)
                shared.results[str(tid)] = {
                    "data": f"Erro: {r}",
                    "desc": f"Falha na execucao: {r}",
                    "chars": 0,
                }
                level[i]["status"] = "error"

    exec_elapsed = time.perf_counter() - t_exec
    _emit(
        "execution_complete",
        {
            "results_count": len(shared.results),
            "results_summary": {tid: r["desc"] for tid, r in shared.results.items()},
            "elapsed_s": exec_elapsed,
        },
    )

    # ================================================================
    # FASE 3: SYNTHESIS
    # ================================================================
    t_synth = time.perf_counter()
    logger.info("=== FASE 3: SYNTHESIS ===")
    _emit("synthesis_start", {})

    synthesis_tools = make_synthesis_tools(shared, _sync_llm, _sync_nano)
    synthesis_prompt = SYNTHESIS_SYSTEM_PROMPT
    if use_websearch and shared.web_references:
        synthesis_prompt = (
            f"{SYNTHESIS_SYSTEM_PROMPT}\n\n{SYNTHESIS_WEBSEARCH_ADDENDUM}"
        )
    synthesis_agent = create_react_agent(
        root_llm, synthesis_tools, prompt=synthesis_prompt
    )

    # Construir manifesto para o Root LM
    manifesto_lines = []
    for tid, r in sorted(shared.results.items(), key=lambda x: int(x[0])):
        manifesto_lines.append(f"TODO {tid}: {r['desc']} ({r['chars']:,} chars)")
    manifesto = "\n".join(manifesto_lines)

    synthesis_input = {
        "messages": [
            HumanMessage(
                content=f"Pergunta do usuario: {query}\n\n"
                f"Resultados dos exploradores:\n{manifesto}\n\n"
                "Use show_results() e get_result(todo_id) para acessar os dados. "
                "Construa a resposta final e use submit_answer()."
            )
        ]
    }
    synthesis_result = await synthesis_agent.ainvoke(
        synthesis_input, config={"recursion_limit": config.synthesis_recursion_limit}
    )
    synthesis_calls = _extract_tool_calls(synthesis_result.get("messages", []))
    _emit("synthesis_tool_calls", {"calls": synthesis_calls})

    if shared.final_answer is None:
        # Fallback: extrair do ultimo message
        msgs = synthesis_result.get("messages", [])
        if msgs:
            last = msgs[-1]
            content = last.content if hasattr(last, "content") else str(last)
            shared.final_answer = content
            logger.warning("submit_answer nao chamado, usando ultimo message.")

    synth_elapsed = time.perf_counter() - t_synth
    total_elapsed = time.perf_counter() - t_plan
    _emit(
        "v2_synthesis_done",
        {
            "answer_chars": len(shared.final_answer or ""),
            "planning_s": plan_elapsed,
            "execution_s": exec_elapsed,
            "synthesis_s": synth_elapsed,
            "total_s": total_elapsed,
        },
    )

    return shared.final_answer or ""


# ============================================================================
# Runner de um unico Explorer (Sub-LM)
# ============================================================================


async def _run_single_explorer(
    todo: dict,
    shared: RLMSharedState,
    sub_llm: Any,
    config: RLMConfig,
    sync_llm_fn: Callable,
    sync_llm_batch_fn: Callable,
    sync_nano_llm_fn: Callable,
    sync_nano_llm_batch_fn: Callable,
    todo_sem: asyncio.Semaphore,
    emit: Callable,
    enable_websearch: bool = False,
) -> None:
    """Executa um Sub-LLM explorador para um unico TODO item."""
    todo_id = todo["id"]
    task_desc = todo["task"]

    async with todo_sem:
        emit("explorer_start", {"todo_id": todo_id, "task": task_desc})
        logger.info("Explorer TODO %d iniciado: %s", todo_id, task_desc)

        # Contexto de dependencias completadas (se houver)
        dep_context = ""
        for dep_id in todo.get("deps", []):
            dep_result = shared.results.get(str(dep_id))
            if dep_result:
                dep_context += f"\nResultado TODO {dep_id} ({dep_result['desc']}):\n{dep_result['data']}\n"
        if len(dep_context) > config.dep_context_max_chars:
            dep_context = (
                dep_context[: config.dep_context_max_chars] + "\n... [truncado]"
            )

        explorer_tools = make_explorer_tools(
            shared=shared,
            todo_id=todo_id,
            llm_fn=sync_llm_fn,
            llm_batch_fn=sync_llm_batch_fn,
            nano_llm_fn=sync_nano_llm_fn,
            nano_llm_batch_fn=sync_nano_llm_batch_fn,
            enable_websearch=enable_websearch,
        )

        explorer_prompt = EXPLORER_SYSTEM_PROMPT
        if enable_websearch:
            explorer_prompt = f"{EXPLORER_SYSTEM_PROMPT}\n{EXPLORER_WEBSEARCH_ADDENDUM}"

        explorer_agent = create_react_agent(
            sub_llm,
            explorer_tools,
            prompt=explorer_prompt,
            response_format=ExplorerResult,
        )

        num_docs = len(shared.doc_contents)
        user_msg = (
            f"Sua tarefa: {task_desc}\n\n"
            f"Documentos disponiveis ({num_docs} docs):\n{shared.catalog}\n\n"
            f"Use search_docs() e get_doc(SEI) para acessar os documentos."
        )
        if dep_context:
            user_msg += f"\n\nResultados de tarefas anteriores:{dep_context}"

        explorer_input = {"messages": [HumanMessage(content=user_msg)]}

        try:
            result = await asyncio.wait_for(
                explorer_agent.ainvoke(
                    explorer_input,
                    config={"recursion_limit": config.explorer_recursion_limit},
                ),
                timeout=config.todo_timeout,
            )
        except TimeoutError:
            logger.error("Explorer TODO %d timeout (%ds)", todo_id, config.todo_timeout)
            shared.results[str(todo_id)] = {
                "data": f"Timeout apos {config.todo_timeout}s",
                "desc": "Timeout na exploracao",
                "chars": 0,
            }
            todo["status"] = "error"
            emit("explorer_error", {"todo_id": todo_id, "error": "timeout"})
            return

        # Emitir log de tool calls
        explorer_calls = _extract_tool_calls(result.get("messages", []))
        emit("explorer_tool_calls", {"todo_id": todo_id, "calls": explorer_calls})

        # Se o explorer nao chamou save_result, tentar structured_response
        if str(todo_id) not in shared.results:
            structured = result.get("structured_response")
            if structured is not None:
                parsed = (
                    structured
                    if isinstance(structured, ExplorerResult)
                    else ExplorerResult.model_validate(structured)
                )
                shared.results[str(todo_id)] = {
                    "data": parsed.data,
                    "desc": parsed.description,
                    "chars": len(parsed.data),
                }
                logger.info(
                    "TODO %d: parsed via structured_response: %s",
                    todo_id,
                    parsed.description,
                )
            else:
                # Fallback: content bruto do ultimo message
                msgs = result.get("messages", [])
                content = ""
                if msgs:
                    last = msgs[-1]
                    content = last.content if hasattr(last, "content") else str(last)
                shared.results[str(todo_id)] = {
                    "data": content,
                    "desc": f"Resultado bruto TODO {todo_id}",
                    "chars": len(content),
                }
                logger.warning(
                    "TODO %d: save_result nao chamado, structured_response ausente, usando content bruto.",
                    todo_id,
                )
            todo["status"] = "done"
            logger.warning(
                "TODO %d: save_result nao chamado, capturando output.", todo_id
            )

        emit(
            "explorer_complete",
            {
                "todo_id": todo_id,
                "desc": shared.results.get(str(todo_id), {}).get("desc", "?"),
            },
        )
        logger.info("Explorer TODO %d concluido.", todo_id)


# ============================================================================
# Helpers
# ============================================================================
