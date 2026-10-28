"""Contratos offline da campanha long-context v2 (sem SEI/Langfuse/rede)."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_EXP_DIR = Path(__file__).parents[2] / "experimentos" / "latencia-session-vs-classico"
sys.path.insert(0, str(_EXP_DIR / "scripts" / "shared"))
sys.path.insert(0, str(_EXP_DIR / "scripts" / "long-context"))

import run_long_context_v2 as runner_module  # noqa: E402
from long_context_v2_ledger import (  # noqa: E402
    LedgerContractError,
    V2Ledger,
    write_private_json,
)
from long_context_v2_manifest import (  # noqa: E402
    MANIFEST_PATH,
    ManifestContractError,
    file_sha256,
    validate_manifest,
)
from long_context_v2_scorer import (  # noqa: E402
    EVALUATION_STATUSES,
    JudgeMaterial,
    JudgeV2ContractError,
    classify_quality_gate,
    parse_judge_output,
    score_judge_output,
)
from long_context_v2_telemetry import (  # noqa: E402
    TelemetryContractError,
    agent_usage_records,
    judge_usage_record,
    normalize_agent_usage,
    normalize_judge_usage,
    resolve_model,
    summarize_usage,
)
from run_long_context_v2 import (  # noqa: E402
    CANARY_ITEM_ID,
    SECOND_CANARY_ITEM_ID,
    CanaryV2Error,
    _aggregate_battery_usage,
    _battery_continuation,
    _build_canary_gate,
    _case_error_cooldown_s,
    _guard_judge_config,
    _judge_with_retries,
    _load_sei_preflight_expectation,
    _mark_case_error_result,
    _mark_provider_rate_limited_result,
    _pre_agent_retry_proof,
    _preflight_and_reserve,
    _rate_limit_retry_proof,
    _reclassify_missing_agent_usage,
    _sanitized_result,
    _select_canary_item_id,
    _select_full_battery_missing_items,
    _validate_fresh_campaign,
    _validate_live_sei_preflight,
    _validate_v2_runtime_preflight,
)
from trace_metrics import Obs  # noqa: E402


def _contract() -> dict:
    return json.loads(
        (
            _EXP_DIR
            / "dataset/long-context/benchmark-long-context-v2-evaluation-contract.json"
        ).read_text()
    )


def _rate_card() -> dict:
    return json.loads((_EXP_DIR / "rate_cards/v2.json").read_text())


def _item(question_type: str = "factual") -> dict:
    return {
        "item_id": "synthetic-item",
        "question_type": question_type,
    }


def _material(negative: bool = False) -> JudgeMaterial:
    return JudgeMaterial(
        question="Pergunta sintética?",
        gold="Gold sintético.",
        rubric={"elementos_obrigatorios": ["A", "B"]},
        target={"kind": "synthetic"},
        source_evidence=[],
        protected_absence={"reference": "absence-1"} if negative else None,
    )


def _judge_value(verdict: str = "unsupported", *, negative: bool = False) -> dict:
    references = [1] if verdict in {"supported", "contradicted"} else []
    return {
        "target_alignment": True,
        "checklist": [
            {"index": 1, "satisfied": True},
            {"index": 2, "satisfied": False},
        ],
        "claims": [
            {
                "text": "Afirmação sintética.",
                "verdict": verdict,
                "evidence_references": references,
                "evidence_basis": "excerpt" if references else "none",
                "absence_evidence_reference": None,
                "citation_present": False,
                "invented": False,
            }
        ],
        "citation_quality": 0.25,
        "negativa_correta": True if negative else None,
        "overall": 0.5,
        "rationale": "Justificativa sintética.",
    }


def test_manifest_schema_and_frozen_integrity_without_protected_content():
    manifest = validate_manifest()
    assert manifest["schema_version"] == "benchmark-long-context-v2-manifest-1"
    assert len(manifest["items"]) == 9
    assert manifest["metadata"]["no_cache"] is True
    assert (
        manifest["metadata"]["document_source"] == "sei_no_cache_with_pinned_validation"
    )
    assert manifest["metadata"]["process_source"] == "sei_no_cache"
    serialized = MANIFEST_PATH.read_text(encoding="utf-8")
    assert "protected://benchmark-long-context-v2/" in serialized
    assert "gold_answer" not in serialized
    assert "id_procedimentos" not in serialized


def test_single_item_selection_accepts_any_manifest_item():
    manifest = validate_manifest()

    assert _select_canary_item_id(None) == CANARY_ITEM_ID
    for item in manifest["items"]:
        assert _select_canary_item_id(item["item_id"]) == item["item_id"]
    with pytest.raises(CanaryV2Error, match="não pertence"):
        _select_canary_item_id("case-outside-manifest")


def test_model_profiles_and_judge_are_default_gpt54_family():
    contract = _contract()
    expected = {
        "standard": ("seiia-ds", "gpt-5.4"),
        "mini": ("seiia-ds-mini", "gpt-5.4-mini"),
        "nano": ("seiia-ds-nano", "gpt-5.4-nano"),
    }
    for profile, (deployment, canonical) in expected.items():
        identity = resolve_model(profile, contract)
        assert (identity.deployment, identity.canonical_model, identity.provider) == (
            deployment,
            canonical,
            "openai",
        )
    assert contract["judge"]["requested_profile"] == "mini"
    assert contract["judge"]["canonical_model"] == "gpt-5.4-mini"


def test_judge_guard_uses_runtime_mini_deployment(tmp_path: Path):
    env_file = tmp_path / "judge.env"
    env_file.write_text(
        "LITELLM_PROXY_URL=https://proxy.invalid\nLITELLM_PROXY_API_KEY=test-key\n",
        encoding="utf-8",
    )
    contract = {
        "judge": {
            "requested_profile": "mini",
            "deployment": "seiia-ds-gpt-luna",
        }
    }

    url, key, model = _guard_judge_config(contract, env_file)

    assert url == "https://proxy.invalid"
    assert key == "test-key"
    assert model == "seiia-ds-gpt-luna"


def test_runtime_preflight_rejects_unpublished_nano_alias():
    manifest = {
        "metadata": {
            "document_source": "sei_no_cache_with_pinned_validation",
            "process_source": "sei_no_cache",
            "desired_model_context_window_tokens": 1_000_000,
        }
    }
    contract = {
        "model_profiles": {
            "standard": {"deployment": "seiia-ds-gpt-terra"},
            "mini": {"deployment": "seiia-ds-gpt-luna"},
            "nano": {"deployment": "seiia-ds-nano"},
        },
        "model_campaign": {"reasoning_effort": "low"},
        "ocr": {"deployment": "seiia-ds-gpt-luna"},
    }
    preflight = {
        "session_main_model_profile": "standard",
        "session_main_model": "seiia-ds-gpt-terra",
        "session_classifier_model_profile": "mini",
        "session_classifier_model": "seiia-ds-gpt-luna",
        "session_explorer_model_profile": "nano",
        "session_explorer_model": "nano",
        "session_ocr_model": "seiia-ds-gpt-luna",
        "session_reasoning_effort_requested": "low",
        "session_main_model_client_retries": 0,
        "benchmark_no_cache_required": True,
        "benchmark_document_source": "sei_no_cache_with_pinned_validation",
        "benchmark_process_source": "sei_no_cache",
        "session_main_model_context_window_tokens": 1_050_000,
    }

    with pytest.raises(CanaryV2Error, match="nano"):
        _validate_v2_runtime_preflight(preflight, manifest, contract)


def test_pending_nd_and_unsupported_semantics_are_distinct():
    assert EVALUATION_STATUSES == (
        "pending_trace",
        "pending_evaluation",
        "evaluated",
        "technical_unavailable",
    )
    result = score_judge_output(
        _judge_value("unsupported"),
        item=_item(),
        material=_material(),
        evidence_count=1,
        thresholds=_contract()["thresholds"],
    )
    assert result.numeric["groundedness"] == 0
    assert result.boolean["hallucination"] is False
    assert result.auxiliary["hallucination_count"] == 0
    assert result.gate["status"] == "passed"
    assert (
        result.gate["non_blocking_diagnostics"]["historical_thresholds"][
            "groundedness"
        ]["met"]
        is False
    )


def test_contradiction_is_hallucination_but_no_evidence_is_not():
    value = _judge_value("contradicted")
    result = score_judge_output(
        value,
        item=_item(),
        material=_material(),
        evidence_count=1,
        thresholds=_contract()["thresholds"],
    )
    assert result.boolean["hallucination"] is True
    assert result.auxiliary["hallucination_count"] == 1
    value["claims"][0]["evidence_references"] = []
    value["claims"][0]["evidence_basis"] = "none"
    with pytest.raises(JudgeV2ContractError, match="Contradição sem evidência"):
        score_judge_output(
            value,
            item=_item(),
            material=_material(),
            evidence_count=1,
            thresholds=_contract()["thresholds"],
        )


def test_strict_judge_schema_rejects_extra_field():
    schema = json.loads(
        (
            _EXP_DIR
            / "dataset/long-context/benchmark-long-context-v2-judge.schema.json"
        ).read_text()
    )
    value = _judge_value()
    value["unexpected"] = True
    with pytest.raises(JudgeV2ContractError, match="unexpected"):
        parse_judge_output(json.dumps(value), schema)


def test_judge_contract_rejects_references_when_evidence_basis_is_none():
    value = _judge_value()
    value["claims"][0]["evidence_references"] = [1]

    with pytest.raises(JudgeV2ContractError, match="evidence_basis=none"):
        score_judge_output(
            value,
            item=_item(),
            material=_material(),
            evidence_count=1,
            thresholds=_contract()["thresholds"],
        )


def test_judge_prompt_states_none_requires_empty_evidence_references():
    prompt = (_EXP_DIR / "judge-prompts/long-context-v2-user.txt").read_text(
        encoding="utf-8"
    )

    assert "evidence_basis=none exige evidence_references=[]" in prompt


def test_agent_usage_deduplicates_generation_and_ignores_parent_usage():
    observations = [
        Obs("parent", "SPAN", "model", None, 0, 1, usage={"input": 999999}),
        Obs(
            "generation",
            "GENERATION",
            "ChatOpenAI",
            "parent",
            0,
            1,
            ns="model:x",
            model="standard",
            usage={
                "input": 100,
                "input_cache_read": 50,
                "output": 30,
                "output_reasoning": 10,
            },
        ),
        Obs(
            "generation",
            "GENERATION",
            "ChatOpenAI",
            "parent",
            0,
            1,
            ns="model:x",
            model="standard",
            usage={
                "input": 100,
                "input_cache_read": 50,
                "output": 30,
                "output_reasoning": 10,
            },
        ),
    ]
    records = agent_usage_records(observations, trace_id="trace", contract=_contract())
    assert len(records) == 1
    assert records[0]["usage"] == {
        "input_uncached": 100,
        "cache_read": 50,
        "cache_write": None,
        "output": 30,
        "reasoning": 10,
        "total_without_cache_write": 190,
        "total": None,
    }


def test_missing_agent_generation_is_null_without_invalidating_cell():
    result = {
        "item_id": "item-2",
        "trace_status": "technical_unavailable",
        "evaluation_status": "evaluated",
        "context_disclosure_observed": True,
        "transport": {"http_status": 200, "terminal_type": "end"},
        "no_cache": {
            "requested": True,
            "effective": True,
            "cold_start_comparable": True,
        },
        "trace": {
            "status": "technical_unavailable",
            "read_status": "complete",
            "dataset_linked": True,
        },
        "usage": {
            "coverage": {"status": "complete", "generation_records": 0},
            "by_scope": {
                "agent": {
                    "available": False,
                    "calls": 0,
                    "tokens": None,
                    "cost_usd": None,
                },
                "judge": {"available": True, "calls": 1, "tokens": {}},
            },
            "total_cost_usd": 0.01,
            "cost": {"cost_usd": 0.01},
        },
        "technical_failures": [
            {
                "stage": "agent_usage",
                "error_type": "TelemetryContractError",
                "error_sha256": runner_module._KNOWN_AGENT_USAGE_NULL_SHA256,
            }
        ],
        "gate": {"dimensions": {"quality": {"status": "passed", "validity": "valid"}}},
    }

    assert _reclassify_missing_agent_usage(result, canary_item_id="item-2") is True
    assert result["trace_status"] == "complete"
    assert result["technical_failures"] == []
    assert result["usage"]["agent_usage"] is None
    assert result["usage"]["agent_usage_reason"] == "telemetry_generation_missing"
    assert result["usage"]["coverage"]["status"] == "complete"
    assert result["gate"]["status"] == "passed"
    assert _battery_continuation(result) == {
        "continue": True,
        "classification": "passed",
    }
    aggregate = _aggregate_battery_usage([result])
    assert aggregate["coverage"] == "complete"
    assert aggregate["total_cost_usd"] is None
    assert aggregate["metric_nulls"] == {"agent_usage": 1}


def test_persisted_trace_usage_error_falls_through_to_metric_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    trace_path = tmp_path / "trace.raw.json"
    trace_path.write_text('{"observations": []}')
    result = {
        "trace_id": "trace",
        "technical_failures": [
            {
                "stage": "agent_usage",
                "error_type": "TelemetryContractError",
                "error_sha256": runner_module._KNOWN_AGENT_USAGE_NULL_SHA256,
            }
        ],
    }

    def raise_telemetry_error(*args, **kwargs):
        raise TelemetryContractError("generation missing")

    monkeypatch.setattr(runner_module, "agent_usage_records", raise_telemetry_error)

    assert (
        runner_module._reclassify_agent_usage_from_persisted_trace(
            result, trace_path=trace_path, contract=_contract()
        )
        is False
    )


def test_recovered_result_marks_missing_agent_usage_without_failure_row():
    result = {
        "item_id": "item-recovered",
        "trace_status": "pending_trace",
        "evaluation_status": "evaluated",
        "context_disclosure_observed": True,
        "transport": {"http_status": 200, "terminal_type": "end"},
        "no_cache": {"effective": True, "cold_start_comparable": True},
        "trace": {
            "status": "technical_unavailable",
            "read_status": "complete",
            "dataset_linked": True,
        },
        "usage": {
            "coverage": {"status": "complete", "generation_records": 0},
            "by_scope": {"agent": {"available": False, "calls": 0}},
            "total_cost_usd": 0.01,
            "cost": {"cost_usd": 0.01},
        },
        "technical_failures": [],
        "gate": {"dimensions": {"quality": {"status": "unavailable"}}},
    }

    assert _reclassify_missing_agent_usage(result, canary_item_id=result["item_id"])
    assert result["trace_status"] == "complete"
    assert result["usage"]["agent_usage_reason"] == "telemetry_generation_missing"
    assert result["gate"]["dimensions"]["observability"]["status"] == "passed"
    assert result["gate"]["dimensions"]["integrity_technical"]["status"] == "passed"


def test_battery_summary_syncs_external_quality_from_accepted_evaluation():
    accepted_quality = {
        "policy_version": "quality-v2",
        "status": "passed",
        "validity": "valid",
        "blocking_checks": {"target_alignment": True},
        "non_blocking_diagnostics": {},
    }
    result = {
        "item_id": "recovered-item",
        "evaluation_status": "evaluated",
        "evaluation": {
            "numeric": {},
            "boolean": {},
            "auxiliary": {},
            "gate": accepted_quality,
        },
        "gate": {
            "status": "failed",
            "failed_dimensions": ["quality"],
            "dimensions": {
                "comparability": {"status": "passed"},
                "integrity_technical": {"status": "passed"},
                "observability": {"status": "passed"},
                "quality": {"status": "unavailable", "validity": "unavailable"},
            },
        },
    }

    summary = runner_module._summarize_battery_item(result, source="fresh_execution")

    assert summary["gate"]["dimensions"]["quality"] == accepted_quality
    assert summary["gate"]["status"] == "passed"
    assert summary["gate"]["failed_dimensions"] == []


def test_full_battery_provider_429_is_completed_case_and_continues():
    result = {
        "item_id": "rate-limited-item",
        "transport": {"http_status": 200, "terminal_type": "error"},
        "evaluation": {"unexpected": "must be removed"},
        "evaluation_status": "technical_unavailable",
        "trace_status": "technical_unavailable",
        "usage": {"unexpected": "must be removed"},
        "technical_failures": [{"stage": "agent"}],
    }
    outcome = SimpleNamespace(terminal_type="error", terminal_status_code=429)

    assert _mark_provider_rate_limited_result(result, outcome=outcome) is True
    assert result["result_status"] == "provider_rate_limited"
    assert result["evaluation"] is None
    assert result["usage"] is None
    assert result["gate"] is None
    assert result["technical_failures"] == []
    assert _battery_continuation(result) == {
        "continue": True,
        "classification": "provider_rate_limited",
    }

    other_error = SimpleNamespace(terminal_type="error", terminal_status_code=500)
    assert _mark_provider_rate_limited_result({}, outcome=other_error) is False


def test_full_battery_document_409_is_completed_error_and_continues(tmp_path: Path):
    raw_path = tmp_path / "stream.raw.sse"
    raw_path.write_text(
        'data: {"type":"status"}\n\n'
        'data: {"type":"error","status_code":409,'
        '"diagnostic":{"category":"document_fetch_failed",'
        '"stage":"fetch_validate_before_write","fingerprint":"abc"}}\n\n'
    )
    result = {
        "item_id": "document-error-item",
        "transport": {"http_status": 200},
        "evaluation": {"unexpected": "must be removed"},
        "usage": {"unexpected": "must be removed"},
        "technical_failures": [{"stage": "agent"}],
    }
    outcome = SimpleNamespace(terminal_type="error", terminal_status_code=409)

    assert _mark_case_error_result(
        result,
        outcome=outcome,
        raw_path=raw_path,
        result_status="ocr_provider_rate_limited",
    )
    assert result["result_status"] == "ocr_provider_rate_limited"
    assert result["evaluation"] is None
    assert result["evaluation_status"] is None
    assert result["usage"] is None
    assert result["gate"] is None
    assert result["technical_failures"] == []
    assert _battery_continuation(result) == {
        "continue": True,
        "classification": "ocr_provider_rate_limited",
    }


def test_full_battery_continues_when_only_judge_postprocessing_is_unavailable():
    result = {
        "transport": {"http_status": 200, "terminal_type": "end"},
        "trace": {"read_status": "complete", "dataset_linked": True},
        "technical_failures": [{"stage": "judge", "error_type": "exhausted"}],
        "gate": {
            "dimensions": {
                "comparability": {"status": "passed"},
                "observability": {"status": "failed"},
                "integrity_technical": {
                    "status": "failed",
                    "checks": {
                        "single_item": True,
                        "transport_http_200_terminal_end": True,
                    },
                },
                "quality": {"status": "unavailable"},
            }
        },
    }

    assert _battery_continuation(result) == {
        "continue": True,
        "classification": "isolated_postprocessing_unavailable",
    }


def test_agent_and_judge_usage_are_separate_with_known_cost():
    contract = _contract()
    agent = {
        "call_key_sha256": "a" * 64,
        "scope": "agent",
        "component": "main",
        "model": resolve_model("standard", contract).__dict__,
        "usage": {
            "input_uncached": 1_000_000,
            "cache_read": 0,
            "output": 1_000_000,
            "reasoning": 0,
            "total": 2_000_000,
        },
    }
    judge = judge_usage_record(
        {
            "prompt_tokens": 1_000_000,
            "cached_tokens": 0,
            "completion_tokens": 1_000_000,
            "reasoning_tokens": 0,
        },
        call_id="judge-1",
        reported_model="gpt-5.4-mini-2026-06-01",
        contract=contract,
    )
    summary = summarize_usage(
        [agent, judge],
        rate_card=_rate_card(),
        rate_card_ref=contract["rate_card"],
    )
    assert judge["model_resolution_source"] == "response_model"
    assert summary["by_scope"]["agent"]["cost_usd"] == 17.5
    assert summary["by_scope"]["judge"]["cost_usd"] == 5.25
    assert summary["total_cost_usd"] == 22.75
    assert summary["rate_card"]["sha256"] == file_sha256(
        _EXP_DIR / "rate_cards/v2.json"
    )


def test_usage_summary_rejects_rate_card_identity_mismatch():
    contract = _contract()
    agent = {
        "call_key_sha256": "a" * 64,
        "scope": "agent",
        "component": "main",
        "model": resolve_model("standard", contract).__dict__,
        "usage": {
            "input_uncached": 1,
            "cache_read": 0,
            "output": 1,
            "reasoning": 0,
            "total": 2,
        },
    }
    incompatible_ref = {**contract["rate_card"], "version": "different-card"}

    with pytest.raises(TelemetryContractError, match="Rate card incompatível"):
        summarize_usage([agent], rate_card=_rate_card(), rate_card_ref=incompatible_ref)


def test_usage_normalization_never_estimates_missing_semantics():
    assert normalize_agent_usage({}).total is None
    assert normalize_agent_usage({}).total_without_cache_write == 0
    assert normalize_judge_usage({}).total == 0
    usage = normalize_agent_usage({"output": 1, "output_reasoning": 2})
    assert (usage.output, usage.reasoning) == (1, 2)
    with pytest.raises(TelemetryContractError, match="não mapeado"):
        resolve_model("experimental", _contract())


def test_agent_usage_maps_langchain_cache_creation_to_cache_write():
    usage = normalize_agent_usage(
        {
            "input": 1024,
            "input_cache_read": 0,
            "input_cache_creation": 3072,
            "output": 8,
            "output_reasoning": 2,
        }
    )

    assert usage.cache_write == 3072
    assert usage.output == 8
    assert usage.reasoning == 2
    assert usage.total == 4106


def test_private_trace_dump_serializes_sdk_datetime_without_changing_permissions(
    tmp_path: Path,
):
    os.chmod(tmp_path, 0o700)
    path = tmp_path / "trace.raw.json"
    write_private_json(path, {"timestamp": datetime(2026, 7, 23, tzinfo=UTC)})
    assert json.loads(path.read_text())["timestamp"] == "2026-07-23 00:00:00+00:00"
    assert path.stat().st_mode & 0o777 == 0o600


def test_ledger_reserves_before_post_and_refuses_second_execution(tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    ledger = V2Ledger(tmp_path / "ledger.jsonl")
    reservation = ledger.reserve(
        run_name="run-v2",
        item_id="case-0960k-q2-synthesis",
        contract_sha256="c" * 64,
        request_identity_sha256="r" * 64,
    )
    assert reservation["post_attempted"] is False
    with pytest.raises(LedgerContractError, match="N=1 já reservado"):
        ledger.reserve(
            run_name="run-v2",
            item_id="case-0960k-q2-synthesis",
            contract_sha256="d" * 64,
            request_identity_sha256="r" * 64,
        )


def test_full_battery_selects_eight_fresh_posts_and_preserves_n1(tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    missing = _select_full_battery_missing_items(validate_manifest())
    assert len(missing) == 8
    assert CANARY_ITEM_ID in missing
    assert SECOND_CANARY_ITEM_ID not in missing

    ledger = V2Ledger(tmp_path / "ledger.jsonl")
    with pytest.raises(LedgerContractError, match="Autorização da bateria ausente"):
        ledger.reserve_full_battery_item(
            authorization_event_id="absent",
            run_name="run-item",
            item_id=missing[0],
            contract_sha256="c" * 64,
            request_identity_sha256="r" * 64,
        )
    authorization = ledger.authorize_full_battery(
        authorization_sha256="a" * 64,
        policy_version="gate-v2",
        reused_results=[
            {
                "item_id": SECOND_CANARY_ITEM_ID,
                "execution_id": "fresh-execution",
                "trace_id": "fresh-trace",
                "source_artifact_sha256": "b" * 64,
                "gate_status": "passed",
                "fresh_comparable": True,
            }
        ],
        excluded_predecessors=[
            {
                "item_id": CANARY_ITEM_ID,
                "execution_id": "frozen-execution",
                "trace_id": "frozen-trace",
                "source_artifact_sha256": "d" * 64,
                "quality_status": "passed",
                "fresh_comparable": False,
                "replacement_reason": ("frozen_evidence_snapshot_not_fresh_comparable"),
            }
        ],
        missing_item_ids=missing,
        expected_item_ids=set(runner_module.EXPECTED_ITEM_IDS),
    )
    first = ledger.reserve_full_battery_item(
        authorization_event_id=authorization["event_id"],
        run_name="run-first",
        item_id=missing[0],
        contract_sha256="c" * 64,
        request_identity_sha256="r" * 64,
    )
    with pytest.raises(LedgerContractError, match="anterior em andamento"):
        ledger.reserve_full_battery_item(
            authorization_event_id=authorization["event_id"],
            run_name="run-second",
            item_id=missing[1],
            contract_sha256="c" * 64,
            request_identity_sha256="s" * 64,
        )
    ledger.transition(
        first["execution_id"],
        event_type="post_completed",
        post_attempted=True,
        evaluation_status="pending_evaluation",
        trace_status="pending_trace",
    )
    ledger.reserve_full_battery_item(
        authorization_event_id=authorization["event_id"],
        run_name="run-second",
        item_id=missing[1],
        contract_sha256="c" * 64,
        request_identity_sha256="s" * 64,
    )
    with pytest.raises(LedgerContractError, match="já foi consumido"):
        ledger.reserve_full_battery_item(
            authorization_event_id=authorization["event_id"],
            run_name="repeat-first",
            item_id=missing[0],
            contract_sha256="c" * 64,
            request_identity_sha256="x" * 64,
        )


def test_full_battery_ocr_luna_sucessora_seleciona_nove_sem_reuso(
    tmp_path: Path,
):
    os.chmod(tmp_path, 0o700)
    missing = _select_full_battery_missing_items(
        validate_manifest(), fresh_all_items=True
    )

    assert len(missing) == 9
    assert set(missing) == set(runner_module.EXPECTED_ITEM_IDS)

    ledger = V2Ledger(tmp_path / "ledger.jsonl")
    authorization = ledger.authorize_full_battery(
        authorization_sha256="a" * 64,
        policy_version="gate-v2",
        reused_results=[],
        excluded_predecessors=[],
        missing_item_ids=missing,
        expected_item_ids=set(runner_module.EXPECTED_ITEM_IDS),
        fresh_all_items=True,
    )

    assert authorization["detail"]["reused_results"] == []
    assert authorization["detail"]["missing_item_ids"] == missing


@pytest.mark.parametrize(
    ("deployment", "canonical_model"),
    (("seiia-ds-mini", "gpt-5.4-mini"), ("seiia-ds-gpt-luna", "gpt-5.6-luna")),
)
def test_fresh_battery_accepts_configured_mini_as_ocr(
    deployment: str, canonical_model: str
):
    campaign = SimpleNamespace(
        mini=SimpleNamespace(
            deployment=deployment,
            canonical_model=canonical_model,
        )
    )
    _validate_fresh_campaign(
        {
            "ocr": {
                "deployment": deployment,
                "canonical_model": canonical_model,
            }
        },
        campaign,
    )


def test_explicit_provider_internal_error_is_non_fatal_case_result(tmp_path: Path):
    raw_path = tmp_path / "stream.raw.sse"
    raw_path.write_text('data: {"type":"error","status_code":500}\n')
    result = {"transport": {}, "technical_failures": [{"stage": "agent"}]}

    marked = _mark_case_error_result(
        result,
        outcome=runner_module.SSEOutcome(
            content="",
            terminal_type="error",
            terminal_status_code=500,
            metadata={},
            status_frames=0,
            preparation_heartbeat_frames=0,
            reasoning_frames=0,
            content_frames=0,
            terminal_detail=None,
            observed_response_time_s=1.0,
        ),
        raw_path=raw_path,
        result_status="provider_internal_error",
    )

    assert marked is True
    assert result["result_status"] == "provider_internal_error"
    assert _battery_continuation(result) == {
        "continue": True,
        "classification": "provider_internal_error",
    }


def test_rate_limit_successor_reuses_three_and_authorizes_only_six(tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    reused_ids = {
        "case-0960k-q1-factual",
        "case-0960k-q2-synthesis",
        "case-0960k-q3-insufficient-evidence",
    }
    missing = runner_module._select_successor_missing_items(
        validate_manifest(), reused_ids=reused_ids
    )

    assert len(missing) == 6
    assert reused_ids.isdisjoint(missing)
    assert reused_ids.union(missing) == set(runner_module.EXPECTED_ITEM_IDS)

    reused = [
        {
            "item_id": item_id,
            "execution_id": f"execution-{index}",
            "trace_id": f"trace-{index}",
            "source_artifact_sha256": str(index) * 64,
            "gate_status": "failed" if index == 1 else "passed",
            "reuse_technical_status": "passed",
            "fresh_comparable": True,
        }
        for index, item_id in enumerate(sorted(reused_ids), start=1)
    ]
    authorization = V2Ledger(tmp_path / "ledger.jsonl").authorize_full_battery(
        authorization_sha256="a" * 64,
        policy_version="gate-v2",
        reused_results=reused,
        excluded_predecessors=[],
        missing_item_ids=missing,
        expected_item_ids=set(runner_module.EXPECTED_ITEM_IDS),
    )

    assert authorization["detail"]["partition"] == "3+6"
    assert authorization["detail"]["expected_fresh_posts"] == 6


def test_case_error_cooldown_uses_retry_after_or_conservative_default():
    assert (
        _case_error_cooldown_s(
            {
                "result_status": "provider_rate_limited",
                "provider_rate_limit": {"retry_after_s": 37},
            }
        )
        == 37
    )
    assert _case_error_cooldown_s({"result_status": "document_fetch_failed"}) == (
        runner_module.RATE_LIMIT_COOLDOWN_S
    )
    assert _case_error_cooldown_s({"result_status": "completed"}) == 0


def test_full_battery_accepts_one_reused_result_without_legacy_predecessor(
    tmp_path: Path,
):
    os.chmod(tmp_path, 0o700)
    missing = _select_full_battery_missing_items(validate_manifest())
    ledger = V2Ledger(tmp_path / "ledger.jsonl")

    authorization = ledger.authorize_full_battery(
        authorization_sha256="a" * 64,
        policy_version="gate-v2",
        reused_results=[
            {
                "item_id": SECOND_CANARY_ITEM_ID,
                "execution_id": "fresh-execution",
                "trace_id": "fresh-trace",
                "source_artifact_sha256": "b" * 64,
                "gate_status": "passed",
                "fresh_comparable": True,
            }
        ],
        excluded_predecessors=[],
        missing_item_ids=missing,
        expected_item_ids=set(runner_module.EXPECTED_ITEM_IDS),
    )

    assert authorization["detail"]["excluded_predecessors"] == []


def test_full_battery_retry_requires_invalidated_predecessor(tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    missing = _select_full_battery_missing_items(validate_manifest())
    ledger = V2Ledger(tmp_path / "ledger.jsonl")
    authorization = ledger.authorize_full_battery(
        authorization_sha256="a" * 64,
        policy_version="gate-v2",
        reused_results=[
            {
                "item_id": SECOND_CANARY_ITEM_ID,
                "execution_id": "fresh-execution",
                "trace_id": "fresh-trace",
                "source_artifact_sha256": "b" * 64,
                "gate_status": "passed",
                "fresh_comparable": True,
            }
        ],
        excluded_predecessors=[],
        missing_item_ids=missing,
        expected_item_ids=set(runner_module.EXPECTED_ITEM_IDS),
    )
    predecessor = ledger.reserve_full_battery_item(
        authorization_event_id=authorization["event_id"],
        run_name="attempt-1",
        item_id=missing[0],
        contract_sha256="c" * 64,
        request_identity_sha256="r" * 64,
    )
    ledger.transition(
        predecessor["execution_id"],
        event_type="battery_item_invalidated_for_retry",
        trace_id="trace-1",
        post_attempted=True,
        evaluation_status="technical_unavailable",
        trace_status="technical_unavailable",
    )

    retry = ledger.reserve_full_battery_retry(
        authorization_event_id=authorization["event_id"],
        predecessor_execution_id=predecessor["execution_id"],
        run_name="attempt-2",
        item_id=missing[0],
        contract_sha256="c" * 64,
        request_identity_sha256="r" * 64,
    )

    assert retry["retry_of_execution_id"] == predecessor["execution_id"]
    ledger.transition(
        retry["execution_id"],
        event_type="battery_item_completed",
        post_attempted=True,
        evaluation_status="evaluated",
        trace_status="complete",
    )
    next_item = ledger.reserve_full_battery_item(
        authorization_event_id=authorization["event_id"],
        run_name="next-item",
        item_id=missing[1],
        contract_sha256="c" * 64,
        request_identity_sha256="n" * 64,
    )
    assert next_item["item_id"] == missing[1]
    with pytest.raises(LedgerContractError, match="já foi consumida"):
        ledger.reserve_full_battery_retry(
            authorization_event_id=authorization["event_id"],
            predecessor_execution_id=predecessor["execution_id"],
            run_name="attempt-3",
            item_id=missing[0],
            contract_sha256="c" * 64,
            request_identity_sha256="r" * 64,
        )


def test_long_context_luna_judge_request_omits_temperature(monkeypatch, tmp_path: Path):
    contract = _contract()
    contract["model_profiles"]["mini"] = {
        "deployment": "seiia-ds-gpt-luna",
        "canonical_model": "gpt-5.6-luna",
        "provider": "openai",
    }
    contract["judge"].update(
        {
            "deployment": "seiia-ds-gpt-luna",
            "canonical_model": "gpt-5.6-luna",
            "provider": "openai",
            "temperature": None,
        }
    )
    monkeypatch.setattr(
        runner_module, "load_judge_artifacts", lambda *_args: ("system", "user", {})
    )
    monkeypatch.setattr(runner_module, "build_judge_input", lambda **_kwargs: {})
    monkeypatch.setattr(runner_module, "judge_messages", lambda **_kwargs: [])
    monkeypatch.setattr(runner_module, "parse_judge_output", lambda *_args: {})
    expected_score = MagicMock()
    monkeypatch.setattr(
        runner_module, "score_judge_output", lambda *_args, **_kwargs: expected_score
    )
    response = SimpleNamespace(
        id="judge-response",
        model="seiia-ds-gpt-luna",
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            prompt_tokens_details=SimpleNamespace(cached_tokens=0),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
    )
    client = MagicMock()
    client.chat.completions.create.return_value = response

    score, _, attempts, _ = _judge_with_retries(
        client=client,
        model="seiia-ds-gpt-luna",
        contract=contract,
        item=_item(),
        material=MagicMock(),
        answer="answer",
        evidence_package=[],
        max_attempts=1,
        backoff_s=1,
        attempts_path=tmp_path / "attempts.json",
    )

    assert score is expected_score
    assert attempts[0]["status"] == "accepted"
    assert "temperature" not in client.chat.completions.create.call_args.kwargs


def test_long_context_judge_contract_retry_receives_rejection_feedback(
    monkeypatch, tmp_path: Path
):
    contract = _contract()
    base_messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "judge input"},
    ]
    monkeypatch.setattr(
        runner_module, "load_judge_artifacts", lambda *_args: ("system", "user", {})
    )
    monkeypatch.setattr(runner_module, "build_judge_input", lambda **_kwargs: {})
    monkeypatch.setattr(
        runner_module, "judge_messages", lambda **_kwargs: base_messages
    )
    monkeypatch.setattr(runner_module, "parse_judge_output", lambda *_args: {})
    expected_score = MagicMock()
    score_calls = iter(
        [
            JudgeV2ContractError("evidence_basis=none não pode ter referência"),
            expected_score,
        ]
    )

    def score_or_raise(*_args, **_kwargs):
        value = next(score_calls)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(runner_module, "score_judge_output", score_or_raise)
    monkeypatch.setattr(runner_module.time, "sleep", lambda *_args: None)
    responses = [
        SimpleNamespace(
            id=f"judge-response-{attempt}",
            model=contract["judge"]["canonical_model"],
            usage=SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=5,
                prompt_tokens_details=SimpleNamespace(cached_tokens=0),
                completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
            ),
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
        )
        for attempt in (1, 2)
    ]
    client = MagicMock()
    client.chat.completions.create.side_effect = responses

    score, _, attempts, _ = _judge_with_retries(
        client=client,
        model=contract["judge"]["deployment"],
        contract=contract,
        item=_item(),
        material=MagicMock(),
        answer="answer",
        evidence_package=[],
        max_attempts=2,
        backoff_s=1,
        attempts_path=tmp_path / "attempts.json",
    )

    first_messages = client.chat.completions.create.call_args_list[0].kwargs["messages"]
    retry_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert first_messages == base_messages
    assert retry_messages[:2] == base_messages
    assert retry_messages[-1]["role"] == "user"
    assert (
        "evidence_basis=none não pode ter referência" in retry_messages[-1]["content"]
    )
    assert score is expected_score
    assert [attempt["status"] for attempt in attempts] == ["rejected", "accepted"]


def test_pre_agent_document_fetch_failure_has_retry_proof(tmp_path: Path):
    raw_path = tmp_path / "stream.raw.sse"
    raw_path.write_text(
        'data: {"type":"status"}\n\n'
        'data: {"type":"error","status_code":409,'
        '"diagnostic":{"category":"document_fetch_failed",'
        '"stage":"fetch_validate_before_write","fingerprint":"abc"}}\n\n'
    )

    proof = _pre_agent_retry_proof(
        raw_path,
        [
            {
                "event_type": "agent_failed",
                "post_attempted": True,
                "evaluation_status": "technical_unavailable",
                "trace_status": "technical_unavailable",
            }
        ],
    )

    assert proof == {
        "failure_stage": "pre_agent",
        "failure_category": "document_fetch_failed",
        "technical_failure": True,
        "zero_generations": True,
        "zero_tools": True,
        "zero_judge_calls": True,
        "zero_tokens": True,
        "zero_cost": True,
        "diagnostic_fingerprint": "abc",
        "raw_sse_sha256": file_sha256(raw_path),
    }


def test_pre_agent_process_metadata_failure_has_retry_proof(tmp_path: Path):
    raw_path = tmp_path / "stream.raw.sse"
    raw_path.write_text(
        'data: {"type":"status"}\n\n'
        'data: {"type":"error","status_code":409,'
        '"diagnostic":{"category":"fresh_process_metadata_missing",'
        '"fingerprint":"def"}}\n\n'
    )

    proof = _pre_agent_retry_proof(
        raw_path,
        [
            {
                "event_type": "agent_failed",
                "post_attempted": True,
                "evaluation_status": "technical_unavailable",
                "trace_status": "technical_unavailable",
            }
        ],
    )

    assert proof is not None
    assert proof["failure_stage"] == "pre_agent"
    assert proof["failure_category"] == "fresh_process_metadata_missing"
    assert proof["zero_generations"] is True
    assert proof["zero_tools"] is True
    assert proof["zero_judge_calls"] is True
    assert proof["zero_tokens"] is True
    assert proof["zero_cost"] is True


def test_rate_limit_retry_proof_requires_conservative_cooldown(tmp_path: Path):
    raw_path = tmp_path / "stream.raw.sse"
    raw_path.write_text(
        'data: {"type":"status","timestamp":90}\n\n'
        'data: {"type":"reasoning","timestamp":95}\n\n'
        'data: {"type":"error","timestamp":100,"status_code":500,'
        '"detail":"APIError: requests exceeded rate limit."}\n\n'
    )
    rows = [
        {
            "event_type": "agent_failed",
            "post_attempted": True,
            "evaluation_status": "technical_unavailable",
            "trace_status": "technical_unavailable",
        }
    ]

    before = _rate_limit_retry_proof(raw_path, rows, now_s=999)
    after = _rate_limit_retry_proof(raw_path, rows, now_s=1000)

    assert before is not None
    assert before["cooldown_satisfied"] is False
    assert after is not None
    assert after["cooldown_satisfied"] is True
    assert after["failure_category"] == "model_rate_limit"
    assert after["reasoning_frames"] == 1
    assert after["content_frames"] == 0
    assert "zero_tokens" not in after
    assert "zero_cost" not in after


def test_battery_usage_keeps_known_subtotal_when_cache_write_is_missing():
    usage = runner_module._aggregate_battery_usage(
        [
            {
                "usage": {
                    "total_cost_usd": None,
                    "cost": {
                        "known_subtotal_excluding_cache_write_usd": {
                            "if_all_requests_short_context": 1.25,
                            "if_all_requests_long_context": 2.5,
                        }
                    },
                    "by_scope": {},
                    "by_model": {},
                }
            },
            {
                "usage": {
                    "total_cost_usd": None,
                    "cost": {
                        "known_subtotal_excluding_cache_write_usd": {
                            "short_context": 0.75,
                            "long_context": 1.5,
                        }
                    },
                    "by_scope": {},
                    "by_model": {},
                }
            },
        ]
    )

    assert usage["total_cost_usd"] is None
    assert usage["missing_only"] == ["cache_write"]
    assert usage["known_subtotal_excluding_cache_write_usd"] == {
        "if_all_requests_short_context": 2.0,
        "if_all_requests_long_context": 4.0,
    }


@pytest.mark.parametrize(
    (
        "quality",
        "comparability",
        "observability",
        "integrity",
        "technical",
        "continue_expected",
    ),
    [
        ("passed", "passed", "passed", "passed", [], True),
        ("failed", "passed", "passed", "passed", [], True),
        ("passed", "passed", "failed", "failed", [{"stage": "trace"}], False),
        ("passed", "failed", "passed", "passed", [], False),
        ("passed", "passed", "passed", "failed", [], False),
    ],
)
def test_full_battery_continues_quality_only_and_fails_fast_on_technical_errors(
    quality,
    comparability,
    observability,
    integrity,
    technical,
    continue_expected,
):
    result = {
        "gate": {
            "dimensions": {
                "quality": {"status": quality},
                "comparability": {"status": comparability},
                "observability": {"status": observability},
                "integrity_technical": {
                    "status": integrity,
                    "checks": {
                        "single_item": True,
                        "transport_http_200_terminal_end": not (
                            integrity == "failed" and not technical
                        ),
                    },
                },
            }
        },
        "technical_failures": technical,
    }
    assert _battery_continuation(result)["continue"] is continue_expected


def _invalid_pre_agent_proof() -> dict[str, object]:
    return {
        "failure_stage": "pre_agent",
        "technical_failure": True,
        "zero_generations": True,
        "zero_tools": True,
        "zero_judge_calls": True,
        "zero_tokens": True,
        "zero_cost": True,
    }


def _failed_predecessor(ledger: V2Ledger) -> tuple[str, str]:
    reservation = ledger.reserve(
        run_name="invalid-run",
        item_id=SECOND_CANARY_ITEM_ID,
        contract_sha256="c" * 64,
        request_identity_sha256="r" * 64,
    )
    execution_id = reservation["execution_id"]
    trace_id = "invalid-trace"
    ledger.transition(
        execution_id,
        event_type="trace_bound",
        trace_id=trace_id,
        post_attempted=False,
        trace_status="pending_trace",
    )
    ledger.transition(
        execution_id,
        event_type="agent_failed",
        trace_id=trace_id,
        post_attempted=True,
        evaluation_status="technical_unavailable",
        trace_status="technical_unavailable",
    )
    return execution_id, trace_id


def test_ledger_preserves_controlled_replacement_chain_and_refuses_fourth_attempt(
    tmp_path: Path,
):
    os.chmod(tmp_path, 0o700)
    ledger = V2Ledger(tmp_path / "ledger.jsonl")
    execution_id, trace_id = _failed_predecessor(ledger)

    authorization = ledger.authorize_replacement(
        predecessor_execution_id=execution_id,
        predecessor_trace_id=trace_id,
        item_id=SECOND_CANARY_ITEM_ID,
        reason="wrong_sei_environment_pre_agent",
        captain_authorization="captain-decision-20260723",
        proof=_invalid_pre_agent_proof(),
    )
    replacement = ledger.reserve_replacement(
        authorization_event_id=authorization["event_id"],
        predecessor_execution_id=execution_id,
        run_name="replacement-run",
        item_id=SECOND_CANARY_ITEM_ID,
        contract_sha256="c" * 64,
        request_identity_sha256="n" * 64,
    )

    assert replacement["replacement_of_execution_id"] == execution_id
    assert (
        replacement["replacement_authorization_event_id"] == authorization["event_id"]
    )
    assert replacement["run_name"] != "invalid-run"
    replacement_execution_id = replacement["execution_id"]
    replacement_trace_id = "replacement-trace"
    ledger.transition(
        replacement_execution_id,
        event_type="trace_bound",
        trace_id=replacement_trace_id,
        post_attempted=False,
        trace_status="pending_trace",
    )
    ledger.transition(
        replacement_execution_id,
        event_type="agent_failed",
        trace_id=replacement_trace_id,
        post_attempted=True,
        evaluation_status="technical_unavailable",
        trace_status="technical_unavailable",
    )
    remediation_proof = {
        **_invalid_pre_agent_proof(),
        "failure_category": "materialized_missing",
    }
    remediation_authorization = ledger.authorize_remediation_replay(
        predecessor_execution_id=replacement_execution_id,
        predecessor_trace_id=replacement_trace_id,
        item_id=SECOND_CANARY_ITEM_ID,
        reason="ocr_materialization_pre_agent",
        captain_authorization="captain-ocr-decision-20260724",
        proof=remediation_proof,
    )
    remediation = ledger.reserve_remediation_replay(
        authorization_event_id=remediation_authorization["event_id"],
        predecessor_execution_id=replacement_execution_id,
        run_name="ocr-remediation-run",
        item_id=SECOND_CANARY_ITEM_ID,
        contract_sha256="c" * 64,
        request_identity_sha256="o" * 64,
    )

    assert remediation["remediation_of_execution_id"] == replacement_execution_id
    with pytest.raises(LedgerContractError, match="remediação OCR já consumida"):
        ledger.reserve_remediation_replay(
            authorization_event_id=remediation_authorization["event_id"],
            predecessor_execution_id=replacement_execution_id,
            run_name="fourth-run",
            item_id=SECOND_CANARY_ITEM_ID,
            contract_sha256="c" * 64,
            request_identity_sha256="x" * 64,
        )


@pytest.mark.parametrize(
    "field",
    [
        "technical_failure",
        "zero_generations",
        "zero_tools",
        "zero_judge_calls",
        "zero_tokens",
        "zero_cost",
    ],
)
def test_ledger_refuses_replacement_when_predecessor_proof_is_not_zero(
    tmp_path: Path, field: str
):
    os.chmod(tmp_path, 0o700)
    ledger = V2Ledger(tmp_path / "ledger.jsonl")
    execution_id, trace_id = _failed_predecessor(ledger)
    proof = _invalid_pre_agent_proof()
    proof[field] = False

    with pytest.raises(LedgerContractError, match="prova da tentativa inválida"):
        ledger.authorize_replacement(
            predecessor_execution_id=execution_id,
            predecessor_trace_id=trace_id,
            item_id=SECOND_CANARY_ITEM_ID,
            reason="wrong_sei_environment_pre_agent",
            captain_authorization="captain-decision-20260723",
            proof=proof,
        )


def _live_preflight_passed() -> dict[str, object]:
    return {
        "schema_version": "benchmark-sei-live-preflight-v1",
        "status": "passed",
        "http_status": 200,
        "live_query_performed": True,
        "public_api_scope_coherent": True,
        "credential_present": True,
        "public_endpoint_sha256": "a" * 64,
        "api_endpoint_sha256": "b" * 64,
        "api_origin_sha256": "a" * 64,
        "credential_sha256": "c" * 64,
        "response_type": "dataframe",
        "response_nonempty": True,
        "process_matched": True,
        "duration_s": 0.1,
    }


def _live_expectation() -> dict[str, str]:
    return {
        "public_endpoint_sha256": "a" * 64,
        "api_endpoint_sha256": "b" * 64,
        "api_origin_sha256": "a" * 64,
        "credential_sha256": "c" * 64,
    }


def test_live_preflight_occurs_before_ledger_reservation(monkeypatch, tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    order: list[str] = []
    ledger = MagicMock()
    ledger.reserve.side_effect = lambda **_kwargs: order.append("reserve") or {
        "execution_id": "new-execution"
    }
    monkeypatch.setattr(
        runner_module,
        "_run_live_sei_preflight",
        lambda **_kwargs: order.append("live-preflight") or _live_preflight_passed(),
    )

    reservation, diagnostic = _preflight_and_reserve(
        ledger=ledger,
        live_preflight_path=tmp_path / "live.json",
        http_client=MagicMock(),
        base_url="https://127.0.0.1:8188",
        process_id="proc-1",
        expectation=_live_expectation(),
        reservation_kwargs={
            "run_name": "run",
            "item_id": SECOND_CANARY_ITEM_ID,
            "contract_sha256": "d" * 64,
            "request_identity_sha256": "e" * 64,
        },
    )

    assert order == ["live-preflight", "reserve"]
    assert reservation["execution_id"] == "new-execution"
    assert diagnostic["status"] == "passed"


def test_failed_live_preflight_does_not_reserve_or_post(monkeypatch, tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    ledger = MagicMock()
    failed = {**_live_preflight_passed(), "status": "failed", "http_status": 401}
    monkeypatch.setattr(
        runner_module, "_run_live_sei_preflight", lambda **_kwargs: failed
    )

    with pytest.raises(CanaryV2Error, match="preflight live"):
        _preflight_and_reserve(
            ledger=ledger,
            live_preflight_path=tmp_path / "live.json",
            http_client=MagicMock(),
            base_url="https://127.0.0.1:8188",
            process_id="proc-1",
            expectation=_live_expectation(),
            reservation_kwargs={
                "run_name": "run",
                "item_id": SECOND_CANARY_ITEM_ID,
                "contract_sha256": "d" * 64,
                "request_identity_sha256": "e" * 64,
            },
        )

    ledger.reserve.assert_not_called()
    assert json.loads((tmp_path / "live.json").read_text())["http_status"] == 401


def test_static_preflight_alone_is_not_accepted_as_live_proof():
    with pytest.raises(CanaryV2Error, match="preflight live"):
        _validate_live_sei_preflight(
            {"status": "ready", "benchmark_no_cache_required": True},
            _live_expectation(),
        )


def test_sei_expectation_rejects_coherent_nonproduction_scope(tmp_path: Path):
    env_file = tmp_path / "sei.env"
    env_file.write_text(
        "SEI_ADDRESS=https://staging.example.test\n"
        "SEI_API_DB_ADDRESS=https://staging.example.test/sei/controlador_ws.php\n"
        "SEI_API_DB_IDENTIFIER_SERVICE=opaque\n"
    )

    with pytest.raises(CanaryV2Error, match="escopo de produção"):
        _load_sei_preflight_expectation(env_file)


@pytest.mark.parametrize(
    (
        "answer_nonempty",
        "target_alignment",
        "hallucination",
        "negative",
        "negative_correct",
        "failed_check",
    ),
    [
        (False, True, False, False, None, "response_nonempty"),
        (True, False, False, False, None, "target_alignment"),
        (True, True, True, False, None, "hallucination_absent"),
        (True, True, False, True, False, "negativa_correta"),
    ],
)
def test_only_catastrophic_quality_conditions_block(
    answer_nonempty,
    target_alignment,
    hallucination,
    negative,
    negative_correct,
    failed_check,
):
    gate = classify_quality_gate(
        numeric={
            "groundedness": 0.0,
            "completeness": 0.0,
            "citation_quality": 0.0,
            "overall": 0.0,
        },
        boolean={
            "hallucination": hallucination,
            "negativa_correta": negative_correct,
        },
        auxiliary={"target_alignment": target_alignment},
        negative=negative,
        answer_nonempty=answer_nonempty,
        thresholds=_contract()["thresholds"],
    )

    assert gate["status"] == "failed"
    assert gate["blocking_checks"][failed_check] is False
    assert all(
        diagnostic["blocking"] is False
        for diagnostic in gate["non_blocking_diagnostics"][
            "historical_thresholds"
        ].values()
    )


@pytest.mark.parametrize(
    (
        "canary_item_id",
        "cold_start",
        "trace_ok",
        "usage_coverage",
        "technical_failures",
        "failed_dimension",
    ),
    [
        (CANARY_ITEM_ID, False, True, True, [], None),
        (SECOND_CANARY_ITEM_ID, False, True, True, [], "comparability"),
        (SECOND_CANARY_ITEM_ID, True, False, True, [], "observability"),
        (SECOND_CANARY_ITEM_ID, True, True, False, [], "observability"),
        (
            SECOND_CANARY_ITEM_ID,
            True,
            True,
            True,
            [{"stage": "trace"}],
            "integrity_technical",
        ),
    ],
)
def test_canary_gate_keeps_dimensions_separate_and_never_authorizes_battery(
    canary_item_id,
    cold_start,
    trace_ok,
    usage_coverage,
    technical_failures,
    failed_dimension,
):
    result = {
        "item_id": canary_item_id,
        "transport": {"http_status": 200, "terminal_type": "end"},
        "context_disclosure_observed": True,
        "no_cache": {
            "requested": True,
            "effective": True,
            "cold_start_comparable": cold_start,
        },
        "technical_failures": technical_failures,
    }
    quality_gate = classify_quality_gate(
        numeric={
            "groundedness": 0.0,
            "completeness": 0.0,
            "citation_quality": 0.0,
            "overall": 0.0,
        },
        boolean={"hallucination": False, "negativa_correta": None},
        auxiliary={"target_alignment": True},
        negative=False,
        answer_nonempty=True,
        thresholds=_contract()["thresholds"],
    )

    gate = _build_canary_gate(
        result,
        canary_item_id=canary_item_id,
        quality_gate=quality_gate,
        trace_ok=trace_ok,
        usage_coverage=usage_coverage,
    )

    assert gate["dimensions"]["quality"]["status"] == "passed"
    assert gate["full_battery_authorized"] is False
    assert gate["stop_after_canary"] is True
    if failed_dimension is None:
        assert gate["status"] == "passed"
        assert gate["failed_dimensions"] == []
    else:
        assert gate["status"] == "failed"
        assert failed_dimension in gate["failed_dimensions"]


def test_sanitized_result_retains_trace_id_without_internal_url():
    sanitized = _sanitized_result(
        {
            "run_name": "run-v2",
            "item_id": "case-0960k-q2-synthesis",
            "trace_id": "trace-v2",
            "trace_url": "http://internal-langfuse/project/traces/trace-v2",
        }
    )

    assert sanitized["trace_id"] == "trace-v2"
    assert sanitized["trace_url"] == "[retida no artefato protegido]"


def test_readback_retries_are_idempotent_but_official_evaluation_is_unique(
    tmp_path: Path,
):
    os.chmod(tmp_path, 0o700)
    ledger = V2Ledger(tmp_path / "ledger.jsonl")
    reservation = ledger.reserve(
        run_name="run-v2",
        item_id="case-0960k-q2-synthesis",
        contract_sha256="c" * 64,
        request_identity_sha256="r" * 64,
    )
    execution_id = reservation["execution_id"]
    for attempt in (1, 2, 3):
        ledger.transition(
            execution_id,
            event_type="trace_readback_attempt",
            trace_id="trace-v2",
            post_attempted=True,
            trace_status="pending_trace" if attempt < 3 else "complete",
            detail={"attempt": attempt},
        )
    ledger.transition(
        execution_id,
        event_type="official_evaluation",
        trace_id="trace-v2",
        evaluation_status="evaluated",
        artifact_sha256="s" * 64,
    )
    with pytest.raises(LedgerContractError, match="duplicada"):
        ledger.transition(
            execution_id,
            event_type="official_evaluation",
            trace_id="trace-v2",
            evaluation_status="evaluated",
            artifact_sha256="s" * 64,
        )
    ledger.transition(
        execution_id,
        event_type="trace_complete",
        trace_id="trace-v2",
        trace_status="complete",
    )
    reclassified = ledger.record_gate_reclassification(
        execution_id=execution_id,
        trace_id="trace-v2",
        policy_version="quality-gates-v2",
        authorization="captain-decision",
        source_artifact_sha256="a" * 64,
        derived_artifact_sha256="b" * 64,
    )
    assert reclassified["event_type"] == "gate_reclassified"
    assert (
        len(
            [
                event
                for event in ledger.events()
                if event["event_type"] == "official_evaluation"
            ]
        )
        == 1
    )
    with pytest.raises(LedgerContractError, match="já aplicada"):
        ledger.record_gate_reclassification(
            execution_id=execution_id,
            trace_id="trace-v2",
            policy_version="quality-gates-v2",
            authorization="captain-decision",
            source_artifact_sha256="a" * 64,
            derived_artifact_sha256="b" * 64,
        )
    assert ledger.official_key(execution_id) == (
        "run-v2",
        "case-0960k-q2-synthesis",
        "trace-v2",
        "c" * 64,
    )


def test_manifest_rejects_protected_content_field(tmp_path: Path):
    manifest = json.loads(MANIFEST_PATH.read_text())
    manifest["items"][0]["question"]["text"] = "conteúdo proibido"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ManifestContractError, match="Additional properties"):
        validate_manifest(path)
