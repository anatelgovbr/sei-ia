"""Testes da busca especulativa (fase 8, frente 2)."""

from __future__ import annotations

import asyncio
import datetime as dt

from sei_ia.agents.session_agent.web_speculative import (
    build_doc_hint,
    plan_speculative_web_queries,
)


class _FakeMsg:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, out):
        self._out = out
        self.prompts = []

    async def ainvoke(self, prompt):
        self.prompts.append(prompt)
        return _FakeMsg(self._out)


def test_planeja_ate_tres_consultas_com_mini_e_injeta_data():
    llm = _FakeLLM(
        '{"queries": ["FIIs DY 12 meses 2026", "FIIs liquidez 2026", "FIIs vacância 2026", "extra"]}'
    )
    queries = asyncio.run(
        plan_speculative_web_queries(
            "Persona: especialista... liste os melhores FIIs mensais",
            model=llm,
            today=dt.date(2026, 7, 8),
        )
    )
    assert queries == [
        "FIIs DY 12 meses 2026",
        "FIIs liquidez 2026",
        "FIIs vacância 2026",
    ]
    assert "2026-07-08" in llm.prompts[0]
    assert "NÃO a reescreva/parafraseie" in llm.prompts[0]


def test_planejador_remove_duplicatas_e_respeita_teto_configuravel():
    llm = _FakeLLM('{"queries": ["A", "A", "B"]}')
    queries = asyncio.run(
        plan_speculative_web_queries("pergunta", model=llm, max_queries=1)
    )
    assert queries == ["A"]


def test_planejador_nao_dispara_busca_especulativa_se_minimo_falhar():
    queries = asyncio.run(
        plan_speculative_web_queries("qual a capital X", model=_FakeLLM(""))
    )
    assert queries == []


def test_planejador_inclui_doc_hint_no_prompt():
    llm = _FakeLLM('{"queries": ["consulta"]}')
    asyncio.run(
        plan_speculative_web_queries(
            "pergunta", doc_hint="Processo sobre Oi S.A.", model=llm
        )
    )
    assert "Oi S.A." in llm.prompts[0]


def test_build_doc_hint_junta_previews():
    class _Meta:
        documentos = {
            "1": {"preview": "Alpha " * 200},
            "2": {"preview": "Beta"},
            "3": {"preview": ""},
        }

    class _Res:
        meta = _Meta()

    hint = build_doc_hint(_Res(), per_doc=50)
    assert "Alpha" in hint and "Beta" in hint
    assert len(hint) < 200  # truncado por per_doc


def test_build_doc_hint_vazio_sem_docs():
    class _Res:
        meta = None

    assert build_doc_hint(_Res()) == ""


import pytest  # noqa: E402


@pytest.mark.parametrize(
    "complexity,marca",
    [
        ("easy", "Profundidade da busca: BAIXA"),
        ("high", "Profundidade da busca: ALTA"),
    ],
)
def test_compose_prompt_web_inclui_profundidade_por_complexidade(complexity, marca):
    from sei_ia.agents.session_agent.agent import compose_system_prompt

    p = compose_system_prompt(
        use_websearch=True, web_tool="web_research", complexity=complexity
    )
    assert marca in p
    assert "web_research_search" in p  # a diretiva rasa continua


def test_web_max_calls_por_complexidade(tmp_path, monkeypatch):
    from sei_ia.agents.session_agent import agent as agent_mod
    from sei_ia.agents.websearch import web_research_agent as wr_mod
    from sei_ia.configs.settings_config import settings

    monkeypatch.setattr(settings, "SESSION_WEB_TOOL", "web_research")
    captured = {}
    real = wr_mod.WebResearchAgent

    def spy(**kw):
        captured.update(kw)
        return real(**kw)

    # o import em build_session_agent é lazy -> patchar o módulo de origem.
    monkeypatch.setattr(wr_mod, "WebResearchAgent", spy)
    agent_mod.build_session_agent(
        tmp_path / "w", checkpointer=None, use_websearch=True, complexity="easy"
    )
    assert captured["max_calls"] == 2  # easy -> 2 buscas
    assert captured["max_pages"] == 5  # easy -> 5 paginas
