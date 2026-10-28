"""Testes puros dos cálculos e artefatos do benchmark comparativo."""

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

_EXP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "experimentos",
    "latencia-session-vs-classico",
)
sys.path.insert(0, os.path.join(_EXP_DIR, "scripts", "shared"))
sys.path.insert(0, os.path.join(_EXP_DIR, "scripts", "session-classico"))

from benchmark_reporting import (  # noqa: E402
    _cache_share,
    _pair_metric,
    cited_urls,
    cost_for_tokens,
    endpoint_records,
    load_rate_card,
    write_artifacts,
)


def _rate_card() -> dict:
    return {
        "version": "test",
        "effective_on": "2026-07-13",
        "source": "test",
        "usd_to_brl": "5",
        "models": {
            "seiia-ds": {
                "input_per_million_usd": "1",
                "cache_read_per_million_usd": "0.1",
                "output_per_million_usd": "2",
            }
        },
    }


def test_cost_counts_input_cache_and_output_once():
    result = cost_for_tokens(
        {
            "seiia-ds": {
                "input": 1_000_000,
                "cache_read": 1_000_000,
                "output": 1_000_000,
                "reasoning": 900_000,
            }
        },
        _rate_card(),
    )

    assert result == {"usd": 3.1, "brl": 15.5, "missing_models": [], "available": True}


def test_cost_is_unavailable_when_any_model_has_no_price():
    result = cost_for_tokens({"unknown": {"input": 1}}, _rate_card())

    assert result["available"] is False
    assert result["usd"] is None and result["brl"] is None
    assert result["missing_models"] == ["unknown"]


def test_cost_keeps_usd_when_brl_exchange_is_missing():
    rate_card = _rate_card()
    rate_card["usd_to_brl"] = None
    result = cost_for_tokens(
        {
            "seiia-ds": {
                "input": 1_000_000,
                "cache_read": 1_000_000,
                "output": 1_000_000,
            }
        },
        rate_card,
    )

    assert result["usd"] == 3.1
    assert result["brl"] is None
    assert result["available"] is False


def test_luna_rate_card_prices_input_cache_and_output():
    rate_card_path = os.path.join(_EXP_DIR, "rate_cards", "v2.json")
    rate_card = load_rate_card(rate_card_path)

    result = cost_for_tokens(
        {
            "seiia-ds-gpt-luna": {
                "input": 1_000_000,
                "cache_read": 1_000_000,
                "output": 1_000_000,
                "reasoning": 900_000,
            }
        },
        rate_card,
    )

    assert result == {
        "usd": 7.1,
        "brl": None,
        "missing_models": [],
        "available": False,
    }


def test_campaign_cost_does_not_bill_reasoning_twice():
    rate_card = load_rate_card(
        os.path.join(_EXP_DIR, "rate_cards", "gpt56-session-v1.json")
    )

    result = cost_for_tokens(
        {
            "seiia-ds-gpt-terra": {
                "input": 0,
                "cache_read": 0,
                "cache_write": 0,
                "output": 10,
                "reasoning": 4,
            }
        },
        rate_card,
    )

    assert result["usd"] == 0.00015


def test_successor_card_prices_terra_and_luna_with_new_standard_rates():
    rate_card = load_rate_card(
        os.path.join(_EXP_DIR, "rate_cards", "gpt56-session-v2.json")
    )

    result = cost_for_tokens(
        {
            deployment: {
                "input": 1_000_000,
                "cache_read": 1_000_000,
                "cache_write": 0,
                "output": 1_000_000,
            }
            for deployment in ("seiia-ds-gpt-terra", "seiia-ds-gpt-luna")
        },
        rate_card,
    )

    assert result["usd"] == 24.64
    assert result["brl"] is None


def test_gpt54_observed_cache_write_is_kept_when_official_rate_is_absent():
    rate_card = load_rate_card(
        os.path.join(_EXP_DIR, "rate_cards", "benchmark-redesign-v1.json")
    )

    result = cost_for_tokens(
        {
            "seiia-ds": {
                "input": 100,
                "cache_read": 20,
                "cache_write": 80,
                "output": 10,
                "reasoning": 2,
            }
        },
        rate_card,
    )

    assert result["available"] is False
    assert result["missing_usage"] == []
    assert result["missing_rate"] == ["cache_write"]
    assert result["known_subtotal_excluding_cache_write_usd"] == {
        "short_context": 0.000405,
        "long_context": 0.000735,
    }


def test_endpoint_records_inclui_usage_do_judge_no_modelo_e_escopo():
    records = endpoint_records(
        [
            {
                "qid": "Q1",
                "endpoints": {
                    "session": {
                        "trace_id": "trace-1",
                        "latency": {},
                        "judge": {
                            "numeric": {"overall": 1.0},
                            "usage": {
                                "role": "judge",
                                "deployment": "seiia-ds-gpt-luna",
                                "input": 40,
                                "cache_read": 40,
                                "cache_write": 60,
                                "output": 20,
                                "reasoning": 5,
                                "total": 120,
                                "generations": 1,
                            },
                        },
                        "metrics": {
                            "tokens_by_model": {
                                "seiia-ds-gpt-terra": {
                                    "input": 10,
                                    "cache_read": 0,
                                    "cache_write": 100,
                                    "output": 5,
                                    "reasoning": 0,
                                    "total": 115,
                                    "generations": 1,
                                }
                            },
                            "tokens_by_scope": {},
                        },
                    }
                },
            }
        ],
        load_rate_card(
            os.path.join(_EXP_DIR, "rate_cards", "benchmark-redesign-v1.json")
        ),
    )

    assert records[0]["tokens_by_model"]["seiia-ds-gpt-luna"]["cache_write"] == 60
    assert records[0]["tokens_by_scope"]["judge"]["cache_read"] == 40


