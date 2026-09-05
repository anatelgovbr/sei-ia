"""Construção do agente de sessão (deepagents). Offline: não chama o LLM."""

import pytest

import sei_ia.agents.session_agent.agent as agent_module
from sei_ia.agents.session_agent.agent import (
    _explorer_subagent,
    build_session_agent,
    compose_system_prompt,
)


def test_explorer_subagent_shape():
    sub = _explorer_subagent()
    assert sub["name"] == "explorador"
    assert sub["system_prompt"]
    assert sub["model"] is not None  # nano, BaseChatModel instance


def test_target_lock_aligns_main_handoff_and_explorer():
    main_prompt = " ".join(
        compose_system_prompt(mode="filesystem", complexity="high").split()
    )
    explorer = _explorer_subagent()
    explorer_description = " ".join(explorer["description"].split())
    explorer_prompt = " ".join(explorer["system_prompt"].split())

    for invariant in ("ALVOS OBRIGATÓRIOS", "EIXOS OBRIGATÓRIOS", "target lock"):
        assert invariant in main_prompt

    for invariant in (
        "path exato",
        "pergunta",
        "todos os eixos obrigatórios",
        "sem abrir novamente",
    ):
        assert invariant in explorer_description

    for invariant in (
        "path exato",
        "todos os eixos",
        "arquivo-fonte",
        "limitação",
    ):
        assert invariant in explorer_prompt


@pytest.mark.parametrize(
    ("mode", "injected_context"),
    [("filesystem", None), ("injected", "<documentos></documentos>")],
)
def test_prompt_avisa_documentos_que_nao_puderam_ser_atualizados(
    mode, injected_context
):
    prompt = compose_system_prompt(
        mode=mode,
        injected_context=injected_context,
        unavailable_document_ids=("DOC-7", "DOC-9"),
    )

    assert "DOCUMENTOS INDISPONÍVEIS NESTE TURNO: há 2 documentos" in prompt
    assert "DOC-7" not in prompt
    assert "DOC-9" not in prompt
    assert "A atualização desses documentos falhou" in prompt
    assert "Não use nem procure conteúdo de versões anteriores" in prompt
    assert "Avise explicitamente o usuário" in prompt
    assert "sem listar IDs internos" in prompt


@pytest.mark.parametrize("prompt_name", ["filesystem", "injected"])
def test_prompt_orienta_identificadores_visiveis_e_oculta_referencias_internas(
    prompt_name,
):
    prompt = " ".join(
        compose_system_prompt(
            mode=prompt_name,
            injected_context=(
                "<documentos></documentos>" if prompt_name == "injected" else None
            ),
        ).split()
    )

    assert "NUNCA revele, transcreva ou explique esses identificadores" in prompt
    assert "Não chame o `id_procedimento` de número do processo" in prompt
    assert "Nunca substitua essa informação pelo ID interno" in prompt


def test_build_session_agent_constroi_grafo_invocavel(tmp_path):
    agent = build_session_agent(tmp_path / "42_123", checkpointer=None)
    # create_deep_agent devolve um CompiledStateGraph invocável.
    assert hasattr(agent, "astream")
    assert hasattr(agent, "ainvoke")


def test_build_session_agent_isola_por_diretorio(tmp_path):
    a = build_session_agent(tmp_path / "1_1", checkpointer=None)
    b = build_session_agent(tmp_path / "2_2", checkpointer=None)
    assert a is not b


@pytest.mark.parametrize("complexity", ["easy", "medium", "high"])
def test_build_session_agent_aceita_complexity(tmp_path, complexity):
    agent = build_session_agent(
        tmp_path / f"s_{complexity}", checkpointer=None, complexity=complexity
    )
    assert hasattr(agent, "astream")


def test_build_session_agent_com_websearch_constroi(tmp_path):
    # use_websearch adiciona a tool deep_research_search (DeepResearchAgent);
    # construção é offline (não chama a stack web), só monta o grafo.
    agent = build_session_agent(tmp_path / "w", checkpointer=None, use_websearch=True)
    assert hasattr(agent, "astream")


def test_build_session_agent_usa_factory_comum_para_principal_e_explorador(
    monkeypatch, tmp_path
):
    calls = []

    def fake_get_model(model_type, **kwargs):
        calls.append((model_type, kwargs))
        return object()

    monkeypatch.setattr(agent_module, "get_model", fake_get_model)
    monkeypatch.setattr(agent_module, "create_deep_agent", lambda **kwargs: kwargs)
    build_session_agent(tmp_path / "cache", checkpointer=None)

    assert {model_type for model_type, _kwargs in calls} >= {"principal", "explorador"}


def test_build_session_agent_propaga_model_override_so_para_o_papel_principal(
    monkeypatch, tmp_path
):
    model_calls = []
    config_calls = []

    def fake_get_model(model_type, **kwargs):
        model_calls.append((model_type, kwargs))
        return object()

    def fake_get_model_config(model_type, **kwargs):
        config_calls.append((model_type, kwargs))
        return {"max_ctx_len": 1_000_000, "max_output_tokens": 32_768}

    monkeypatch.setattr(agent_module, "get_model", fake_get_model)
    monkeypatch.setattr(agent_module, "get_model_config", fake_get_model_config)
    monkeypatch.setattr(agent_module, "create_deep_agent", lambda **kwargs: kwargs)

    build_session_agent(
        tmp_path / "override",
        checkpointer=None,
        model_override="openai/seiia-ds-gemini-pro",
    )

    principal_model_calls = [kw for mt, kw in model_calls if mt == "principal"]
    explorador_model_calls = [kw for mt, kw in model_calls if mt == "explorador"]
    assert principal_model_calls
    assert all(
        kw.get("model_override") == "openai/seiia-ds-gemini-pro"
        for kw in principal_model_calls
    )
    assert all(kw.get("model_override") is None for kw in explorador_model_calls)

    principal_config_calls = [kw for mt, kw in config_calls if mt == "principal"]
    assert principal_config_calls
    assert all(
        kw.get("model_override") == "openai/seiia-ds-gemini-pro"
        for kw in principal_config_calls
    )


@pytest.mark.parametrize("use_thinking", [False, True])
def test_build_session_agent_reasoning_effort_tem_prioridade_sobre_use_thinking(
    monkeypatch, tmp_path, use_thinking
):
    model_calls = []

    def fake_get_model(model_type, **kwargs):
        model_calls.append((model_type, kwargs))
        return object()

    monkeypatch.setattr(agent_module, "get_model", fake_get_model)
    monkeypatch.setattr(agent_module, "create_deep_agent", lambda **kwargs: kwargs)

    build_session_agent(
        tmp_path / "reasoning",
        checkpointer=None,
        use_thinking=use_thinking,
        reasoning_effort="none",
    )

    principal_calls = [kw for mt, kw in model_calls if mt == "principal"]
    assert principal_calls
    assert all(kw["reasoning"]["effort"] == "none" for kw in principal_calls)
