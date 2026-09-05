"""Testes do WebResearchAgent (fase 8: tool web rasa com truncar-e-armazenar)."""

from __future__ import annotations

import asyncio

import pytest

from sei_ia.agents.session_agent.web_evidence_gate import EvidenceGateVerdict
from sei_ia.agents.websearch.searx_crawl_tool import SearxCrawlAgent
from sei_ia.agents.websearch.web_research_agent import (
    WebResearchAgent,
    _slugify,
    _strip_base64_images,
    _truncate_with_footer,
)


def _agent(tmp_path, **kw) -> WebResearchAgent:
    defaults = {
        "searx_base_url": "http://searx.invalid",
        "fastcrw_base_url": "http://fastcrw.invalid",
        "byparr_base_url": None,
        "session_root": str(tmp_path),
    }
    defaults.update(kw)
    return WebResearchAgent(
        **defaults,
    )


# ---------------------------------------------------------------------------
# Funções puras
# ---------------------------------------------------------------------------


def test_slugify_normaliza_e_limita():
    assert (
        _slugify("Top 10 FIIs — Ranking Atualizado!")
        == "top-10-fiis-ranking-atualizado"
    )
    assert len(_slugify("x" * 200)) <= 48
    assert _slugify("///") == "pagina"


def test_strip_base64_images_vira_placeholder():
    md = "antes ![grafico](data:image/png;base64,AAAA) depois"
    assert _strip_base64_images(md) == "antes [IMAGE: grafico] depois"


def test_truncate_curto_so_anexa_ponteiro():
    out = _truncate_with_footer("conteudo curto", "web/x.md", budget=100)
    assert out.startswith("conteudo curto")
    assert "web/x.md" in out


def test_truncate_longo_head_tail_e_ponteiro():
    lines = [f"linha {i:04d}" for i in range(400)]
    content = "\n".join(lines)
    out = _truncate_with_footer(content, "web/pagina-abc.md", budget=1000)
    assert len(out) < len(content)
    assert out.startswith("linha 0000")  # head preservado
    assert out.rstrip().endswith("linha 0399")  # tail preservado
    assert "caracteres omitidos" in out
    assert "read_file('web/pagina-abc.md'" in out  # ponteiro pro miolo


# ---------------------------------------------------------------------------
# Persistência determinística
# ---------------------------------------------------------------------------


def test_store_page_grava_em_web_com_nome_estavel(tmp_path):
    agent = _agent(tmp_path)
    rel1 = agent._store_page("https://ex.com/a", "Título A", "corpo")
    rel2 = agent._store_page("https://ex.com/a", "Título A", "corpo v2")
    assert rel1 == rel2  # mesmo URL -> mesmo arquivo (sobrescreve, não duplica)
    assert rel1.startswith("web/") and rel1.endswith(".md")
    saved = (tmp_path / rel1).read_text(encoding="utf-8")
    assert "corpo v2" in saved and "https://ex.com/a" in saved


# ---------------------------------------------------------------------------
# Seleção determinística de URLs
# ---------------------------------------------------------------------------


def test_select_urls_dedup_dominio_e_max_pages(tmp_path):
    agent = _agent(tmp_path, max_pages=3)
    results = [
        {"url": f"https://mesmo.com/p{i}", "title": f"p{i}"} for i in range(5)
    ] + [{"url": "https://outro.com/x", "title": "x"}]
    sel = agent._select_urls(results)
    assert len(sel) == 3
    mesmos = [r for r in sel if "mesmo.com" in r["url"]]
    assert len(mesmos) == 2  # cap de 2 por domínio
    assert any("outro.com" in r["url"] for r in sel)


# ---------------------------------------------------------------------------
# Fluxo _arun (sem rede: _search_searx/_fetch_page monkeypatched)
# ---------------------------------------------------------------------------


def test_arun_salva_paginas_e_devolve_janela_com_ponteiro(tmp_path, monkeypatch):
    agent = _agent(tmp_path, max_pages=2, window_chars=300)

    async def fake_search(query):
        return [
            {"url": "https://a.com/1", "title": "Página A", "snippet": "resumo A"},
            {"url": "https://b.com/2", "title": "Página B", "snippet": "resumo B"},
        ]

    async def fake_fetch(url, title, min_len):
        return {"url": url, "title": title, "content": f"CONTEUDO de {url}\n" * 40}

    monkeypatch.setattr(agent, "_search_searx", fake_search)
    monkeypatch.setattr(agent, "_fetch_page", fake_fetch)

    out = asyncio.run(agent._arun("query de teste"))
    assert len(out) == 1
    content = out[0]["content"]
    assert "2 páginas crawleadas" in content
    assert "read_file('web/" in content  # ponteiro
    assert len(out[0]["references"]) == 2
    saved = list((tmp_path / "web").glob("*.md"))
    assert len(saved) == 2  # persistência por código