def test_cited_urls_reads_html_and_raw_urls_once():
    urls = cited_urls(
        'Veja <a href="https://a.example">A</a> e https://b.example/. https://a.example'
    )

    assert urls == ["https://a.example", "https://b.example/"]


def test_pair_metric_bolds_winner_in_correct_direction():
    assert _pair_metric(0.88, 0.93, higher_is_better=True) == "0.88 / **0.93**"
    assert _pair_metric(10, 20, higher_is_better=False) == "**10.00** / 20.00"
    assert _pair_metric(1, 1, higher_is_better=True) == "1.00 / 1.00"


def test_cache_share_uses_input_plus_cache_as_denominator():
    record = {"tokens_by_model": {"seiia-ds": {"input": 1000, "cache_read": 3000}}}

    assert _cache_share(record) == 75.0


def test_write_artifacts_renders_missing_money_as_nd(tmp_path):
    rate_path = tmp_path / "rate.json"
    rate_path.write_text(json.dumps(_rate_card()), encoding="utf-8")
    results = [
        {
            "qid": "WEB-FII-01",
            "case": {"processo": None, "requires_web": True, "size_class": "web"},
            "endpoints": {
                "session": {
                    "trace_id": "t1",
                    "latency": {"ttfc_s": 1.0, "total_s": 2.0},
                    "judge": {
                        "numeric": {
                            "overall": 0.8,
                            "groundedness": 0.8,
                            "completeness": 0.8,
                            "citation_quality": 0.8,
                        },
                        "bool": {"hallucination": False},
                    },
                    "metrics": {"tokens_by_model": {"unknown": {"input": 10}}},
                    "tool_metrics": {"total_calls": 1},
                    "cited_urls": ["https://source.example"],
                }
            },
        }
    ]

    paths = write_artifacts(
        tmp_path / "artifacts",
        {"run_name": "test", "dataset": "test"},
        results,
        rate_path,
    )

    assert all(path.exists() for path in paths.values())
    report = paths["report"].read_text(encoding="utf-8")
    assert "N/D" in report
    assert "Comparação caso a caso" in report
    assert "Overall (session/clássico)" in report
    assert "Resumo executivo" in report
    assert "Leitura caso a caso" in report
    assert "Leitura para decisão" in report
    assert "Como interpretar os scores" in report
    assert "Groundedness (G)" in report
    assert "Tokens e custo por chamada" in report
    assert "Custo USD total (session/clássico)" in report
    assert "Cache (k; cache/(input+cache) %, session/clássico)" in report
    assert "| total |" in report
    assert "Dif. custo %" in report
    assert "Tokens por modelo e pergunta" in report
    assert "Perguntas e respostas" in report
    assert "<details>" in report
    assert "não inclui registros do clássico" in report
    assert "0.93 contra 0.88" not in report


def test_write_artifacts_rejects_results_pinned_to_old_rate_card(tmp_path):
    old_path = os.path.join(_EXP_DIR, "rate_cards", "gpt56-session-v1.json")
    new_path = os.path.join(_EXP_DIR, "rate_cards", "gpt56-session-v2.json")
    old_card = load_rate_card(old_path)
    old_reference = {
        "version": old_card["version"],
        "effective_on": old_card["effective_on"],
        "aggregation_compatibility_key": old_card.get("aggregation_compatibility_key"),
        "sha256": hashlib.sha256(Path(old_path).read_bytes()).hexdigest(),
    }

    with pytest.raises(ValueError, match="rate card incompatível"):
        write_artifacts(
            tmp_path / "artifacts",
            {"model_campaign": {"rate_card": old_reference}},
            [],
            new_path,
        )


def test_write_artifacts_persists_response_for_both_endpoints(tmp_path):
    rate_path = tmp_path / "rate.json"
    rate_path.write_text(json.dumps(_rate_card()), encoding="utf-8")
    results = [
        {
            "qid": "Q17",
            "question": "Qual foi a mudança?",
            "case": {"processo": "x", "size_class": "small"},
            "endpoints": {
                "session": {
                    "trace_id": "session-trace",
                    "response": "Resposta do session",
                    "latency": {"ttfc_s": 1, "total_s": 2},
                    "judge": None,
                    "metrics": {"tokens_by_model": {"seiia-ds": {"input": 1}}},
                },
                "classic": {
                    "trace_id": "classic-trace",
                    "response": "Resposta do clássico",
                    "latency": {"ttfc_s": 1, "total_s": 2},
                    "judge": None,
                    "metrics": {"tokens_by_model": {"seiia-ds": {"input": 1}}},
                },
            },
        }
    ]

    paths = write_artifacts(
        tmp_path / "artifacts",
        {"run_name": "test", "dataset": "test"},
        results,
        rate_path,
    )

    measurements = paths["measurements"].read_text(encoding="utf-8")
    assert measurements.count('"response": "Resposta do') == 2
    report = paths["report"].read_text(encoding="utf-8")
    assert "Resposta do clássico" in report
