"""Regressão da contabilização OCR separada no long-context v2."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_EXP_DIR = Path(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "experimentos",
        "latencia-session-vs-classico",
    )
)
sys.path.insert(0, str(_EXP_DIR / "scripts" / "shared"))
sys.path.insert(0, str(_EXP_DIR / "scripts" / "long-context"))

from long_context_v2_telemetry import (  # noqa: E402
    ocr_usage_records,
    summarize_usage,
)


def test_ocr_usage_has_own_bucket_and_partial_cost_without_double_count():
    rate_card = json.loads(
        (_EXP_DIR / "rate_cards" / "gpt56-session-v1.json").read_text()
    )
    contract = {
        "model_profiles": {
            "standard": {
                "deployment": "seiia-ds-gpt-terra",
                "canonical_model": "gpt-5.6-terra",
                "provider": "openai",
            },
            "mini": {
                "deployment": "seiia-ds-gpt-luna",
                "canonical_model": "gpt-5.6-luna",
                "provider": "openai",
            },
        },
        "ocr": {
            "requested_profile": "mini",
            "deployment": "seiia-ds-gpt-luna",
            "canonical_model": "gpt-5.6-luna",
            "provider": "openai",
        },
    }
    raw = [
        {
            "schema_version": "sei-extraction-ocr-usage-v1",
            "call_key_sha256": "a" * 64,
            "role": "ocr",
            "deployment": "seiia-ds-gpt-luna",
            "reported_model": "gpt-5.6-luna",
            "usage": {
                "prompt_tokens": 100,
                "cached_tokens": 20,
                "cache_write_tokens": None,
                "completion_tokens": 10,
                "reasoning_tokens": 2,
            },
        }
    ]

    records = ocr_usage_records(raw, contract=contract)
    summary = summarize_usage(
        records,
        rate_card=rate_card,
        rate_card_ref={
            "sha256": "test",
            **{
                key: rate_card.get(key)
                for key in (
                    "version",
                    "effective_on",
                    "aggregation_compatibility_key",
                )
            },
        },
    )

    assert summary["by_scope"]["ocr"]["calls"] == 1
    assert summary["by_scope"]["ocr"]["tokens"]["cache_write"] is None
    assert summary["by_scope"]["ocr"]["cost_usd"] is None
    assert summary["cost"]["known_subtotal_excluding_cache_write_usd"]
    assert summary["by_model"]["gpt-5.6-luna"]["calls"] == 1
