"""Contrato do juiz usado pelo benchmark Session."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

_EXP_DIR = Path(__file__).parents[2] / "experimentos" / "latencia-session-vs-classico"
sys.path.insert(0, str(_EXP_DIR / "scripts" / "shared"))
sys.path.insert(0, str(_EXP_DIR / "scripts" / "session-classico"))

import judge  # noqa: E402
from model_campaign import load_model_campaign  # noqa: E402


def _capture_judge_request(monkeypatch, *, cache_write_tokens: int | None = 60) -> dict:
    request: dict = {}
    result = {
        "groundedness": 1,
        "completeness": 1,
        "citation_quality": 1,
        "hallucination": False,
        "negativa_correta": None,
        "overall": 1,
        "rationale": "ok",
    }

    class FakeCompletions:
        def create(self, **kwargs):
            request.update(kwargs)
            return SimpleNamespace(
                model=kwargs["model"],
                usage=SimpleNamespace(
                    prompt_tokens=100,
                    completion_tokens=20,
                    prompt_tokens_details=SimpleNamespace(
                        cached_tokens=40, cache_write_tokens=cache_write_tokens
                    ),
                    completion_tokens_details=SimpleNamespace(reasoning_tokens=5),
                ),
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))
                ],
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    monkeypatch.setattr(judge, "_client", lambda _cfg: client)
    return request


def test_luna_judge_request_omits_temperature_from_campaign(monkeypatch):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    campaign = load_model_campaign(
        standard_model="seiia-ds-gpt-terra",
        mini_model="seiia-ds-gpt-luna",
        nano_model="seiia-ds-gpt-luna",
        reasoning_effort="low",
        n=1,
        rate_card_path=_EXP_DIR / "rate_cards" / "gpt56-session-v2.json",
        reuse_historical_baseline=True,
    )
    campaign.apply_environment()
    request = _capture_judge_request(monkeypatch)

    judge.judge_response("pergunta", {}, "resposta")

    assert request["model"] == "seiia-ds-gpt-luna"
    assert "temperature" not in request


def test_historical_judge_request_preserves_zero_temperature(monkeypatch):
    monkeypatch.setenv("EXP_JUDGE_OMIT_TEMPERATURE", "false")
    request = _capture_judge_request(monkeypatch)

    judge.judge_response(
        "pergunta",
        {},
        "resposta",
        judge.JudgeConfig(model="seiia-ds-mini"),
    )

    assert request["temperature"] == 0.0


def test_judge_usage_is_preserved_without_benchmark_cache_parameters(monkeypatch):
    request = _capture_judge_request(monkeypatch)

    result = judge.judge_response(
        "pergunta",
        {},
        "resposta",
        judge.JudgeConfig(model="seiia-ds-gpt-luna"),
    )

    assert "prompt_cache_options" not in request
    assert "prompt_cache_key" not in request
    assert result.usage == {
        "role": "judge",
        "deployment": "seiia-ds-gpt-luna",
        "reported_model": "seiia-ds-gpt-luna",
        "input": 60,
        "cache_read": 40,
        "cache_write": 60,
        "output": 20,
        "reasoning": 5,
        "total": 120,
        "generations": 1,
    }


def test_judge_input_does_not_depend_on_cache_write_counter(monkeypatch):
    _capture_judge_request(monkeypatch, cache_write_tokens=None)

    result = judge.judge_response(
        "pergunta",
        {},
        "resposta",
        judge.JudgeConfig(model="seiia-ds-mini"),
    )

    assert result.usage["input"] == 60
    assert result.usage["cache_read"] == 40
    assert result.usage["cache_write"] is None
