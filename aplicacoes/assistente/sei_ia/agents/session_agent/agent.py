"""Construtor do agente de sessão (deepagents) para /llm_lang/session_stream.

Espelha `poc-deepagents-track-local/agent.py` na API canônica do deepagents 0.6.x:
`create_deep_agent` + `FilesystemBackend` escopado + subagente explorador. Sem
sandbox: o backend não é sandbox, então a tool `execute` é inerte (retorna erro) e
o system prompt instrui o agente a não usar shell. Sem RAG próprio; atenção:
`create_deep_agent` instala SEMPRE o `SummarizationMiddleware` do deepagents
(gatilho por fração de tokens), que coexiste com o `ConversationWindowMiddleware`
(corte por turnos) passado abaixo — são dois mecanismos de contexto distintos.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission

from sei_ia.agents.session_agent.explorer_limit import ExplorerConcurrencyMiddleware
from sei_ia.agents.session_agent.prompts import (
    COMPLEXITY_DIRECTIVES,
    DISCLAIMER_DIRECTIVE,
    EXPLORER_PROMPT,
    INJECTED_SYSTEM_PROMPT,
    LONG_TOPIC_DIRECTIVE,
    SESSION_SYSTEM_PROMPT,
    WEBRESEARCH_DEPTH_BY_COMPLEXITY,
    WEBRESEARCH_SHALLOW_DIRECTIVE,
    WEBSEARCH_DIRECTIVE,
)
from sei_ia.agents.session_agent.read_session import make_read_session_tool
from sei_ia.agents.session_agent.window import ConversationWindowMiddleware
from sei_ia.configs.settings_config import settings
from sei_ia.services.llm_models.get_model import get_model, get_model_config


def _explorer_subagent() -> dict:
    return {
        "name": "explorador",
        "description": (
            "Lê UM documento da sessão usando o path exato recebido, sem buscar "
            "substitutos. A descrição da task deve incluir a pergunta, o path, a "
            "referência-alvo e todos os eixos obrigatórios. Deve devolver cada eixo "
            "como encontrado, não encontrado ou evidência insuficiente. "
            "Emita múltiplas `task` no mesmo turno (paralelo) quando precisar de "
            "2+ documentos, sem abrir novamente no principal."
        ),
        "system_prompt": EXPLORER_PROMPT,
        # stream_usage=True: o explorador usa Chat Completions em streaming (nao a
        # Responses API do principal), que so inclui token usage com stream_options.
        # include_usage. Sem isso o usage do subagente vira 0 no Langfuse.
        "model": get_model(settings.SESSION_EXPLORER_MODEL, stream_usage=True),  # nano
    }


def _resolve_web_directive(web_tool: str, complexity: str) -> tuple[str, str]:
    """BASE estável + orientação de PROFUNDIDADE que varia por complexidade (frente 3).

    Mantidas separadas por causa do prompt caching (ver ``_compose_injected_prompt``).
    """
    if web_tool == "web_research":
        return WEBRESEARCH_SHALLOW_DIRECTIVE, WEBRESEARCH_DEPTH_BY_COMPLEXITY.get(
            complexity, ""
        )
    return WEBSEARCH_DIRECTIVE, ""


def _compose_injected_prompt(
    *,
    web_base: str,
    web_depth: str,
    use_websearch: bool,
    injected_context: str | None,
    long_topic: bool,
) -> str:
    if not injected_context:
        raise ValueError("modo injetado exige injected_context (bloco de documentos)")
    # ORDEM p/ PROMPT CACHING: o prefixo grande e estável
    # (prompt+disclaimer+web_base+docs) vem PRIMEIRO; tudo que VARIA por turno — a
    # profundidade (muda com a complexidade) e o LONG_TOPIC (aparece ao cruzar a
    # janela) — vai DEPOIS do bloco de docs. Assim o bloco (o caro) é cacheável
    # mesmo quando a complexidade muda entre turnos da mesma sessão.
    parts = [INJECTED_SYSTEM_PROMPT, DISCLAIMER_DIRECTIVE]
    if use_websearch:
        parts.append(web_base)
    parts.append(injected_context)
    if use_websearch and web_depth:
        parts.append(web_depth)
    if long_topic:
        parts.append(LONG_TOPIC_DIRECTIVE)
    return "\n\n".join(parts)


def _compose_filesystem_prompt(
    *,
    complexity: str,
    use_websearch: bool,
    web_base: str,
    web_depth: str,
    long_topic: bool,
) -> str:
    # sem bloco grande no prompt (docs via tools) → ordem não afeta caching.
    directive = COMPLEXITY_DIRECTIVES.get(complexity, COMPLEXITY_DIRECTIVES["medium"])
    if complexity == "high":
        directive = (
            f"{directive}\nUse no máximo {settings.SESSION_MAX_EXPLORERS} "
            f"exploradores em paralelo."
        )
    if use_websearch:
        web_full = f"{web_base}\n\n{web_depth}".strip() if web_depth else web_base
        directive = f"{directive}\n\n{web_full}"
    system_prompt = f"{SESSION_SYSTEM_PROMPT}\n\n{DISCLAIMER_DIRECTIVE}\n\n{directive}"
    if long_topic:
        system_prompt = f"{system_prompt}\n\n{LONG_TOPIC_DIRECTIVE}"
    return system_prompt


def compose_system_prompt(
    *,
    mode: str = "filesystem",
    complexity: str = "medium",
    use_websearch: bool = False,
    long_topic: bool = False,
    injected_context: str | None = None,
    web_tool: str = "deep_research",
    unavailable_document_ids: tuple[str, ...] = (),
) -> str:
    """Monta o system prompt do agente conforme o modo (função pura, testável).

    ``filesystem``: prompt de exploração + diretiva de complexidade (comportamento
    original, byte a byte). ``injected``: prompt do modo injetado + o bloco de
    documentos POR ÚLTIMO (prefixo estável entre turnos → prompt caching); a diretiva
    de complexidade não entra (ela calibra exploração, que não existe neste modo).
    ``web_tool`` escolhe a diretiva de busca: ``deep_research`` (tool profunda, uma
    chamada) ou ``web_research`` (tool rasa; o principal dirige a profundidade).
    """
    web_base, web_depth = _resolve_web_directive(web_tool, complexity)

    if mode == "injected":
        system_prompt = _compose_injected_prompt(
            web_base=web_base,
            web_depth=web_depth,
            use_websearch=use_websearch,
            injected_context=injected_context,
            long_topic=long_topic,
        )
    else:
        system_prompt = _compose_filesystem_prompt(
            complexity=complexity,
            use_websearch=use_websearch,
            web_base=web_base,
            web_depth=web_depth,
            long_topic=long_topic,
        )

    if unavailable_document_ids:
        count = len(unavailable_document_ids)
        document_label = "documento" if count == 1 else "documentos"
        system_prompt = (
            f"{system_prompt}\n\nDOCUMENTOS INDISPONÍVEIS NESTE TURNO: há {count} "
            f"{document_label}. A atualização desses documentos falhou. Não use nem "
            "procure conteúdo de versões anteriores. Avise explicitamente o usuário "
            "que não foi possível atualizar esses documentos, sem listar IDs internos, "
            "paths ou nomes de arquivos; use somente números visíveis quando existirem."
        )
    return system_prompt


def build_session_agent(
    session_dir: str | Path,
    *,
    checkpointer,
    resolved=None,
    complexity: str = "medium",
    use_websearch: bool = False,
    max_turns: int = 20,
    long_topic: bool = False,
    use_thinking: bool = False,
    mode: str = "filesystem",
    injected_context: str | None = None,
    speculative_queries: list[str] | None = None,
    web_question: str = "",
    evidence_gate_callbacks: list[object] | None = None,
    unavailable_document_ids: tuple[str, ...] = (),
    web_research_state: dict[str, Any] | None = None,
    model_override: str | None = None,
    reasoning_effort: str | None = None,
):
    """Monta o agente apontado para o diretório da sessão.

    ``model_override`` substitui o alias físico do papel `principal`
    (SESSION_MAIN_MODEL) por um alias que carregue a tag `agents:principal`
    no catálogo ao vivo do proxy LiteLLM — mesmo mecanismo do `ChatRequest.model`
    do endpoint clássico, já validado pelo caller contra
    `model_catalog.validate_model_override`. Só afeta o modelo principal;
    explorador/classificador/evidence-gate continuam nos tiers fixos.

    ``reasoning_effort`` (explícito no payload, já validado pelo caller contra
    o catálogo do proxy — ver ``model_catalog.validate_reasoning_effort``) tem
    prioridade sobre ``use_thinking``: quando presente, o modelo principal
    reasona com ESSE nível, independente de ``use_thinking``. Sem ele, cai no
    comportamento antigo (``use_thinking`` liga/desliga entre
    ``SESSION_REASONING_EFFORT``/``SESSION_REASONING_EFFORT_THINKING``).

    ``session_dir`` é o boundary ``{id_usuario}_{id_topico}``. ``checkpointer`` é o
    singleton Postgres; o ``thread_id`` (session_key) é passado na invocação.
    ``complexity`` (easy/medium/high) anexa a diretiva de esforço ao system prompt.
    ``use_websearch`` adiciona a tool ``deep_research_search`` (DeepResearchAgent).
    ``max_turns`` governa o middleware de janela (apara turnos antigos no checkpointer).
    ``long_topic`` insere LONG_TOPIC_DIRECTIVE quando o histórico excede a janela.
    ``resolved`` é o snapshot já preparado que alimenta a tool ``read_session``;
    a tool captura os metadados por closure e não consulta rede/cache. O Deep Agents
    gerencia resultados grandes, compactação e overflow. ``mode`` (``filesystem`` |
    ``injected``) é a decisão de tamanho (fase 5).
    No modo
    ``injected`` (fase 6), ``injected_context`` (bloco de documentos completo, montado
    por ``inject.build_injected_context``) entra no system prompt e o agente sobe SEM
    o subagente explorador — o conteúdo já está inline; as tools de filesystem ficam
    só para reconferência (decisão do Ennio 2026-07-06). O ``SessionManager`` segue
    escrevendo os arquivos no disco normalmente (a injeção é adicional).

    Reasoning é SEMPRE ligado no modelo principal (Responses API), com effort
    ``SESSION_REASONING_EFFORT`` (``low`` por padrão), **independente da complexidade**.
    ``use_thinking=True`` sobe o effort para ``SESSION_REASONING_EFFORT_THINKING``
    (``medium``). A temperatura não é enviada pelo modelo principal, permitindo
    que o proxy/modelo aplique seu default. O explorador (nano) nunca reasona.
    """
    backend = FilesystemBackend(
        root_dir=str(session_dir),
        virtual_mode=True,
        max_file_size_mb=settings.SESSION_MAX_FILE_SIZE_MB,
    )
    injected = mode == "injected"

    # A janela configurada no profile é a fonte local única: não consultar o proxy
    # durante a construção do agente. O caller pode fornecer um orçamento menor
    # quando já conhece o prompt real do turno.
    main_config = get_model_config(
        settings.SESSION_MAIN_MODEL, model_override=model_override
    )
    max_input_tokens = main_config["max_ctx_len"]

    tools = []
    read_session_tool = make_read_session_tool(resolved)
    if read_session_tool is not None:
        tools.append(read_session_tool)
    if use_websearch:
        # Tool web do session, escolhida pelo knob SESSION_WEB_TOOL (fase 8). O
        # clássico segue no DeepResearchAgent próprio, intocado. Imports tardios: os
        # módulos puxam httpx/bs4 e os clientes da stack web.
        if settings.SESSION_WEB_TOOL == "web_research":
            # Rasa (truncar-e-armazenar): zero LLM interno; salva páginas em web/ na
            # sessão e devolve janela+ponteiro; profundidade dirigida pelo principal.
            from sei_ia.agents.websearch.web_research_agent import WebResearchAgent

            # Profundidade por complexidade (frente 3): calibra 2 eixos, ambos capados
            # pelos tetos configurados. Evita over-search/over-crawl em pergunta trivial
            # (medido) e libera exploração no amplo.
            #   nº de buscas (max_calls):  easy=2  medium=4  high=teto
            #   páginas por busca (max_pages): easy=5  medium=8  high=teto
            _calls_ceiling = settings.SESSION_WEBRESEARCH_MAX_CALLS
            _pages_ceiling = settings.SESSION_WEBSEARCH_MAX_PAGES
            web_max_calls = min(
                {"easy": 2, "medium": 4, "high": _calls_ceiling}.get(complexity, 4),
                _calls_ceiling,
            )
            web_max_pages = min(
                {"easy": 5, "medium": 8, "high": _pages_ceiling}.get(complexity, 8),
                _pages_ceiling,
            )
            web_tool = WebResearchAgent(
                searx_base_url=settings.SEARX_BASE_URL,
                fastcrw_base_url=settings.FASTCRW_BASE_URL,
                byparr_base_url=settings.BYPARR_BASE_URL,
                session_root=str(session_dir),
                max_pages=web_max_pages,
                window_chars=settings.SESSION_WEBRESEARCH_WINDOW_CHARS,
                max_calls=web_max_calls,
                crawl_concurrency=settings.SESSION_WEBRESEARCH_CRAWL_CONCURRENCY,
                evidence_gate_enabled=settings.SESSION_WEBRESEARCH_EVIDENCE_GATE_ENABLED,
                evidence_gate_model=(
                    get_model("triagem_busca", stream_usage=True)
                    if settings.SESSION_WEBRESEARCH_EVIDENCE_GATE_ENABLED
                    else None
                ),
                evidence_gate_question=web_question,
                evidence_gate_callbacks=evidence_gate_callbacks,
                evidence_gate_input_chars=settings.SESSION_WEBRESEARCH_EVIDENCE_GATE_INPUT_CHARS,
            )
            web_tool.bind_research_state(web_research_state)
            # Buscas especulativas: o planejador mini lista até N pontos externos
            # necessários. Todas começam antes do principal; a 1ª chamada da tool
            # colhe o lote. Requer loop rodando (build é chamado pelo handler async).
            if speculative_queries:
                # Em easy/medium o orçamento de buscas é menor que o global;
                # não deixe o lote especulativo consumi-lo antes do principal.
                web_tool.start_speculative(speculative_queries[:web_max_calls])
        else:
            # Profunda (mesma do clássico): rounds/extração por página internos.
            from sei_ia.agents.websearch.deep_research_agent import DeepResearchAgent

            web_tool = DeepResearchAgent(
                searx_base_url=settings.SEARX_BASE_URL,
                fastcrw_base_url=settings.FASTCRW_BASE_URL,
                byparr_base_url=settings.BYPARR_BASE_URL,
                llm=get_model(
                    agent_tag=settings.SESSION_MAIN_MODEL,
                    model_override=model_override,
                ),
                # explorador/classificador: default do compress_llm/extract_llm
                # compartilhado com o DeepResearchAgent. _classify_search_mode
                # rebind pra triagem_busca na hora certa (ver
                # deep_research_agent.py).
                compress_llm=get_model(agent_tag="explorador"),
                extract_llm=get_model(agent_tag="classificador"),
                max_pages=settings.SESSION_WEBSEARCH_MAX_PAGES,
                max_rounds=settings.SESSION_WEBSEARCH_MAX_ROUNDS,
                llm_ctx_len=settings.CTX_LEN_STANDARD_MODEL,
                compress_llm_ctx_len=settings.CTX_LEN_NANO_MODEL,
            )
        tools.append(web_tool)

    system_prompt = compose_system_prompt(
        mode=mode,
        complexity=complexity,
        use_websearch=use_websearch,
        long_topic=long_topic,
        injected_context=injected_context,
        web_tool=settings.SESSION_WEB_TOOL,
        unavailable_document_ids=unavailable_document_ids,
    )

    # Reasoning SEMPRE on no modelo principal, effort low por padrão (independe da
    # complexidade). use_thinking=True sobe o effort para medium; reasoning_effort
    # explícito no payload tem prioridade sobre os dois. A temperatura é omitida
    # para que o proxy/modelo aplique seu default. O explorador (nano) não recebe
    # esses kwargs.
    effort = reasoning_effort or (
        settings.SESSION_REASONING_EFFORT_THINKING
        if use_thinking
        else settings.SESSION_REASONING_EFFORT
    )
    # profile explícito: o alias do proxy não resolve no registry do langchain
    # (ficaria None → summarizer no fallback fixo de 170k). Com a janela real, o
    # deepagents usa trigger por fração (0.85) da janela configurada no profile.
    return create_deep_agent(
        model=get_model(
            settings.SESSION_MAIN_MODEL,
            model_override=model_override,
            use_responses_api=True,
            reasoning={
                "effort": effort,
                "summary": settings.SESSION_REASONING_SUMMARY,
            },
            profile={"max_input_tokens": max_input_tokens},
        ),
        system_prompt=system_prompt,
        tools=tools,
        backend=backend,
        permissions=[
            FilesystemPermission(
                operations=["write"], paths=["/session.json"], mode="deny"
            ),
            FilesystemPermission(
                operations=["write"],
                paths=["/proc_*", "/proc_*/**"],
                mode="deny",
            ),
        ],
        # Injetado: SEM explorador (conteúdo já inline; tools de FS só p/ reconferir).
        subagents=[] if injected else [_explorer_subagent()],
        checkpointer=checkpointer,
        middleware=[
            ConversationWindowMiddleware(max_turns),
            # Teto real do "no máximo N exploradores em paralelo" do prompt: capa
            # as tool calls `task` concorrentes por semáforo (ver explorer_limit.py).
            ExplorerConcurrencyMiddleware(settings.SESSION_MAX_EXPLORERS),
        ],
    )
