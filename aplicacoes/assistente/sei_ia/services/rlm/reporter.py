"""RLM v2 — Relatório de execução para modo debug.

Classe `RLMReporter` que coleta eventos on_step do pipeline RLM e imprime
um relatório estruturado ao final da execução.

Uso típico:
    reporter = RLMReporter()
    user_state = await rlm_pipeline(user_state, config=config, on_step=reporter)
    reporter.print_report(user_state)
"""

from __future__ import annotations

import re
import time
from collections import Counter
from typing import Any

# Cores ANSI
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BLUE = "\033[34m"

_SEP = "─" * 58
_W = 60  # largura da caixa do cabeçalho


def _trunc(text: str, n: int = 55) -> str:
    s = str(text).replace("\n", " ").strip()
    return s[:n] + "…" if len(s) > n else s


class RLMReporter:
    """Coleta eventos on_step e imprime relatório ao final do pipeline.

    É chamável diretamente como função (compatível com o parâmetro on_step):
        reporter = RLMReporter()
        await rlm_pipeline(..., on_step=reporter)
        reporter.print_report(user_state)

    Para encadear com outro on_step existente:
        def _chain(event, data):
            existing_handler(event, data)
            reporter(event, data)
        await rlm_pipeline(..., on_step=_chain)
    """

    def __init__(self) -> None:
        self._events: list[tuple[str, dict, float]] = []
        # timestamp por todo_id para calcular elapsed dos explorers
        self._explorer_t0: dict[int, float] = {}

    def __call__(self, event: str, data: dict[str, Any]) -> None:
        """Chamado pelo engine a cada passo; compatível com on_step."""
        t = time.perf_counter()
        self._events.append((event, data, t))
        if event == "explorer_start":
            tid = data.get("todo_id")
            if tid is not None:
                self._explorer_t0[tid] = t

    # ─────────────────────────────────────────────────────────────────
    # Helpers de acesso aos eventos
    # ─────────────────────────────────────────────────────────────────

    def _first(self, name: str) -> dict:
        for e, d, _ in self._events:
            if e == name:
                return d
        return {}

    def _all(self, name: str) -> list[tuple[dict, float]]:
        return [(d, t) for e, d, t in self._events if e == name]

    # ─────────────────────────────────────────────────────────────────
    # Relatório principal
    # ─────────────────────────────────────────────────────────────────

    def print_report(
        self,
        user_state: dict[str, Any],
        threshold: int | None = None,
        path: str | None = None,
    ) -> None:
        """Agrega eventos e imprime o relatório completo no stdout.

        Args:
            user_state: estado final do pipeline.
            threshold: valor de direct_llm_token_threshold usado na decisão.
            path: "rlm" ou "direto" — caminho tomado.
        """
        lines: list[str] = []

        title = "RLM v2 — RELATÓRIO DE EXECUÇÃO"
        pad = _W - len(title) - 2
        left, right = pad // 2, pad - pad // 2
        lines += [
            "",
            f"╔{'═' * _W}╗",
            f"║{' ' * left} {_BOLD}{title}{_RESET}{' ' * right} ║",
            f"╚{'═' * _W}╝",
            "",
        ]

        lines += self._sec_context(user_state, threshold=threshold, path=path)
        lines += self._sec_flow()
        lines += self._sec_timings()
        lines += self._sec_tool_stats()
        lines += self._sec_top15()
        lines += self._sec_answer()

        print("\n".join(lines))

    # ─────────────────────────────────────────────────────────────────
    # Seção 1 — Contexto
    # ─────────────────────────────────────────────────────────────────

    def _sec_context(
        self,
        user_state: dict,
        threshold: int | None = None,
        path: str | None = None,
    ) -> list[str]:
        ctx = self._first("repl_context_built")
        seg = self._first("segmentation_complete")
        total_tokens = user_state.get("all_tokens_counter", 0)
        num_docs = ctx.get("num_docs") or seg.get("num_docs", "?")
        ctx_chars = ctx.get("context_chars", "?")
        procs = user_state.get("id_procedimentos", [])

        ctx_chars_fmt = (
            f"{ctx_chars:,}" if isinstance(ctx_chars, int) else str(ctx_chars)
        )

        lines = [
            f"{_BOLD}📂 CONTEXTO{_RESET}",
            f"  Processos : {len(procs):<6}   Documentos : {num_docs}",
            f"  Tokens est: {total_tokens:>10,}   Ctx chars  : {ctx_chars_fmt}",
        ]

        if threshold is not None or path is not None:
            _path = path or (
                "rlm"
                if self._first("planning_start") != {}
                or self._first("segmentation_start") != {}
                else "direto"
            )
            if _path == "rlm":
                path_label = f"{_GREEN}{_BOLD}RLM{_RESET}"
                cmp = f"{total_tokens:,} >= {threshold:,}" if threshold else ""
            else:
                path_label = f"{_CYAN}{_BOLD}Direto{_RESET}"
                cmp = f"{total_tokens:,} < {threshold:,}" if threshold else ""
            threshold_str = f"  (threshold: {threshold:,})" if threshold else ""
            lines.append(f"  Path      : {path_label}  {cmp}{threshold_str}")

        lines.append("")
        return lines

    # ─────────────────────────────────────────────────────────────────
    # Seção 2 — Fluxo de Execução
    # ─────────────────────────────────────────────────────────────────

    def _sec_flow(self) -> list[str]:
        lines = [f"{_BOLD}🗺  FLUXO DE EXECUÇÃO{_RESET}"]

        # Planning
        plan = self._first("planning_complete")
        p_elapsed = plan.get("elapsed_s", 0)
        p_calls = self._first("planning_tool_calls").get("calls", [])
        p_summary = self._call_summary(p_calls)
        lines.append(
            f"  {_CYAN}Root LM — Planning{_RESET} ─── {p_elapsed:.1f}s"
            + (f"  [{p_summary}]" if p_summary else "")
        )

        # Explorers
        todos = plan.get("todos", [])
        if todos:
            lines.append(f"  {_SEP}")
            lines.append("  Execução paralela")

            todo_calls: dict[int, list] = {}
            for d, _ in self._all("explorer_tool_calls"):
                tid = d.get("todo_id")
                if tid is not None:
                    todo_calls[tid] = d.get("calls", [])

            explorer_elapsed: dict[int, float] = {}
            for d, t in self._all("explorer_complete"):
                tid = d.get("todo_id")
                t0 = self._explorer_t0.get(tid)
                if t0 is not None:
                    explorer_elapsed[tid] = t - t0

            errors: set = {d.get("todo_id") for d, _ in self._all("explorer_error")}

            for todo in todos:
                tid = todo["id"]
                task = _trunc(todo.get("task", ""), 48)
                elapsed = explorer_elapsed.get(tid)
                calls = todo_calls.get(tid, [])
                summary = self._call_summary(calls)
                e_str = f"{elapsed:.1f}s" if elapsed is not None else "  ?"
                status = f" {_RED}[TIMEOUT]{_RESET}" if tid in errors else ""
                deps = todo.get("deps", [])
                dep_str = f"  deps={deps}" if deps else ""

                lines.append(
                    f'    TODO #{tid:>2}  {e_str:>7}{status}  "{task}"{dep_str}'
                )
                if summary:
                    lines.append(f"             {_DIM}{summary}{_RESET}")

            lines.append(f"  {_SEP}")

        # Synthesis
        s_calls = self._first("synthesis_tool_calls").get("calls", [])
        v2 = self._first("v2_synthesis_done")
        s_elapsed = v2.get("synthesis_s", 0)
        s_summary = self._call_summary(s_calls)
        lines.append(
            f"  {_CYAN}Root LM — Synthesis{_RESET} ─── {s_elapsed:.1f}s"
            + (f"  [{s_summary}]" if s_summary else "")
        )
        lines.append("")
        return lines

    def _call_summary(self, calls: list[dict]) -> str:
        """'get_doc x2  search_docs x3  ask_sub_llm(high) x1'"""
        counter: Counter = Counter()
        for c in calls:
            tool = c.get("tool", "?")
            inp = c.get("input") or {}
            if tool in ("ask_sub_llm", "ask_sub_llm_batch") and isinstance(inp, dict):
                effort = inp.get("effort", "?")
                tool = f"{tool}({effort})"
            counter[tool] += 1
        return "  ".join(f"{t} x{n}" for t, n in counter.most_common())

    # ─────────────────────────────────────────────────────────────────
    # Seção 3 — Tempo por Fase
    # ─────────────────────────────────────────────────────────────────

    def _sec_timings(self) -> list[str]:
        v2 = self._first("v2_synthesis_done")
        sc = self._first("synthesis_complete")
        planning_s = v2.get("planning_s", 0)
        execution_s = v2.get("execution_s", 0)
        synthesis_s = v2.get("synthesis_s", 0)
        total_s = v2.get("total_s") or sc.get("total_elapsed_s", 0)
        if total_s <= 0:
            return []

        def pct(v: float) -> str:
            return f"{v / total_s * 100:5.1f}%"

        return [
            f"{_BOLD}⏱  TEMPO POR FASE{_RESET}",
            f"  Planning  : {planning_s:>8.1f}s  ({pct(planning_s)})",
            f"  Execution : {execution_s:>8.1f}s  ({pct(execution_s)})",
            f"  Synthesis : {synthesis_s:>8.1f}s  ({pct(synthesis_s)})",
            f"  {'─' * 36}",
            f"  Total     : {total_s:>8.1f}s",
            "",
        ]

    # ─────────────────────────────────────────────────────────────────
    # Seção 4 — Chamadas por Tool
    # ─────────────────────────────────────────────────────────────────

    def _sec_tool_stats(self) -> list[str]:
        counter: Counter = Counter()

        def _count_calls(calls: list[dict]) -> None:
            for c in calls:
                tool = c.get("tool", "?")
                inp = c.get("input") or {}
                if tool in ("ask_sub_llm", "ask_sub_llm_batch") and isinstance(
                    inp, dict
                ):
                    tool = f"{tool}({inp.get('effort', '?')})"
                counter[tool] += 1

        _count_calls(self._first("planning_tool_calls").get("calls", []))
        _count_calls(self._first("synthesis_tool_calls").get("calls", []))
        for d, _ in self._all("explorer_tool_calls"):
            _count_calls(d.get("calls", []))

        total = sum(counter.values())
        if not counter:
            return []

        items = counter.most_common()
        max_len = max(len(t) for t, _ in items)
        lines = [f"{_BOLD}🔧 CHAMADAS POR TOOL{_RESET}"]
        for i in range(0, len(items), 2):
            t1, n1 = items[i]
            left = f"  {t1:<{max_len}} : {n1:>4}"
            if i + 1 < len(items):
                t2, n2 = items[i + 1]
                right = f"    {t2:<{max_len}} : {n2:>4}"
                lines.append(left + right)
            else:
                lines.append(left)
        lines += [f"  {'─' * 40}", f"  TOTAL: {total} calls", ""]
        return lines

    # ─────────────────────────────────────────────────────────────────
    # Seção 5 — Top 15 Explorers mais lentos
    # ─────────────────────────────────────────────────────────────────

    def _sec_top15(self) -> list[str]:
        plan = self._first("planning_complete")
        todos_by_id = {t["id"]: t for t in plan.get("todos", [])}

        todo_n_calls: dict[int, int] = {}
        for d, _ in self._all("explorer_tool_calls"):
            tid = d.get("todo_id")
            if tid is not None:
                todo_n_calls[tid] = len(d.get("calls", []))

        timed: list[tuple[int, float]] = []
        seen: set[int] = set()
        for d, t in self._all("explorer_complete"):
            tid = d.get("todo_id")
            t0 = self._explorer_t0.get(tid)
            if tid is not None and t0 is not None and tid not in seen:
                timed.append((tid, t - t0))
                seen.add(tid)
        # Inclui explorers com erro
        for d, t in self._all("explorer_error"):
            tid = d.get("todo_id")
            t0 = self._explorer_t0.get(tid)
            if tid is not None and t0 is not None and tid not in seen:
                timed.append((tid, t - t0))
                seen.add(tid)

        if not timed:
            return []

        top = sorted(timed, key=lambda x: x[1], reverse=True)[:15]
        lines = [
            f"{_BOLD}🔝 TOP {min(15, len(timed))} EXPLORERS MAIS LENTOS{_RESET}",
            f"  {'#':>2}  {'TODO':>4}  {'Elapsed':>8}  {'Calls':>5}  Task",
            f"  {'─' * 58}",
        ]
        for rank, (tid, elapsed) in enumerate(top, 1):
            task = _trunc(todos_by_id.get(tid, {}).get("task", "?"), 40)
            n = todo_n_calls.get(tid, 0)
            lines.append(
                f'  {rank:>2}    #{tid:<3}  {elapsed:>7.1f}s  {n:>5}  "{task}"'
            )
        lines.append("")
        return lines

    # ─────────────────────────────────────────────────────────────────
    # Seção 6 — Resposta Final
    # ─────────────────────────────────────────────────────────────────

    def _sec_answer(self) -> list[str]:
        sc = self._first("synthesis_complete")
        final_answer = sc.get("final_answer", "")
        prompt_chars = sc.get("prompt_chars", 0)
        prompt_tokens = sc.get("prompt_tokens", 0)
        if not final_answer:
            return []

        chars = len(final_answer)
        tokens_est = chars // 4

        # Citações HTML geradas por transform_response_sources_enhanced
        cite_pat = re.compile(
            r'class="AssistenteSEIIAfonteResposta"[^>]*title="([^"]*)"[^>]*>'
            r"(\[[^\]]+\])</a>"
        )
        citations = cite_pat.findall(final_answer)

        lines = [f"{_BOLD}📝 RESPOSTA FINAL{_RESET}"]
        lines.append(f"  Chars resp : {chars:>8,}   Tokens est : {tokens_est:>6,}")
        if prompt_chars:
            tk_str = f"  ({prompt_tokens:,} tokens)" if prompt_tokens else ""
            lines.append(f"  Prompt ctx : {prompt_chars:>8,} chars{tk_str}")

        if citations:
            lines.append(
                f"  Citations  : {_GREEN}{_BOLD}SIM{_RESET}"
                f" — {len(citations)} tags AssistenteSEIIAfonteResposta"
            )
            for title, ref in citations[:10]:
                lines.append(f'    {ref}  →  title="{_trunc(title, 50)}"')
            if len(citations) > 10:
                lines.append(f"    … e mais {len(citations) - 10} citações")
        else:
            # final_answer ainda tem tags brutas <doc_ID> (conversão para HTML
            # ocorre depois do pipeline, em transform_response_sources_enhanced)
            raw_tags = re.findall(r"<doc_(\w+)>", final_answer)
            unique_docs = sorted(set(raw_tags))
            if unique_docs:
                lines.append(
                    f"  Citations  : {_GREEN}{_BOLD}SIM{_RESET}"
                    f" — {len(raw_tags)} referências"
                    f" ({len(unique_docs)} docs únicos)"
                )
                for did in unique_docs[:10]:
                    n = raw_tags.count(did)
                    lines.append(f"    <doc_{did}>  ×{n}")
                if len(unique_docs) > 10:
                    lines.append(f"    … e mais {len(unique_docs) - 10} docs")
            else:
                lines.append(f"  Citations  : {_DIM}Nenhuma{_RESET}")

        lines += [
            "",
            f"{_BOLD}💬 TEXTO DA RESPOSTA{_RESET}",
            f"  {_SEP}",
        ]
        for paragraph in final_answer.split("\n"):
            lines.append(f"  {paragraph}")
        lines += [f"  {_SEP}", ""]
        return lines
