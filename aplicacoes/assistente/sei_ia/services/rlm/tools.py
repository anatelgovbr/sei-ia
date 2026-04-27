"""LangGraph Tools para o RLM v2.

Cada operacao do pipeline RLM e uma @tool do LangGraph,
garantindo traceabilidade completa das decisoes dos agentes.

Tres conjuntos de tools:
- Planning: Root LM cria TODO
- Explorer: Sub-LLMs exploram documentos
- Synthesis: Root LM consolida resultados
"""

from __future__ import annotations

import bisect
import json
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel as PydanticBaseModel, Field as PydanticField

logger = logging.getLogger(__name__)


# ============================================================================
# Structured Output — Schema para response_format dos exploradores
# ============================================================================


class ExplorerResult(PydanticBaseModel):
    """Resultado estruturado de um explorador. Usado como response_format."""

    data: str = PydanticField(description="Informacao completa extraida dos documentos")
    description: str = PydanticField(
        description="Resumo breve (1 frase) do que foi encontrado"
    )


# ============================================================================
# Shared State — dados pesados vivem aqui, fora do LangGraph State
# ============================================================================


@dataclass
class RLMSharedState:
    """Estado compartilhado entre todas as fases do RLM.

    O context (38M+ chars) nunca entra no graph state do LangGraph.
    As tools acessam via closure sobre esta instancia.
    """

    context: str
    doc_contents: dict[str, str]
    boundary_positions: list[int]
    boundary_seis: list[str]
    catalog: str
    todo_list: list[dict] = field(default_factory=list)
    # Keys in shared.results are always str(todo_id)
    results: dict[str, dict] = field(default_factory=dict)
    final_answer: str | None = None

    # Web search — refs com numeracao global entre exploradores
    web_references: list[dict] = field(default_factory=list)
    _web_ref_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _web_ref_counter: list[int] = field(default_factory=lambda: [0], repr=False)


def build_shared_state(
    context: str,
    catalog: str,
) -> RLMSharedState:
    """Constroi RLMSharedState a partir do context string.

    Parsea boundaries de <doc SEI> e extrai doc_contents,
    reutilizando a mesma logica do repl.py.
    """
    boundary_positions: list[int] = []
    boundary_seis: list[str] = []

    for m in re.finditer(r"<doc (\d+)>", context):
        sei = m.group(1)
        content_start = m.end()
        if content_start < len(context) and context[content_start] == "\n":
            content_start += 1
        next_nl = context.find("\n", content_start)
        if next_nl != -1:
            content_start = next_nl + 1
        boundary_positions.append(content_start)
        boundary_seis.append(sei)

    doc_contents: dict[str, str] = {}
    for i, sei in enumerate(boundary_seis):
        start = boundary_positions[i]
        end_tag = context.find("</doc>", start)
        if end_tag == -1:
            end_tag = len(context)
        doc_contents[sei] = context[start:end_tag].strip()

    return RLMSharedState(
        context=context,
        doc_contents=doc_contents,
        boundary_positions=boundary_positions,
        boundary_seis=boundary_seis,
        catalog=catalog,
    )


# ============================================================================
# Tools de PLANNING (Root LM — Fase 1)
# ============================================================================


def make_planning_tools(shared: RLMSharedState) -> list[BaseTool]:
    """Tools disponiveis para o Root LM na fase de planejamento."""

    @tool
    def show_catalog() -> str:
        """Mostra catalogo de documentos disponiveis: tipos, quantidades, SEIs."""
        return shared.catalog

    @tool
    def create_todo(tasks: list[dict]) -> str:
        """Cria plano de trabalho com TODOs.

        Cada task deve ter: id (int), task (str), deps (list[int]).
        Tasks com deps=[] rodam em paralelo.
        Tasks com deps=[1,2] esperam 1 e 2 completarem.

        Exemplo:
            create_todo([
                {"id": 1, "task": "Identificar partes do processo", "deps": []},
                {"id": 2, "task": "Extrair decisoes", "deps": []},
                {"id": 3, "task": "Consolidar", "deps": [1, 2]},
            ])
        """
        for t in tasks:
            t["status"] = "pending"
            t.setdefault("deps", [])
        shared.todo_list = tasks
        lines = [f"  {t['id']}. {t['task']} (deps={t['deps']})" for t in tasks]
        return f"TODO criado com {len(tasks)} tarefas:\n" + "\n".join(lines)

    return [show_catalog, create_todo]


# ============================================================================
# Tools de EXPLORACAO (Sub-LLMs — Fase 2)
# ============================================================================


