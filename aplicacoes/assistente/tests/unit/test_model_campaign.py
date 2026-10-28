"""Configuração compartilhada pelos runners de benchmark, sem rede."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

_EXP_DIR = Path(__file__).parents[2] / "experimentos" / "latencia-session-vs-classico"
sys.path.insert(0, str(_EXP_DIR / "scripts" / "shared"))

from model_campaign import (  # noqa: E402
    ModelCampaignError,
    load_model_campaign,
    plan_long_context_cells,
    plan_session_cells,
    price_usage,
    runtime_contract,
)


def _write_rate_card(path: Path, standard: str, mini: str) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "test",
                "deployments": {
                    standard: {
                        "profile": "standard",
                        "canonical_model": "model-standard",
                        "provider": "test",
                        "context_window_tokens": 1050000,
                        "capabilities": ["text"],
                    },
                    mini: {
                        "profile": "mini",
                        "canonical_model": "model-mini",
                        "provider": "test",
                        "context_window_tokens": 400000,
                        "capabilities": ["text", "image_url"],
                    },
                    "nano-a": {
                        "profile": "nano",
                        "canonical_model": "model-nano",
                        "provider": "test",
                        "context_window_tokens": 128000,
                        "capabilities": ["text"],
                    },
                },
                "model_cards": {
                    "model-standard": {
                        "default_snapshot": "model-standard",
                        "context_window_tokens": 1050000,
                    },
                    "model-mini": {
                        "default_snapshot": "model-mini",
                        "context_window_tokens": 400000,
                    },
                    "model-nano": {
                        "default_snapshot": "model-nano",
                        "context_window_tokens": 128000,
                    },
                },
                "judge_policy": {
                    "temperature_by_model": {"model-mini": 0},
                },
                "models": {
                    "model-standard": {
                        "threshold_input_tokens": 272000,
                        "short_context": {
                            "input_per_million_usd": 2.5,
                            "cache_read_per_million_usd": 0.25,
                            "cache_write_per_million_usd": 3.125,
                            "output_per_million_usd": 15,
                        },
                        "long_context": {
                            "input_per_million_usd": 5,
                            "cache_read_per_million_usd": 0.5,
                            "cache_write_per_million_usd": 6.25,
                            "output_per_million_usd": 22.5,
                        },
                    },
                    "model-mini": {
                        "input_per_million_usd": 1,
                        "cache_read_per_million_usd": 0.1,
                        "output_per_million_usd": 6,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _campaign(path: Path, standard: str, mini: str):
    return load_model_campaign(
        standard_model=standard,
        mini_model=mini,
        nano_model="nano-a",
        reasoning_effort="low",
        n=1,
        rate_card_path=path,
        reuse_historical_baseline=True,
    )


def test_aliases_are_resolved_from_configuration_without_code_change(tmp_path: Path):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    _write_rate_card(first_path, "standard-a", "mini-a")
    _write_rate_card(second_path, "standard-b", "mini-b")

    first = _campaign(first_path, "standard-a", "mini-a")
    second = _campaign(second_path, "standard-b", "mini-b")

    assert first.standard.deployment == "standard-a"
    assert second.standard.deployment == "standard-b"
    assert first.mini.deployment == "mini-a"
    assert second.mini.deployment == "mini-b"


def test_campaign_applies_configured_explorer_alias(tmp_path: Path, monkeypatch):
    rate_card = tmp_path / "rate-card.json"
    _write_rate_card(rate_card, "standard-a", "mini-a")
    campaign = load_model_campaign(
        standard_model="standard-a",
        mini_model="mini-a",
        nano_model="mini-a",
        reasoning_effort="low",
        n=1,
        rate_card_path=rate_card,
        reuse_historical_baseline=True,
    )
    monkeypatch.setenv("LITELLM_NANO_MODEL", "stale-env-alias")

    campaign.apply_environment()

    assert campaign.nano.deployment == "mini-a"
    assert os.environ["LITELLM_NANO_MODEL"] == "mini-a"
    assert os.environ["ASSISTENTE_CTX_LEN_STANDARD_MODEL"] == "1050000"
    assert os.environ["ASSISTENTE_CTX_LEN_MINI_MODEL"] == "400000"
    assert os.environ["ASSISTENTE_CTX_LEN_NANO_MODEL"] == "400000"


def test_judge_temperature_and_context_windows_come_from_rate_card(tmp_path: Path):
    rate_card = tmp_path / "rate-card.json"
    _write_rate_card(rate_card, "standard-a", "mini-a")
    campaign = _campaign(rate_card, "standard-a", "mini-a")

    assert campaign.judge_temperature == 0.0
    assert campaign.profile_context_windows == {
        "standard": 1050000,
        "mini": 400000,
        "nano": 128000,
    }


def test_isolated_stack_requires_explicit_long_context_evidence_pin():
    compose = (_EXP_DIR / "docker-compose.isolated.yml").read_text(encoding="utf-8")
    long_context_compose = (_EXP_DIR / "docker-compose.long-context.yml").read_text(
        encoding="utf-8"
    )

    assert 'ASSISTENTE_MAX_RETRIES: "0"' in compose
    assert (
        "ASSISTENTE_SEI_API_MAX_RETRIES: ${BENCHMARK_SEI_API_MAX_RETRIES:-5}" in compose
    )
    assert "ASSISTENTE_SESSION_BENCHMARK_EVIDENCE_INDEX" not in compose
    assert (
        "ASSISTENTE_SESSION_BENCHMARK_EVIDENCE_INDEX: "
        "${BENCHMARK_EVIDENCE_INDEX:?defina BENCHMARK_EVIDENCE_INDEX}"
        in long_context_compose
    )
    assert (
        "LITELLM_NANO_MODEL: "
        "${BENCHMARK_NANO_MODEL:?defina BENCHMARK_NANO_MODEL}" in compose
    )
    assert (
        "ASSISTENTE_CTX_LEN_MINI_MODEL: "
        "${BENCHMARK_MINI_CONTEXT_TOKENS:?defina BENCHMARK_MINI_CONTEXT_TOKENS}"
        in compose
    )
    assert (
        "ASSISTENTE_CTX_LEN_NANO_MODEL: "
        "${BENCHMARK_NANO_CONTEXT_TOKENS:?defina BENCHMARK_NANO_CONTEXT_TOKENS}"
        in compose
    )
    assert (
        "ASSISTENTE_OCR_MODEL: "
        "${BENCHMARK_OCR_MODEL:?defina BENCHMARK_OCR_MODEL}" in compose
    )
    assert "PROMPT_CACHE" not in compose
    assert "benchmark_assistente_frontend:" in compose
    assert "aliases:\n          - api_assistente" in compose
    assert (
        "networks: !override\n      - seiia\n      - benchmark_assistente_frontend"
        in compose
    )


def test_offline_plans_have_ten_standard_and_nine_long_context_cells(tmp_path: Path):
    rate_card = tmp_path / "rate-card.json"
    _write_rate_card(rate_card, "standard-a", "mini-a")
    campaign = _campaign(rate_card, "standard-a", "mini-a")
    session = plan_session_cells({f"Q{i:02d}" for i in range(1, 11)}, campaign)

    item_ids = {f"case-{index}" for index in range(9)}
    consumed = "case-3"
    summary_path = tmp_path / "canary.json"
    summary_path.write_text(
        json.dumps(
            {
                "status": "valid",
                "requested_models": {
                    "principal": {"alias": "standard-a"},
                    "classifier_auxiliary": {"alias": "mini-a"},
                },
                "authorization": {
                    "post_started_count": 1,
                    "inference_retries": 0,
                },
                "safety": {"second_inference": False},
                "identity": {
                    "item_id_sha256": hashlib.sha256(consumed.encode()).hexdigest()
                },
            }
        ),
        encoding="utf-8",
    )
    long_context = plan_long_context_cells(
        item_ids, campaign, reused_summary_path=summary_path
    )

    assert session["total_cells"] == session["new_session_calls"] == 10
    assert session["new_classic_calls"] == 0
    assert long_context["total_cells"] == 9
    assert long_context["consumed_cells"] == 1
    assert long_context["pending_calls"] == 8


def test_missing_cache_write_preserves_known_cost_subtotals(tmp_path: Path):
    rate_card_path = tmp_path / "rate-card.json"
    _write_rate_card(rate_card_path, "standard-a", "mini-a")
    campaign = _campaign(rate_card_path, "standard-a", "mini-a")

    result = price_usage(
        campaign.standard,
        {
            "input_uncached": 100,
            "cache_read": 20,
            "cache_write": None,
            "output": 10,
            "reasoning": 2,
        },
        campaign.rate_card,
    )

    assert result["available"] is False
    assert result["missing_usage"] == ["cache_write"]
    assert result["known_subtotal_excluding_cache_write_usd"] == {
        "if_all_requests_short_context": 0.000435,
        "if_all_requests_long_context": 0.00078,
    }


def test_flat_legacy_rate_with_missing_cache_write_has_known_subtotal(
    tmp_path: Path,
):
    rate_card_path = tmp_path / "rate-card.json"
    _write_rate_card(rate_card_path, "standard-a", "mini-a")
    raw = json.loads(rate_card_path.read_text())
    raw["models"]["model-mini"] = {
        "short_context": {
            "input_per_million_usd": 1,
            "cache_read_per_million_usd": 0.1,
            "cache_write_per_million_usd": None,
            "output_per_million_usd": 6,
        },
        "long_context": None,
    }
    rate_card_path.write_text(json.dumps(raw))
    campaign = _campaign(rate_card_path, "standard-a", "mini-a")

    result = price_usage(
        campaign.mini,
        {
            "input_uncached": 100,
            "cache_read": 20,
            "cache_write": None,
            "output": 10,
            "reasoning": 2,
        },
        campaign.rate_card,
    )

    assert result["available"] is False
    assert result["missing_usage"] == ["cache_write"]
    assert result["known_subtotal_excluding_cache_write_usd"] == {
        "if_all_requests_short_context": 0.000174,
        "if_all_requests_long_context": 0.000174,
    }


def test_observed_cache_write_with_missing_official_rate_keeps_total_unavailable(
    tmp_path: Path,
):
    rate_card_path = tmp_path / "rate-card.json"
    _write_rate_card(rate_card_path, "standard-a", "mini-a")
    raw = json.loads(rate_card_path.read_text())
    raw["models"]["model-standard"]["short_context"]["cache_write_per_million_usd"] = (
        None
    )
    raw["models"]["model-standard"]["long_context"]["cache_write_per_million_usd"] = (
        None
    )
    rate_card_path.write_text(json.dumps(raw))
    campaign = _campaign(rate_card_path, "standard-a", "mini-a")

    result = price_usage(
        campaign.standard,
        {
            "input_uncached": 100,
            "cache_read": 20,
            "cache_write": 80,
            "output": 10,
            "reasoning": 2,
        },
        campaign.rate_card,
    )

    assert result["available"] is False
    assert result["missing_rate"] == ["cache_write"]
    assert result["observed_cache_write"] == 80
    assert result["known_subtotal_excluding_cache_write_usd"] == {
        "if_all_requests_short_context": 0.000435,
        "if_all_requests_long_context": 0.00078,
    }


def test_luna_campaign_omits_long_context_judge_temperature(tmp_path: Path):
    rate_card_path = tmp_path / "rate-card.json"
    _write_rate_card(rate_card_path, "standard-a", "mini-a")
    raw = json.loads(rate_card_path.read_text())
    raw["deployments"]["mini-a"]["canonical_model"] = "gpt-5.6-luna"
    raw["models"]["gpt-5.6-luna"] = raw["models"].pop("model-mini")
    raw["model_cards"]["gpt-5.6-luna"] = raw["model_cards"].pop("model-mini")
    raw["model_cards"]["gpt-5.6-luna"]["default_snapshot"] = "gpt-5.6-luna"
    raw["judge_policy"]["temperature_by_model"] = {"gpt-5.6-luna": None}
    rate_card_path.write_text(json.dumps(raw))
    campaign = _campaign(rate_card_path, "standard-a", "mini-a")

    contract = runtime_contract(
        {
            "model_profiles": {
                "standard": {},
                "mini": {},
                "nano": {"deployment": "nano"},
            },
            "judge": {"temperature": 0.0},
        },
        campaign,
    )

    assert contract["judge"]["temperature"] is None
    assert contract["model_profiles"]["nano"]["deployment"] == "nano-a"


def test_gpt56_successor_card_is_loaded_by_both_campaign_plans():
    rate_card_path = _EXP_DIR / "rate_cards/gpt56-session-v2.json"
    campaign = load_model_campaign(
        standard_model="seiia-ds-gpt-terra",
        mini_model="seiia-ds-gpt-luna",
        nano_model="seiia-ds-gpt-luna",
        reasoning_effort="low",
        n=1,
        rate_card_path=rate_card_path,
        reuse_historical_baseline=True,
    )

    session = plan_session_cells({"Q01"}, campaign)
    long_context = plan_long_context_cells(
        {"case-1"}, campaign, reused_summary_path=None
    )

    assert campaign.rate_card_reference["version"] == "gpt56-session-v2"
    assert campaign.rate_card_reference["effective_on"] == "2026-07-30"
    assert campaign.rate_card["retrieved_on"] == "2026-07-31"
    assert campaign.rate_card["pricing_service_tier"] == "standard"
    assert (
        campaign.rate_card_reference["aggregation_compatibility_key"]
        == "openai-gpt56-standard-2026-07-30"
    )
    assert session["rate_card"] == campaign.rate_card_reference
    assert long_context["rate_card"] == campaign.rate_card_reference
    assert campaign.rate_card["models"]["gpt-5.6-terra"]["short_context"] == {
        "input_per_million_usd": 2.0,
        "cache_read_per_million_usd": 0.2,
        "cache_write_per_million_usd": 2.5,
        "output_per_million_usd": 12.0,
    }
    assert campaign.rate_card["models"]["gpt-5.6-terra"]["long_context"] == {
        "input_per_million_usd": 4.0,
        "cache_read_per_million_usd": 0.4,
        "cache_write_per_million_usd": 5.0,
        "output_per_million_usd": 18.0,
    }
    assert campaign.rate_card["models"]["gpt-5.6-luna"]["short_context"] == {
        "input_per_million_usd": 0.2,
        "cache_read_per_million_usd": 0.02,
        "cache_write_per_million_usd": 0.25,
        "output_per_million_usd": 1.2,
    }
    assert campaign.rate_card["models"]["gpt-5.6-luna"]["long_context"] == {
        "input_per_million_usd": 0.4,
        "cache_read_per_million_usd": 0.04,
        "cache_write_per_million_usd": 0.5,
        "output_per_million_usd": 1.8,
    }
    assert campaign.rate_card["model_cards"]["gpt-5.6-luna"] == {
        **campaign.rate_card["model_cards"]["gpt-5.6-terra"],
        "default_snapshot": "gpt-5.6-luna",
    }
    assert (
        campaign.rate_card["model_cards"]["gpt-5.6-terra"]["max_input_tokens"] == 922000
    )
    assert (
        campaign.rate_card["model_cards"]["gpt-5.6-terra"]["max_output_tokens"]
        == 128000
    )
    assert (
        campaign.rate_card["model_cards"]["gpt-5.6-terra"]["knowledge_cutoff"]
        == "2026-02-16"
    )


def test_redesign_v2_prices_without_cache_write_operation():
    gpt54 = load_model_campaign(
        standard_model="seiia-ds",
        mini_model="seiia-ds-mini",
        nano_model="seiia-ds-nano",
        reasoning_effort="low",
        n=1,
        rate_card_path=_EXP_DIR / "rate_cards/benchmark-redesign-v2.json",
        reuse_historical_baseline=True,
    )
    terra_luna = load_model_campaign(
        standard_model="seiia-ds-gpt-terra",
        mini_model="seiia-ds-gpt-luna",
        nano_model="seiia-ds-gpt-luna",
        reasoning_effort="low",
        n=1,
        rate_card_path=_EXP_DIR / "rate_cards/benchmark-redesign-v2.json",
        reuse_historical_baseline=True,
    )

    identities = (
        gpt54.standard,
        terra_luna.standard,
        terra_luna.mini,
    )
    for identity in identities:
        usage = {
            "input_uncached": 100,
            "cache_read": 20,
            "cache_write": 999,
            "output": 10,
            "reasoning": 2,
        }
        result = price_usage(identity, usage, gpt54.rate_card)
        usage["cache_write"] = 0
        without_raw_write = price_usage(identity, usage, gpt54.rate_card)

        assert result["available"] is True
        assert result["cache_write_applicable"] is False
        assert result["cost_usd"] == without_raw_write["cost_usd"]


def test_successor_card_rejects_reuse_pinned_to_old_card(tmp_path: Path):
    campaign = load_model_campaign(
        standard_model="seiia-ds-gpt-terra",
        mini_model="seiia-ds-gpt-luna",
        nano_model="seiia-ds-gpt-luna",
        reasoning_effort="low",
        n=1,
        rate_card_path=_EXP_DIR / "rate_cards/gpt56-session-v2.json",
        reuse_historical_baseline=True,
    )
    item_id = "case-1"
    summary_path = tmp_path / "old-card-result.json"
    summary_path.write_text(
        json.dumps(
            {
                "status": "valid",
                "requested_models": {
                    "principal": {"alias": campaign.standard.deployment},
                    "classifier_auxiliary": {"alias": campaign.mini.deployment},
                },
                "authorization": {"post_started_count": 1, "inference_retries": 0},
                "safety": {"second_inference": False},
                "identity": {
                    "item_id_sha256": hashlib.sha256(item_id.encode()).hexdigest()
                },
                "rate_card": {
                    "version": "gpt56-session-v1",
                    "effective_on": "2026-07-30",
                    "aggregation_compatibility_key": None,
                    "sha256": campaign.rate_card["supersedes"]["sha256"],
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ModelCampaignError, match="rate card incompatível"):
        plan_long_context_cells({item_id}, campaign, reused_summary_path=summary_path)
