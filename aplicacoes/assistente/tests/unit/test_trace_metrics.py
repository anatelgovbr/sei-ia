"""Unit test puro do analisador de trace do experimento (sem rede).

Alimenta `compute_session_metrics` com observations sinteticas cobrindo os tres
casos de classificacao — principal, subagente (explorador) e web (deep_research) —
e verifica o agrupamento em etapas, a particao nao-sobreposta do tempo e os tokens
por componente. O modulo mora em `experimentos/`, fora do pacote `sei_ia`; inserimos
o dir no path para importar sem instalar.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

_EXP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "experimentos",
    "latencia-session-vs-classico",
)
sys.path.insert(0, os.path.join(_EXP_DIR, "scripts", "shared"))

from trace_metrics import (  # noqa: E402
    Obs,
    aggregate_tokens_by_model,
    compute_session_metrics,
    normalize,
    normalize_model_id,
)


def _obs(id_, type_, name, parent, start, end, ns="", model=None, usage=None):
    return Obs(
        id=id_,
        type=type_,
        name=name,
        parent_id=parent,
        start=start,
        end=end,
        ns=ns,
        model=model,
        usage=usage or {},
    )


def _build_tree():
    """Arvore sintetica: setup (gap) + agent com principal, 1 explorador e 1 web."""
    return [
        # gap de setup: o primeiro obs comeca em t=0, o session_agent so em t=10
        _obs("run", "SPAN", "Dataset run: x", None, 0.0, 40.0),
        _obs("root", "SPAN", "session_agent", "run", 10.0, 38.0),
        _obs("lg", "SPAN", "LangGraph", "root", 10.0, 38.0),
        # turno 1 do principal (model span + generation)
        _obs("m1", "SPAN", "model", "lg", 10.0, 15.0, ns="model:aaa"),
        _obs(
            "g1",
            "GENERATION",
            "ChatOpenAI",
            "m1",
            10.1,
            14.9,
            ns="model:aaa",
            model="seiia-ds",
            usage={"input": 1000, "output": 50, "total": 1050},
        ),
        # tool de filesystem do principal
        _obs("t1", "SPAN", "read_file", "lg", 15.0, 15.2, ns="tools:bbb"),
        # explorador (subagente) via task; sua generation tem ns com 2 segmentos
        _obs("task1", "SPAN", "task", "lg", 15.2, 22.0, ns="tools:ccc"),
        _obs(
            "gsub",
            "GENERATION",
            "ChatOpenAI",
            "task1",
            15.3,
            21.9,
            ns="tools:ccc|model:ddd",
            model="seiia-ds-nano",
            usage={"input": 4000, "output": 200, "total": 4200},
        ),
        # web: deep_research tool com generations internas (principal + extract)
        _obs("web1", "SPAN", "deep_research", "lg", 22.0, 30.0, ns="tools:eee"),
        _obs(
            "gweb1",
            "GENERATION",
            "ChatOpenAI",
            "web1",
            22.1,
            27.0,
            ns="",
            model="seiia-ds",
            usage={"input": 3000, "output": 300, "total": 3300},
        ),
        _obs(
            "gweb2",
            "GENERATION",
            "ChatOpenAI",
            "web1",
            27.0,
            29.5,
            ns="",
            model="seiia-ds-mini",
            usage={"input": 800, "output": 100, "total": 900},
        ),
        # turno final do principal (sintese)
        _obs("m2", "SPAN", "model", "lg", 30.0, 37.0, ns="model:fff"),
        _obs(
            "g2",
            "GENERATION",
            "ChatOpenAI",
            "m2",
            30.1,
            36.9,
            ns="model:fff",
            model="seiia-ds",
            usage={"input": 6000, "output": 400, "total": 6400},
        ),
    ]


def test_returns_none_without_root():
    obs = [_obs("x", "SPAN", "LangGraph", None, 0.0, 1.0)]
    assert compute_session_metrics(obs) is None


def test_stage_partition_covers_total():
    m = compute_session_metrics(_build_tree())
    st = m["stage_timings"]
    # setup = 10 (root.start - t_start=0); agent = 28 (38-10); post = 2 (40-38)
    assert st["pre_agent_s"] == 10.0
    assert st["agent_s"] == 28.0
    assert st["post_agent_s"] == 2.0
    soma = st["pre_agent_s"] + st["agent_s"] + st["post_agent_s"]
    assert abs(soma - st["span_total_s"]) < 1e-6  # particao cobre o total


def test_component_timings():
    st = compute_session_metrics(_build_tree())["stage_timings"]
    # principal_llm = dur(g1)+dur(g2) = 4.8 + 6.8 = 11.6 (web/sub excluidos)
    assert abs(st["principal_llm_s"] - 11.6) < 1e-6
    assert abs(st["subagent_s"] - 6.8) < 1e-6  # dur do span task
    assert abs(st["tools_fs_s"] - 0.2) < 1e-6  # read_file
    assert abs(st["web_search_s"] - 8.0) < 1e-6  # dur do span deep_research


def test_turns_count():
    m = compute_session_metrics(_build_tree())
    assert m["turns"]["principal_turns"] == 2
    assert m["turns"]["subagents"] == 1


def test_tokens_by_component():
    m = compute_session_metrics(_build_tree())
    tok = m["tokens"]
    # principal: g1 + g2
    assert tok["principal"] == {
        "input": 7000,
        "output": 450,
        "total": 7450,
        "generations": 2,
    }
    # subagente: gsub (ns 2 segmentos)
    assert tok["subagent"] == {
        "input": 4000,
        "output": 200,
        "total": 4200,
        "generations": 1,
    }
    # web: gweb1 + gweb2 (ancestral deep_research)
    assert tok["web"] == {"input": 3800, "output": 400, "total": 4200, "generations": 2}
    # split por modelo dentro do web
    assert set(m["tokens_web_by_model"]) == {"seiia-ds", "seiia-ds-mini"}


# --- agregador de tokens por modelo (fase 3) ----------------------------------


def test_normalize_model_id_alias_e_none(monkeypatch):
    monkeypatch.setenv("LITELLM_STANDARD_MODEL", "hostil-standard")
    monkeypatch.setenv("LITELLM_MINI_MODEL", "hostil-mini")
    assert normalize_model_id("standard") == "seiia-ds"
    assert normalize_model_id("mini") == "seiia-ds-mini"
    assert normalize_model_id("nano") == "seiia-ds-nano"
    assert (
        normalize_model_id(
            "standard",
            {"standard": "seiia-ds-gpt-terra", "mini": "seiia-ds-gpt-luna"},
        )
        == "seiia-ds-gpt-terra"
    )
    # id ja real passa direto (nao re-mapeia)
    assert normalize_model_id("seiia-ds-nano") == "seiia-ds-nano"
    # modelo ausente cai no balde '?'
    assert normalize_model_id(None) == "?"
    assert normalize_model_id("") == "?"


def test_tokens_by_model_agrega_trace_inteiro():
    """Soma TODAS as GENERATIONs do trace por modelo, sem depender do root."""
    tbm = aggregate_tokens_by_model(_build_tree())
    assert set(tbm) == {"seiia-ds", "seiia-ds-nano", "seiia-ds-mini"}
    # seiia-ds = g1 + gweb1 + g2 (principal + web + sintese), independente do componente
    assert tbm["seiia-ds"]["input"] == 10000
    assert tbm["seiia-ds"]["output"] == 750
    assert tbm["seiia-ds"]["total"] == 10750
    assert tbm["seiia-ds"]["generations"] == 3
    # subagente (nano) contabilizado — ignora-lo subestimaria o modo filesystem
    assert tbm["seiia-ds-nano"] == {
        "input": 4000,
        "cache_read": 0,
        "cache_write": None,
        "output": 200,
        "reasoning": 0,
        "total": 4200,
        "generations": 1,
    }
    assert tbm["seiia-ds-mini"]["input"] == 800


def test_tokens_by_model_split_cache_read_e_reasoning():
    """usage_details com cache_read/reasoning: campos contabilizados SEPARADOS do total."""
    obs = [
        _obs(
            "g",
            "GENERATION",
            "ChatOpenAI",
            None,
            0.0,
            1.0,
            model="standard",  # alias -> normaliza para seiia-ds
            usage={
                "input": 248,
                "input_cache_read": 31232,
                "output": 835,
                "output_reasoning": 512,
                "total": 32315,  # inflado por cache_read; nunca usado sozinho
            },
        ),
    ]
    b = aggregate_tokens_by_model(obs)["seiia-ds"]
    assert b["input"] == 248  # fresco, sem o cache
    assert b["cache_read"] == 31232
    assert b["output"] == 835
    assert b["reasoning"] == 512
    assert b["total"] == 32315
    assert b["generations"] == 1


def test_tokens_by_model_preserva_cache_write_observado():
    obs = [
        _obs(
            "g",
            "GENERATION",
            "ChatOpenAI",
            None,
            0.0,
            1.0,
            model="standard",
            usage={
                "input": 248,
                "input_cache_read": 31_232,
                "input_cache_write": 30_976,
                "output": 835,
                "output_reasoning": 512,
                "total": 63_803,
            },
        ),
    ]

    bucket = aggregate_tokens_by_model(obs)["seiia-ds"]

    assert bucket["cache_write"] == 30_976


def test_tokens_by_model_canonicaliza_cache_creation_do_langchain():
    obs = [
        _obs(
            "g",
            "GENERATION",
            "ChatOpenAI",
            None,
            0.0,
            1.0,
            model="standard",
            usage={
                "input": 1024,
                "input_cache_creation": 3072,
                "input_cache_read": 0,
                "output": 8,
                "total": 4104,
            },
        ),
    ]

    bucket = aggregate_tokens_by_model(obs)["seiia-ds"]

    assert bucket["cache_write"] == 3072


def test_normalize_uses_dict_usage_when_usage_details_is_null():
    sdk_observation = SimpleNamespace(
        id="generation-1",
        type="GENERATION",
        name="ChatOpenAI",
        parent_observation_id=None,
        start_time=0.0,
        end_time=1.0,
        metadata={},
        model="seiia-ds-gpt-terra",
        usage_details=None,
        usage={"input": 123, "output": 45, "total": 168, "unit": "TOKENS"},
    )

    [observation] = normalize([sdk_observation])

    assert observation.usage == {"input": 123, "output": 45, "total": 168}


def test_tokens_by_model_usa_mapa_explicito_da_campanha():
    obs = [
        _obs(
            "g",
            "GENERATION",
            "ChatOpenAI",
            None,
            0.0,
            1.0,
            model="standard",
            usage={"input": 10, "output": 2, "total": 12},
        )
    ]

    buckets = aggregate_tokens_by_model(
        obs,
        {"standard": "seiia-ds-gpt-terra", "mini": "seiia-ds-gpt-luna"},
    )

    assert set(buckets) == {"seiia-ds-gpt-terra"}


def test_tokens_by_model_soma_alias_e_id_real_no_mesmo_balde():
    """standard e seiia-ds caem no MESMO balde (senao o modelo se divide entre traces)."""
    obs = [
        _obs(
            "a",
            "GENERATION",
            "x",
            None,
            0.0,
            1.0,
            model="standard",
            usage={"input": 100, "output": 10, "total": 110},
        ),
        _obs(
            "b",
            "GENERATION",
            "x",
            None,
            1.0,
            2.0,
            model="seiia-ds",
            usage={"input": 200, "output": 20, "total": 220},
        ),
    ]
    tbm = aggregate_tokens_by_model(obs)
    assert set(tbm) == {"seiia-ds"}
    assert tbm["seiia-ds"]["input"] == 300
    assert tbm["seiia-ds"]["generations"] == 2


def test_tokens_by_model_ignora_nao_generation_e_marca_modelo_ausente():
    obs = [
        _obs("span", "SPAN", "model", None, 0.0, 1.0),  # SPAN nao conta
        _obs(
            "g",
            "GENERATION",
            "x",
            None,
            0.0,
            1.0,
            model=None,
            usage={"input": 5, "output": 1, "total": 6},
        ),  # sem model -> '?'
    ]
    tbm = aggregate_tokens_by_model(obs)
    assert set(tbm) == {"?"}
    assert tbm["?"]["input"] == 5
