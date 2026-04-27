#!/usr/bin/env python3
"""PoC: Executa o pipeline RLM v2 (TODO + LangGraph) com UserState real (pickle) e API LiteLLM Proxy.

Carrega o UserState salvo após concatenate_documents (pickle) e executa
o rlm_pipeline() apontando para o LiteLLM Proxy real.

Emite mapeamento detalhado de cada passo e iteração.

Uso:
    uv run scripts/run_poc_real.py
    uv run scripts/run_poc_real.py --verbose
    uv run scripts/run_poc_real.py --pickle data/user_state_after_concat.pkl
    uv run scripts/run_poc_real.py --val-all   # sem truncagens no output
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import pickle
import sys
import time
from pathlib import Path
from typing import Any

# Adicionar raiz do assistente ao path
_ASSISTENTE_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(_ASSISTENTE_ROOT))

from sei_ia.services.rlm.config import RLMConfig  # noqa: E402
from sei_ia.services.rlm.engine_repl import (  # noqa: E402
    rlm_pipeline,
    should_use_rlm,
)
from sei_ia.services.rlm.reporter import RLMReporter  # noqa: E402

# ==============================================================================
# FORMATAÇÃO / REPORTER
# ==============================================================================

# Cores ANSI
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_MAGENTA = "\033[35m"
_BLUE = "\033[34m"
_WHITE = "\033[97m"


def _sep(char: str = "-", width: int = 70) -> str:
    return char * width


def _header(text: str, char: str = "=", width: int = 70) -> str:
    pad = max(0, width - len(text) - 4)
    left = pad // 2
    right = pad - left
    return f"{char * left}  {text}  {char * right}"


def _trunc(text: str, limit: int, val_all: bool) -> str:
    """Trunca texto a `limit` chars, a menos que val_all=True."""
    if val_all or len(text) <= limit:
        return text
    return text[:limit] + f"... [{len(text) - limit} chars omitidos]"


class StepReporter:
    """Reporter que imprime cada passo do RLM de forma estruturada."""

    def __init__(self, val_all: bool = False):
        self.events: list[tuple[str, dict[str, Any]]] = []
        self._step_counter = 0
        self._val_all = val_all

    def __call__(self, event: str, data: dict[str, Any]) -> None:
        """Chamado pelo engine a cada passo relevante."""
        self.events.append((event, data))
        handler = getattr(self, f"_on_{event}", None)
        if handler:
            handler(data)
        else:
            self._step_counter += 1
            print(f"  {_DIM}[{event}] {data}{_RESET}")

    # ------------------------------------------------------------------
    # FASE 1: Segmentação
    # ------------------------------------------------------------------

    def _on_segmentation_start(self, d: dict) -> None:
        print()
        print(f"{_BOLD}{_CYAN}{_header('FASE 1: SEGMENTACAO')}{_RESET}")
        print(f"  Tokens totais nos documentos: {_BOLD}{d['total_tokens']:,}{_RESET}")
        print()

    def _on_segmentation_complete(self, d: dict) -> None:
        print(f"  {_sep()}")
        print(f"  {_BOLD}Segmentacao concluida:{_RESET}")
        print(f"    Documentos:     {d['num_docs']}")
        print(f"    Total secoes:   {d.get('total_sections', '?')}")
        print(f"    Tempo fase 1:   {d['elapsed_s']:.1f}s")
        print()

    # ------------------------------------------------------------------
    # FASE 2: Cache
    # ------------------------------------------------------------------

    def _on_cache_hit(self, d: dict) -> None:
        print(f"  {_GREEN}{_BOLD}[CACHE HIT]{_RESET} Usando resultado cacheado.")
        print(f"    Tempo total: {d['elapsed_s']:.1f}s")
        print()

    # ------------------------------------------------------------------
    # FASE 3: Contexto REPL
    # ------------------------------------------------------------------

    def _on_repl_context_built(self, d: dict) -> None:
        print(f"{_BOLD}{_CYAN}{_header('FASE 2: CONTEXTO REPL')}{_RESET}")
        print(f"  Documentos:     {d['num_docs']}")
        print(f"  Total secoes:   {d['total_sections']}")
        print(f"  Context chars:  {d['context_chars']:,}")
        print()

    # ------------------------------------------------------------------
    # FASE 4: REPL Inicializado
    # ------------------------------------------------------------------

    def _on_repl_initialized(self, d: dict) -> None:
        print(f"{_BOLD}{_CYAN}{_header('FASE 3: REPL INICIALIZADO')}{_RESET}")
        print(f"  Max iteracoes:  {d['max_iterations']}")
        print()

    # ------------------------------------------------------------------
    # FASE 5: Loop Iterativo
    # ------------------------------------------------------------------

    def _on_iteration_start(self, d: dict) -> None:
        it = d["iteration"]
        print(f"{_BOLD}{_MAGENTA}{_header(f'ITERACAO {it}')}{_RESET}")
        print()

    def _on_root_lm_response(self, d: dict) -> None:
        reasoning = d.get("reasoning", "")
        print(f"  {_BOLD}[ROOT LM]{_RESET} ({d['elapsed_s']:.1f}s)")
        print(f"    Resposta:  {_DIM}{_trunc(reasoning, 150, self._val_all)}{_RESET}")
        print()

    def _on_repl_execution(self, d: dict) -> None:
        block = d["block"]
        has_final = d["has_final"]
        final_marker = f" {_GREEN}[FINAL_VAR]{_RESET}" if has_final else ""

        print(
            f"  {_BOLD}[REPL bloco {block}]{_RESET} "
            f"({d['exec_time']:.1f}s){final_marker}"
        )

        code = d.get("code", "")
        stdout = d.get("stdout", "")
        stderr = d.get("stderr", "")

        if code:
            print(f"    Codigo:\n{_DIM}{_trunc(code, 200, self._val_all)}{_RESET}")
        if stdout:
            print(f"    Output:\n{_DIM}{_trunc(stdout, 300, self._val_all)}{_RESET}")
        if stderr:
            print(f"    Stderr:\n{_RED}{_trunc(stderr, 200, self._val_all)}{_RESET}")
        if d.get("llm_calls_in_block"):
            print(f"    Sub-LM calls: {d['llm_calls_in_block']}")
        print()

    def _on_iteration_end(self, d: dict) -> None:
        it = d["iteration"]
        print(f"  {_sep('-', 50)}")
        print(f"  {_BOLD}Fim iteracao {it}:{_RESET}")
        print(f"    LLM calls total: {d['total_llm_calls']}")
        print(f"    Tempo iteracao:  {d['elapsed_s']:.1f}s")
        print()

    # ------------------------------------------------------------------
    # FASE FINAL
    # ------------------------------------------------------------------

    def _on_loop_stopped(self, d: dict) -> None:
        print(f"{_BOLD}{_CYAN}{_header('LOOP ENCERRADO')}{_RESET}")
        print(f"  Motivo:        {_YELLOW}{d['reason']}{_RESET}")
        print(f"  Iteracoes:     {d['iterations']}")
        print(f"  LLM calls:     {d['total_llm_calls']}")
        print(f"  Tempo loop:    {d['elapsed_s']:.1f}s")
        print()

    def _on_synthesis_complete(self, d: dict) -> None:
        print(f"{_BOLD}{_CYAN}{_header('SINTESE FINAL')}{_RESET}")
        print(f"  Prompt chars:    {d['prompt_chars']:,}")
        print(f"  Prompt tokens:   {d['prompt_tokens']:,}")
        print(f"  Docs citados:    {d['docs_referenced']}")
        print(f"  Tempo total:     {d['total_elapsed_s']:.1f}s")
        print()
        final_answer = d.get("final_answer", "")
        if final_answer:
            print(f"{_BOLD}{_GREEN}{_header('RESPOSTA FINAL AO USUARIO')}{_RESET}")
            print(final_answer)
            print()

    # ------------------------------------------------------------------
    # V2 — Eventos do pipeline TODO + LangGraph
    # ------------------------------------------------------------------

    def _on_planning_start(self, d: dict) -> None:
        print(f"\n{_BOLD}{_CYAN}{_header('FASE 1: PLANNING')}{_RESET}")

    def _on_planning_complete(self, d: dict) -> None:
        todos = d.get("todos", [])
        elapsed = d.get("elapsed_s", 0)
        print(f"  TODOs criados: {d.get('todo_count', 0)} ({elapsed:.1f}s)")
        for t in todos:
            deps = t.get("deps", [])
            dep_str = f" (deps={deps})" if deps else ""
            print(f"    {t['id']}. {t['task']}{dep_str}")
        print()

    def _on_execution_start(self, d: dict) -> None:
        print(f"{_BOLD}{_MAGENTA}{_header('FASE 2: EXECUTION')}{_RESET}")
        print(f"  TODOs a executar: {d.get('todo_count', 0)}")

    def _on_explorer_start(self, d: dict) -> None:
        print(
            f"\n  {_BOLD}[Explorer TODO {d.get('todo_id')}]{_RESET} {d.get('task', '')}"
        )

    def _on_explorer_complete(self, d: dict) -> None:
        print(f"    {_GREEN}OK{_RESET}: {d.get('desc', '?')}")

    def _on_explorer_error(self, d: dict) -> None:
        print(f"    {_RED}ERRO{_RESET}: {d.get('error', '?')}")

    def _on_planning_tool_calls(self, d: dict) -> None:
        self._print_tool_calls("Planning", d.get("calls", []))

    def _on_explorer_tool_calls(self, d: dict) -> None:
        tid = d.get("todo_id", "?")
        self._print_tool_calls(f"Explorer TODO {tid}", d.get("calls", []))

    def _on_synthesis_tool_calls(self, d: dict) -> None:
        self._print_tool_calls("Synthesis", d.get("calls", []))

    def _print_tool_calls(self, phase: str, calls: list) -> None:
        if not calls:
            return
        print(f"    {_DIM}[{phase}] {len(calls)} tool calls:{_RESET}")
        for i, c in enumerate(calls, 1):
            name = c.get("tool", "?")
            inp = str(c.get("input", ""))
            out = str(c.get("output", "") or "")
            print(f"      {_BLUE}[{i}] {name}{_RESET}")
            print(f"          INPUT:  {inp}")
            if out:
                print(f"          OUTPUT: {out}")

    def _on_execution_complete(self, d: dict) -> None:
        summary = d.get("results_summary", {})
        elapsed = d.get("elapsed_s", 0)
        print(
            f"\n  {_BOLD}Resultados: {d.get('results_count', 0)} TODOs completos ({elapsed:.1f}s){_RESET}"
        )
        for tid, desc in summary.items():
            print(f"    TODO {tid}: {desc}")
        print()

    def _on_synthesis_start(self, d: dict) -> None:
        print(f"{_BOLD}{_CYAN}{_header('FASE 3: SYNTHESIS')}{_RESET}")

    def _on_v2_synthesis_done(self, d: dict) -> None:
        print(f"\n{_BOLD}{_CYAN}{_header('TIMING POR FASE')}{_RESET}")
        print(f"  Planning:   {d.get('planning_s', 0):.1f}s")
        print(f"  Execution:  {d.get('execution_s', 0):.1f}s")
        print(f"  Synthesis:  {d.get('synthesis_s', 0):.1f}s")
        print(f"  Total v2:   {d.get('total_s', 0):.1f}s")
        print(f"  Resposta:   {d.get('answer_chars', 0):,} chars")
        print()

    # ------------------------------------------------------------------
    # RESUMO FINAL
    # ------------------------------------------------------------------

    def print_summary(self) -> None:
        """Imprime tabela-resumo de todos os eventos capturados."""
        print(f"{_BOLD}{_GREEN}{_header('RESUMO DE EVENTOS')}{_RESET}")

        counts: dict[str, int] = {}
        for event, _ in self.events:
            counts[event] = counts.get(event, 0) + 1

        for event, count in counts.items():
            print(f"  {event:30s} x{count}")

        # Métricas adicionais do v2
        total_tool_calls = 0
        explorer_tool_counts: dict[str, int] = {}
        save_result_count = 0
        response_format_count = 0
        raw_fallback_count = 0

        for event, data in self.events:
            if event.endswith("_tool_calls"):
                calls = data.get("calls", [])
                total_tool_calls += len(calls)
                if event == "explorer_tool_calls":
                    tid = str(data.get("todo_id", "?"))
                    explorer_tool_counts[tid] = len(calls)
                    for c in calls:
                        if c.get("tool") == "save_result":
                            save_result_count += 1
            if event == "explorer_complete":
                desc = data.get("desc", "")
                if "parsed via response_format" in desc:
                    response_format_count += 1
                elif "Resultado bruto" in desc:
                    raw_fallback_count += 1

        # Contar ask_sub_llm por effort
        ask_low = 0
        ask_high = 0
        ask_no_effort = 0
        for event, data in self.events:
            if event == "explorer_tool_calls":
                for c in data.get("calls", []):
                    if c.get("tool") in ("ask_sub_llm", "ask_sub_llm_batch"):
                        inp = c.get("input", {})
                        effort = inp.get("effort", "") if isinstance(inp, dict) else ""
                        if effort == "low":
                            ask_low += 1
                        elif effort == "high":
                            ask_high += 1
                        else:
                            ask_no_effort += 1

        # Extrair timing do v2_synthesis_done
        timing = {}
        todo_count = 0
        answer_chars = 0
        for event, data in self.events:
            if event == "v2_synthesis_done":
                timing = data
                answer_chars = data.get("answer_chars", 0)
            if event == "planning_complete":
                todo_count = data.get("todo_count", 0)

        if total_tool_calls > 0:
            print()
            # Tabela de métricas
            print(f"{_BOLD}{_GREEN}{_header('DASHBOARD')}{_RESET}")
            rows = [
                ("Planning", f"{timing.get('planning_s', 0):.1f}s"),
                ("Execution", f"{timing.get('execution_s', 0):.1f}s"),
                ("Synthesis", f"{timing.get('synthesis_s', 0):.1f}s"),
                ("Total", f"{_BOLD}{timing.get('total_s', 0):.1f}s{_RESET}"),
                ("", ""),
                ("TODOs", f"{todo_count} ({save_result_count} save_result)"),
                ("Tool calls", str(total_tool_calls)),
                ("ask_sub_llm low (Nano)", str(ask_low)),
                ("ask_sub_llm high (Mini)", str(ask_high)),
                ("Resposta", f"{answer_chars:,} chars"),
                (
                    "Erros",
                    f"{raw_fallback_count} fallback, {response_format_count} parse",
                ),
            ]
            col_w = max(len(r[0]) for r in rows) + 2
            val_w = max(len(r[1]) for r in rows if r[1]) + 2
            border = f"  ┌{'─' * col_w}┬{'─' * val_w}┐"
            mid = f"  ├{'─' * col_w}┼{'─' * val_w}┤"
            bottom = f"  └{'─' * col_w}┴{'─' * val_w}┘"
            print(border)
            for i, (label, value) in enumerate(rows):
                if not label and not value:
                    print(mid)
                else:
                    print(f"  │{label:<{col_w}}│{value:<{val_w}}│")
                    if i < len(rows) - 1 and rows[i + 1] != ("", ""):
                        pass  # no separator between regular rows
            print(bottom)

            # Detalhamento por explorer
            if explorer_tool_counts:
                print()
                print(f"  {_DIM}Tool calls por explorer:{_RESET}")
                for tid, cnt in sorted(explorer_tool_counts.items()):
                    print(f"    TODO {tid}: {cnt} calls")
        print()


# ==============================================================================
# CLI
# ==============================================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PoC RLM: Execucao com UserState real e LiteLLM Proxy."
    )
    parser.add_argument(
        "--pickle",
        type=str,
        default=str(
            _ASSISTENTE_ROOT / "data" / "rlm_test" / "user_state_after_concat.pkl"
        ),
        help="Caminho para o pickle do UserState.",
    )
    parser.add_argument(
        "--val-all",
        action="store_true",
        help="Exibir output completo sem truncagens (codigo, stdout, stderr, resposta).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Ativar logs detalhados (DEBUG).",
    )
    return parser.parse_args()


def load_pickle(path: str) -> dict:
    """Carrega UserState do pickle."""
    pkl_path = Path(path)
    if not pkl_path.exists():
        print(f"ERRO: Pickle nao encontrado: {path}")
        sys.exit(1)

    with open(pkl_path, "rb") as f:
        state = pickle.load(f)

    print(
        f"Pickle carregado: {pkl_path.name} ({pkl_path.stat().st_size / 1024:.1f} KB)"
    )
    return state


def print_state_summary(state: dict) -> None:
    """Imprime resumo do UserState carregado."""
    print(f"\n{_BOLD}{_header('USERSTATE CARREGADO')}{_RESET}")
    print(f"  all_tokens_counter:   {state.get('all_tokens_counter', '?'):,}")
    print(f"  general_max_ctx_len:  {state.get('general_max_ctx_len', '?'):,}")
    print(f"  limit_rag:            {state.get('limit_rag', '?'):,}")
    print(f"  intent:               {state.get('intent', '?')}")
    print(f"  model_type:           {state.get('model_type', '?')}")

    req = state.get("user_request", "")
    print(f"  user_request:         {req[:100]}...")

    procs = state.get("id_procedimentos", [])
    total_docs = 0
    for proc in procs:
        docs = proc.id_documentos if hasattr(proc, "id_documentos") else []
        total_docs += len(docs)
        proc_id = getattr(proc, "id_procedimento", "?")
        print(f"    Proc {proc_id}: {len(docs)} documentos")
    print(f"  Total: {len(procs)} procedimentos, {total_docs} documentos")
    print(f"  should_use_rlm:       {should_use_rlm(state)}")
    print()


async def main():
    args = parse_args()

    # Configurar logging
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    # Carregar pickle
    user_state = load_pickle(args.pickle)

    # Ajustar thresholds para forcar RLM path
    user_state["limit_rag"] = 20_000
    user_state["general_max_ctx_len"] = 237_500

    print_state_summary(user_state)

    # Configuracao RLM
    config = RLMConfig()

    print(f"{_BOLD}{_header('CONFIGURACAO RLM')}{_RESET}")
    print(f"  root_model_type:             {config.root_model_type}")
    print(f"  sub_model_type:              {config.sub_model_type}")
    print(f"  nano_model_type:             {config.nano_model_type}")
    print(f"  max_parallel_todos:          {config.max_parallel_todos}")
    print(f"  llm_concurrency:             {config.llm_concurrency}")
    print(f"  todo_timeout:                {config.todo_timeout}s")
    if args.val_all:
        print(f"  {_YELLOW}val-all: ON (sem truncagens){_RESET}")
    print()

    # Criar reporters
    step_reporter = StepReporter(val_all=args.val_all)
    rlm_reporter = RLMReporter()

    def _on_step(event: str, data: dict) -> None:
        step_reporter(event, data)
        rlm_reporter(event, data)

    # Executar
    pipeline_name = "RLM v2 (TODO + LangGraph)"
    print(f"{_BOLD}{_GREEN}{_header(f'INICIANDO {pipeline_name}')}{_RESET}")
    start = time.perf_counter()

    try:
        user_state = await rlm_pipeline(user_state, config=config, on_step=_on_step)
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"\n{_RED}ERRO apos {elapsed:.1f}s: {type(e).__name__}: {e}{_RESET}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    elapsed = time.perf_counter() - start

    # Resumo de eventos (step-by-step)
    step_reporter.print_summary()

    # Relatório de execução agregado
    rlm_reporter.print_report(user_state)

    # Last_prompt
    prompt = user_state.get("last_prompt", "")
    if prompt:
        if args.val_all:
            print(f"{_BOLD}{_header('LAST_PROMPT COMPLETO')}{_RESET}")
            print(prompt)
        else:
            print(
                f"{_BOLD}{_header('PREVIEW DO LAST_PROMPT (primeiros 3000 chars)')}{_RESET}"
            )
            print(prompt[:3000])
            if len(prompt) > 3000:
                print(f"\n{_DIM}... ({len(prompt) - 3000:,} chars restantes){_RESET}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
