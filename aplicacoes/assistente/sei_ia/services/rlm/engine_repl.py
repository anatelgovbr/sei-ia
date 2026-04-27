"""Orquestrador RLM v2 (Recursive Language Model).

Arquitetura Plan-Execute-Synthesize via LangGraph Tools:
    [1] Coletar documentos (SEM segmentacao)
    [2] Construir contexto string + catalogo por tipo
    [3] LangGraph pipeline: TODO planning -> tool execution -> synthesis
    [4] Montar last_prompt compativel com generate_response()

O pipeline LangGraph (rlm.graph) recebe o contexto completo e um catalogo
estruturado por tipo de documento, delega exploracoes a tools (ask_sub_lm,
read_document, search_all, etc.) e consolida achados em resposta final.

Contrato:
    ENTRADA: UserState com id_procedimentos populados, all_tokens_counter > limit_rag
    SAIDA: UserState com last_prompt preenchido, doc_rag=True, rag_method="rlm_v2"
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from sei_ia.services.rlm.config import RLMConfig
from sei_ia.services.rlm.prompts_repl import CITATION_INSTRUCTIONS
from sei_ia.services.rlm.segmenter import count_tokens

logger = logging.getLogger(__name__)

# Compativel com sei_ia.data.pydantic_models.UserState (TypedDict).
UserState = dict[str, Any]


# ==============================================================================
# FUNCOES PUBLICAS
# ==============================================================================


def should_use_rlm(user_state: UserState) -> bool:
    """Ativa RLM quando o volume de tokens excede o limite do RAG single-pass.

    Mapa de decisao:
        all_tokens_counter <= general_max_ctx_len  -> build_direct_prompt()
        general_max_ctx_len < tokens <= limit_rag  -> make_prompt_with_rag_enhanced()
        all_tokens_counter > limit_rag             -> rlm_pipeline()
    """
    return user_state["all_tokens_counter"] > user_state["limit_rag"]


async def rlm_pipeline(
    user_state: UserState,
    config: RLMConfig | None = None,
    root_llm: Any | None = None,
    sub_llm: Any | None = None,
    on_step: Callable[[str, dict[str, Any]], None] | None = None,
) -> UserState:
    """Pipeline RLM: Plan -> Execute -> Synthesize via LangGraph Tools."""
    from sei_ia.services.rlm.graph import run_rlm_v2
    from sei_ia.services.rlm.tools import build_shared_state

    _emit = on_step or (lambda _e, _d: None)
    t0 = time.perf_counter()

    if config is None:
        config = RLMConfig()

    if root_llm is None:
        root_llm = _create_default_llm(config.root_model_type, config.root_temperature)
    if sub_llm is None:
        sub_llm = _create_default_llm(config.sub_model_type, config.sub_temperature)

    # Nano-LLM para ask_sub_lm effort="low"
    nano_llm = _create_default_llm(config.nano_model_type, config.sub_temperature)

    logger.info(
        "Iniciando RLM v2 pipeline: %d tokens (root=%s, sub=%s, nano=%s)",
        user_state.get("all_tokens_counter", 0),
        config.root_model_type,
        config.sub_model_type,
        config.nano_model_type,
    )

    # [1] Coletar documentos
    _emit(
        "segmentation_start",
        {"total_tokens": user_state.get("all_tokens_counter", 0)},
    )
    t_seg = time.perf_counter()
    doc_list, id_to_formatted, contents = _collect_documents(user_state)

    if not doc_list:
        user_state["last_prompt"] = (
            "Os documentos fornecidos estao com conteudo vazio.\n\n"
            f"Pergunta do usuario: {user_state.get('user_request', '')}"
        )
        user_state["doc_rag"] = False
        user_state["rag_method"] = "rlm_v2"
        return user_state

    _emit(
        "segmentation_complete",
        {
            "num_docs": len(doc_list),
            "total_sections": 0,
            "total_gist_tokens": 0,
            "total_original_tokens": sum(d["total_tokens"] for d in doc_list),
            "compression_ratio": 0,
            "elapsed_s": time.perf_counter() - t_seg,
        },
    )

    # [2] Construir contexto + catalogo
    context_string = _build_context_string(doc_list, contents)
    query = user_state.get("user_request", "")

    _emit(
        "repl_context_built",
        {
            "num_docs": len(doc_list),
            "total_sections": 0,
            "context_chars": len(context_string),
        },
    )

    catalog = _build_catalog(doc_list, context_string)

    # [3] Construir shared state e rodar pipeline
    shared = build_shared_state(context_string, catalog)
    use_websearch = bool(user_state.get("use_websearch", False))

    final_answer = await run_rlm_v2(
        shared=shared,
        root_llm=root_llm,
        sub_llm=sub_llm,
        config=config,
        query=query,
        nano_llm=nano_llm,
        on_step=on_step,
        use_websearch=use_websearch,
    )

    # Propagar refs web para user_state (post-processing resolve <web_N>)
    if shared.web_references:
        logger.info(
            "web_references: %d refs coletadas (counter=%d)",
            len(shared.web_references),
            shared._web_ref_counter[0],
        )
        user_state["tool_web_search"] = [
            {"references": list(shared.web_references)},
        ]
        # Desabilita websearch no chat_gpt posterior para evitar busca duplicada
        user_state["use_websearch"] = False

    # [4] Montar last_prompt
    last_prompt = _build_last_prompt(
        final_answer,
        doc_list,
        query,
        id_to_formatted,
        has_web_references=bool(shared.web_references),
    )
    prompt_tokens = count_tokens(last_prompt)

    user_state["last_prompt"] = last_prompt
    user_state["doc_rag"] = True
    user_state["rag_method"] = "rlm_v2"
    user_state["rag_documents_count"] = len(doc_list)
    user_state["id_to_formatted_map"] = id_to_formatted

    _emit(
        "synthesis_complete",
        {
            "prompt_chars": len(last_prompt),
            "prompt_tokens": prompt_tokens,
            "findings_count": len(shared.results),
            "findings_relevant": len(shared.results),
            "docs_referenced": list(id_to_formatted.values()),
            "total_elapsed_s": time.perf_counter() - t0,
            "final_answer": final_answer,
            "last_prompt": last_prompt,
        },
    )

    logger.info(
        "RLM v2 concluido: %d TODOs, %.1fs total.",
        len(shared.todo_list),
        time.perf_counter() - t0,
    )

    return user_state


# ==============================================================================
# HELPERS INTERNOS
# ==============================================================================


def _create_default_llm(model_type: str, temperature: float) -> Any:
    """Cria LLM padrao via langchain-openai (compativel com LiteLLM proxy)."""
    try:
        from sei_ia.services.llm_models.get_model import get_model

        return get_model(model_type, temperature=temperature)
    except Exception:
        pass

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise ImportError(
            "langchain-openai e necessario. Instale com: pip install langchain-openai"
        ) from e

    try:
        from sei_ia.configs.settings_config import settings

        base_url = settings.LITELLM_PROXY_URL
        api_key = settings.LITELLM_PROXY_API_KEY or "dummy-key"
    except Exception:
        import os

        base_url = os.environ.get("OPENAI_BASE_URL", "http://localhost:4000")
        api_key = os.environ.get("OPENAI_API_KEY", "dummy-key")

    return ChatOpenAI(
        model=model_type,
        temperature=temperature,
        base_url=base_url,
        api_key=api_key,
    )


async def _llm_invoke_text(llm: Any, prompt: str | list[dict[str, str]]) -> str:
    """Chama o LLM e retorna o texto da resposta.

    Aceita string (prompt unico) ou lista de mensagens (chat).
    """
    if isinstance(prompt, list):
        # Chat messages
        response = await llm.ainvoke(prompt)
    else:
        response = await llm.ainvoke(prompt)
    if hasattr(response, "content"):
        return response.content
    return str(response)


async def _llm_invoke_batched(llm: Any, prompts: list[str]) -> list[str]:
    """Chama o LLM com multiplos prompts concorrentemente.

    Falhas individuais retornam string de erro sem derrubar o batch inteiro.
    """
    tasks = [_llm_invoke_text(llm, p) for p in prompts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r if isinstance(r, str) else f"Erro na chamada LLM: {r}" for r in results]


# ==============================================================================
# COLETA DE DOCUMENTOS (SEM SEGMENTACAO)
# ==============================================================================


def _parse_metadata_str(meta_str: str) -> dict[str, str]:
    """Parseia metadata string 'Chave: Valor\\n...' em dict."""
    result: dict[str, str] = {}
    if not meta_str:
        return result
    for line in meta_str.strip().splitlines():
        if ": " in line:
            key, _, value = line.partition(": ")
            result[key.strip()] = value.strip()
    return result


def _collect_documents(
    user_state: UserState,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    """Coleta documentos com metadados completos, agrupados por processo.

    Retorna:
        (doc_list, id_to_formatted_map, contents_by_sei)

    Onde doc_list e uma lista de dicts com metadados dos documentos.
    O id_to_formatted_map e identity mapping (SEI -> SEI) pois usamos
    o SEI number diretamente como doc_id nos marcadores de citacao.
    """
    doc_data_list: list[dict[str, Any]] = []
    id_to_formatted: dict[str, str] = {}
    contents: dict[str, str] = {}

    procedimentos = user_state.get("id_procedimentos") or []

    for proc in procedimentos:
        proc_id = getattr(proc, "id_procedimento", "unknown")
        proc_meta = _parse_metadata_str(getattr(proc, "metadata", "") or "")

        docs = proc.id_documentos if hasattr(proc, "id_documentos") else []
        for doc in docs:
            content = getattr(doc, "content", None) or ""
            if not content.strip():
                continue

            doc_id = getattr(doc, "id_documento", "unknown")
            doc_id_fmt = getattr(doc, "id_documento_formatado", None) or doc_id
            total_tokens = getattr(doc, "doc_tokens", None) or count_tokens(content)
            doc_meta = _parse_metadata_str(getattr(doc, "metadata", "") or "")
            doc_metadata_str = getattr(doc, "metadata", "") or ""

            # Identity mapping: SEI number -> SEI number
            id_to_formatted[doc_id_fmt] = doc_id_fmt
            contents[doc_id_fmt] = content

            doc_data_list.append(
                {
                    "sei_number": doc_id_fmt,
                    "doc_id": doc_id,
                    "doc_id_formatado": doc_id_fmt,
                    "total_tokens": total_tokens,
                    "content": content,
                    "proc_id": proc_id,
                    "proc_numero": proc_meta.get("Numero do Processo", ""),
                    "proc_tipo": proc_meta.get("Tipo do Processo", ""),
                    "proc_descricao": proc_meta.get(
                        "Descricao/Especificacao do Processo", ""
                    ),
                    "doc_tipo": doc_meta.get("Descricao do tipo de Documento", ""),
                    "doc_formato": doc_meta.get("Formato do arquivo do Documento", ""),
                    "doc_data": doc_meta.get("Data de Inclusao do Documento", ""),
                    "doc_descricao": doc_meta.get("Descricao do Documento", ""),
                    "doc_metadata_str": doc_metadata_str,
                }
            )

            logger.debug(
                "Documento %s coletado: %d tokens.",
                doc_id_fmt,
                total_tokens,
            )

    logger.info(
        "Coleta concluida: %d documentos, %d tokens total.",
        len(doc_data_list),
        sum(d["total_tokens"] for d in doc_data_list),
    )

    return doc_data_list, id_to_formatted, contents


# ==============================================================================
# CONTEXTO STRING
# ==============================================================================


def _build_context_string(
    doc_list: list[dict[str, Any]],
    contents: dict[str, str],
) -> str:
    """Constroi string com formato hibrido XML+PIPE por processo/documento.

    Envelope XML (<processo>, <doc>) delimita fronteiras de forma inequivoca.
    Metadados internos em formato PIPE (compacto, ~43% menos tokens que XML puro).

    Formato:
        <processo>
        id | numero | tipo | descricao
        <doc sei>
        tipo | formato | data | tokens
        conteudo livre...
        </doc>
        </processo>
    """
    # Agrupar docs por processo
    procs_order: list[str] = []
    procs_docs: dict[str, list[dict[str, Any]]] = {}
    for d in doc_list:
        pid = d.get("proc_id", "unknown")
        if pid not in procs_docs:
            procs_order.append(pid)
            procs_docs[pid] = []
        procs_docs[pid].append(d)

    parts: list[str] = []
    for pid in procs_order:
        docs = procs_docs[pid]
        first = docs[0]
        proc_numero = first.get("proc_numero", "")
        proc_tipo = first.get("proc_tipo", "")
        proc_desc = first.get("proc_descricao", "").strip()

        parts.append("<processo>")
        parts.append(f"{pid} | {proc_numero} | {proc_tipo} | {proc_desc}")

        for d in docs:
            sei = d["doc_id_formatado"]
            tokens = d.get("total_tokens", 0)
            doc_metadata_str = d.get("doc_metadata_str", "")

            parts.append(f"<doc {sei}>")
            parts.append(f"{tokens} tok")
            if doc_metadata_str:
                parts.append(doc_metadata_str)
            parts.append(contents[sei])
            parts.append("</doc>")

        parts.append("</processo>")

    return "\n".join(parts)


# ==============================================================================
# CATALOGO POR TIPO
# ==============================================================================


def _build_catalog(
    doc_list: list[dict[str, Any]],
    context_string: str,
) -> str:
    """Constroi catalogo textual agrupando documentos por tipo.

    Args:
        doc_list: Lista de dicts com metadados dos documentos.
        context_string: String de contexto completa (usada para contagem de chars).

    Returns:
        Texto formatado com resumo de contexto e catalogo por tipo de documento.
    """
    num_procs = len({d.get("proc_id", "?") for d in doc_list})
    docs_by_type: dict[str, list[str]] = defaultdict(list)
    total_tokens_by_type: dict[str, int] = defaultdict(int)
    for d in doc_list:
        tipo = d.get("doc_tipo", "Desconhecido") or "Desconhecido"
        docs_by_type[tipo].append(d["doc_id_formatado"])
        total_tokens_by_type[tipo] += d.get("total_tokens", 0)

    catalog_parts = [
        f"Contexto: {len(context_string):,} chars, {num_procs} processo(s), {len(doc_list)} documentos.",
        "",
        "Catalogo por tipo:",
    ]
    for tipo, seis in docs_by_type.items():
        total_tok = total_tokens_by_type[tipo]
        preview = ", ".join(seis[:8])
        if len(seis) > 8:
            preview += f", ... (+{len(seis) - 8})"
        catalog_parts.append(
            f"  {tipo}: {len(seis)} docs ({total_tok:,} tok) -- SEIs: {preview}"
        )
    return "\n".join(catalog_parts)


# ==============================================================================
# SINTESE FINAL -- Construcao do last_prompt
# ==============================================================================


def _build_last_prompt(
    final_answer: str,
    doc_data: list[dict[str, Any]],
    query: str,
    id_to_formatted: dict[str, str],
    has_web_references: bool = False,
) -> str:
    """Constroi o last_prompt compativel com generate_response().

    Formato identico ao engine.py para compatibilidade.
    Nao injeta citacoes artificiais -- o LLM e responsavel por citar.
    """
    parts: list[str] = ["[INFORMACOES EXTRAIDAS DOS DOCUMENTOS]"]

    for d in doc_data:
        sei = d["doc_id_formatado"]
        meta = d.get("doc_metadata_str", "")
        inner = f"\n{meta}" if meta else ""
        parts.append(f"\n<doc_{sei}>{inner}\n</doc_{sei}>")

    parts.append(f"\n{final_answer}")
    parts.append("\n[/INFORMACOES EXTRAIDAS DOS DOCUMENTOS]")

    parts.append(
        f"\n[INSTRUCOES PARA CITACOES]\n{CITATION_INSTRUCTIONS}\n[/INSTRUCOES PARA CITACOES]"
    )

    if has_web_references:
        from sei_ia.agents.prompts.web_search import WEB_SEARCH_PROMPT

        parts.append(f"\n{WEB_SEARCH_PROMPT}")

    parts.append(f"\nPergunta do usuario: {query}")

    return "\n".join(parts)