def make_explorer_tools(
    shared: RLMSharedState,
    todo_id: int,
    llm_fn: Callable[[str], str],
    llm_batch_fn: Callable[[list[str]], list[str]],
    nano_llm_fn: Callable[[str], str] | None = None,
    nano_llm_batch_fn: Callable[[list[str]], list[str]] | None = None,
    enable_websearch: bool = False,
) -> list[BaseTool]:
    """Tools disponiveis para cada Sub-LLM explorador."""

    @tool
    def get_doc(sei: str) -> str:
        """Retorna conteudo completo de um documento pelo numero SEI."""
        sei = str(sei).strip()
        content = shared.doc_contents.get(sei)
        if content is None:
            return f"Erro: documento SEI '{sei}' nao encontrado."
        return content

    @tool
    def search_docs(pattern: str, max_results: int = 20) -> str:
        """Busca regex em todos os documentos. Retorna SEI, posicao e snippet.

        Args:
            pattern: expressao regular a buscar.
            max_results: maximo de resultados (default 20).
        """
        results = []
        try:
            for m in re.finditer(pattern, shared.context, re.IGNORECASE):
                bi = bisect.bisect_right(shared.boundary_positions, m.start()) - 1
                sei = (
                    shared.boundary_seis[bi]
                    if 0 <= bi < len(shared.boundary_seis)
                    else "unknown"
                )
                snippet_start = max(0, m.start() - 100)
                snippet_end = min(len(shared.context), m.end() + 100)
                results.append(
                    f"SEI {sei} (pos {m.start()}): "
                    f"...{shared.context[snippet_start:snippet_end]}..."
                )
                if len(results) >= max_results:
                    break
        except re.error as e:
            return f"Erro regex: {e}"
        if not results:
            return "Nenhum resultado encontrado."
        return "\n---\n".join(results)

    @tool
    def ask_sub_llm(prompt: str, effort: str) -> str:
        """Envia pergunta a um Sub-LLM. OBRIGATORIO informar effort.

        Args:
            prompt: pergunta ou instrucao para o Sub-LLM.
            effort: OBRIGATORIO. "low" ou "high".

        effort="low" (Nano-LLM — rapido e barato):
            ask_sub_llm("Quais as partes envolvidas?\\n\\n" + doc, effort="low")
            ask_sub_llm("Este doc e parecer, oficio ou despacho?\\n\\n" + doc, effort="low")
            ask_sub_llm("Extraia datas e valores deste trecho:\\n\\n" + trecho, effort="low")
            ask_sub_llm("Resuma os fatos principais:\\n\\n" + doc, effort="low")

        effort="high" (Mini-LLM — mais capaz, mais lento):
            ask_sub_llm("Avalie a fundamentacao juridica deste ato:\\n\\n" + doc, effort="high")
            ask_sub_llm("Compare as teses sobre prescricao:\\n\\n" + docs, effort="high")
            ask_sub_llm("Sintetize estes 10 resumos em texto unico:\\n\\n" + resumos, effort="high")
        """
        if effort == "high" or nano_llm_fn is None:
            return llm_fn(prompt)
        return nano_llm_fn(prompt)

    @tool
    def ask_sub_llm_batch(prompts: list[str], effort: str) -> list[str]:
        """Envia multiplas perguntas a Sub-LLMs em paralelo. OBRIGATORIO informar effort.

        Args:
            prompts: lista de perguntas.
            effort: OBRIGATORIO. "low" (Nano-LLM) ou "high" (Mini-LLM).

        Exemplo effort="low":
            ask_sub_llm_batch(["Resuma doc X", "Resuma doc Y", ...], effort="low")

        Exemplo effort="high":
            ask_sub_llm_batch(["Analise juridica de X", "Analise juridica de Y"], effort="high")
        """
        if effort == "high" or nano_llm_batch_fn is None:
            return llm_batch_fn(prompts)
        return nano_llm_batch_fn(prompts)

    @tool
    def save_result(data: str, description: str) -> str:
        """Salva resultado da exploracao. Chame ao terminar sua tarefa.

        Args:
            data: informacao completa extraida (texto, JSON, etc).
            description: resumo breve (1 frase) do que encontrou.
        """
        shared.results[str(todo_id)] = {
            "data": data,
            "desc": description,
            "chars": len(data),
        }
        # Marca TODO como done
        for t in shared.todo_list:
            if t.get("id") == todo_id:
                t["status"] = "done"
                break
        logger.info("TODO %d salvo: %s (%d chars)", todo_id, description, len(data))
        return f"Resultado salvo para TODO {todo_id}: {description}"

    tools = [get_doc, search_docs, ask_sub_llm, ask_sub_llm_batch, save_result]
    if enable_websearch:
        tools.append(_make_websearch_tool(shared, todo_id))
    return tools