def test_arun_limita_concorrencia_global_e_por_dominio(tmp_path, monkeypatch):
    agent = _agent(tmp_path, max_pages=12, crawl_concurrency=6)
    active = 0
    peak = 0
    active_by_domain: dict[str, int] = {}
    peak_by_domain: dict[str, int] = {}

    async def fake_search(query):
        return [
            {
                "url": f"https://dominio-{i // 2}.com/p{i}",
                "title": f"Página {i}",
                "snippet": "resumo",
            }
            for i in range(12)
        ]

    async def fake_fetch(url, title, min_len):
        nonlocal active, peak
        domain = url.split("/")[2]
        active += 1
        active_by_domain[domain] = active_by_domain.get(domain, 0) + 1
        peak = max(peak, active)
        peak_by_domain[domain] = max(
            peak_by_domain.get(domain, 0), active_by_domain[domain]
        )
        await asyncio.sleep(0.02)
        active -= 1
        active_by_domain[domain] -= 1
        return {"url": url, "title": title, "content": "conteúdo útil " * 30}

    monkeypatch.setattr(agent, "_search_searx", fake_search)
    monkeypatch.setattr(agent, "_fetch_page", fake_fetch)

    asyncio.run(agent._arun("query concorrente"))

    assert peak <= 6
    assert max(peak_by_domain.values()) == 1


def test_byparr_tem_limite_de_concorrencia_proprio(tmp_path, monkeypatch):
    agent = _agent(tmp_path, byparr_base_url="http://byparr.invalid")
    active = 0
    peak = 0

    async def fake_parent_byparr(self, url, title, min_content_len):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1

    monkeypatch.setattr(SearxCrawlAgent, "_fetch_page_byparr", fake_parent_byparr)

    async def scenario():
        await asyncio.gather(
            *(
                agent._fetch_page_byparr(f"https://exemplo.com/{i}", "", 0)
                for i in range(8)
            )
        )

    asyncio.run(scenario())
    assert peak <= 2


def test_arun_busca_vazia_pede_refino(tmp_path, monkeypatch):
    agent = _agent(tmp_path)

    async def fake_search(query):
        return []

    monkeypatch.setattr(agent, "_search_searx", fake_search)
    out = asyncio.run(agent._arun("query sem resultado"))
    assert "não retornou resultados" in out[0]["content"]
    assert out[0]["references"] == []


def test_arun_sem_paginas_orienta_sintese_sem_repetir_busca(tmp_path, monkeypatch):
    agent = _agent(tmp_path)

    async def fake_search(query):
        return [{"url": "https://a.com/1", "title": "A", "snippet": "dado"}]

    async def fake_fetch(url, title, min_len):
        return None

    monkeypatch.setattr(agent, "_search_searx", fake_search)
    monkeypatch.setattr(agent, "_fetch_page", fake_fetch)

    out = asyncio.run(agent._arun("query bloqueada"))
    content = out[0]["content"].lower()
    assert "sintetize" in content
    assert "chame novamente" not in content


def test_arun_zero_llm_interno(tmp_path):
    # A tool rasa não pode depender de LLM: constrói e opera com llm=None.
    agent = _agent(tmp_path)
    assert (
        agent.llm is None and agent.compress_llm is None and agent.extract_llm is None
    )


# ---------------------------------------------------------------------------
# Wiring no build_session_agent (construção offline)
# ---------------------------------------------------------------------------


def test_build_session_agent_com_web_research_constroi(tmp_path, monkeypatch):
    from sei_ia.agents.session_agent.agent import build_session_agent
    from sei_ia.configs.settings_config import settings

    monkeypatch.setattr(settings, "SESSION_WEB_TOOL", "web_research")
    agent = build_session_agent(tmp_path / "w", checkpointer=None, use_websearch=True)
    assert agent is not None


@pytest.mark.parametrize(
    "tool,esperado",
    [
        ("web_research", "web_research_search"),
        ("deep_research", "deep_research_search"),
    ],
)
def test_compose_system_prompt_escolhe_diretiva(tool, esperado):
    from sei_ia.agents.session_agent.agent import compose_system_prompt

    prompt = compose_system_prompt(use_websearch=True, web_tool=tool)
    assert esperado in prompt


def test_arun_orcamento_duro_de_chamadas(tmp_path, monkeypatch):
    # Após max_calls chamadas, a tool RECUSA e instrui a síntese (corta runaway).
    agent = _agent(tmp_path, max_calls=2)

    async def fake_search(query):
        return [{"url": "https://a.com/1", "title": "A", "snippet": "s"}]

    async def fake_fetch(url, title, min_len):
        return {"url": url, "title": title, "content": "x" * 500}

    monkeypatch.setattr(agent, "_search_searx", fake_search)
    monkeypatch.setattr(agent, "_fetch_page", fake_fetch)

    asyncio.run(agent._arun("q1"))
    asyncio.run(agent._arun("q2"))
    out = asyncio.run(agent._arun("q3"))  # 3a chamada: estourou o orçamento
    assert "ORÇAMENTO DE BUSCAS ESGOTADO" in out[0]["content"]
    assert out[0]["references"] == []


