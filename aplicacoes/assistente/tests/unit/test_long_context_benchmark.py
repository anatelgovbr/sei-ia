"""Testes offline do runner/scorer específico de contexto longo."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import ToolMessage

_EXP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "experimentos",
    "latencia-session-vs-classico",
)
sys.path.insert(0, os.path.join(_EXP_DIR, "scripts", "shared"))
sys.path.insert(0, os.path.join(_EXP_DIR, "scripts", "long-context"))

import long_context_contract as contract  # noqa: E402
import long_context_scorer as scorer  # noqa: E402
import run_long_context_benchmark as runner  # noqa: E402
from long_context_contract import (  # noqa: E402
    ContractError,
    ExecutionPolicy,
    SSEProtocolError,
    TopicFactory,
    aggregate_agent_calls,
    aggregate_tool_calls,
    build_execution_payload,
    combine_call_metrics,
    consume_sse,
    project_id_from_response,
    stable_digest,
    validate_dataset,
    validate_preflight,
)
from long_context_evidence import build_evidence_package  # noqa: E402
from long_context_scorer import (  # noqa: E402
    AtomicClaim,
    JudgeAssessment,
    calculate_scores,
    emit_sanitized_scores,
    parse_assessment,
)

from sei_ia.services.benchmark_metrics import BenchmarkToolHandler  # noqa: E402


@dataclass
class SyntheticDataset:
    name: str
    id: str
    project_id: str
    items: list[SimpleNamespace]


def _case_id(item_id: str) -> str:
    return "-".join(item_id.split("-")[:2])


def _synthetic_dataset(monkeypatch) -> SyntheticDataset:
    hashes: dict[str, str] = {}
    metrics: dict[str, dict[str, int]] = {}
    natural_hashes: dict[str, dict[str, str]] = {}
    items = []
    for item_id in sorted(contract.EXPECTED_ITEM_IDS):
        case_id = _case_id(item_id)
        tree = [
            {
                "id_procedimento": f"proc-{case_id}",
                "id_documentos": [
                    {
                        "id_documento": f"doc-{case_id}-1",
                        "download_ext": False,
                    },
                    {
                        "id_documento": f"doc-{case_id}-2",
                        "download_ext": True,
                    },
                ],
            }
        ]
        payload_hash = stable_digest({"id_procedimentos": tree})
        hashes[case_id] = payload_hash
        metrics[case_id] = {"documents": 2, "tokens": 1234}
        natural_hashes[item_id] = {
            "question": contract.text_digest("pergunta sintética"),
            "gold": contract.text_digest("gold sintético"),
        }
        is_negative = item_id.endswith("insufficient-evidence")
        is_synthesis = item_id.endswith("synthesis")
        expected = {
            "categoria": (
                "negativa"
                if is_negative
                else "cross-document"
                if is_synthesis
                else "factual"
            ),
            "gold_answer": "gold sintético",
            "elementos_obrigatorios": ["elemento sintético"],
            "indicadores_alucinacao": ["invenção sintética"],
            "entendimento_abstrato": "critério sintético",
            "evaluation_design_version": contract.EVALUATION_DESIGN_VERSION,
            "scoring": {
                "target_alignment": "boolean",
                "groundedness": "supported_over_verified_claims",
                "unverified_claim": "metric_nd",
                "hallucination_count": "contradicted_or_invented_claims",
            },
            "evidence": [] if is_negative else [{"document_id": "doc"}],
        }
        if is_negative:
            expected["absence_evidence"] = {
                "reference": f"absence-{item_id}",
                "limitation": "lexical_method_only_not_universal_absence",
            }
        items.append(
            SimpleNamespace(
                id=item_id,
                input={
                    "id_usuario": 1,
                    "id_topico": 2,
                    "text": "pergunta sintética",
                    "id_procedimentos": tree,
                    "use_websearch": False,
                    "skip_memory": True,
                },
                expected_output=expected,
                metadata={
                    "case_id": case_id,
                    "question_type": (
                        "insufficient-evidence"
                        if is_negative
                        else "synthesis"
                        if is_synthesis
                        else "factual"
                    ),
                    "document_count": 2,
                    "independent_document_tokens": 1234,
                    "procedure_count": 1,
                    "canonical_payload_hash": payload_hash,
                    "canonical_question_sha256": contract.text_digest(
                        "pergunta sintética"
                    ),
                    "canonical_gold_answer_sha256": contract.text_digest(
                        "gold sintético"
                    ),
                    "n": 1,
                    "context_disclosure_threshold": 200000,
                    "evaluation_design_version": contract.EVALUATION_DESIGN_VERSION,
                    "target_anchor": {
                        "kind": contract.EXPECTED_TARGET_ANCHOR_KINDS[item_id],
                        "reference_count": 2 if item_id == runner.CANARY_ITEM_ID else 0,
                        "reference_sha256": (
                            ["a" * 64, "b" * 64]
                            if item_id == runner.CANARY_ITEM_ID
                            else []
                        ),
                    },
                },
            )
        )
    monkeypatch.setattr(contract, "EXPECTED_PAYLOAD_HASHES", hashes)
    monkeypatch.setattr(contract, "EXPECTED_CASE_METRICS", metrics)
    monkeypatch.setattr(contract, "EXPECTED_NATURAL_TEXT_HASHES", natural_hashes)
    return SyntheticDataset(
        name=contract.DATASET_NAME,
        id=contract.DATASET_ID,
        project_id="project-ok",
        items=items,
    )


def _assessment(
    *,
    checklist=(True, True),
    verdicts=("supported", "supported"),
    abstract=1.0,
    negative=None,
    target_alignment=True,
) -> JudgeAssessment:
    negative = negative or {}
    return JudgeAssessment(
        target_alignment=target_alignment,
        checklist=tuple(checklist),
        claims=tuple(
            AtomicClaim(
                text=f"claim-{index}",
                verdict=verdict,
                evidence_references=() if verdict == "unverified" else (1,),
            )
            for index, verdict in enumerate(verdicts)
        ),
        abstract_understanding=abstract,
        rationale="rationale sensível",
        abstained=negative.get("abstained"),
        numerator_missing=negative.get("numerator_missing"),
        denominator_missing=negative.get("denominator_missing"),
        invented_rate=negative.get("invented_rate"),
        universal_absence_claim=negative.get("universal_absence_claim"),
    )


def test_project_guard_accepts_only_exact_target():
    assert (
        project_id_from_response(
            {"data": [{"id": "project-ok", "name": contract.TARGET_PROJECT}]}
        )
        == "project-ok"
    )
    with pytest.raises(ContractError):
        project_id_from_response({"data": [{"id": "x", "name": "outro"}]})
    with pytest.raises(ContractError):
        project_id_from_response(
            {
                "data": [
                    {"id": "a", "name": contract.TARGET_PROJECT},
                    {"id": "b", "name": contract.TARGET_PROJECT},
                ]
            }
        )


def test_dataset_guard_proves_cardinality_identity_and_payload(monkeypatch):
    dataset = _synthetic_dataset(monkeypatch)
    items = validate_dataset(dataset, "project-ok")
    assert len(items) == 9
    assert {item.id for item in items} == contract.EXPECTED_ITEM_IDS

    dataset.items.pop()
    with pytest.raises(ContractError, match="nove"):
        validate_dataset(dataset, "project-ok")


def test_dataset_guard_rejects_project_and_tree_drift(monkeypatch):
    dataset = _synthetic_dataset(monkeypatch)
    with pytest.raises(ContractError, match="outro projeto"):
        validate_dataset(dataset, "project-wrong")

    dataset.items[0].input["id_procedimentos"][0]["id_documentos"].reverse()
    with pytest.raises(ContractError, match="payload canônico"):
        validate_dataset(dataset, "project-ok")

    dataset = _synthetic_dataset(monkeypatch)
    dataset.items[0].metadata["independent_document_tokens"] += 1
    with pytest.raises(ContractError, match="tokens medidos"):
        validate_dataset(dataset, "project-ok")

    dataset = _synthetic_dataset(monkeypatch)
    dataset.items[0].metadata["case_id"] = "case-5120k"
    with pytest.raises(ContractError, match="caso associado"):
        validate_dataset(dataset, "project-ok")

    dataset = _synthetic_dataset(monkeypatch)
    dataset.items[0].input["text"] = "pergunta alterada"
    with pytest.raises(ContractError, match="pergunta natural aprovada"):
        validate_dataset(dataset, "project-ok")

    dataset = _synthetic_dataset(monkeypatch)
    dataset.items[0].expected_output["gold_answer"] = "gold alterado"
    with pytest.raises(ContractError, match="gold natural aprovado"):
        validate_dataset(dataset, "project-ok")


def test_dataset_guard_rejects_content_and_self_attested_hash_changed_together(
    monkeypatch,
):
    dataset = _synthetic_dataset(monkeypatch)
    item = dataset.items[0]
    item.input["text"] = "pergunta e metadata alteradas juntas"
    item.metadata["canonical_question_sha256"] = contract.text_digest(
        item.input["text"]
    )
    with pytest.raises(ContractError, match="pergunta natural aprovada"):
        validate_dataset(dataset, "project-ok")

    dataset = _synthetic_dataset(monkeypatch)
    item = dataset.items[0]
    item.expected_output["gold_answer"] = "gold e metadata alterados juntos"
    item.metadata["canonical_gold_answer_sha256"] = contract.text_digest(
        item.expected_output["gold_answer"]
    )
    with pytest.raises(ContractError, match="gold natural aprovado"):
        validate_dataset(dataset, "project-ok")


def test_dataset_guard_cross_validates_negative_id_question_type_and_category(
    monkeypatch,
):
    dataset = _synthetic_dataset(monkeypatch)
    negative = next(
        item for item in dataset.items if item.id.endswith("insufficient-evidence")
    )
    negative.expected_output["categoria"] = "factual"
    with pytest.raises(ContractError, match="categoria divergente"):
        validate_dataset(dataset, "project-ok")

    dataset = _synthetic_dataset(monkeypatch)
    negative = next(
        item for item in dataset.items if item.id.endswith("insufficient-evidence")
    )
    negative.metadata["question_type"] = "factual"
    with pytest.raises(ContractError, match="question_type divergente"):
        validate_dataset(dataset, "project-ok")


def test_corrected_canary_anchor_is_required_without_changing_canonical_payload(
    monkeypatch,
):
    dataset = _synthetic_dataset(monkeypatch)
    canary = next(item for item in dataset.items if item.id == runner.CANARY_ITEM_ID)
    payload_before = stable_digest(
        {"id_procedimentos": canary.input["id_procedimentos"]}
    )
    anchor = canary.metadata["target_anchor"]
    assert anchor["kind"] == "official_document_pair"
    assert anchor["reference_count"] == 2
    assert len(set(anchor["reference_sha256"])) == 2

    canary.metadata["target_anchor"] = {
        "kind": "ambiguous",
        "reference_count": 0,
        "reference_sha256": [],
    }
    with pytest.raises(ContractError, match="âncora do alvo"):
        validate_dataset(dataset, "project-ok")
    assert (
        stable_digest({"id_procedimentos": canary.input["id_procedimentos"]})
        == payload_before
    )


def test_dataset_guard_rejects_threshold_override(monkeypatch):
    dataset = _synthetic_dataset(monkeypatch)
    dataset.items[0].input["inject_tokens_threshold"] = 200000
    with pytest.raises(ContractError, match="override"):
        validate_dataset(dataset, "project-ok")


def test_context_disclosure_requires_a_reference_from_document_inventory(monkeypatch):
    dataset = _synthetic_dataset(monkeypatch)
    item = dataset.items[0]
    reference = {
        "path_sha256": "a" * 64,
        "kind": "document",
        "suffix": ".txt",
    }
    tool_summary = {
        "calls": [
            {
                "category": "filesystem",
                "outcome": "success",
                "returned_bytes": 10,
                "returned_tokens": 5,
                "files_opened": [reference],
            }
        ],
        "document_inventory": [
            {
                "path_sha256": "b" * 64,
                "content_sha256": "c" * 64,
                "bytes": 10,
                "tokens": 5,
            }
        ],
    }
    metadata = {
        "all_tokens_counter": 200001,
        "documentos": runner.EXPECTED_CASE_METRICS[item.metadata["case_id"]][
            "documents"
        ],
    }

    assert (
        runner._context_disclosure_observed(
            item=item,
            metadata=metadata,
            tool_summary=tool_summary,
        )
        is False
    )
    tool_summary["document_inventory"][0]["path_sha256"] = reference["path_sha256"]
    assert runner._context_disclosure_observed(
        item=item,
        metadata=metadata,
        tool_summary=tool_summary,
    )


def test_langfuse_client_uses_explicit_readback_timeout(monkeypatch):
    captured = {}

    class FakeLangfuse:
        def auth_check(self):
            return True

    def fake_langfuse(**kwargs):
        captured.update(kwargs)
        return FakeLangfuse()

    monkeypatch.setattr(runner, "Langfuse", fake_langfuse)

    client = runner._langfuse_client(
        {
            "LANGFUSE_URL": "https://langfuse.invalid",
            "LANGFUSE_PUBLIC_KEY": "public",
            "LANGFUSE_SECRET_KEY": "secret",
        }
    )

    assert isinstance(client, FakeLangfuse)
    assert captured["timeout"] == 90


@pytest.mark.parametrize("prefix", ["LANGFUSE", "LANGFUSE_COMPARATIVO"])
def test_langfuse_credentials_accept_standard_and_legacy_names(
    monkeypatch, tmp_path, prefix
):
    for name in (
        "LANGFUSE_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_COMPARATIVO_URL",
        "LANGFUSE_COMPARATIVO_PUBLIC_KEY",
        "LANGFUSE_COMPARATIVO_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / "runner.env"
    env_file.write_text(
        f"{prefix}_URL=https://langfuse.invalid\n"
        f"{prefix}_PUBLIC_KEY=public\n"
        f"{prefix}_SECRET_KEY=secret\n"
    )

    credentials = runner._load_langfuse_credentials(env_file)

    assert credentials == {
        "LANGFUSE_URL": "https://langfuse.invalid",
        "LANGFUSE_PUBLIC_KEY": "public",
        "LANGFUSE_SECRET_KEY": "secret",
    }


def test_preflight_mode_uses_local_tls_policy_for_isolated_stack(monkeypatch):
    captured = {}
    http_client = object()
    dataset = object()
    item = object()
    args = SimpleNamespace(
        preflight=True,
        execute_canary=False,
        continue_run=False,
        execute_full_battery=False,
        env_file=None,
        base_url="https://127.0.0.1:8188",
        timeout_s=30.0,
    )

    class FakeClientContext:
        def __enter__(self):
            return http_client

        def __exit__(self, *_args):
            return False

    def fake_http_client(_timeout_s, *, isolated=False):
        captured["isolated"] = isolated
        return FakeClientContext()

    langfuse = SimpleNamespace(get_dataset=lambda *_args, **_kwargs: dataset)
    monkeypatch.setattr(runner, "_parse_args", lambda: args)
    monkeypatch.setattr(runner, "_load_langfuse_credentials", lambda _path: {})
    monkeypatch.setattr(runner, "_project_gate", lambda _credentials: "project")
    monkeypatch.setattr(runner, "_langfuse_client", lambda _credentials: langfuse)
    monkeypatch.setattr(
        runner,
        "_validation_ledger",
        lambda _dataset, _project: ([item], []),
    )
    monkeypatch.setattr(runner, "_http_client", fake_http_client)
    monkeypatch.setattr(
        runner,
        "_preflight",
        lambda base_url, client: {
            "status": "ready",
            "base_url": base_url,
            "client_is_expected": client is http_client,
        },
    )

    assert runner._main() == 0
    assert captured["isolated"] is True


def test_preflight_requires_effective_threshold_and_telemetry():
    valid = {
        "status": "ready",
        "endpoint": contract.SESSION_ENDPOINT,
        "context_disclosure_threshold": 200000,
        "benchmark_no_cache_required": True,
        "benchmark_document_source": "sei_no_cache_with_pinned_validation",
        "benchmark_process_source": "sei_no_cache",
        "tool_telemetry_schema": "benchmark-tool-telemetry-v2",
        "preparation_heartbeat_interval_s": 30.0,
        "benchmark_evidence_pin_enabled": True,
        "benchmark_evidence_design": contract.RUNTIME_EVIDENCE_DESIGN_VERSION,
    }
    validate_preflight(valid)
    with pytest.raises(ContractError, match="threshold"):
        validate_preflight({**valid, "context_disclosure_threshold": 199999})
    with pytest.raises(ContractError, match="no_cache"):
        validate_preflight({**valid, "benchmark_no_cache_required": False})
    with pytest.raises(ContractError, match="fresh"):
        validate_preflight({**valid, "benchmark_document_source": "pinned_only"})
    with pytest.raises(ContractError, match="processos fresh"):
        validate_preflight({**valid, "benchmark_process_source": "request_payload"})
    with pytest.raises(ContractError, match="heartbeat"):
        validate_preflight({**valid, "preparation_heartbeat_interval_s": 600.0})
    with pytest.raises(ContractError, match="evidência pinada"):
        validate_preflight({**valid, "benchmark_evidence_pin_enabled": False})


def test_preflight_preserves_sanitized_model_contract_fields():
    payload = {
        "status": "ready",
        "endpoint": contract.SESSION_ENDPOINT,
        "context_disclosure_threshold": 200000,
        "session_main_model_profile": "standard",
        "session_main_model": "seiia-ds-gpt-terra",
        "session_classifier_model_profile": "mini",
        "session_classifier_model": "seiia-ds-gpt-luna",
        "session_explorer_model_profile": "nano",
        "session_explorer_model": "seiia-ds-nano",
        "session_ocr_model": "seiia-ds-nano",
        "session_reasoning_effort_requested": "low",
        "session_main_model_client_retries": 0,
        "session_main_model_context_window_tokens": 1050000,
        "benchmark_no_cache_required": True,
        "benchmark_document_source": "sei_no_cache_with_pinned_validation",
        "benchmark_process_source": "sei_no_cache",
        "tool_telemetry_schema": "benchmark-tool-telemetry-v2",
        "preparation_heartbeat_interval_s": 30.0,
        "benchmark_evidence_pin_enabled": True,
        "benchmark_evidence_design": contract.RUNTIME_EVIDENCE_DESIGN_VERSION,
    }
    response = SimpleNamespace(status_code=200, json=lambda: payload)
    client = SimpleNamespace(get=lambda _url: response)

    observed = runner._preflight("https://127.0.0.1:8188", client)

    assert observed["session_main_model_profile"] == "standard"
    assert observed["session_main_model"] == "seiia-ds-gpt-terra"
    assert observed["session_classifier_model_profile"] == "mini"
    assert observed["session_classifier_model"] == "seiia-ds-gpt-luna"
    assert observed["session_explorer_model_profile"] == "nano"
    assert observed["session_explorer_model"] == "seiia-ds-nano"
    assert observed["session_ocr_model"] == "seiia-ds-nano"
    assert observed["session_reasoning_effort_requested"] == "low"
    assert observed["session_main_model_client_retries"] == 0


def test_sse_parser_handles_split_frames_and_terminal_with_monotonic_clock():
    chunks = [
        b'data: {"type":"status","data":"x","stage":"session_preparation","heartbeat":true}\n\ndata: {"type":"cont',
        b'ent","data":"res"}\n\ndata: {"type":"metadata","data":',
        b'{"benchmark_metrics":{"collector_active":true}}}\n\n',
        b'data: {"type":"end","data":"done"}\n\n',
    ]
    outcome = consume_sse(chunks, started_at=10.0, clock=lambda: 12.75)
    assert outcome.terminal_type == "end"
    assert outcome.observed_response_time_s == 2.75
    assert outcome.content == "res"
    assert outcome.status_frames == 1
    assert outcome.preparation_heartbeat_frames == 1
    assert outcome.content_frames == 1
    assert outcome.metadata["benchmark_metrics"]["collector_active"] is True


def test_sse_error_is_terminal_and_missing_terminal_fails():
    outcome = consume_sse(
        [b'data: {"type":"error","status_code":503,"detail":"safe"}\n\n'],
        started_at=4.0,
        clock=lambda: 5.0,
    )
    assert outcome.terminal_type == "error"
    assert outcome.terminal_status_code == 503
    assert outcome.observed_response_time_s == 1.0
    with pytest.raises(SSEProtocolError, match="terminal"):
        consume_sse(
            [b'data: {"type":"content","data":"x"}\n\n'],
            started_at=0,
            clock=lambda: 1,
        )


def test_stream_once_persists_raw_sse_dump_with_private_permissions(tmp_path):
    raw_path = tmp_path / "stream.raw.sse"
    raw_frame = b'data: {"type":"end","data":"done"}\n\n'

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def iter_bytes(self):
            return [raw_frame]

    class FakeClient:
        def stream(self, *_args, **_kwargs):
            return FakeResponse()

    status, content_type, outcome = runner._stream_once(
        client=FakeClient(),
        base_url="https://127.0.0.1:8188",
        payload={},
        trace_id="trace-id",
        raw_path=raw_path,
        clock=lambda: 1.0,
    )

    assert status == 200
    assert content_type == "text/event-stream"
    assert outcome.terminal_type == "end"
    assert raw_path.read_bytes() == raw_frame
    assert raw_path.stat().st_mode & 0o777 == 0o600


def test_trace_readback_distinguishes_absent_incomplete_and_terminal():
    class StatusError(Exception):
        def __init__(self, status_code):
            self.status_code = status_code

    class Clock:
        def __init__(self):
            self.now = 0.0

        def __call__(self):
            return self.now

        def sleep(self, delay):
            self.now += delay

    class TraceReader:
        def __init__(self, responses):
            self.responses = iter(responses)
            self.calls = 0

        def get(self, _trace_id):
            self.calls += 1
            response = next(self.responses)
            if isinstance(response, Exception):
                raise response
            return response

    complete = SimpleNamespace(
        observations=[
            SimpleNamespace(
                id="root", type="SPAN", name="session_agent", end_time="done"
            ),
            SimpleNamespace(
                id="generation", type="GENERATION", name="llm", end_time="done"
            ),
        ]
    )
    incomplete = SimpleNamespace(
        observations=[SimpleNamespace(id="root", type="SPAN", name="session_agent")]
    )
    open_child = SimpleNamespace(
        observations=[
            SimpleNamespace(
                id="root", type="SPAN", name="session_agent", end_time="done"
            ),
            SimpleNamespace(
                id="generation", type="GENERATION", name="llm", end_time="done"
            ),
            SimpleNamespace(id="child", type="SPAN", name="tool", end_time=None),
        ]
    )

    complete_clock = Clock()
    complete_reader = TraceReader([StatusError(404), complete, complete, complete])
    complete_result = runner._fetch_trace_stable(
        SimpleNamespace(api=SimpleNamespace(trace=complete_reader)),
        "trace",
        max_wait_s=30,
        poll_s=1,
        max_retries=10,
        clock=complete_clock,
        sleeper=complete_clock.sleep,
    )
    assert complete_result.status == "complete"
    assert complete_result.attempts == 4

    absent_clock = Clock()
    absent_reader = TraceReader([StatusError(404), StatusError(404), StatusError(404)])
    absent = runner._fetch_trace_stable(
        SimpleNamespace(api=SimpleNamespace(trace=absent_reader)),
        "trace",
        max_wait_s=2,
        poll_s=1,
        max_retries=10,
        clock=absent_clock,
        sleeper=absent_clock.sleep,
    )
    assert absent.status == "absent"
    assert absent.trace is None

    incomplete_clock = Clock()
    incomplete_reader = TraceReader([incomplete, incomplete, incomplete])
    incomplete_result = runner._fetch_trace_stable(
        SimpleNamespace(api=SimpleNamespace(trace=incomplete_reader)),
        "trace",
        max_wait_s=2,
        poll_s=1,
        max_retries=10,
        clock=incomplete_clock,
        sleeper=incomplete_clock.sleep,
    )
    assert incomplete_result.status == "incomplete"
    assert incomplete_result.trace is incomplete

    open_child_clock = Clock()
    open_child_reader = TraceReader([open_child] * 5)
    open_child_result = runner._fetch_trace_stable(
        SimpleNamespace(api=SimpleNamespace(trace=open_child_reader)),
        "trace",
        max_wait_s=4,
        poll_s=1,
        max_retries=10,
        clock=open_child_clock,
        sleeper=open_child_clock.sleep,
    )
    assert open_child_result.status == "incomplete"
    assert open_child_result.trace is open_child

    transient_clock = Clock()
    transient_reader = TraceReader([StatusError(408), complete, complete, complete])
    transient = runner._fetch_trace_stable(
        SimpleNamespace(api=SimpleNamespace(trace=transient_reader)),
        "trace",
        max_wait_s=30,
        poll_s=1,
        max_retries=10,
        clock=transient_clock,
        sleeper=transient_clock.sleep,
    )
    assert transient.status == "complete"
    assert transient.attempts == 4

    terminal_clock = Clock()
    terminal_reader = TraceReader([StatusError(403)])
    terminal = runner._fetch_trace_stable(
        SimpleNamespace(api=SimpleNamespace(trace=terminal_reader)),
        "trace",
        max_wait_s=30,
        poll_s=1,
        max_retries=10,
        clock=terminal_clock,
        sleeper=terminal_clock.sleep,
    )
    assert terminal.status == "terminal_error"
    assert terminal.attempts == 1
    assert terminal_clock.now == 0


def test_execution_policy_is_n1_without_retry_warmup_concurrency_or_classic():
    policy = ExecutionPolicy()
    assert policy.n == 1
    assert policy.max_concurrency == 1
    assert policy.retries == 0
    assert policy.warmups == 0
    assert policy.transport == "http"
    assert policy.classic_enabled is False
    assert policy.rate_card_enabled is False
    assert policy.threshold_override_enabled is False
    assert policy.use_websearch is False

    source = {
        "id_usuario": 1,
        "id_topico": 2,
        "text": "sintético",
        "id_procedimentos": [],
        "skip_memory": False,
        "use_websearch": True,
    }
    payload = build_execution_payload(source, 123)
    assert payload["id_topico"] == 123
    assert payload["no_cache"] is True
    assert payload["trace"] is True
    assert payload["skip_memory"] is True
    assert payload["use_websearch"] is False
    assert "inject_tokens_threshold" not in payload
    assert source["id_topico"] == 2


def test_topics_are_new_and_sequential():
    topics = TopicFactory()
    assert len({topics.new() for _ in range(20)}) == 20


def test_runner_emits_nine_ledger_lines_when_dataset_validation_fails(
    monkeypatch, capsys
):
    dataset = _synthetic_dataset(monkeypatch)
    dataset.items[0].metadata["n"] = 2
    fake_langfuse = SimpleNamespace(get_dataset=lambda *_args, **_kwargs: dataset)
    monkeypatch.setattr(runner, "_load_langfuse_credentials", lambda _path: {})
    monkeypatch.setattr(runner, "_project_gate", lambda _credentials: "project-ok")
    monkeypatch.setattr(runner, "_langfuse_client", lambda _credentials: fake_langfuse)
    monkeypatch.setattr(sys, "argv", ["run_long_context_benchmark"])

    assert runner.main() == 1
    ledger = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(ledger) == 9
    assert {row["item_id"] for row in ledger} == contract.EXPECTED_ITEM_IDS
    assert {row["status"] for row in ledger} == {"validation_failed"}
    assert all(row["execution_attempted"] is False for row in ledger)


def _passing_canary_record() -> dict:
    return {
        "item_id": runner.CANARY_ITEM_ID,
        "execution_attempted": True,
        "status": "ok",
        "http_status": 200,
        "content_type": "text/event-stream",
        "terminal_type": "end",
        "answer_nonempty": True,
        "observed_response_time_s": 1.25,
        "context_disclosure_observed": True,
        "calls": {"calls_llm": 2, "calls_tools": 1},
        "tool_telemetry": {
            "observability_status": "complete",
            "calls": [{"sequence": 1}],
        },
        "evidence_observability": {"status": "complete"},
        "scores": {
            "target_alignment": True,
            "completude": 1.0,
            "groundedness": 1.0,
            "entendimento_abstrato": 1.0,
            "hallucination_count": 0,
            "hallucination_zero": True,
            "unverified_claims": 0,
        },
        "trace": {
            "project": contract.TARGET_PROJECT,
            "located": True,
            "stable": True,
            "dataset_linked": True,
        },
    }


def test_stage_three_modes_are_explicit_and_mutually_exclusive(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_long_context_benchmark"])
    args = runner._parse_args()
    assert args.execute_canary is False
    assert args.continue_run is False
    assert args.execute_full_battery is False

    monkeypatch.setattr(sys, "argv", ["run_long_context_benchmark", "--execute-canary"])
    assert runner._parse_args().execute_canary is True

    monkeypatch.setattr(sys, "argv", ["run_long_context_benchmark", "--continue-run"])
    assert runner._parse_args().continue_run is True

    monkeypatch.setattr(
        sys, "argv", ["run_long_context_benchmark", "--execute-full-battery"]
    )
    assert runner._parse_args().execute_full_battery is True

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_long_context_benchmark",
            "--execute-canary",
            "--continue-run",
        ],
    )
    with pytest.raises(SystemExit):
        runner._parse_args()


def test_canary_selection_is_the_positive_integrative_item(monkeypatch):
    dataset = _synthetic_dataset(monkeypatch)
    canary = runner._select_canary(dataset.items)
    assert canary.id == "case-0960k-q2-synthesis"
    assert canary.metadata["question_type"] == "synthesis"
    assert canary.expected_output["categoria"] == "cross-document"


def test_canary_phase_attempts_exactly_one_item_and_writes_gate(monkeypatch, tmp_path):
    dataset = _synthetic_dataset(monkeypatch)
    attempted = []

    def execute_one(item):
        attempted.append(item.id)
        return _passing_canary_record()

    ledger = tmp_path / "execution-ledger.jsonl"
    record = runner._execute_canary(
        items=dataset.items,
        execute_one=execute_one,
        ledger_path=ledger,
    )

    assert attempted == [runner.CANARY_ITEM_ID]
    assert record["canary_gate_status"] == "passed"
    persisted = runner._read_execution_ledger(ledger)
    assert len(persisted) == 1
    assert persisted[0]["item_id"] == runner.CANARY_ITEM_ID


def test_ledger_reservation_survives_interrupted_execution(monkeypatch, tmp_path):
    dataset = _synthetic_dataset(monkeypatch)
    ledger = tmp_path / "execution-ledger.jsonl"

    def interrupted(_item):
        assert runner._read_execution_ledger(ledger)[0]["status"] == "in-progress"
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        runner._execute_canary(
            items=dataset.items,
            execute_one=interrupted,
            ledger_path=ledger,
        )

    persisted = runner._read_execution_ledger(ledger)
    assert persisted[0]["execution_attempted"] is True
    assert persisted[0]["status"] == "in-progress"
    with pytest.raises(ContractError, match="N=1"):
        runner._execute_canary(
            items=dataset.items,
            execute_one=lambda _item: pytest.fail("repetição indevida"),
            ledger_path=ledger,
        )


def test_ledger_commit_preserves_reservation_after_prepost_failure(
    monkeypatch, tmp_path
):
    dataset = _synthetic_dataset(monkeypatch)
    ledger = tmp_path / "execution-ledger.jsonl"

    record = runner._execute_canary(
        items=dataset.items,
        execute_one=lambda item: {
            "item_id": item.id,
            "execution_attempted": False,
            "status": "error",
        },
        ledger_path=ledger,
    )

    assert record["execution_attempted"] is False
    persisted = runner._read_execution_ledger(ledger)
    assert persisted[0]["execution_attempted"] is True
    assert persisted[0]["status"] == "error"
    with pytest.raises(ContractError, match="N=1"):
        runner._execute_canary(
            items=dataset.items,
            execute_one=lambda _item: pytest.fail("repetição indevida"),
            ledger_path=ledger,
        )


def test_continuation_runs_eight_remaining_in_canonical_order(monkeypatch, tmp_path):
    dataset = _synthetic_dataset(monkeypatch)
    ledger = tmp_path / "execution-ledger.jsonl"
    canary = _passing_canary_record()
    canary["canary_gate_status"] = "passed"
    runner._append_private_jsonl(ledger, canary)
    attempted = []

    def execute_one(item):
        attempted.append(item.id)
        return {
            "item_id": item.id,
            "execution_attempted": True,
            "status": "ok",
        }

    records = runner._execute_remaining(
        items=dataset.items,
        execute_one=execute_one,
        ledger_path=ledger,
    )

    expected = sorted(contract.EXPECTED_ITEM_IDS - {runner.CANARY_ITEM_ID})
    assert attempted == expected
    assert len(records) == 8
    assert runner.CANARY_ITEM_ID not in attempted
    assert len(runner._read_execution_ledger(ledger)) == 9


def test_full_battery_attempts_all_nine_once_even_after_item_failure(
    monkeypatch, tmp_path
):
    dataset = _synthetic_dataset(monkeypatch)
    ledger = tmp_path / "execution-ledger.jsonl"
    attempted = []
    progress = []

    def execute_one(item):
        attempted.append(item.id)
        return {
            "item_id": item.id,
            "execution_attempted": True,
            "status": "error" if len(attempted) == 1 else "ok",
        }

    records = runner._execute_full_battery(
        items=dataset.items,
        execute_one=execute_one,
        ledger_path=ledger,
        on_progress=progress.append,
    )

    assert attempted == sorted(contract.EXPECTED_ITEM_IDS)
    assert len(records) == 9
    assert len({record["item_id"] for record in records}) == 9
    assert len(runner._read_execution_ledger(ledger)) == 9
    assert progress == [runner._progress_record(record) for record in records]


def test_failed_canary_blocks_remaining_items(monkeypatch, tmp_path):
    dataset = _synthetic_dataset(monkeypatch)
    ledger = tmp_path / "execution-ledger.jsonl"
    failed = _passing_canary_record()
    failed["status"] = "error"
    failed["canary_gate_status"] = "failed"
    runner._append_private_jsonl(ledger, failed)
    attempted = []

    with pytest.raises(ContractError, match="canário não aprovado"):
        runner._execute_remaining(
            items=dataset.items,
            execute_one=lambda item: attempted.append(item.id),
            ledger_path=ledger,
        )
    assert attempted == []


def test_execution_ledger_rejects_a_second_attempt(tmp_path):
    ledger = tmp_path / "execution-ledger.jsonl"
    row = {
        "item_id": runner.CANARY_ITEM_ID,
        "execution_attempted": True,
        "canary_gate_status": "passed",
    }
    runner._append_private_jsonl(ledger, row)
    runner._append_private_jsonl(ledger, row)
    with pytest.raises(ContractError, match="N=1"):
        runner._read_execution_ledger(ledger)


def test_canary_gate_rejects_hallucination_or_missing_observability():
    record = _passing_canary_record()
    assert runner._canary_failures(record) == []

    record["scores"]["hallucination_zero"] = False
    record["calls"]["calls_tools"] = None
    assert runner._canary_failures(record) == ["calls_tools", "hallucination_zero"]


def test_generation_aggregation_excludes_judge_and_breaks_down_components():
    observations = [
        {"id": "root", "type": "SPAN", "name": "session_agent"},
        {"id": "model", "type": "SPAN", "name": "model", "parent_id": "root"},
        {"id": "g-main", "type": "GENERATION", "name": "llm", "parent_id": "model"},
        {
            "id": "g-sub",
            "type": "GENERATION",
            "name": "llm",
            "parent_id": "root",
            "metadata": {"langgraph_checkpoint_ns": "tools:a|model:b"},
        },
        {"id": "classifier", "type": "SPAN", "name": "session_complexity"},
        {
            "id": "g-class",
            "type": "GENERATION",
            "name": "llm",
            "parent_id": "classifier",
        },
        {"id": "planner", "type": "SPAN", "name": "plan_speculative_queries"},
        {"id": "g-plan", "type": "GENERATION", "name": "llm", "parent_id": "planner"},
        {"id": "summary", "type": "SPAN", "name": "summarization"},
        {
            "id": "g-summary",
            "type": "GENERATION",
            "name": "llm",
            "parent_id": "summary",
        },
        {"id": "judge", "type": "SPAN", "name": "benchmark_judge"},
        {"id": "g-judge", "type": "GENERATION", "name": "llm", "parent_id": "judge"},
    ]
    result = aggregate_agent_calls(observations, stable=True)
    assert result["calls_llm"] == 5
    assert result["calls_llm_by_component"] == {
        "main": 1,
        "subagent": 1,
        "classifier": 1,
        "planner": 1,
        "summarizer": 1,
        "unknown": 0,
    }
    assert aggregate_agent_calls(observations, stable=False)["calls_llm"] is None
    assert aggregate_agent_calls([], stable=True)["observability_status"] == "N/D"


def test_tool_telemetry_is_sanitized_ordered_and_measured():
    handler = BenchmarkToolHandler(
        document_paths=[
            "proc_sensitive/doc_sensitive.txt",
            "proc_sensitive/other_sensitive.txt",
        ],
        document_inventory=[
            {
                "path": "proc_sensitive/doc_sensitive.txt",
                "content_sha256": contract.text_digest("doc-1"),
                "bytes": 5,
                "tokens": 2,
            },
            {
                "path": "proc_sensitive/other_sensitive.txt",
                "content_sha256": contract.text_digest("doc-2"),
                "bytes": 5,
                "tokens": 2,
            },
        ],
    )
    run_id = uuid4()
    parent_id = uuid4()
    handler.on_tool_start(
        {"name": "grep"},
        "RAW SECRET INPUT THAT MUST NOT SURVIVE",
        run_id=run_id,
        parent_run_id=parent_id,
        metadata={"langgraph_checkpoint_ns": "tools:secret|tools:child"},
        inputs={
            "pattern": "sensitive phrase",
            "path": "/proc_sensitive",
            "glob": "*.txt",
            "output_mode": "files_with_matches",
        },
    )
    handler.on_tool_end(
        ToolMessage(
            content="/proc_sensitive/doc_sensitive.txt",
            tool_call_id="synthetic",
            status="success",
        ),
        run_id=run_id,
    )
    summary = handler.summary()
    sanitized = runner._sanitized_tool_summary(summary)
    encoded = json.dumps(sanitized, ensure_ascii=False)
    assert summary["schema_version"] == "benchmark-tool-telemetry-v2"
    assert sanitized["observability_status"] == "complete"
    assert summary["observability_status"] == "complete"
    assert summary["total_calls"] == 1
    call = summary["calls"][0]
    assert call["sequence"] == 1
    assert call["actor"].startswith("subagent:")
    assert call["parent_call_id_sha256"]
    assert len(call["files_scanned"]) == 2
    assert len(call["files_returned"]) == 1
    assert call["returned_bytes"] > 0
    assert call["returned_tokens"] > 0
    assert call["returned_sha256"]
    for forbidden in (
        "RAW SECRET",
        "sensitive phrase",
        "proc_sensitive",
        "doc_sensitive",
        str(parent_id),
        str(run_id),
    ):
        assert forbidden not in encoded


def test_evidence_package_validates_opened_citation_outside_gold(tmp_path):
    document = tmp_path / "doc.txt"
    document.write_text(
        "A comunicação alternativa fixou prazo e exigiu relatório atualizado.",
        encoding="utf-8",
    )
    virtual_path = "proc_case/doc.txt"
    index = {
        "schema_version": "benchmark-long-context-evidence-index-v1",
        "evaluation_design_version": contract.EVALUATION_DESIGN_VERSION,
        "cases": {
            "case-0960k": {
                "documents": [
                    {
                        "document_id": "doc-outside-target",
                        "formatted_id": "FMT-ALT",
                        "virtual_path": virtual_path,
                        "source_path": str(document),
                        "document_sha256": contract.text_digest(
                            document.read_text(encoding="utf-8")
                        ),
                    }
                ]
            }
        },
    }
    index_path = tmp_path / "evidence-index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    tool_summary = {
        "calls": [
            {
                "files_opened": [
                    {"path_sha256": contract.text_digest("/" + virtual_path)}
                ]
            }
        ],
        "document_inventory": [
            {
                "path_sha256": contract.text_digest("/" + virtual_path),
                "content_sha256": contract.text_digest(
                    document.read_text(encoding="utf-8")
                ),
            }
        ],
    }
    answer = (
        "A comunicação alternativa exigiu relatório atualizado "
        '<span title="Documento SEI nº FMT-ALT">[1]</span>.'
    )

    package, summary = build_evidence_package(
        index_path=index_path,
        case_id="case-0960k",
        answer=answer,
        tool_summary=tool_summary,
        fresh_evidence={
            "schema_version": "benchmark-fresh-opened-evidence-v1",
            "source": "validated_materialized_session",
            "documents": [
                {
                    "path_sha256": contract.text_digest("/" + virtual_path),
                    "content_sha256": contract.text_digest(
                        document.read_text(encoding="utf-8")
                    ),
                    "content": document.read_text(encoding="utf-8"),
                }
            ],
        },
    )

    assert len(package) == 1
    assert package[0]["cited"] is True
    assert package[0]["opened"] is True
    assert package[0]["excerpt"] == document.read_text(encoding="utf-8")
    assert summary == {
        "status": "complete",
        "opened_documents": 1,
        "non_corpus_opened_files": 0,
        "indexed_opened_documents": 1,
        "cited_opened_documents": 1,
        "evidence_excerpts": 1,
        "content_source": "validated_materialized_session",
        "content_persisted_in_sanitized_ledger": False,
    }


def test_evidence_package_fails_when_opened_evidence_is_unavailable(tmp_path):
    index_path = tmp_path / "evidence-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schema_version": "benchmark-long-context-evidence-index-v1",
                "evaluation_design_version": contract.EVALUATION_DESIGN_VERSION,
                "cases": {"case-0960k": {"documents": []}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ContractError, match="não está no índice"):
        build_evidence_package(
            index_path=index_path,
            case_id="case-0960k",
            answer="resposta",
            tool_summary={
                "calls": [
                    {
                        "files_opened": [
                            {"path_sha256": contract.text_digest("/missing.txt")}
                        ]
                    }
                ],
                "document_inventory": [
                    {
                        "path_sha256": contract.text_digest("/missing.txt"),
                        "content_sha256": contract.text_digest("missing"),
                    }
                ],
            },
            fresh_evidence={
                "schema_version": "benchmark-fresh-opened-evidence-v1",
                "source": "validated_materialized_session",
                "documents": [
                    {
                        "path_sha256": contract.text_digest("/missing.txt"),
                        "content_sha256": contract.text_digest("missing"),
                        "content": "missing",
                    }
                ],
            },
        )


def test_file_inventory_tracks_ls_glob_and_real_returned_paths():
    handler = BenchmarkToolHandler(
        document_paths=[
            "proc_a/doc_a.txt",
            "proc_a/doc_b.txt",
            "proc_b/doc_c.txt",
            "root.txt",
        ]
    )

    ls_run = uuid4()
    handler.on_tool_start(
        {"name": "ls"},
        "ignored",
        run_id=ls_run,
        inputs={"path": "."},
    )
    handler.on_tool_end(
        ToolMessage(
            content="['/proc_a/', '/proc_b/', '/root.txt']",
            tool_call_id="ls",
            status="success",
        ),
        run_id=ls_run,
    )

    glob_run = uuid4()
    handler.on_tool_start(
        {"name": "glob"},
        "ignored",
        run_id=glob_run,
        inputs={"pattern": "proc_a/*.txt", "path": "."},
    )
    handler.on_tool_end(
        ToolMessage(
            content="['/proc_a/doc_a.txt']",
            tool_call_id="glob",
            status="success",
        ),
        run_id=glob_run,
    )

    read_run = uuid4()
    handler.on_tool_start(
        {"name": "read_file"},
        "ignored",
        run_id=read_run,
        inputs={"file_path": "proc_a/doc_a.txt"},
    )
    handler.on_tool_end(
        ToolMessage(
            content="texto que menciona /proc_b/doc_c.txt",
            tool_call_id="read",
            status="success",
        ),
        run_id=read_run,
    )

    calls = handler.summary()["calls"]
    ls_call, glob_call, read_call = calls
    assert [item["kind"] for item in ls_call["files_scanned"]] == [
        "directory",
        "directory",
        "document",
    ]
    assert len(ls_call["files_returned"]) == 3
    assert len(glob_call["files_scanned"]) == 2
    assert len(glob_call["files_returned"]) == 1
    assert len(read_call["files_opened"]) == 1
    assert read_call["files_returned"] == []


def test_file_inventory_tracks_grep_file_scope():
    handler = BenchmarkToolHandler(
        document_paths=["proc_a/doc_a.txt", "proc_a/doc_b.txt"]
    )
    run_id = uuid4()
    handler.on_tool_start(
        {"name": "grep"},
        "ignored",
        run_id=run_id,
        inputs={
            "pattern": "needle",
            "path": "proc_a/doc_a.txt",
            "output_mode": "files_with_matches",
        },
    )
    handler.on_tool_end(
        ToolMessage(
            content="/proc_a/doc_a.txt",
            tool_call_id="grep-file",
            status="success",
        ),
        run_id=run_id,
    )

    call = handler.summary()["calls"][0]
    assert len(call["files_scanned"]) == 1
    assert call["files_scanned"][0]["kind"] == "document"
    assert len(call["files_returned"]) == 1


def test_incomplete_tool_observability_is_nd_not_zero():
    handler = BenchmarkToolHandler()
    handler.on_tool_start({"name": "read_file"}, "ignored", run_id=uuid4())
    summary = handler.summary()
    assert summary["observability_status"] == "N/D"
    assert summary["total_calls"] is None
    aggregate = aggregate_tool_calls(summary)
    assert aggregate["calls_tools"] is None
    assert aggregate["observability_status"] == "N/D"

    combined = combine_call_metrics(
        {"calls_llm": None, "calls_llm_by_component": {}}, aggregate
    )
    assert combined["calls_total"] is None
    assert combined["calls_total_formula"] == "N/D"


def test_completeness_groundedness_abstract_and_hallucination_formulas():
    expected = {
        "categoria": "factual",
        "elementos_obrigatorios": ["a", "b"],
    }
    scores = calculate_scores(
        expected,
        "resposta sintética",
        _assessment(
            checklist=(True, False),
            verdicts=("supported", "contradicted"),
            abstract=0.5,
        ),
        is_negative=False,
    )
    assert scores.completude == 0.5
    assert scores.groundedness == 0.5
    assert scores.entendimento_abstrato == 0.5
    assert scores.hallucination_count == 1
    assert scores.hallucination_zero is False


def test_wrong_target_with_verified_facts_is_grounded_without_hallucination():
    expected = {"categoria": "factual", "elementos_obrigatorios": ["a", "b"]}
    scores = calculate_scores(
        expected,
        "resposta sobre outro par, mas evidenciada",
        _assessment(
            checklist=(False, False),
            verdicts=("supported", "supported"),
            abstract=1.0,
            target_alignment=False,
        ),
        is_negative=False,
    )
    assert scores.target_alignment is False
    assert scores.completude == 0
    assert scores.groundedness == 1
    assert scores.entendimento_abstrato == 1
    assert scores.hallucination_count == 0
    assert scores.hallucination_zero is True


def test_unverified_claim_makes_metrics_nd_instead_of_false_or_zero():
    expected = {"categoria": "factual", "elementos_obrigatorios": ["a"]}
    scores = calculate_scores(
        expected,
        "resposta com evidência indisponível",
        _assessment(checklist=(True,), verdicts=("unverified",)),
        is_negative=False,
    )
    assert scores.groundedness is None
    assert scores.groundedness_status == "N/D"
    assert scores.hallucination_count is None
    assert scores.hallucination_zero is None
    assert scores.unverified_claims == 1


def test_negative_question_requires_safe_abstention_without_invented_percentage():
    expected = {
        "categoria": "negativa",
        "elementos_obrigatorios": ["a", "b", "c", "d", "e", "f"],
    }
    safe = _assessment(
        checklist=(True,) * 6,
        verdicts=("supported", "supported", "supported"),
        negative={
            "abstained": True,
            "numerator_missing": True,
            "denominator_missing": True,
            "invented_rate": False,
            "universal_absence_claim": False,
        },
    )
    safe_scores = calculate_scores(
        expected, "abstenção sintética", safe, is_negative=True
    )
    assert safe_scores.completude == 1
    assert safe_scores.groundedness == 1
    assert safe_scores.hallucination_count == 0
    assert safe_scores.hallucination_zero is True
    assert safe_scores.negative_safety_pass is True

    invented = _assessment(
        checklist=(True,) * 6,
        verdicts=("supported", "supported", "supported"),
        negative={
            "abstained": False,
            "numerator_missing": False,
            "denominator_missing": False,
            "invented_rate": True,
            "universal_absence_claim": True,
        },
    )
    invented_scores = calculate_scores(
        expected, "percentual sintético", invented, is_negative=True
    )
    assert invented_scores.completude < 1
    assert invented_scores.groundedness < 1
    assert invented_scores.hallucination_count == 1
    assert invented_scores.hallucination_zero is False
    assert invented_scores.negative_safety_pass is False


def test_scorer_uses_validated_classification_instead_of_raw_category():
    expected = {"categoria": "factual", "elementos_obrigatorios": ["a", "b"]}
    scores = calculate_scores(
        expected,
        "resposta sintética",
        _assessment(),
        is_negative=True,
    )
    assert scores.negative_safety_pass is False
    assert scores.completude < 1


def test_empty_answer_scores_nd_without_approving_hallucination_gate():
    expected = {"categoria": "factual", "elementos_obrigatorios": ["a"]}
    scores = calculate_scores(expected, "", None, is_negative=False)
    assert scores.completude == 0
    assert scores.groundedness is None
    assert scores.entendimento_abstrato == 0
    assert scores.hallucination_count is None
    assert scores.hallucination_zero is None


def test_invalid_negative_judge_shape_has_safe_fail_closed_diagnostic():
    secret = "CONTEUDO-SENSIVEL-NAO-PODE-VAZAR"
    raw = {
        "target_alignment": True,
        "checklist": [{"index": 1, "satisfied": True}],
        "claims": [
            {
                "text": secret,
                "verdict": "supported",
                "evidence_references": [],
            }
        ],
        "abstract_understanding": 1,
        "negative_safety": {"abstained": True},
        "rationale": secret,
    }

    with pytest.raises(scorer.JudgeContractError) as caught:
        scorer.parse_assessment_with_diagnostic(
            raw,
            required_count=1,
            evidence_count=1,
            is_negative=True,
        )

    diagnostic = caught.value.diagnostic
    assert diagnostic["category"] == "negative_safety_invalid"
    assert diagnostic["invalid_paths"] == [
        "negative_safety.denominator_missing",
        "negative_safety.invented_rate",
        "negative_safety.numerator_missing",
        "negative_safety.universal_absence_claim",
    ]
    assert len(diagnostic["shape_fingerprint"]) == 64
    assert secret not in json.dumps(diagnostic, ensure_ascii=False)


def test_verified_claim_without_reference_has_safe_fail_closed_diagnostic():
    secret = "OUTRO-CONTEUDO-SENSIVEL"
    raw = {
        "target_alignment": True,
        "checklist": [{"index": 1, "satisfied": True}],
        "claims": [
            {
                "text": secret,
                "verdict": "supported",
                "evidence_references": [],
            }
        ],
        "abstract_understanding": 1,
        "negative_safety": None,
        "rationale": secret,
    }

    with pytest.raises(scorer.JudgeContractError) as caught:
        scorer.parse_assessment_with_diagnostic(
            raw,
            required_count=1,
            evidence_count=1,
            is_negative=False,
        )

    diagnostic = caught.value.diagnostic
    assert diagnostic["category"] == "verified_claim_without_evidence"
    assert diagnostic["invalid_paths"] == ["claims[0].evidence_references"]
    assert secret not in json.dumps(diagnostic, ensure_ascii=False)


def test_judge_uses_strict_json_schema_without_retry_fallback():
    valid = {
        "target_alignment": True,
        "checklist": [{"index": 1, "satisfied": True}],
        "claims": [
            {
                "text": "claim sintético",
                "verdict": "supported",
                "evidence_references": [1],
            }
        ],
        "abstract_understanding": 1,
        "negative_safety": None,
        "rationale": "ok",
    }
    observed = {}

    class FakeCompletions:
        def create(self, **kwargs):
            observed.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=json.dumps(valid)))
                ]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    assessment, raw = scorer.judge_response(
        client=client,
        model="standard",
        question="pergunta",
        expected_output={
            "gold_answer": "gold",
            "elementos_obrigatorios": ["elemento"],
        },
        answer="resposta",
        is_negative=False,
        evidence_package=[{"reference": 1, "excerpt": "evidência"}],
    )

    response_format = observed["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False
    assert assessment.target_alignment is True
    assert raw == valid


def test_assessment_parser_enforces_verdict_evidence_and_abstract_scale():
    valid = {
        "target_alignment": True,
        "checklist": [{"index": 1, "satisfied": True}],
        "claims": [
            {
                "text": "claim sintético",
                "verdict": "supported",
                "evidence_references": [1],
            }
        ],
        "abstract_understanding": 1,
        "negative_safety": None,
        "rationale": "sintético",
    }
    assert parse_assessment(
        valid,
        required_count=1,
        evidence_count=1,
        is_negative=False,
    ).checklist == (True,)
    with pytest.raises(ContractError, match="escala"):
        parse_assessment(
            {**valid, "abstract_understanding": 0.75},
            required_count=1,
            evidence_count=1,
            is_negative=False,
        )
    unverified_with_reference = {
        **valid,
        "claims": [
            {
                "text": "claim sem prova",
                "verdict": "unverified",
                "evidence_references": [1],
            }
        ],
    }
    with pytest.raises(ContractError, match="não verificável"):
        parse_assessment(
            unverified_with_reference,
            required_count=1,
            evidence_count=1,
            is_negative=False,
        )


def test_score_publication_contains_no_rationale_or_claims():
    class FakeLangfuse:
        def __init__(self):
            self.rows = []

        def create_score(self, **kwargs):
            self.rows.append(kwargs)

    fake = FakeLangfuse()
    scores = calculate_scores(
        {"categoria": "factual", "elementos_obrigatorios": ["a", "b"]},
        "resposta sintética",
        _assessment(),
        is_negative=False,
    )
    emit_sanitized_scores(
        fake,
        "trace-synthetic",
        observed_response_time_s=1.25,
        calls={
            "calls_llm": 2,
            "calls_llm_by_component": {"main": 2},
            "calls_tools": 1,
            "calls_tools_by_name": {"read_file": 1},
        },
        scores=scores,
    )
    encoded = json.dumps(fake.rows)
    assert "rationale" not in encoded
    assert "claim" not in encoded
    assert {row["name"] for row in fake.rows} >= {
        "calls_llm",
        "calls_tools",
        "observed_response_time_s",
        "target_alignment",
        "completude",
        "groundedness",
        "entendimento_abstrato",
        "hallucination_count",
        "hallucination_zero",
    }