# ============================================================================
# Tool de WEB SEARCH (opcional para exploradores)
# ============================================================================


def _make_websearch_tool(
    shared: RLMSharedState,
    todo_id: int,
) -> BaseTool:
    """Cria tool web_search para um explorador, com renumeracao global de refs."""

    @tool
    def web_search(query: str) -> str:
        """Busca informacoes atualizadas na web usando Bing.

        Use para: legislacao vigente, jurisprudencia recente, normas externas,
        dados publicos, noticias relevantes ao processo.

        Args:
            query: pergunta ou termo de busca. Seja especifico e direto.

        Returns:
            Texto com informacoes encontradas. Refs marcadas com <web_N>.
            PRESERVE os marcadores <web_N> no seu save_result.
        """
        from sei_ia.agents.websearch.azure_web_search_tool import (
            bing_grounding_search,
        )

        logger.info("Explorer TODO %d: web_search(%r)", todo_id, query[:100])
        raw_result = bing_grounding_search.invoke({"query": query})

        try:
            parsed = json.loads(raw_result)
        except (json.JSONDecodeError, TypeError):
            return raw_result

        text = parsed.get("text", "")
        local_refs = parsed.get("references", [])

        if not local_refs:
            return text

        # Renumera refs com counter global (thread-safe)
        with shared._web_ref_lock:
            offset = shared._web_ref_counter[0]
            renumbered_refs = []
            for ref in local_refs:
                old_idx = ref["idx"]
                new_idx = offset + old_idx
                renumbered_refs.append(
                    {
                        "idx": new_idx,
                        "url": ref.get("url", ""),
                        "title": ref.get("title", ""),
                    }
                )
            shared._web_ref_counter[0] = offset + len(local_refs)

        # Substitui marcadores no texto (ordem reversa para nao deslocar)
        for ref, new_ref in sorted(
            zip(local_refs, renumbered_refs, strict=False),
            key=lambda pair: pair[0]["idx"],
            reverse=True,
        ):
            old_full = f"<web_{ref['idx']}></web_{ref['idx']}>"
            old_open = f"<web_{ref['idx']}>"
            new_marker = f"<web_{new_ref['idx']}>"
            text = text.replace(old_full, new_marker)
            text = text.replace(old_open, new_marker)

        # Armazena refs renumeradas no shared state
        with shared._web_ref_lock:
            shared.web_references.extend(renumbered_refs)

        logger.info(
            "Explorer TODO %d: web_search retornou %d refs (global idx %d-%d)",
            todo_id,
            len(renumbered_refs),
            renumbered_refs[0]["idx"],
            renumbered_refs[-1]["idx"],
        )
        return text

    return web_search


# ============================================================================
# Tools de SINTESE (Root LM — Fase 3)
# ============================================================================


def make_synthesis_tools(
    shared: RLMSharedState,
    llm_fn: Callable[[str], str],
    nano_llm_fn: Callable[[str], str] | None = None,
) -> list[BaseTool]:
    """Tools disponiveis para o Root LM na fase de sintese."""

    @tool
    def show_results() -> str:
        """Mostra manifesto: lista de resultados com descricao e tamanho (sem dados completos)."""
        if not shared.results:
            return "Nenhum resultado disponivel."
        lines = []
        for tid, r in sorted(shared.results.items(), key=lambda x: int(x[0])):
            lines.append(f"TODO {tid}: {r['desc']} ({r['chars']:,} chars)")
        return "\n".join(lines)

    @tool
    def get_result(todo_id: str) -> str:
        """Retorna dados completos de um resultado de exploracao."""
        r = shared.results.get(str(todo_id))
        if r is None:
            return f"Erro: resultado do TODO {todo_id} nao encontrado."
        return r["data"]

    @tool
    def ask_sub_llm(prompt: str, effort: str = "high") -> str:
        """Consulta Sub-LLM para analise adicional ou consolidacao.

        Args:
            prompt: pergunta ou instrucao para o Sub-LLM.
            effort: OBRIGATORIO. "low" (Nano-LLM) ou "high" (Mini-LLM). Default "high".
        """
        if effort == "high" or nano_llm_fn is None:
            return llm_fn(prompt)
        return nano_llm_fn(prompt)

    @tool
    def submit_answer(answer: str) -> str:
        """Submete resposta final ao usuario. Use quando a resposta estiver completa."""
        shared.final_answer = answer
        return "Resposta final submetida com sucesso."

    return [show_results, get_result, ask_sub_llm, submit_answer]
