from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_APP = Path(__file__).resolve().parents[2]
_MODULE_PATH = (
    _APP / "experimentos/latencia-session-vs-classico/benchmark-redesign/benchmark.py"
)
_SPEC = importlib.util.spec_from_file_location("benchmark_redesign", _MODULE_PATH)
assert _SPEC and _SPEC.loader
benchmark = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(benchmark)


def _cache_proof(arm_name: str = "terra-luna", *, cache_read: int = 2048) -> dict:
    arm = benchmark._arm(benchmark._load_config(), arm_name)
    return {
        "status": "passed",
        "campaign": {
            "arm": arm_name,
            "aliases": {
                key: arm[key] for key in ("standard_model", "mini_model", "nano_model")
            },
            "rate_card": {
                "sha256": arm["rate_card_sha256"],
                "aggregation_compatibility_key": arm["rate_card_compatibility_key"],
            },
            "provider": arm["provider"],
        },
        "provider": arm["provider"],
        "trace_id": "trace-cache-proof",
        "provenance": {
            "provider_raw": "response.usage.input_tokens_details.cached_tokens",
            "litellm": "usage.prompt_tokens_details.cached_tokens",
            "langfuse": "usageDetails.input_cache_read",
            "normalizer": "cache_read",
            "cache_read": "provider_raw.input_tokens_details.cached_tokens",
        },
        "read": {"cache_read": cache_read},
        "boundaries": {
            key: {"status": "passed"}
            for key in ("provider_raw", "litellm", "langfuse", "normalizer")
        },
    }


def test_redesign_has_two_fixed_arms_and_n_one():
    config = benchmark._load_config()

    assert config["n"] == 1
    assert set(config["arms"]) == {"gpt54", "terra-luna"}
    assert benchmark._arm(config, "gpt54")["standard_model"] == "seiia-ds"


def test_preflight_blocks_canary_without_cache_read_proof(monkeypatch):
    monkeypatch.setattr(benchmark, "_load_private_environment", lambda: {})

    proof = benchmark.build_preflight(arm_name="terra-luna", cache_proof=None)

    assert proof["status"] == "blocked"
    assert proof["cache_gate"]["reason"] == "cache_read_proof_missing"
    assert proof["n"] == 1
    assert proof["inference_attempted"] is False


def test_canary_command_is_one_session_cell_without_warmup_or_retry(monkeypatch):
    monkeypatch.setattr(benchmark, "_load_private_environment", lambda: {})

    command, _ = benchmark._canary_command(
        arm_name="terra-luna",
        run_name="canary-test",
        artifacts_dir=Path("/tmp/canary-test"),
    )

    assert command[command.index("--n") + 1] == "1"
    assert "--canary" in command
    assert "--no-warmup" in command
    assert "--require-explicit-prompt-cache" not in command
    assert command[command.index("--endpoints") + 1] == "session"
    assert "--only" in command
    assert "--retry" not in command


def test_battery_command_is_ten_session_cells_without_warmup_or_retry(monkeypatch):
    monkeypatch.setattr(benchmark, "_load_private_environment", lambda: {})

    command, env = benchmark._battery_command(
        arm_name="gpt54",
        run_name="battery-test",
        artifacts_dir=Path("/tmp/battery-test"),
    )

    assert command[command.index("--n") + 1] == "1"
    assert "--canary" not in command
    assert "--only" not in command
    assert "--no-warmup" in command
    assert "--require-explicit-prompt-cache" not in command
    assert command[command.index("--endpoints") + 1] == "session"
    assert "--retry" not in command
    assert "EXP_JUDGE_PROMPT_CACHE_MODE" not in env
    assert "EXP_JUDGE_PROMPT_CACHE_KEY" not in env


def test_terra_battery_does_not_configure_cache_write_operation(monkeypatch):
    monkeypatch.setattr(benchmark, "_load_private_environment", lambda: {})

    command, env = benchmark._battery_command(
        arm_name="terra-luna",
        run_name="terra-battery-test",
        artifacts_dir=Path("/tmp/terra-battery-test"),
    )

    assert "--require-explicit-prompt-cache" not in command
    assert "EXP_JUDGE_PROMPT_CACHE_MODE" not in env
    assert "EXP_JUDGE_PROMPT_CACHE_KEY" not in env


def test_terra_battery_propagates_luna_to_explorer_slot(monkeypatch):
    monkeypatch.setattr(benchmark, "_load_private_environment", lambda: {})

    command, _ = benchmark._battery_command(
        arm_name="terra-luna",
        run_name="terra-battery-test",
        artifacts_dir=Path("/tmp/terra-battery-test"),
    )

    assert command[command.index("--nano-model") + 1] == "seiia-ds-gpt-luna"


def test_cache_gate_requires_only_observed_cache_read(tmp_path):
    proof = tmp_path / "cache-proof.json"
    proof.write_text(json.dumps(_cache_proof()))

    result = benchmark._cache_gate(
        proof,
        arm_name="terra-luna",
        arm=benchmark._arm(benchmark._load_config(), "terra-luna"),
    )

    assert result["status"] == "passed"


def test_cache_proof_requires_all_four_reconciled_boundaries(tmp_path):
    proof = tmp_path / "cache-proof.json"
    proof.write_text('{"status":"passed","boundaries":{}}')

    arm = benchmark._arm(benchmark._load_config(), "terra-luna")
    assert (
        benchmark._cache_gate(proof, arm_name="terra-luna", arm=arm)["status"]
        == "blocked"
    )

    proof.write_text(json.dumps(_cache_proof()))
    assert (
        benchmark._cache_gate(
            proof,
            arm_name="terra-luna",
            arm=benchmark._arm(benchmark._load_config(), "terra-luna"),
        )["status"]
        == "passed"
    )


def test_cache_proof_requires_positive_observed_read(tmp_path):
    proof = tmp_path / "cache-proof.json"
    proof.write_text(json.dumps(_cache_proof(cache_read=0)))

    result = benchmark._cache_gate(
        proof,
        arm_name="terra-luna",
        arm=benchmark._arm(benchmark._load_config(), "terra-luna"),
    )

    assert result == {"status": "blocked", "reason": "cache_read_not_observed"}


def test_cache_proof_cannot_be_reused_by_another_arm(tmp_path):
    proof = tmp_path / "cache-proof.json"
    proof.write_text(json.dumps(_cache_proof("terra-luna")))

    result = benchmark._cache_gate(
        proof,
        arm_name="gpt54",
        arm=benchmark._arm(benchmark._load_config(), "gpt54"),
    )

    assert result == {"status": "blocked", "reason": "cache_proof_campaign_mismatch"}


def test_normalize_cache_usage_preserves_only_cache_read():
    usage = {
        "input_tokens": 4096,
        "output_tokens": 8,
        "input_tokens_details": {"cached_tokens": 1024},
    }

    normalized = benchmark._normalize_cache_usage(
        usage,
        read_path="input_tokens_details.cached_tokens",
    )

    assert normalized == {
        "cache_read": 1024,
        "provenance": {"cache_read": "input_tokens_details.cached_tokens"},
    }