def test_arun_fetch_direto_por_url(tmp_path, monkeypatch):
    # Query com URLs explicitas baixa direto (sem SearXNG, sem cap de dominio).
    agent = _agent(tmp_path, max_pages=5)
    searched = []

    async def fake_search(query):
        searched.append(query)
        return []

    async def fake_fetch(url, title, min_len):
        return {"url": url, "title": f"pg {url[-1]}", "content": "conteudo util " * 30}

    monkeypatch.setattr(agent, "_search_searx", fake_search)
    monkeypatch.setattr(agent, "_fetch_page", fake_fetch)

    out = asyncio.run(
        agent._arun(
            "https://ex.com/fundos/a1 https://ex.com/fundos/a2 https://ex.com/fundos/a3"
        )
    )
    assert searched == []  # NAO passou pelo SearXNG
    assert (
        len(out[0]["references"]) == 3
    )  # 3 do MESMO dominio (sem cap p/ URL explicita)
    assert "3 páginas crawleadas" in out[0]["content"]


def test_start_speculative_e_harvest_na_primeira_chamada(tmp_path, monkeypatch):
    # start_speculative dispara o lote; a 1a _arun COLHE (nao busca de novo).
    agent = _agent(tmp_path, max_pages=2)
    calls = []

    async def fake_search(query):
        calls.append(query)
        return [{"url": f"https://a.com/{len(calls)}", "title": "A", "snippet": "s"}]

    async def fake_fetch(url, title, min_len):
        return {"url": url, "title": title, "content": "conteudo " * 40}

    monkeypatch.setattr(agent, "_search_searx", fake_search)
    monkeypatch.setattr(agent, "_fetch_page", fake_fetch)

    async def scenario():
        agent.start_speculative(["ponto A", "ponto B", "ponto C"])
        # 1a chamada: colhe o lote especulativo (a query do agente e ignorada)
        out1 = await agent._arun("query DIFERENTE do agente")
        # 2a chamada: busca normal
        out2 = await agent._arun("refino")
        return out1, out2

    out1, out2 = asyncio.run(scenario())
    assert set(calls[:3]) == {"ponto A", "ponto B", "ponto C"}
    assert calls[3:] == ["refino"]
    assert {item["query"] for item in out1} == {"ponto A", "ponto B", "ponto C"}
    assert agent._calls_made == 4  # lote especulativo + refino


def test_gate_nano_limita_pos_busca_a_uma_query_dirigida(tmp_path, monkeypatch):
    agent = _agent(
        tmp_path,
        max_pages=1,
        max_calls=6,
        evidence_gate_enabled=True,
        evidence_gate_model=object(),
        evidence_gate_question="pergunta original",
    )

    async def fake_search(query):
        return [{"url": f"https://fonte.test/{query}", "title": query, "snippet": "s"}]

    async def fake_fetch(url, title, min_len):
        return {"url": url, "title": title, "content": "evidência " * 100}

    async def fake_gate(question, batches, **kwargs):
        assert question == "pergunta original"
        assert batches
        return EvidenceGateVerdict(
            ledger=(),
            gaps=({"entity": "X", "criterion": "Y", "reason": "falta"},),
            next_query="X Y fonte",
        )

    monkeypatch.setattr(agent, "_search_searx", fake_search)
    monkeypatch.setattr(agent, "_fetch_page", fake_fetch)
    monkeypatch.setattr(
        "sei_ia.agents.websearch.web_research_agent.assess_web_evidence", fake_gate
    )

    async def scenario():
        agent.start_speculative(["ponto A", "ponto B", "ponto C"])
        return await agent._arun("query ignorada")

    out = asyncio.run(scenario())

    assert "MATRIZ DE EVIDÊNCIAS" in out[0]["content"]
    assert agent.max_calls == 4  # 3 especulativas + uma dirigida


def test_harvest_falha_cai_para_busca_normal(tmp_path, monkeypatch):
    agent = _agent(tmp_path)
    n = {"c": 0}

    async def flaky(query):
        n["c"] += 1
        if n["c"] == 1:
            raise RuntimeError("spec boom")  # especulativa quebra
        return []  # fallback: busca normal sem resultados (como o searx real)

    monkeypatch.setattr(agent, "_search_searx", flaky)

    async def scenario():
        agent.start_speculative(["q"])  # precisa de loop rodando (como no build async)
        # especulativa levanta -> harvest captura -> cai pro fluxo normal, que
        # retorna dict de "sem resultados" (nao propaga excecao).
        return await agent._arun("pergunta")

    out = asyncio.run(scenario())
    assert isinstance(out, list) and "não retornou resultados" in out[0]["content"]
