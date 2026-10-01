"""Runner fail-closed da campanha long-context v2 (validação offline + um canário)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit, urlunsplit

SCRIPT_DIR = Path(__file__).resolve().parent
EXPERIMENT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(EXPERIMENT_ROOT / "scripts" / "shared"))

from dotenv import dotenv_values  # noqa: E402
from long_context_contract import (  # noqa: E402
    DATASET_NAME,
    EXPECTED_ITEM_IDS,
    SESSION_ENDPOINT,
    TARGET_PROJECT,
    SSEOutcome,
    TopicFactory,
    build_execution_payload,
    plain,
    stable_digest,
    validate_dataset,
)
from long_context_evidence import build_evidence_package  # noqa: E402
from long_context_v2_ledger import (  # noqa: E402
    V2Ledger,
    assert_private_tree,
    write_private_json,
)
from long_context_v2_manifest import (  # noqa: E402
    MANIFEST_PATH,
    file_sha256,
    load_protected_json,
    validate_manifest,
)
from long_context_v2_scorer import (  # noqa: E402
    QUALITY_GATE_POLICY_VERSION,
    JudgeV2ContractError,
    ScoreV2,
    build_judge_input,
    classify_quality_gate,
    judge_messages,
    load_judge_artifacts,
    load_judge_material,
    merge_evidence_package,
    parse_judge_output,
    score_judge_output,
)
from long_context_v2_telemetry import (  # noqa: E402
    AgentUsageUnavailableError,
    TelemetryContractError,
    agent_usage_records,
    judge_usage_record,
    ocr_usage_records,
    summarize_usage,
)
from model_campaign import (  # noqa: E402
    ModelCampaign,
    add_model_campaign_args,
    campaign_from_args,
    campaign_requested,
    plan_long_context_cells,
    runtime_contract,
)
from openai import OpenAI  # noqa: E402
from run_long_context_benchmark import (  # noqa: E402
    ISOLATED_BASE_URL,
    _configured_values,
    _context_disclosure_observed,
    _dataset_run_linked,
    _fetch_trace_stable,
    _guard_isolated_base_url,
    _http_client,
    _langfuse_client,
    _load_langfuse_credentials,
    _preflight,
    _project_gate,
    _sanitized_tool_summary,
    _stream_once,
)
from trace_metrics import normalize  # noqa: E402

CANARY_ITEM_ID = "case-0960k-q2-synthesis"
SECOND_CANARY_ITEM_ID = "case-0960k-q1-factual"
RATE_LIMIT_COOLDOWN_S = 15 * 60
BENCHMARK_LIVE_PREFLIGHT_ENDPOINT = "/llm_lang/session_benchmark_live_preflight"
PRODUCTION_SEI_PUBLIC_ENDPOINT_SHA256 = (
    "6f4ea5a1095d05a2c86ce4ff330d5ae236e7a517a1cf066e28c20ddd96f9882b"
)
PRODUCTION_SEI_API_ENDPOINT_SHA256 = (
    "33a6a4068c068b4a8b976639d0c371618bb56bfab2f7ff0d3db706becef49245"
)
FACTUAL_REPLACEMENT_POLICY = {
    "kind": "wrong_environment",
    "item_id": SECOND_CANARY_ITEM_ID,
    "predecessor_run_name": "long-context-v2-canary-factual-20260723T234554Z",
    "predecessor_execution_id": "d00149c7-1c30-4f1d-a412-75db4ff59c84",
    "predecessor_trace_id": "83f1e2e3237ef638c1599b1146b03b3c",
    "reason": "wrong_sei_environment_pre_agent",
    "captain_authorization": (
        "fix-sei-preflight-and-rerun-factual-20260723.md:"
        "4c968d6bcdc65173f84d09ae068c45a93e8a8e9dfdc6ef02c44a1c695d3118c7"
    ),
}
OCR_REMEDIATION_POLICY = {
    "kind": "ocr_materialization",
    "item_id": SECOND_CANARY_ITEM_ID,
    "predecessor_run_name": (
        "long-context-v2-canary-factual-replacement-20260724T003905Z"
    ),
    "predecessor_execution_id": "1668aac4-0df4-49ab-9fee-9b2d52f83b59",
    "predecessor_trace_id": "a5c00d57b85c28418dd1ba723e6a4d27",
    "reason": "ocr_materialization_pre_agent",
    "captain_authorization": (
        "fix-ocr-materialization-20260724.md:"
        "faa79f524efb6ba6b04c31096f83f39030353ab5c877b125d15f26b82ebcbd54"
    ),
}
# O canário revelou que ``usageDetails.output`` exclui reasoning. Este predecessor
# difere do contrato atual somente nessa semântica de pós-processamento; inferência,
# prompt/schema/modelo do juiz e scores oficiais permanecem os mesmos.
TELEMETRY_SEMANTICS_PREDECESSOR_SHA256 = (
    "078759b44301d3bcac8e38563cabb48511457e1460e5f6cb82a3f2ebf96f06dc"
)
GATE_RECLASSIFICATION_AUTHORIZATION = (
    "reclassify-canary-gates-20260724.md:captain-explicit-quality-gate-separation"
)
FULL_BATTERY_AUTHORIZATION_SHA256 = (
    "2984a3c55aea2f4b1134d3dcce690d32de9eaa8b473fb37304738c70be9ac3a9"
)
FRESH_FULL_BATTERY_AUTHORIZATION_SHA256 = hashlib.sha256(
    b"gpt56-ocr-luna-fresh-all-nine-20260731"
).hexdigest()
RATE_LIMIT_SUCCESSOR_AUTHORIZATION_SHA256 = (
    "18524a6825e1d38c5cca043293a5f101b1c109a606130bf950bc20481976b352"
)
FULL_BATTERY_REUSED_ITEM_ID = SECOND_CANARY_ITEM_ID
FULL_BATTERY_EXCLUDED_PREDECESSOR_ITEM_ID = CANARY_ITEM_ID
RATE_LIMIT_SUCCESSOR_REUSED_ITEM_IDS = frozenset(
    {
        "case-0960k-q1-factual",
        "case-0960k-q2-synthesis",
        "case-0960k-q3-insufficient-evidence",
    }
)
_ISOLATED_TECHNICAL_STAGES = frozenset({"judge", "trace", "agent_usage", "usage"})
_AGENT_USAGE_UNAVAILABLE_REASON = "telemetry_generation_missing"
_NON_FATAL_CASE_ERROR_STATUSES = frozenset(
    {
        "provider_rate_limited",
        "document_fetch_failed",
        "ocr_content_filtered",
        "ocr_provider_rate_limited",
        "provider_internal_error",
    }
)
_KNOWN_AGENT_USAGE_NULL_SHA256 = (
    "b1c9186616c1b51dec881243a733a2fe9f6124e1c7e93fd68ec058c3da47cd03"
)


class CanaryV2Error(RuntimeError):
    """Gate técnico ou de configuração da campanha v2."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    path = EXPERIMENT_ROOT / manifest["evaluation_contract"]["ref"]
    return json.loads(path.read_text(encoding="utf-8"))


def _select_canary_item_id(requested_item_id: str | None) -> str:
    """Mantém o default histórico e aceita um item explícito do manifesto."""
    selected = requested_item_id or CANARY_ITEM_ID
    if selected not in EXPECTED_ITEM_IDS:
        raise CanaryV2Error(f"Item não pertence ao manifesto v2: {selected}")
    return selected


def _item_by_id(items: list[Any], item_id: str) -> Any:
    matches = [item for item in items if str(getattr(item, "id", "")) == item_id]
    if len(matches) != 1:
        raise CanaryV2Error(f"Item canário deve existir uma vez: {item_id}")
    return matches[0]


def _manifest_item(manifest: dict[str, Any], item_id: str) -> dict[str, Any]:
    matches = [item for item in manifest["items"] if item["item_id"] == item_id]
    if len(matches) != 1:
        raise CanaryV2Error(f"Item ausente no manifesto: {item_id}")
    return matches[0]


def _corpus(manifest: dict[str, Any], case_id: str) -> dict[str, Any]:
    matches = [corpus for corpus in manifest["corpora"] if corpus["case_id"] == case_id]
    if len(matches) != 1:
        raise CanaryV2Error(f"Corpus ausente no manifesto: {case_id}")
    return matches[0]


def _validate_v2_runtime_preflight(  # noqa: PLR0912 - contrato fail-closed
    preflight: dict[str, Any], manifest: dict[str, Any], contract: dict[str, Any]
) -> None:
    if preflight.get("session_main_model_profile") != "standard":
        raise CanaryV2Error("Profile principal efetivo diverge de standard")
    expected = contract["model_profiles"]
    if preflight.get("session_main_model") != expected["standard"]["deployment"]:
        raise CanaryV2Error("Deployment principal efetivo diverge da campanha")
    if preflight.get("session_classifier_model_profile") != "mini":
        raise CanaryV2Error("Profile auxiliar efetivo diverge de mini")
    if preflight.get("session_classifier_model") != expected["mini"]["deployment"]:
        raise CanaryV2Error("Deployment auxiliar efetivo diverge da campanha")
    if preflight.get("session_explorer_model_profile") != "nano":
        raise CanaryV2Error("Profile explorador efetivo diverge de nano")
    if preflight.get("session_explorer_model") != expected["nano"]["deployment"]:
        raise CanaryV2Error(
            "Deployment explorador (profile nano) efetivo diverge da campanha"
        )
    if preflight.get("session_ocr_model") != contract["ocr"]["deployment"]:
        raise CanaryV2Error("Deployment OCR efetivo diverge da campanha")
    campaign = contract.get("model_campaign")
    if campaign is not None and (
        preflight.get("session_reasoning_effort_requested")
        != campaign["reasoning_effort"]
    ):
        raise CanaryV2Error("Reasoning efetivo diverge da campanha")
    if preflight.get("session_main_model_client_retries") != 0:
        raise CanaryV2Error("Runner exige zero retry do cliente")
    if preflight.get("benchmark_no_cache_required") is not True:
        raise CanaryV2Error("Deployment não exige no_cache no benchmark")
    if (
        preflight.get("benchmark_document_source")
        != manifest["metadata"]["document_source"]
    ):
        raise CanaryV2Error("Fonte documental efetiva diverge do manifesto")
    if (
        preflight.get("benchmark_process_source")
        != manifest["metadata"]["process_source"]
    ):
        raise CanaryV2Error("Fonte processual efetiva diverge do manifesto")
    context_window = preflight.get("session_main_model_context_window_tokens")
    desired = manifest["metadata"]["desired_model_context_window_tokens"]
    if not isinstance(context_window, int) or context_window < desired:
        raise CanaryV2Error(
            "Janela efetiva do modelo é menor que a capacidade requerida"
        )
    if campaign is not None and context_window != campaign.get(
        "standard_context_window_tokens"
    ):
        raise CanaryV2Error("Janela efetiva diverge da configuração da campanha")


def _normalized_endpoint(value: str, *, origin_only: bool) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise CanaryV2Error("Endpoint SEI de referência é inválido")
    host = parsed.hostname.lower()
    default_port = 443 if parsed.scheme == "https" else 80
    netloc = host if parsed.port in {None, default_port} else f"{host}:{parsed.port}"
    path = "" if origin_only else parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def _load_sei_preflight_expectation(env_file: Path | None) -> dict[str, str]:
    """Fixa hashes do escopo SEI esperado sem herdar o shell conflitante."""
    if env_file is None or not env_file.is_file():
        raise CanaryV2Error("Arquivo explícito do ambiente SEI é obrigatório")
    values = dotenv_values(env_file)
    public_raw = values.get("SEI_ADDRESS")
    credential = values.get("SEI_API_DB_IDENTIFIER_SERVICE")
    if not public_raw or not credential:
        raise CanaryV2Error("Configuração SEI explícita está incompleta")
    api_raw = values.get("SEI_API_DB_ADDRESS") or (
        str(public_raw).rstrip("/") + "/sei/controlador_ws.php"
    )
    public_endpoint = _normalized_endpoint(str(public_raw), origin_only=True)
    api_endpoint = _normalized_endpoint(str(api_raw), origin_only=False)
    api_origin = _normalized_endpoint(str(api_raw), origin_only=True)
    if public_endpoint != api_origin:
        raise CanaryV2Error("Arquivo SEI explícito contém hosts cruzados")
    if (
        _sha256_text(public_endpoint) != PRODUCTION_SEI_PUBLIC_ENDPOINT_SHA256
        or _sha256_text(api_endpoint) != PRODUCTION_SEI_API_ENDPOINT_SHA256
    ):
        raise CanaryV2Error("Arquivo SEI explícito não pertence ao escopo de produção")
    return {
        "public_endpoint_sha256": _sha256_text(public_endpoint),
        "api_endpoint_sha256": _sha256_text(api_endpoint),
        "api_origin_sha256": _sha256_text(api_origin),
        "credential_sha256": _sha256_text(str(credential)),
    }


def _run_live_sei_preflight(
    *,
    http_client: Any,
    base_url: str,
    process_id: str,
    expectation: dict[str, str],
) -> dict[str, Any]:
    """Executa um único GET live no container e nunca propaga conteúdo da resposta."""
    started = time.monotonic()
    try:
        response = http_client.get(
            base_url + BENCHMARK_LIVE_PREFLIGHT_ENDPOINT,
            headers={"X-Benchmark-Process-Id": process_id},
        )
    except Exception as exc:  # noqa: BLE001 - persistência sanitizada e fail-closed
        return {
            "schema_version": "benchmark-sei-live-preflight-v1",
            "status": "failed",
            "http_status": None,
            "request_duration_s": max(0.0, time.monotonic() - started),
            "failure_category": "live_preflight_request_error",
            "error_type": type(exc).__name__,
            "expected": expectation,
        }
    request_duration_s = max(0.0, time.monotonic() - started)
    diagnostic: dict[str, Any] = {
        "schema_version": "benchmark-sei-live-preflight-v1",
        "status": "failed",
        "http_status": response.status_code,
        "request_duration_s": request_duration_s,
        "expected": expectation,
    }
    if response.status_code != 200:
        diagnostic["failure_category"] = (
            "authorization_rejected"
            if response.status_code in {401, 403}
            else "live_preflight_http_error"
        )
        return diagnostic
    try:
        payload = response.json()
    except (TypeError, ValueError):
        diagnostic["failure_category"] = "live_preflight_contract_error"
        return diagnostic
    if not isinstance(payload, dict):
        diagnostic["failure_category"] = "live_preflight_contract_error"
        return diagnostic
    safe_fields = {
        key: payload.get(key)
        for key in (
            "schema_version",
            "status",
            "live_query_performed",
            "public_api_scope_coherent",
            "credential_present",
            "public_endpoint_sha256",
            "api_endpoint_sha256",
            "api_origin_sha256",
            "credential_sha256",
            "response_type",
            "response_nonempty",
            "process_matched",
            "duration_s",
        )
    }
    return {
        **safe_fields,
        "http_status": response.status_code,
        "request_duration_s": request_duration_s,
        "expected": expectation,
    }


def _validate_live_sei_preflight(
    diagnostic: dict[str, Any], expectation: dict[str, str]
) -> None:
    expected_keys = {
        "public_endpoint_sha256",
        "api_endpoint_sha256",
        "api_origin_sha256",
        "credential_sha256",
    }
    checks = (
        set(expectation) == expected_keys,
        all(
            isinstance(value, str) and len(value) == 64
            for value in expectation.values()
        ),
        diagnostic.get("schema_version") == "benchmark-sei-live-preflight-v1",
        diagnostic.get("status") == "passed",
        diagnostic.get("http_status") == 200,
        diagnostic.get("live_query_performed") is True,
        diagnostic.get("public_api_scope_coherent") is True,
        diagnostic.get("credential_present") is True,
        diagnostic.get("response_type") == "dataframe",
        diagnostic.get("response_nonempty") is True,
        diagnostic.get("process_matched") is True,
        all(diagnostic.get(key) == value for key, value in expectation.items()),
    )
    if not all(checks):
        raise CanaryV2Error("preflight live SEI não comprovou o ambiente esperado")


def _guard_judge_config(
    contract: dict[str, Any], env_file: Path | None
) -> tuple[str, str, str]:
    values = _configured_values(env_file)
    url = values.get("LITELLM_PROXY_URL")
    key = values.get("LITELLM_PROXY_API_KEY")
    if not url or not key:
        raise CanaryV2Error("Configuração explícita do proxy do juiz está ausente")
    parsed = urlsplit(str(url))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CanaryV2Error("URL do proxy do juiz é inválida")
    judge = contract["judge"]
    deployment = judge.get("deployment")
    if judge.get("requested_profile") != "mini" or not isinstance(deployment, str):
        raise CanaryV2Error("Juiz deve usar o profile mini da campanha")
    return str(url).rstrip("/"), str(key), deployment


def _judge_usage_dict(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        raise TelemetryContractError("Resposta do juiz sem usage")
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    completion_details = getattr(usage, "completion_tokens_details", None)
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "cached_tokens": getattr(prompt_details, "cached_tokens", 0),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "reasoning_tokens": getattr(completion_details, "reasoning_tokens", 0),
    }


def _judge_with_retries(
    *,
    client: OpenAI,
    model: str,
    contract: dict[str, Any],
    item: dict[str, Any],
    material: Any,
    answer: str,
    evidence_package: list[dict[str, Any]],
    max_attempts: int,
    backoff_s: float,
    attempts_path: Path,
) -> tuple[
    Any | None, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None
]:
    """Retry apenas do juiz; toda resposta/usage é preservada e nada repete o agente."""
    system_prompt, user_prompt, schema = load_judge_artifacts(contract, EXPERIMENT_ROOT)
    payload = build_judge_input(
        item=item,
        material=material,
        answer=answer,
        evidence_package=evidence_package,
        contract=contract,
    )
    messages = judge_messages(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        judge_input=payload,
    )
    usage_records: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    score = None
    accepted_raw: dict[str, Any] | None = None
    retry_feedback: str | None = None
    for attempt in range(1, max_attempts + 1):
        response = None
        try:
            attempt_messages = messages
            if retry_feedback is not None:
                attempt_messages = [
                    *messages,
                    {
                        "role": "user",
                        "content": (
                            "O objeto JSON anterior violou o contrato semântico: "
                            f"{retry_feedback}. Reemita o objeto JSON completo e "
                            "corrija somente a coerência entre verdict, evidence_basis, "
                            "evidence_references e absence_evidence_reference."
                        ),
                    },
                ]
            request = {
                "model": model,
                "max_tokens": contract["judge"]["max_output_tokens"],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "benchmark_long_context_v2_judge",
                        "strict": True,
                        "schema": schema,
                    },
                },
                "messages": attempt_messages,
            }
            temperature = contract["judge"].get("temperature")
            if temperature is not None:
                request["temperature"] = temperature
            response = client.chat.completions.create(**request)
            raw_usage = _judge_usage_dict(response)
            usage_records.append(
                judge_usage_record(
                    raw_usage,
                    call_id=str(getattr(response, "id", f"judge-{attempt}")),
                    reported_model=getattr(response, "model", None),
                    contract=contract,
                )
            )
            content = response.choices[0].message.content or ""
            raw = parse_judge_output(content, schema)
            score = score_judge_output(
                raw,
                item=item,
                material=material,
                evidence_count=len(evidence_package),
                thresholds=contract["thresholds"],
            )
            accepted_raw = raw
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "accepted",
                    "response_id": getattr(response, "id", None),
                    "reported_model": getattr(response, "model", None),
                    "usage": raw_usage,
                    "raw": raw,
                    "retry_feedback_sha256": (
                        _sha256_text(retry_feedback)
                        if retry_feedback is not None
                        else None
                    ),
                }
            )
            break
        except Exception as exc:  # noqa: BLE001 - retry de avaliação é autorizado
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "rejected",
                    "error_type": type(exc).__name__,
                    "error_sha256": _sha256_text(str(exc)),
                    "response_id": getattr(response, "id", None),
                    "retry_feedback_sha256": (
                        _sha256_text(retry_feedback)
                        if retry_feedback is not None
                        else None
                    ),
                }
            )
            write_private_json(attempts_path, attempts)
            if isinstance(exc, JudgeV2ContractError):
                retry_feedback = str(exc)
            if attempt < max_attempts:
                time.sleep(backoff_s * (2 ** (attempt - 1)))
    write_private_json(attempts_path, attempts)
    return score, usage_records, attempts, accepted_raw


def _emit_scores(
    langfuse: Any, trace_id: str, contract_sha256: str, score: Any
) -> None:
    def score_id(name: str) -> str:
        return str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"benchmark-long-context-v2:{trace_id}:{contract_sha256}:{name}",
            )
        )

    for name, value in score.numeric.items():
        langfuse.create_score(
            trace_id=trace_id,
            score_id=score_id(name),
            name=name,
            value=value,
            data_type="NUMERIC",
            comment=score.rationale if name == "overall" else None,
        )
    for name, value in score.boolean.items():
        if value is not None:
            langfuse.create_score(
                trace_id=trace_id,
                score_id=score_id(name),
                name=name,
                value=1 if value else 0,
                data_type="BOOLEAN",
            )
    langfuse.create_score(
        trace_id=trace_id,
        score_id=score_id("target_alignment"),
        name="target_alignment",
        value=1 if score.auxiliary["target_alignment"] else 0,
        data_type="BOOLEAN",
    )
    langfuse.create_score(
        trace_id=trace_id,
        score_id=score_id("hallucination_count"),
        name="hallucination_count",
        value=score.auxiliary["hallucination_count"],
        data_type="NUMERIC",
    )


def _protected_report(result: dict[str, Any]) -> str:
    """Relatório integral; o chamador garante retenção 0600 fora do Git."""
    return "\n".join(
        [
            "# Canário long-context v2 — relatório protegido",
            "",
            f"Run: `{result['run_name']}`",
            f"Item: `{result['item_id']}`",
            f"Trace: `{result.get('trace_id')}`",
            f"Trace URL: {result.get('trace_url')}",
            "",
            "## Resposta integral",
            "",
            result.get("answer") or "N/D técnico",
            "",
            "## Evidências explícitas",
            "",
            "```json",
            json.dumps(result.get("evidence_package"), ensure_ascii=False, indent=2),
            "```",
            "",
            "## Avaliação canônica",
            "",
            "```json",
            json.dumps(result.get("evaluation"), ensure_ascii=False, indent=2),
            "```",
            "",
            "## Chamadas, tokens, custo e cobertura",
            "",
            "```json",
            json.dumps(
                {
                    "no_cache": result.get("no_cache"),
                    "latency": result.get("latency"),
                    "tool_calls": result.get("tool_calls"),
                    "usage": result.get("usage"),
                    "trace": result.get("trace"),
                    "technical_failures": result.get("technical_failures"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
            "## Gate",
            "",
            "```json",
            json.dumps(result.get("gate"), ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )


def _sanitized_result(result: dict[str, Any]) -> dict[str, Any]:
    evaluation = result.get("evaluation") or {}
    evidence = result.get("evidence_package") or []
    return {
        "schema_version": "benchmark-long-context-v2-canary-sanitized-1",
        "run_name": result["run_name"],
        "item_id": result["item_id"],
        "result_status": result.get("result_status", "completed"),
        "provider_rate_limit": result.get("provider_rate_limit"),
        "case_error": result.get("case_error"),
        "case_id": result.get("case_id"),
        "execution_id": result.get("execution_id"),
        "trace_id": result.get("trace_id"),
        "trace_url": "[retida no artefato protegido]",
        "replacement": result.get("replacement"),
        "recovery": result.get("recovery"),
        "sei_live_preflight": result.get("sei_live_preflight"),
        "transport": result.get("transport"),
        "no_cache": result.get("no_cache"),
        "latency": result.get("latency"),
        "context_disclosure_observed": result.get("context_disclosure_observed"),
        "evaluation_status": result.get("evaluation_status"),
        "trace_status": result.get("trace_status"),
        "execution_contract_sha256": result.get("execution_contract_sha256"),
        "telemetry_contract_sha256": result.get("telemetry_contract_sha256"),
        "evaluation": {
            "numeric": evaluation.get("numeric"),
            "boolean": evaluation.get("boolean"),
            "auxiliary": evaluation.get("auxiliary"),
            "gate": evaluation.get("gate"),
            "rationale_sha256": _sha256_text(str(evaluation.get("rationale", ""))),
            "claim_verdict_counts": {
                verdict: sum(
                    claim.get("verdict") == verdict
                    for claim in evaluation.get("claims", [])
                )
                for verdict in ("supported", "unsupported", "contradicted")
            },
        },
        "evidence": {
            "count": len(evidence),
            "package_sha256": stable_digest(evidence) if evidence else None,
            "observability": result.get("evidence_observability"),
        },
        "tool_calls": result.get("tool_calls"),
        "usage": result.get("usage"),
        "trace": result.get("trace"),
        "judge_attempts": [
            {
                "attempt": row.get("attempt"),
                "status": row.get("status"),
                "error_type": row.get("error_type"),
            }
            for row in result.get("judge_attempts", [])
        ],
        "technical_failures": result.get("technical_failures"),
        "gate": result.get("gate"),
    }


def _build_canary_gate(
    result: dict[str, Any],
    *,
    canary_item_id: str,
    quality_gate: dict[str, Any],
    trace_ok: bool,
    usage_coverage: bool,
    cold_start_required: bool | None = None,
    full_battery_authorized: bool = False,
) -> dict[str, Any]:
    """Compõe dimensões independentes sem chamar o conjunto de qualidade."""
    no_cache = result.get("no_cache")
    cold_start_comparable = (
        isinstance(no_cache, dict) and no_cache.get("cold_start_comparable") is True
    )
    if cold_start_required is None:
        cold_start_required = canary_item_id == SECOND_CANARY_ITEM_ID
    dimensions = {
        "quality": quality_gate,
        "comparability": {
            "checks": {
                "context_disclosure": (
                    result.get("context_disclosure_observed") is True
                ),
                "no_cache_effective": (
                    isinstance(no_cache, dict)
                    and no_cache.get("requested") is True
                    and no_cache.get("effective") is True
                ),
                "cold_start_comparable_when_required": (
                    cold_start_comparable or not cold_start_required
                ),
            },
            "cold_start_comparable": cold_start_comparable,
            "cold_start_comparable_required": cold_start_required,
        },
        "observability": {
            "checks": {
                "trace_complete_and_dataset_linked": trace_ok,
                "usage_coverage_complete": usage_coverage,
            }
        },
        "integrity_technical": {
            "checks": {
                "single_item": result["item_id"] == canary_item_id,
                "transport_http_200_terminal_end": (
                    result.get("transport", {}).get("http_status") == 200
                    and (
                        result.get("transport", {}).get("terminal_type") == "end"
                        or result.get("transport", {}).get(
                            "recovered_after_post_agent_export_error"
                        )
                        is True
                    )
                ),
                "no_technical_failures": not result["technical_failures"],
            }
        },
    }
    for name, dimension in dimensions.items():
        if name == "quality":
            continue
        passed = all(dimension["checks"].values())
        dimension["status"] = "passed" if passed else "failed"
    passed = all(
        dimension.get("status") == "passed" for dimension in dimensions.values()
    )
    failed_dimensions = [
        name
        for name, dimension in dimensions.items()
        if dimension.get("status") != "passed"
    ]
    return {
        "schema_version": "benchmark-long-context-v2-canary-gate-2",
        "policy_version": QUALITY_GATE_POLICY_VERSION,
        "dimensions": dimensions,
        "status": "passed" if passed else "failed",
        "failed_dimensions": failed_dimensions,
        "authorized_canary": {
            "status": "passed" if passed else "failed",
            "explicit_full_battery_authorization_required": True,
        },
        "stop_after_canary": not full_battery_authorized,
        "full_battery_authorized": full_battery_authorized,
    }


def _mark_agent_usage_metric_null(usage: dict[str, Any]) -> None:
    """Registra a lacuna de geração como métrica nula, sem invalidar a célula."""
    known_cost = usage.get("total_cost_usd")
    usage["agent_usage"] = None
    usage["agent_usage_reason"] = _AGENT_USAGE_UNAVAILABLE_REASON
    coverage = usage.setdefault("coverage", {})
    coverage["status"] = "complete"
    coverage["generation_records"] = 0
    agent = usage.setdefault("by_scope", {}).setdefault("agent", {})
    agent.update(
        {
            "available": False,
            "calls": None,
            "tokens": None,
            "cost_usd": None,
            "reason": _AGENT_USAGE_UNAVAILABLE_REASON,
        }
    )
    usage["total_cost_usd"] = None
    usage["cost"] = {
        "cost_usd": None,
        "known_subtotal_excluding_agent_usage_usd": (
            float(known_cost) if isinstance(known_cost, (int, float)) else None
        ),
        "missing_usage": ["agent_usage"],
    }


def _reclassify_missing_agent_usage(
    result: dict[str, Any], *, canary_item_id: str
) -> bool:
    """Corrige offline o legado que confundia métrica nula com falha da célula."""
    matching = [
        failure
        for failure in result.get("technical_failures") or []
        if failure.get("stage") == "agent_usage"
        and failure.get("error_type") == "TelemetryContractError"
        and failure.get("error_sha256") == _KNOWN_AGENT_USAGE_NULL_SHA256
    ]
    trace = result.get("trace") or {}
    transport = result.get("transport") or {}
    usage = result.get("usage") or {}
    coverage = usage.get("coverage") or {}
    agent_scope = (usage.get("by_scope") or {}).get("agent") or {}
    recovered_without_failure_row = (
        not result.get("technical_failures")
        and trace.get("status") == "technical_unavailable"
    )
    if (
        (len(matching) != 1 and not recovered_without_failure_row)
        or trace.get("read_status") != "complete"
        or trace.get("dataset_linked") is not True
        or transport.get("http_status") != 200
        or transport.get("terminal_type") != "end"
        or result.get("evaluation_status") != "evaluated"
        or coverage.get("generation_records") != 0
        or agent_scope.get("available") is not False
        or agent_scope.get("calls") != 0
    ):
        return False
    result["technical_failures"] = [
        failure
        for failure in result.get("technical_failures") or []
        if failure not in matching
    ]
    result["trace_status"] = "complete"
    trace["status"] = "complete"
    result["trace"] = trace
    _mark_agent_usage_metric_null(result["usage"])
    synchronized_gate = _synchronize_external_quality_gate(result)
    quality_gate = (synchronized_gate or {}).get("dimensions", {}).get("quality") or {}
    result["gate"] = _build_canary_gate(
        result,
        canary_item_id=canary_item_id,
        quality_gate=quality_gate,
        trace_ok=True,
        usage_coverage=True,
        cold_start_required=True,
        full_battery_authorized=True,
    )
    return True


def _reclassify_agent_usage_from_persisted_trace(
    result: dict[str, Any], *, trace_path: Path, contract: dict[str, Any]
) -> bool:
    """Recalcula usage offline quando o SDK omitiu ``usage_details``."""
    matching = [
        failure
        for failure in result.get("technical_failures") or []
        if failure.get("stage") == "agent_usage"
        and failure.get("error_type") == "TelemetryContractError"
        and failure.get("error_sha256") == _KNOWN_AGENT_USAGE_NULL_SHA256
    ]
    if len(matching) != 1 or not trace_path.is_file() or trace_path.is_symlink():
        return False
    raw_trace = json.loads(trace_path.read_text(encoding="utf-8"))
    raw_observations = raw_trace.get("observations") or []
    sdk_observations = [
        SimpleNamespace(
            id=row.get("id"),
            type=row.get("type"),
            name=row.get("name"),
            parent_observation_id=row.get("parent_observation_id"),
            start_time=None,
            end_time=None,
            metadata=row.get("metadata"),
            model=row.get("model"),
            usage_details=row.get("usage_details"),
            usage=row.get("usage"),
        )
        for row in raw_observations
    ]
    try:
        agent_usage = agent_usage_records(
            normalize(sdk_observations),
            trace_id=str(result.get("trace_id") or "persisted-trace"),
            contract=contract,
        )
    except TelemetryContractError:
        return False
    if not agent_usage:
        return False
    accepted_attempts = [
        attempt
        for attempt in result.get("judge_attempts", [])
        if attempt.get("status") == "accepted"
    ]
    if len(accepted_attempts) != 1:
        return False
    judge_attempt = accepted_attempts[0]
    judge_usage = judge_usage_record(
        judge_attempt["usage"],
        call_id=judge_attempt["response_id"],
        reported_model=judge_attempt.get("reported_model"),
        contract=contract,
    )
    rate_card = json.loads(
        (EXPERIMENT_ROOT / contract["rate_card"]["ref"]).read_text(encoding="utf-8")
    )
    result["usage"] = summarize_usage(
        [
            *agent_usage,
            *ocr_usage_records(result.get("ocr_usage") or [], contract=contract),
            judge_usage,
        ],
        rate_card=rate_card,
        rate_card_ref=contract["rate_card"],
    )
    result["technical_failures"] = [
        failure
        for failure in result.get("technical_failures") or []
        if failure not in matching
    ]
    result["trace_status"] = "complete"
    result.setdefault("trace", {})["status"] = "complete"
    synchronized_gate = _synchronize_external_quality_gate(result)
    quality_gate = (synchronized_gate or {}).get("dimensions", {}).get("quality") or {}
    result["gate"] = _build_canary_gate(
        result,
        canary_item_id=str(result["item_id"]),
        quality_gate=quality_gate,
        trace_ok=True,
        usage_coverage=True,
        cold_start_required=True,
        full_battery_authorized=True,
    )
    return True


def _mark_case_error_result(
    result: dict[str, Any],
    *,
    outcome: SSEOutcome,
    raw_path: Path | None = None,
    result_status: str | None = None,
) -> bool:
    """Conclui 429/409 por caso sem fabricar avaliação, telemetria ou retry."""
    if outcome.terminal_type != "error":
        return False
    status_code = outcome.terminal_status_code
    case_error = None
    if status_code == 429:
        retry_after_s = None
        if raw_path is not None:
            terminal = next(
                (
                    frame
                    for line in reversed(
                        raw_path.read_text(encoding="utf-8").splitlines()
                    )
                    if line.startswith("data: ")
                    and (frame := json.loads(line[6:])).get("type") == "error"
                ),
                None,
            )
            candidates = (
                terminal.get("retry_after_s") if isinstance(terminal, dict) else None,
                (terminal.get("diagnostic") or {}).get("retry_after_s")
                if isinstance(terminal, dict)
                and isinstance(terminal.get("diagnostic"), dict)
                else None,
            )
            retry_after_s = next(
                (
                    float(value)
                    for value in candidates
                    if isinstance(value, (int, float)) and value > 0
                ),
                None,
            )
        result_status = "provider_rate_limited"
        result["provider_rate_limit"] = {
            "http_status": 429,
            "retry_after_s": retry_after_s,
            "rate_limit_code": None,
        }
    elif (
        status_code == 500
        and result_status == "provider_internal_error"
        and raw_path is not None
    ):
        case_error = {
            "category": result_status,
            "http_status": 500,
            "raw_sse_sha256": file_sha256(raw_path),
        }
    elif status_code == 409 and raw_path is not None:
        terminal = next(
            (
                frame
                for line in reversed(raw_path.read_text(encoding="utf-8").splitlines())
                if line.startswith("data: ")
                and (frame := json.loads(line[6:])).get("type") == "error"
            ),
            None,
        )
        diagnostic = terminal.get("diagnostic") if isinstance(terminal, dict) else None
        if not isinstance(diagnostic, dict) or (
            diagnostic.get("category"),
            diagnostic.get("stage"),
        ) != ("document_fetch_failed", "fetch_validate_before_write"):
            return False
        result_status = result_status or "document_fetch_failed"
        case_error = {
            "category": result_status,
            "http_status": 409,
            "diagnostic_category": diagnostic["category"],
            "diagnostic_stage": diagnostic["stage"],
            "diagnostic_fingerprint": diagnostic.get("fingerprint"),
            "raw_sse_sha256": file_sha256(raw_path),
        }
    else:
        return False
    if result_status not in _NON_FATAL_CASE_ERROR_STATUSES:
        return False
    transport = result.setdefault("transport", {})
    transport["terminal_type"] = "error"
    transport["terminal_status_code"] = status_code
    result.update(
        {
            "result_status": result_status,
            "answer": None,
            "evaluation": None,
            "evaluation_status": None,
            "trace_status": None,
            "usage": None,
            "gate": None,
            "technical_failures": [],
        }
    )
    if case_error is not None:
        result["case_error"] = case_error
    return True


def _mark_provider_rate_limited_result(
    result: dict[str, Any], *, outcome: SSEOutcome
) -> bool:
    """Compatibilidade do contrato histórico para tentativa 429."""
    return _mark_case_error_result(result, outcome=outcome)


def _quality_gate_from_result(
    result: dict[str, Any], *, question_type: str, contract: dict[str, Any]
) -> dict[str, Any]:
    evaluation = result.get("evaluation")
    if not isinstance(evaluation, dict):
        return {
            "policy_version": QUALITY_GATE_POLICY_VERSION,
            "status": "unavailable",
            "validity": "unavailable",
            "blocking_checks": None,
            "non_blocking_diagnostics": None,
        }
    numeric = evaluation.get("numeric")
    boolean = evaluation.get("boolean")
    auxiliary = evaluation.get("auxiliary")
    if not all(isinstance(value, dict) for value in (numeric, boolean, auxiliary)):
        raise CanaryV2Error("Avaliação persistida não permite classificar qualidade")
    answer = result.get("answer")
    return classify_quality_gate(
        numeric=numeric,
        boolean=boolean,
        auxiliary=auxiliary,
        negative=question_type == "insufficient-evidence",
        answer_nonempty=isinstance(answer, str) and bool(answer.strip()),
        thresholds=contract["thresholds"],
    )


def _load_replacement_proof(
    *, ledger: V2Ledger, output_root: Path, policy: dict[str, str]
) -> dict[str, Any]:
    """Prova pelos artefatos preservados que o predecessor não iniciou agente."""
    events = ledger.events()
    predecessor_rows = [
        event
        for event in events
        if event.get("execution_id") == policy["predecessor_execution_id"]
    ]
    reservations = [
        event
        for event in predecessor_rows
        if event.get("event_type") == "reservation"
        and event.get("run_name") == policy["predecessor_run_name"]
        and event.get("item_id") == policy["item_id"]
    ]
    if len(reservations) != 1:
        raise CanaryV2Error("Reserva do predecessor inválido não foi comprovada")
    if any(
        event.get("event_type") == "official_evaluation" for event in predecessor_rows
    ):
        raise CanaryV2Error("Predecessor inválido possui avaliação oficial")

    run_root = output_root / "runs" / policy["predecessor_run_name"]
    item_root = run_root / "items" / policy["item_id"]
    is_ocr_remediation = policy.get("kind") == "ocr_materialization"
    sanitized_path = run_root / (
        "canary-result-sanitized.json"
        if is_ocr_remediation
        else "second-canary-result-sanitized.json"
    )
    result_path = item_root / "result-protected.json"
    trace_path = item_root / "trace-readback.raw.json"
    for path in (sanitized_path, result_path, trace_path):
        if not path.is_file() or path.is_symlink():
            raise CanaryV2Error("Artefato preservado do predecessor está ausente")
    sanitized = json.loads(sanitized_path.read_text(encoding="utf-8"))
    protected = json.loads(result_path.read_text(encoding="utf-8"))
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    observations = trace.get("observations") if isinstance(trace, dict) else None
    if not isinstance(observations, list):
        raise CanaryV2Error("Trace preservado do predecessor é inválido")
    generations = [
        row
        for row in observations
        if isinstance(row, dict) and row.get("type") == "GENERATION"
    ]
    observation_tokens = sum(
        int((row.get("usage") or {}).get("total") or 0)
        for row in observations
        if isinstance(row, dict) and isinstance(row.get("usage"), dict)
    )
    observation_cost = sum(
        float(row.get("calculatedTotalCost") or 0)
        for row in observations
        if isinstance(row, dict)
    )
    protected_identity_ok = (
        sanitized.get("trace_id") == policy["predecessor_trace_id"]
        and sanitized.get("item_id") == policy["item_id"]
        and protected.get("execution_id") == policy["predecessor_execution_id"]
        and protected.get("trace_id") == policy["predecessor_trace_id"]
        and trace.get("id") == policy["predecessor_trace_id"]
    )
    identity_ok = protected_identity_ok and (
        is_ocr_remediation
        or sanitized.get("execution_id") == policy["predecessor_execution_id"]
    )
    if is_ocr_remediation:
        usage = sanitized.get("usage") or {}
        proof_checks = {
            "identity": identity_ok,
            "failure_stage": (
                sanitized.get("failure", {}).get("stage")
                == "session_materialization_validation"
                and sanitized.get("failure", {}).get("category")
                == "materialized_missing"
                and protected.get("evaluation_status") == "technical_unavailable"
                and protected.get("answer") is None
            ),
            "zero_generations": (
                not generations and sanitized.get("trace", {}).get("generations") == 0
            ),
            "zero_tools": (
                sanitized.get("tool_calls", {}).get("total") == 0
                and len(observations) == 1
            ),
            "zero_judge_calls": (
                usage.get("by_scope", {}).get("judge", {}).get("calls") == 0
                and protected.get("evaluation") is None
                and protected.get("judge_attempts") == []
            ),
            "zero_tokens": (
                usage.get("observed_total_tokens") == 0 and observation_tokens == 0
            ),
            "zero_cost": (
                usage.get("total_cost_usd") == 0
                and float(trace.get("totalCost") or 0) == 0
                and observation_cost == 0
            ),
        }
    else:
        proof_checks = {
            "identity": identity_ok,
            "failure_stage": (
                sanitized.get("agent_inference_started") is False
                and sanitized.get("failure", {}).get("stage")
                == "pre_agent_process_metadata_refresh"
                and sanitized.get("failure", {}).get("status")
                == "technical_unavailable"
                and protected.get("evaluation_status") == "technical_unavailable"
            ),
            "zero_generations": (
                not generations
                and sanitized.get("trace", {}).get("generations") == 0
                and sanitized.get("usage", {}).get("agent_llm_calls") == 0
            ),
            "zero_tools": (
                sanitized.get("tools", {}).get("calls") == 0 and len(observations) == 1
            ),
            "zero_judge_calls": (
                sanitized.get("evaluation", {}).get("judge_calls") == 0
                and sanitized.get("usage", {}).get("judge_llm_calls") == 0
                and protected.get("evaluation") is None
                and protected.get("judge_attempts") is None
            ),
            "zero_tokens": (
                sanitized.get("usage", {}).get("observed_total_tokens") == 0
                and observation_tokens == 0
            ),
            "zero_cost": (
                sanitized.get("usage", {}).get("observed_total_cost_usd") == 0
                and float(trace.get("totalCost") or 0) == 0
                and observation_cost == 0
            ),
        }
    if not all(proof_checks.values()):
        failed = sorted(key for key, value in proof_checks.items() if not value)
        raise CanaryV2Error("Prova do predecessor inválido falhou: " + ",".join(failed))
    return {
        "failure_stage": "pre_agent",
        **({"failure_category": "materialized_missing"} if is_ocr_remediation else {}),
        "technical_failure": True,
        "zero_generations": True,
        "zero_tools": True,
        "zero_judge_calls": True,
        "zero_tokens": True,
        "zero_cost": True,
        "artifacts_sha256": {
            "sanitized_result": file_sha256(sanitized_path),
            "protected_result": file_sha256(result_path),
            "trace_readback": file_sha256(trace_path),
        },
    }


def _preflight_and_reserve(
    *,
    ledger: V2Ledger,
    live_preflight_path: Path,
    http_client: Any,
    base_url: str,
    process_id: str,
    expectation: dict[str, str],
    reservation_kwargs: dict[str, str],
    replacement_policy: dict[str, str] | None = None,
    replacement_proof: dict[str, Any] | None = None,
    full_battery_authorization_event_id: str | None = None,
    full_battery_retry_of_execution_id: str | None = None,
    prevalidated_live_diagnostic: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Executa/prova o GET live antes de qualquer autorização ou reserva."""
    diagnostic = prevalidated_live_diagnostic or _run_live_sei_preflight(
        http_client=http_client,
        base_url=base_url,
        process_id=process_id,
        expectation=expectation,
    )
    write_private_json(live_preflight_path, diagnostic)
    _validate_live_sei_preflight(diagnostic, expectation)
    if full_battery_authorization_event_id is not None:
        if replacement_policy is not None or replacement_proof is not None:
            raise CanaryV2Error(
                "Bateria não aceita política de substituição do canário"
            )
        if full_battery_retry_of_execution_id is not None:
            return (
                ledger.reserve_full_battery_retry(
                    authorization_event_id=full_battery_authorization_event_id,
                    predecessor_execution_id=full_battery_retry_of_execution_id,
                    **reservation_kwargs,
                ),
                diagnostic,
            )
        return (
            ledger.reserve_full_battery_item(
                authorization_event_id=full_battery_authorization_event_id,
                **reservation_kwargs,
            ),
            diagnostic,
        )
    if replacement_policy is None:
        if replacement_proof is not None:
            raise CanaryV2Error("Prova de substituição sem política explícita")
        return ledger.reserve(**reservation_kwargs), diagnostic
    if replacement_proof is None:
        raise CanaryV2Error("Substituição sem prova do predecessor")
    authorization_args = {
        "predecessor_execution_id": replacement_policy["predecessor_execution_id"],
        "predecessor_trace_id": replacement_policy["predecessor_trace_id"],
        "item_id": replacement_policy["item_id"],
        "reason": replacement_policy["reason"],
        "captain_authorization": replacement_policy["captain_authorization"],
        "proof": replacement_proof,
    }
    if replacement_policy.get("kind") == "ocr_materialization":
        authorization = ledger.authorize_remediation_replay(**authorization_args)
        reservation = ledger.reserve_remediation_replay(
            authorization_event_id=authorization["event_id"],
            predecessor_execution_id=replacement_policy["predecessor_execution_id"],
            **reservation_kwargs,
        )
    else:
        authorization = ledger.authorize_replacement(**authorization_args)
        reservation = ledger.reserve_replacement(
            authorization_event_id=authorization["event_id"],
            predecessor_execution_id=replacement_policy["predecessor_execution_id"],
            **reservation_kwargs,
        )
    return reservation, diagnostic


def execute_canary(  # noqa: C901, PLR0912, PLR0915
    *,
    manifest: dict[str, Any],
    contract: dict[str, Any],
    protected_bundle_root: Path,
    output_root: Path,
    run_name: str,
    item: Any,
    langfuse: Any,
    langfuse_host: str,
    project_id: str,
    http_client: Any,
    base_url: str,
    judge_client: OpenAI,
    judge_model: str,
    trace_wait_s: float,
    trace_poll_s: float,
    trace_max_retries: int,
    trace_backoff_factor: float,
    trace_backoff_max_s: float,
    judge_max_attempts: int,
    judge_backoff_s: float,
    runtime_preflight: dict[str, Any],
    sei_preflight_expectation: dict[str, str],
    replacement_policy: dict[str, str] | None = None,
    canary_item_id: str = CANARY_ITEM_ID,
    full_battery_authorization_event_id: str | None = None,
    full_battery_retry_of_execution_id: str | None = None,
    full_battery_live_preflight: dict[str, Any] | None = None,
    full_battery_mode: bool = False,
) -> dict[str, Any]:
    """Executa exatamente um POST; julgamento e readback podem retry sem nova inferência."""
    if full_battery_mode:
        if canary_item_id not in EXPECTED_ITEM_IDS:
            raise CanaryV2Error("Item alheio à bateria v2")
        if full_battery_authorization_event_id is None:
            raise CanaryV2Error("Bateria sem evento de autorização")
    else:
        canary_item_id = _select_canary_item_id(canary_item_id)
    item_manifest = _manifest_item(manifest, canary_item_id)
    case_id = item_manifest["case_id"]
    material = load_judge_material(item_manifest, protected_bundle_root)
    corpus = _corpus(manifest, case_id)
    process_metadata = load_protected_json(
        corpus["process_metadata_ref"], protected_bundle_root
    )
    topic_id = TopicFactory().new()
    payload = build_execution_payload(item.input, topic_id)
    if payload.get("text") != material.question:
        raise CanaryV2Error("Pergunta do dataset diverge da referência protegida")
    if payload.get("id_procedimentos") != process_metadata.get("id_procedimentos"):
        raise CanaryV2Error("Procedimentos divergem da referência protegida")
    if payload.get("use_websearch") is not False:
        raise CanaryV2Error("Canário v2 não permite websearch")
    if (
        payload.get("no_cache") is not True
        or manifest["metadata"]["no_cache"] is not True
    ):
        raise CanaryV2Error("Canário v2 exige no_cache=true")

    process_rows = process_metadata.get("id_procedimentos")
    if not isinstance(process_rows, list) or len(process_rows) != 1:
        raise CanaryV2Error("Canário substituto exige um único processo protegido")
    process_id = str(process_rows[0].get("id_procedimento") or "")
    if not process_id:
        raise CanaryV2Error("Processo protegido ausente no canário")

    run_root = output_root / "runs" / run_name
    items_root = run_root / "items"
    item_root = items_root / canary_item_id
    run_root.mkdir(parents=True, exist_ok=False, mode=0o700)
    run_root.chmod(0o700)
    write_private_json(run_root / "runtime-preflight.json", runtime_preflight)
    output_root.chmod(0o700)
    (output_root / "runs").chmod(0o700)
    ledger = V2Ledger(output_root / "execution-ledger.jsonl")
    replacement_proof = (
        _load_replacement_proof(
            ledger=ledger, output_root=output_root, policy=replacement_policy
        )
        if replacement_policy is not None
        else None
    )
    contract_sha = manifest["evaluation_contract"]["sha256"]
    reservation, live_sei_preflight = _preflight_and_reserve(
        ledger=ledger,
        live_preflight_path=run_root / "sei-live-preflight.json",
        http_client=http_client,
        base_url=base_url,
        process_id=process_id,
        expectation=sei_preflight_expectation,
        reservation_kwargs={
            "run_name": run_name,
            "item_id": canary_item_id,
            "contract_sha256": contract_sha,
            "request_identity_sha256": stable_digest(payload),
        },
        replacement_policy=replacement_policy,
        replacement_proof=replacement_proof,
        full_battery_authorization_event_id=(
            full_battery_authorization_event_id if full_battery_mode else None
        ),
        full_battery_retry_of_execution_id=(
            full_battery_retry_of_execution_id if full_battery_mode else None
        ),
        prevalidated_live_diagnostic=full_battery_live_preflight,
    )
    execution_id = reservation["execution_id"]
    item_root.mkdir(parents=True, exist_ok=False, mode=0o700)
    item_root.chmod(0o700)
    items_root.chmod(0o700)
    replacement = (
        {
            "reason": replacement_policy["reason"],
            "predecessor_execution_id": replacement_policy["predecessor_execution_id"],
            "predecessor_trace_id": replacement_policy["predecessor_trace_id"],
            "authorization_event_id": reservation["replacement_authorization_event_id"],
        }
        if replacement_policy is not None
        else None
    )

    result: dict[str, Any] = {
        "schema_version": "benchmark-long-context-v2-canary-protected-1",
        "run_name": run_name,
        "item_id": canary_item_id,
        "case_id": case_id,
        "execution_id": execution_id,
        "replacement": replacement,
        "sei_live_preflight": live_sei_preflight,
        "trace_id": None,
        "trace_url": None,
        "execution_contract_sha256": contract_sha,
        "telemetry_contract_sha256": contract_sha,
        "answer": None,
        "evidence_package": None,
        "evaluation": None,
        "evaluation_status": "pending_evaluation",
        "trace_status": "pending_trace",
        "no_cache": None,
        "latency": None,
        "usage": None,
        "technical_failures": [],
    }
    protected_result_path = item_root / "result-protected.json"
    raw_sse_path = item_root / "stream.raw.sse"
    trace_id: str | None = None
    outcome = None

    try:
        with item.run(
            run_name=run_name,
            run_metadata={
                "benchmark": DATASET_NAME,
                "campaign": (
                    "long-context-v2-full-battery"
                    if full_battery_mode
                    else "long-context-v2"
                ),
                "contract_sha256": contract_sha,
                "case_id": case_id,
                "n": 1,
                "transport": "http",
                "endpoint": SESSION_ENDPOINT,
                "websearch": False,
                "no_cache": True,
                "document_source": manifest["metadata"]["document_source"],
                "process_source": manifest["metadata"]["process_source"],
                "inference_retry": False,
                "warmup": False,
                "canary": not full_battery_mode,
                "full_battery_authorized": full_battery_mode,
                "replacement_of_execution_id": (
                    replacement["predecessor_execution_id"]
                    if replacement is not None
                    else None
                ),
            },
        ) as span:
            trace_id = span.trace_id
            result["trace_id"] = trace_id
            result["trace_url"] = (
                f"{langfuse_host.rstrip('/')}/project/{project_id}/traces/{trace_id}"
            )
            ledger.transition(
                execution_id,
                event_type="trace_bound",
                trace_id=trace_id,
                post_attempted=False,
                trace_status="pending_trace",
            )
            http_status, content_type, outcome = _stream_once(
                client=http_client,
                base_url=base_url,
                payload=payload,
                trace_id=trace_id,
                raw_path=raw_sse_path,
            )
            response_metadata = (
                outcome.metadata if isinstance(outcome.metadata, dict) else {}
            )
            result["ocr_usage"] = response_metadata.get("benchmark_ocr_usage") or []
            no_cache_effective = response_metadata.get("no_cache")
            evidence_diagnostic = (
                response_metadata.get("benchmark_evidence_preflight") or {}
            )
            preparation_s = response_metadata.get("preparation_duration_s")
            post_preparation_s = (
                max(0.0, outcome.observed_response_time_s - preparation_s)
                if isinstance(preparation_s, (int, float))
                else None
            )
            result["no_cache"] = {
                "requested": payload["no_cache"],
                "effective": no_cache_effective,
                "document_source": evidence_diagnostic.get("runtime_document_source"),
                "snapshot_role": evidence_diagnostic.get("snapshot_role"),
                "process_source": response_metadata.get("benchmark_process_source"),
                "session_reset": response_metadata.get("benchmark_session_reset"),
                "cold_start_comparable": (
                    payload["no_cache"] is True
                    and no_cache_effective is True
                    and evidence_diagnostic.get("runtime_document_source")
                    == "sei_no_cache"
                    and evidence_diagnostic.get("snapshot_role") == "validation_only"
                    and response_metadata.get("benchmark_process_source")
                    == "sei_no_cache"
                    and response_metadata.get("benchmark_session_reset") is True
                ),
            }
            result["latency"] = {
                "session_preparation_s": preparation_s,
                "stream_terminal_s": outcome.observed_response_time_s,
                "post_preparation_stream_s": post_preparation_s,
                "evaluation_s": None,
                "trace_readback_s": None,
                "inference_latency_scope": "session_preparation + post_preparation_stream",
                "excluded_from_inference_latency": ["evaluation_s", "trace_readback_s"],
            }
            result["transport"] = {
                "http_status": http_status,
                "content_type": content_type,
                "terminal_type": outcome.terminal_type,
                "terminal_status_code": outcome.terminal_status_code,
                "response_time_s": outcome.observed_response_time_s,
                "preparation_heartbeat_frames": outcome.preparation_heartbeat_frames,
                "no_cache_effective": no_cache_effective,
                "answer_sha256": _sha256_text(outcome.content),
            }
            if outcome.terminal_type != "end":
                raise CanaryV2Error("Stream terminou com frame SSE de erro")
            if no_cache_effective is not True:
                raise CanaryV2Error("Resposta não comprovou no_cache=true")
            if (
                full_battery_mode or canary_item_id == SECOND_CANARY_ITEM_ID
            ) and result["no_cache"]["cold_start_comparable"] is not True:
                raise CanaryV2Error("Segundo canário não comprovou cold start SEI")
            result["answer"] = outcome.content
            span.update(
                output={
                    "terminal_type": outcome.terminal_type,
                    "answer_sha256": result["transport"]["answer_sha256"],
                    "response_time_s": outcome.observed_response_time_s,
                }
            )
        ledger.transition(
            execution_id,
            event_type="post_completed",
            trace_id=trace_id,
            post_attempted=True,
            evaluation_status="pending_evaluation",
            trace_status="pending_trace",
        )
        write_private_json(protected_result_path, result)
    except Exception as exc:  # exatamente uma tentativa; nunca repetir aqui
        if (
            full_battery_mode
            and outcome is not None
            and _mark_case_error_result(
                result,
                outcome=outcome,
                raw_path=raw_sse_path,
            )
        ):
            event_type = (
                "provider_rate_limited"
                if result["result_status"] == "provider_rate_limited"
                else "case_error_recorded"
            )
            ledger.transition(
                execution_id,
                event_type=event_type,
                trace_id=trace_id,
                post_attempted=True,
                detail={
                    "result_status": result["result_status"],
                    "http_status": outcome.terminal_status_code,
                },
            )
            write_private_json(protected_result_path, result)
            return result
        result["technical_failures"].append(
            {
                "stage": "agent",
                "error_type": type(exc).__name__,
                "error_sha256": _sha256_text(str(exc)),
            }
        )
        result["evaluation_status"] = "technical_unavailable"
        result["trace_status"] = "technical_unavailable"
        ledger.transition(
            execution_id,
            event_type="agent_failed",
            trace_id=trace_id,
            post_attempted=raw_sse_path.exists(),
            evaluation_status="technical_unavailable",
            trace_status="technical_unavailable",
            detail={
                "error_type": type(exc).__name__,
                "error_sha256": _sha256_text(str(exc)),
            },
        )
        write_private_json(protected_result_path, result)
        raise

    if outcome is None or outcome.terminal_type != "end" or not outcome.content.strip():
        raise CanaryV2Error("Stream não terminou com resposta válida")
    benchmark_metrics = (
        outcome.metadata.get("benchmark_metrics")
        if isinstance(outcome.metadata, dict)
        else None
    )
    tool_summary = _sanitized_tool_summary(benchmark_metrics)
    result["tool_calls"] = {
        "total": tool_summary["total_calls"],
        "by_name": tool_summary["calls_by_name"],
    }
    result["context_disclosure_observed"] = _context_disclosure_observed(
        item=item,
        metadata=outcome.metadata,
        tool_summary=tool_summary,
    )
    if not result["context_disclosure_observed"]:
        raise CanaryV2Error("Context disclosure não foi observado")
    opened_evidence, evidence_observability = build_evidence_package(
        index_path=protected_bundle_root / "evidence-index.json",
        case_id=case_id,
        answer=outcome.content,
        tool_summary=tool_summary,
        fresh_evidence=response_metadata.get("benchmark_fresh_evidence"),
    )
    evidence_package = merge_evidence_package(material.source_evidence, opened_evidence)
    result["evidence_package"] = evidence_package
    result["evidence_observability"] = evidence_observability
    write_private_json(protected_result_path, result)
    ledger.transition(
        execution_id,
        event_type="evidence_persisted",
        trace_id=trace_id,
        post_attempted=True,
        evaluation_status="pending_evaluation",
        artifact_sha256=file_sha256(protected_result_path),
    )

    judge_started = time.monotonic()
    score, judge_usage, judge_attempts, accepted_raw = _judge_with_retries(
        client=judge_client,
        model=judge_model,
        contract=contract,
        item=item_manifest,
        material=material,
        answer=outcome.content,
        evidence_package=evidence_package,
        max_attempts=judge_max_attempts,
        backoff_s=judge_backoff_s,
        attempts_path=item_root / "judge-attempts-protected.json",
    )
    result["latency"]["evaluation_s"] = max(0.0, time.monotonic() - judge_started)
    result["judge_attempts"] = judge_attempts
    result["judge_accepted_raw"] = accepted_raw
    if score is None:
        result["evaluation_status"] = "technical_unavailable"
        result["technical_failures"].append(
            {"stage": "judge", "error_type": "JudgeRetriesExhausted"}
        )
        ledger.transition(
            execution_id,
            event_type="evaluation_unavailable",
            trace_id=trace_id,
            evaluation_status="technical_unavailable",
            detail={"attempts": len(judge_attempts)},
        )
    else:
        result["evaluation"] = score.as_dict()
        result["evaluation_status"] = "evaluated"
        write_private_json(protected_result_path, result)
        ledger.transition(
            execution_id,
            event_type="official_evaluation",
            trace_id=trace_id,
            evaluation_status="evaluated",
            artifact_sha256=file_sha256(protected_result_path),
            detail={"judge_attempts": len(judge_attempts)},
        )

    langfuse.flush()
    trace_read_started = time.monotonic()
    trace_read = _fetch_trace_stable(
        langfuse,
        trace_id,
        max_wait_s=trace_wait_s,
        poll_s=trace_poll_s,
        max_retries=trace_max_retries,
        backoff_factor=trace_backoff_factor,
        backoff_max_s=trace_backoff_max_s,
    )
    result["latency"]["trace_readback_s"] = max(
        0.0, time.monotonic() - trace_read_started
    )
    ledger.transition(
        execution_id,
        event_type="trace_readback",
        trace_id=trace_id,
        trace_status=(
            "complete" if trace_read.status == "complete" else "pending_trace"
        ),
        detail={"status": trace_read.status, "attempts": trace_read.attempts},
    )
    full_trace = trace_read.trace
    dataset_linked = False
    agent_usage: list[dict[str, Any]] = []
    agent_usage_reason: str | None = None
    if trace_read.status == "complete" and full_trace is not None:
        live_project = getattr(full_trace, "project_id", None)
        if live_project is not None and live_project != project_id:
            raise CanaryV2Error("Trace apareceu em projeto divergente")
        dataset_linked = _dataset_run_linked(
            langfuse,
            dataset_id=str(getattr(item, "dataset_id", "")),
            run_name=run_name,
            item_id=canary_item_id,
            trace_id=trace_id,
            max_wait_s=trace_wait_s,
            poll_s=trace_poll_s,
            max_retries=trace_max_retries,
            backoff_factor=trace_backoff_factor,
            backoff_max_s=trace_backoff_max_s,
        )
        write_private_json(item_root / "trace.raw.json", plain(full_trace))
        try:
            agent_usage = agent_usage_records(
                normalize(list(getattr(full_trace, "observations", None) or [])),
                trace_id=trace_id,
                contract=contract,
            )
            result["trace_status"] = "complete"
            ledger.transition(
                execution_id,
                event_type="trace_complete",
                trace_id=trace_id,
                trace_status="complete",
                artifact_sha256=file_sha256(item_root / "trace.raw.json"),
            )
        except AgentUsageUnavailableError:
            agent_usage_reason = _AGENT_USAGE_UNAVAILABLE_REASON
            result["trace_status"] = "complete"
            ledger.transition(
                execution_id,
                event_type="trace_complete",
                trace_id=trace_id,
                trace_status="complete",
                artifact_sha256=file_sha256(item_root / "trace.raw.json"),
                detail={
                    "agent_usage": None,
                    "agent_usage_reason": agent_usage_reason,
                },
            )
        except TelemetryContractError as exc:
            result["trace_status"] = "technical_unavailable"
            result["technical_failures"].append(
                {
                    "stage": "agent_usage",
                    "error_type": type(exc).__name__,
                    "error_sha256": _sha256_text(str(exc)),
                }
            )
    else:
        result["trace_status"] = "technical_unavailable"
        result["technical_failures"].append(
            {"stage": "trace", "error_type": f"TraceReadback:{trace_read.status}"}
        )
        ledger.transition(
            execution_id,
            event_type="trace_unavailable",
            trace_id=trace_id,
            trace_status="technical_unavailable",
            detail={"status": trace_read.status, "attempts": trace_read.attempts},
        )
    result["trace"] = {
        "status": result["trace_status"],
        "read_status": trace_read.status,
        "read_attempts": trace_read.attempts,
        "project": TARGET_PROJECT,
        "dataset_linked": dataset_linked,
    }

    rate_card = json.loads(
        (EXPERIMENT_ROOT / contract["rate_card"]["ref"]).read_text(encoding="utf-8")
    )
    try:
        ocr_usage = ocr_usage_records(result.get("ocr_usage") or [], contract=contract)
    except TelemetryContractError as exc:
        ocr_usage = []
        result["technical_failures"].append(
            {
                "stage": "ocr_usage",
                "error_type": type(exc).__name__,
                "error_sha256": _sha256_text(str(exc)),
            }
        )
    all_usage = [*agent_usage, *ocr_usage, *judge_usage]
    if all_usage:
        result["usage"] = summarize_usage(
            all_usage,
            rate_card=rate_card,
            rate_card_ref=contract["rate_card"],
        )
        if agent_usage_reason is not None:
            _mark_agent_usage_metric_null(result["usage"])
    else:
        result["technical_failures"].append(
            {"stage": "usage", "error_type": "UsageUnavailable"}
        )

    if score is not None and result["trace_status"] == "complete" and dataset_linked:
        _emit_scores(langfuse, trace_id, contract_sha, score)
        langfuse.flush()

    result["gate"] = _build_canary_gate(
        result,
        canary_item_id=canary_item_id,
        quality_gate=_quality_gate_from_result(
            result, question_type=item_manifest["question_type"], contract=contract
        ),
        trace_ok=result["trace_status"] == "complete" and dataset_linked,
        usage_coverage=(
            isinstance(result.get("usage"), dict)
            and result["usage"]["coverage"]["status"] == "complete"
            and (
                result["usage"]["by_scope"]["agent"]["available"]
                or result["usage"].get("agent_usage_reason")
                == _AGENT_USAGE_UNAVAILABLE_REASON
            )
            and result["usage"]["by_scope"]["judge"]["available"]
        ),
        cold_start_required=True if full_battery_mode else None,
        full_battery_authorized=full_battery_mode,
    )
    write_private_json(protected_result_path, result)
    report_path = run_root / "canary-report-protected.md"
    report_path.write_text(_protected_report(result), encoding="utf-8")
    report_path.chmod(0o600)
    sanitized = _sanitized_result(result)
    sanitized["protected_report_sha256"] = file_sha256(report_path)
    write_private_json(run_root / "canary-result-sanitized.json", sanitized)
    assert_private_tree(output_root)
    return sanitized


def reclassify_existing_canary(
    *,
    manifest: dict[str, Any],
    contract: dict[str, Any],
    output_root: Path,
    run_name: str,
    canary_item_id: str,
) -> dict[str, Any]:
    """Deriva somente gates de artefatos oficiais; não abre rede nem chama modelos."""
    canary_item_id = _select_canary_item_id(canary_item_id)
    item_manifest = _manifest_item(manifest, canary_item_id)
    run_root = output_root / "runs" / run_name
    item_root = run_root / "items" / canary_item_id
    source_path = item_root / "result-protected.json"
    derived_path = item_root / "gate-reclassification-v2-protected.json"
    if not source_path.is_file() or source_path.is_symlink():
        raise CanaryV2Error("Resultado protegido ausente para reclassificação")
    if derived_path.exists():
        raise CanaryV2Error("Reclassificação desta política já possui artefato")
    result = json.loads(source_path.read_text(encoding="utf-8"))
    execution_id = result.get("execution_id")
    trace_id = result.get("trace_id")
    if (
        result.get("run_name") != run_name
        or result.get("item_id") != canary_item_id
        or not isinstance(execution_id, str)
        or not isinstance(trace_id, str)
        or result.get("evaluation_status") != "evaluated"
        or not isinstance(result.get("evaluation"), dict)
    ):
        raise CanaryV2Error("Identidade oficial da reclassificação divergiu")
    ledger = V2Ledger(output_root / "execution-ledger.jsonl")
    official_key = ledger.official_key(execution_id)
    if official_key is None or official_key[:3] != (
        run_name,
        canary_item_id,
        trace_id,
    ):
        raise CanaryV2Error("Ledger não comprova o resultado oficial reclassificado")

    quality_gate = _quality_gate_from_result(
        result, question_type=item_manifest["question_type"], contract=contract
    )
    gate = _build_canary_gate(
        result,
        canary_item_id=canary_item_id,
        quality_gate=quality_gate,
        trace_ok=(
            result.get("trace_status") == "complete"
            and result.get("trace", {}).get("dataset_linked") is True
        ),
        usage_coverage=(
            isinstance(result.get("usage"), dict)
            and result["usage"].get("coverage", {}).get("status") == "complete"
            and result["usage"].get("by_scope", {}).get("agent", {}).get("available")
            is True
            and result["usage"].get("by_scope", {}).get("judge", {}).get("available")
            is True
        ),
    )
    source_sha256 = file_sha256(source_path)
    derived = {
        "schema_version": "benchmark-long-context-v2-gate-reclassification-1",
        "policy_version": QUALITY_GATE_POLICY_VERSION,
        "authorization": GATE_RECLASSIFICATION_AUTHORIZATION,
        "run_name": run_name,
        "item_id": canary_item_id,
        "execution_id": execution_id,
        "trace_id": trace_id,
        "source_artifact_sha256": source_sha256,
        "source_evaluation_sha256": stable_digest(result["evaluation"]),
        "source_gate_sha256": stable_digest(result.get("gate")),
        "derivation": {
            "post": False,
            "agent_inference": False,
            "judge_call": False,
            "ocr": False,
            "official_evaluation_reused": True,
        },
        "quality_gate": quality_gate,
        "gate": gate,
    }
    write_private_json(derived_path, derived)
    derived_sha256 = file_sha256(derived_path)
    event = ledger.record_gate_reclassification(
        execution_id=execution_id,
        trace_id=trace_id,
        policy_version=QUALITY_GATE_POLICY_VERSION,
        authorization=GATE_RECLASSIFICATION_AUTHORIZATION,
        source_artifact_sha256=source_sha256,
        derived_artifact_sha256=derived_sha256,
    )
    sanitized = {
        **derived,
        "execution_id": execution_id,
        "source_artifact_sha256": source_sha256,
        "derived_artifact_sha256": derived_sha256,
        "ledger_event_id": event["event_id"],
    }
    write_private_json(
        run_root / "canary-gate-reclassification-sanitized.json", sanitized
    )
    assert_private_tree(output_root)
    return sanitized


def _score_from_protected(evaluation: dict[str, Any]) -> ScoreV2:
    return ScoreV2(
        numeric=evaluation["numeric"],
        boolean=evaluation["boolean"],
        auxiliary=evaluation["auxiliary"],
        claims=evaluation["claims"],
        checklist=evaluation["checklist"],
        rationale=evaluation["rationale"],
        gate=evaluation["gate"],
    )


def resume_readback(  # noqa: PLR0915
    *,
    manifest: dict[str, Any],
    contract: dict[str, Any],
    output_root: Path,
    run_name: str,
    item: Any,
    langfuse: Any,
    project_id: str,
    trace_wait_s: float,
    trace_poll_s: float,
    trace_max_retries: int,
    trace_backoff_factor: float,
    trace_backoff_max_s: float,
    canary_item_id: str = CANARY_ITEM_ID,
) -> dict[str, Any]:
    """Retoma somente readback/custo do canário já consumido; nunca chama o agente/juiz."""
    canary_item_id = _select_canary_item_id(canary_item_id)
    run_root = output_root / "runs" / run_name
    item_root = run_root / "items" / canary_item_id
    protected_result_path = item_root / "result-protected.json"
    if not protected_result_path.is_file():
        raise CanaryV2Error("Resultado protegido ausente para retomada")
    result = json.loads(protected_result_path.read_text(encoding="utf-8"))
    trace_id = result.get("trace_id")
    execution_id = result.get("execution_id")
    if not isinstance(trace_id, str) or not isinstance(execution_id, str):
        raise CanaryV2Error("Resultado protegido sem identidades da execução")
    if result.get("evaluation_status") != "evaluated" or not isinstance(
        result.get("evaluation"), dict
    ):
        raise CanaryV2Error("Retomada exige avaliação oficial já persistida")

    ledger = V2Ledger(output_root / "execution-ledger.jsonl")
    official_key = ledger.official_key(execution_id)
    expected_prefix = (run_name, canary_item_id, trace_id)
    accepted_contracts = {
        manifest["evaluation_contract"]["sha256"],
        TELEMETRY_SEMANTICS_PREDECESSOR_SHA256,
    }
    if (
        official_key is None
        or official_key[:3] != expected_prefix
        or official_key[3] not in accepted_contracts
    ):
        raise CanaryV2Error("Ledger não comprova a avaliação oficial esperada")
    execution_contract_sha256 = official_key[3]
    telemetry_contract_sha256 = manifest["evaluation_contract"]["sha256"]
    result["execution_contract_sha256"] = execution_contract_sha256
    result["telemetry_contract_sha256"] = telemetry_contract_sha256
    completed = [
        event
        for event in ledger.events()
        if event.get("execution_id") == execution_id
        and event.get("event_type") == "trace_complete"
    ]
    sanitized_path = run_root / "canary-result-sanitized.json"
    if completed and sanitized_path.is_file():
        return json.loads(sanitized_path.read_text(encoding="utf-8"))

    accepted_attempts = [
        attempt
        for attempt in result.get("judge_attempts", [])
        if attempt.get("status") == "accepted"
    ]
    if len(accepted_attempts) != 1:
        raise CanaryV2Error("Usage do juiz oficial não é recuperável de forma única")
    judge_attempt = accepted_attempts[0]
    judge_usage = [
        judge_usage_record(
            judge_attempt["usage"],
            call_id=judge_attempt["response_id"],
            reported_model=judge_attempt.get("reported_model"),
            contract=contract,
        )
    ]

    trace_read = _fetch_trace_stable(
        langfuse,
        trace_id,
        max_wait_s=trace_wait_s,
        poll_s=trace_poll_s,
        max_retries=trace_max_retries,
        backoff_factor=trace_backoff_factor,
        backoff_max_s=trace_backoff_max_s,
    )
    ledger.transition(
        execution_id,
        event_type="trace_readback",
        trace_id=trace_id,
        trace_status=(
            "complete" if trace_read.status == "complete" else "pending_trace"
        ),
        detail={"status": trace_read.status, "attempts": trace_read.attempts},
    )
    if trace_read.status != "complete" or trace_read.trace is None:
        ledger.transition(
            execution_id,
            event_type="trace_unavailable",
            trace_id=trace_id,
            trace_status="technical_unavailable",
            detail={"status": trace_read.status, "attempts": trace_read.attempts},
        )
        raise CanaryV2Error(f"Trace indisponível na retomada: {trace_read.status}")
    full_trace = trace_read.trace
    live_project = getattr(full_trace, "project_id", None)
    if live_project is not None and live_project != project_id:
        raise CanaryV2Error("Trace da retomada pertence a projeto divergente")
    dataset_linked = _dataset_run_linked(
        langfuse,
        dataset_id=str(getattr(item, "dataset_id", "")),
        run_name=run_name,
        item_id=canary_item_id,
        trace_id=trace_id,
        max_wait_s=trace_wait_s,
        poll_s=trace_poll_s,
        max_retries=trace_max_retries,
        backoff_factor=trace_backoff_factor,
        backoff_max_s=trace_backoff_max_s,
    )
    if not dataset_linked:
        raise CanaryV2Error("Trace da retomada não está associado ao dataset/run/item")

    raw_trace_path = item_root / "trace.raw.json"
    write_private_json(raw_trace_path, plain(full_trace))
    agent_usage = agent_usage_records(
        normalize(list(getattr(full_trace, "observations", None) or [])),
        trace_id=trace_id,
        contract=contract,
    )
    rate_card = json.loads(
        (EXPERIMENT_ROOT / contract["rate_card"]["ref"]).read_text(encoding="utf-8")
    )
    result["usage"] = summarize_usage(
        [
            *agent_usage,
            *ocr_usage_records(result.get("ocr_usage") or [], contract=contract),
            *judge_usage,
        ],
        rate_card=rate_card,
        rate_card_ref=contract["rate_card"],
    )
    result["trace_status"] = "complete"
    result["trace"] = {
        "status": "complete",
        "read_status": trace_read.status,
        "read_attempts": trace_read.attempts,
        "project": TARGET_PROJECT,
        "dataset_linked": True,
    }
    result["technical_failures"] = []
    score = _score_from_protected(result["evaluation"])
    _emit_scores(
        langfuse,
        trace_id,
        execution_contract_sha256,
        score,
    )
    langfuse.flush()
    item_manifest = _manifest_item(manifest, canary_item_id)
    result["gate"] = _build_canary_gate(
        result,
        canary_item_id=canary_item_id,
        quality_gate=_quality_gate_from_result(
            result, question_type=item_manifest["question_type"], contract=contract
        ),
        trace_ok=True,
        usage_coverage=(
            result["usage"]["coverage"]["status"] == "complete"
            and result["usage"]["by_scope"]["agent"]["available"]
            and result["usage"]["by_scope"]["judge"]["available"]
        ),
    )
    write_private_json(protected_result_path, result)
    report_path = run_root / "canary-report-protected.md"
    report_path.write_text(_protected_report(result), encoding="utf-8")
    report_path.chmod(0o600)
    sanitized = _sanitized_result(result)
    sanitized["protected_report_sha256"] = file_sha256(report_path)
    write_private_json(sanitized_path, sanitized)
    if execution_contract_sha256 != telemetry_contract_sha256:
        ledger.transition(
            execution_id,
            event_type="telemetry_semantics_corrected",
            trace_id=trace_id,
            detail={
                "execution_contract_sha256": execution_contract_sha256,
                "telemetry_contract_sha256": telemetry_contract_sha256,
                "scope": "post_inference_usage_normalization_only",
            },
        )
    ledger.transition(
        execution_id,
        event_type="trace_complete",
        trace_id=trace_id,
        trace_status="complete",
        artifact_sha256=file_sha256(raw_trace_path),
        detail={"resume_without_inference": True},
    )
    assert_private_tree(output_root)
    return sanitized


def _load_full_battery_authorization(
    path: Path | None,
    *,
    fresh_all_items: bool = False,
    rate_limit_successor: bool = False,
) -> str:
    if fresh_all_items and rate_limit_successor:
        raise CanaryV2Error("Modos 0+9 e sucessor 3+6 são mutuamente exclusivos")
    if fresh_all_items:
        if path is not None:
            raise CanaryV2Error(
                "Bateria 0+9 não aceita autorização histórica por arquivo"
            )
        return FRESH_FULL_BATTERY_AUTHORIZATION_SHA256
    if path is None or not path.is_file() or path.is_symlink():
        raise CanaryV2Error("Arquivo explícito de autorização da bateria é obrigatório")
    observed = file_sha256(path)
    expected = (
        RATE_LIMIT_SUCCESSOR_AUTHORIZATION_SHA256
        if rate_limit_successor
        else FULL_BATTERY_AUTHORIZATION_SHA256
    )
    if observed != expected:
        raise CanaryV2Error("Hash da autorização da bateria divergiu")
    return observed


def _source_root_for_item(roots: list[Path], item_id: str) -> Path:
    matches: list[Path] = []
    for root in roots:
        ledger = V2Ledger(root / "execution-ledger.jsonl")
        events = ledger.events()
        execution_ids = {
            str(event["execution_id"])
            for event in events
            if event.get("event_type") == "reservation"
            and event.get("item_id") == item_id
        }
        if any(
            event.get("event_type") == "official_evaluation"
            and str(event.get("execution_id")) in execution_ids
            for event in events
        ):
            matches.append(root)
    if len(matches) != 1:
        raise CanaryV2Error(
            f"Resultado oficial fonte não é único para {item_id}: {len(matches)}"
        )
    return matches[0]


def _confirm_source_result(
    *,
    root: Path,
    item_id: str,
    manifest: dict[str, Any],
    contract: dict[str, Any],
    allow_battery_completion: bool = False,
    read_only_source: bool = False,
) -> dict[str, Any]:
    ledger_path = root / "execution-ledger.jsonl"
    if read_only_source:
        if not ledger_path.is_file() or ledger_path.is_symlink():
            raise CanaryV2Error("Ledger histórico reutilizado está ausente")
        try:
            events = [
                json.loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except json.JSONDecodeError as exc:
            raise CanaryV2Error("Ledger histórico reutilizado está corrompido") from exc
        if not all(isinstance(event, dict) for event in events):
            raise CanaryV2Error("Ledger histórico reutilizado é inválido")
    else:
        events = V2Ledger(ledger_path).events()
    reservations = [
        event
        for event in events
        if event.get("event_type") == "reservation" and event.get("item_id") == item_id
    ]
    official_reservations = [
        reservation
        for reservation in reservations
        if any(
            event.get("event_type") == "official_evaluation"
            and event.get("execution_id") == reservation.get("execution_id")
            for event in events
        )
    ]
    if len(official_reservations) != 1:
        raise CanaryV2Error(f"Avaliação oficial fonte não é única: {item_id}")
    reservation = official_reservations[0]
    execution_id = str(reservation["execution_id"])
    run_name = str(reservation["run_name"])
    rows = [event for event in events if event.get("execution_id") == execution_id]
    official = [
        event for event in rows if event.get("event_type") == "official_evaluation"
    ]
    completed = [event for event in rows if event.get("event_type") == "trace_complete"]
    if allow_battery_completion and not completed:
        completed = [
            event
            for event in rows
            if event.get("event_type") == "battery_item_completed"
        ]
    trace_ids = {str(event["trace_id"]) for event in rows if event.get("trace_id")}
    if len(official) != 1 or not completed or len(trace_ids) != 1:
        raise CanaryV2Error(f"Fonte oficial incompleta: {item_id}")
    trace_id = next(iter(trace_ids))
    source_path = root / "runs" / run_name / "items" / item_id / "result-protected.json"
    if not source_path.is_file() or source_path.is_symlink():
        raise CanaryV2Error(f"Artefato oficial ausente: {item_id}")
    result = json.loads(source_path.read_text(encoding="utf-8"))
    if (
        result.get("execution_id") != execution_id
        or result.get("trace_id") != trace_id
        or result.get("evaluation_status") != "evaluated"
        or result.get("trace_status") != "complete"
        or result.get("trace", {}).get("dataset_linked") is not True
        or not isinstance(result.get("usage"), dict)
        or result["usage"].get("coverage", {}).get("status") != "complete"
    ):
        raise CanaryV2Error(f"Identidade/observabilidade oficial divergiu: {item_id}")
    item_manifest = _manifest_item(manifest, item_id)
    quality_gate = _quality_gate_from_result(
        result, question_type=item_manifest["question_type"], contract=contract
    )
    gate = _build_canary_gate(
        result,
        canary_item_id=item_id,
        quality_gate=quality_gate,
        trace_ok=True,
        usage_coverage=(
            result["usage"].get("by_scope", {}).get("agent", {}).get("available")
            is True
            and result["usage"].get("by_scope", {}).get("judge", {}).get("available")
            is True
        ),
        cold_start_required=True,
        full_battery_authorized=True,
    )
    no_cache = result.get("no_cache") or {}
    fresh_comparable = (
        no_cache.get("cold_start_comparable") is True
        and no_cache.get("document_source") == "sei_no_cache"
        and no_cache.get("snapshot_role") == "validation_only"
        and no_cache.get("process_source") == "sei_no_cache"
        and no_cache.get("session_reset") is True
    )
    return {
        "item_id": item_id,
        "question_type": item_manifest["question_type"],
        "case_id": item_manifest["case_id"],
        "run_name": run_name,
        "execution_id": execution_id,
        "trace_id": trace_id,
        "source_artifact_sha256": file_sha256(source_path),
        "quality_status": quality_gate["status"],
        "gate_status": gate["status"],
        "gate": gate,
        "evaluation_status": result.get("evaluation_status"),
        "trace_status": result.get("trace_status"),
        "failed_dimensions": gate["failed_dimensions"],
        "fresh_comparable": fresh_comparable,
        "transport": result.get("transport"),
        "no_cache": no_cache,
        "latency": result.get("latency"),
        "evaluation": {
            "numeric": result["evaluation"].get("numeric"),
            "boolean": result["evaluation"].get("boolean"),
            "auxiliary": result["evaluation"].get("auxiliary"),
            "quality_gate": quality_gate,
        },
        "tool_calls": result.get("tool_calls"),
        "usage": result.get("usage"),
        "trace": result.get("trace"),
        "technical_failures": result.get("technical_failures"),
    }


def _select_full_battery_missing_items(
    manifest: dict[str, Any], *, fresh_all_items: bool = False
) -> list[str]:
    if fresh_all_items:
        missing = [item["item_id"] for item in manifest["items"]]
        if len(missing) != 9 or set(missing) != EXPECTED_ITEM_IDS:
            raise CanaryV2Error("Seleção oficial 0+9 da bateria divergiu")
        return missing
    missing = [
        item["item_id"]
        for item in manifest["items"]
        if item["item_id"] != FULL_BATTERY_REUSED_ITEM_ID
    ]
    if (
        len(missing) != 8
        or FULL_BATTERY_EXCLUDED_PREDECESSOR_ITEM_ID not in missing
        or set(missing).union({FULL_BATTERY_REUSED_ITEM_ID}) != EXPECTED_ITEM_IDS
    ):
        raise CanaryV2Error("Seleção oficial 1+8 da bateria divergiu")
    return missing


def _validate_fresh_campaign(
    contract: dict[str, Any], campaign: ModelCampaign | None
) -> None:
    if campaign is None:
        raise CanaryV2Error("Bateria 0+9 exige campanha de modelos explícita")
    ocr = contract.get("ocr", {})
    if (
        ocr.get("deployment") != campaign.mini.deployment
        or ocr.get("canonical_model") != campaign.mini.canonical_model
    ):
        raise CanaryV2Error("OCR da bateria 0+9 diverge do profile mini configurado")


def _select_successor_missing_items(
    manifest: dict[str, Any], *, reused_ids: set[str] | frozenset[str]
) -> list[str]:
    if set(reused_ids) != set(RATE_LIMIT_SUCCESSOR_REUSED_ITEM_IDS):
        raise CanaryV2Error("Itens reutilizados do sucessor 3+6 divergiram")
    missing = [
        item["item_id"]
        for item in manifest["items"]
        if item["item_id"] not in reused_ids
    ]
    if (
        len(missing) != 6
        or len(set(missing)) != 6
        or set(missing).intersection(reused_ids)
        or set(missing).union(reused_ids) != EXPECTED_ITEM_IDS
    ):
        raise CanaryV2Error("Seleção oficial 3+6 da bateria divergiu")
    return missing


def _confirm_successor_reused_partition(
    *,
    reused_output_roots: list[Path],
    manifest: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[list[dict[str, Any]], None, list[str]]:
    roots = [root.expanduser().resolve(strict=True) for root in reused_output_roots]
    if len(roots) != 1:
        raise CanaryV2Error("Sucessor 3+6 exige exatamente um output histórico")
    source_root = roots[0]
    reused: list[dict[str, Any]] = []
    for item_id in RATE_LIMIT_SUCCESSOR_REUSED_ITEM_IDS:
        result = _confirm_source_result(
            root=source_root,
            item_id=item_id,
            manifest=manifest,
            contract=contract,
            allow_battery_completion=True,
            read_only_source=True,
        )
        transport = result.get("transport") or {}
        technical_failures = result.get("technical_failures")
        if not (
            result.get("fresh_comparable") is True
            and result.get("evaluation_status") == "evaluated"
            and result.get("trace_status") == "complete"
            and transport.get("http_status") == 200
            and transport.get("terminal_type") == "end"
            and technical_failures == []
        ):
            raise CanaryV2Error(
                f"Resultado histórico não é tecnicamente reutilizável: {item_id}"
            )
        result["reuse_technical_status"] = "passed"
        reused.append(result)
    missing = _select_successor_missing_items(
        manifest, reused_ids=RATE_LIMIT_SUCCESSOR_REUSED_ITEM_IDS
    )
    return reused, None, missing


def _confirm_full_battery_partition(
    *,
    reused_output_roots: list[Path],
    manifest: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    roots = [root.expanduser().resolve(strict=True) for root in reused_output_roots]
    if len(roots) != 2 or len(set(roots)) != 2:
        raise CanaryV2Error(
            "Exatamente dois roots históricos distintos são obrigatórios"
        )
    factual = _confirm_source_result(
        root=_source_root_for_item(roots, FULL_BATTERY_REUSED_ITEM_ID),
        item_id=FULL_BATTERY_REUSED_ITEM_ID,
        manifest=manifest,
        contract=contract,
    )
    predecessor = _confirm_source_result(
        root=_source_root_for_item(roots, FULL_BATTERY_EXCLUDED_PREDECESSOR_ITEM_ID),
        item_id=FULL_BATTERY_EXCLUDED_PREDECESSOR_ITEM_ID,
        manifest=manifest,
        contract=contract,
    )
    if not factual["fresh_comparable"] or factual["gate_status"] != "passed":
        raise CanaryV2Error("Canário factual fresh não é reutilizável")
    if (
        predecessor["fresh_comparable"]
        or predecessor["quality_status"] != "passed"
        or predecessor["failed_dimensions"] != ["comparability"]
        or predecessor["no_cache"].get("document_source") != "frozen_evidence_snapshot"
    ):
        raise CanaryV2Error(
            "Canário synthesis não é predecessor exclusivamente de comparabilidade"
        )
    predecessor["replacement_reason"] = "frozen_evidence_snapshot_not_fresh_comparable"
    missing = _select_full_battery_missing_items(manifest)
    return factual, predecessor, missing


def _confirm_configured_reused_partition(
    *,
    reused_output_roots: list[Path],
    reused_summary_path: Path,
    manifest: dict[str, Any],
    campaign: ModelCampaign,
) -> tuple[dict[str, Any], None, list[str]]:
    plan = plan_long_context_cells(
        {item["item_id"] for item in manifest["items"]},
        campaign,
        reused_summary_path=reused_summary_path,
    )
    if plan["consumed_cells"] != 1 or plan["pending_calls"] != 8:
        raise CanaryV2Error("Partição configurada 1+8 divergiu")
    roots = [root.expanduser().resolve(strict=True) for root in reused_output_roots]
    if len(roots) != 1:
        raise CanaryV2Error("Exatamente um output reutilizado é obrigatório")
    summary = json.loads(reused_summary_path.read_text(encoding="utf-8"))
    item_hash = summary["identity"]["item_id_sha256"]
    item_id = next(
        item["item_id"]
        for item in manifest["items"]
        if _sha256_text(item["item_id"]) == item_hash
    )
    source_root = _source_root_for_item(roots, item_id)
    reservations = [
        event
        for event in V2Ledger(source_root / "execution-ledger.jsonl").events()
        if event.get("event_type") == "reservation" and event.get("item_id") == item_id
    ]
    if len(reservations) != 1:
        raise CanaryV2Error("Reserva do canário reutilizado não é única")
    source_path = (
        source_root
        / "runs"
        / reservations[0]["run_name"]
        / "items"
        / item_id
        / "result-protected.json"
    )
    protected = json.loads(source_path.read_text(encoding="utf-8"))
    if protected.get("trace_id") != summary["identity"]["trace_id"]:
        raise CanaryV2Error("Trace do canário reutilizado divergiu")
    no_cache = protected.get("no_cache") or {}
    if not (
        no_cache.get("cold_start_comparable") is True
        and no_cache.get("document_source") == "sei_no_cache"
        and no_cache.get("process_source") == "sei_no_cache"
        and no_cache.get("session_reset") is True
    ):
        raise CanaryV2Error("Canário reutilizado não é fresh comparável")
    agent_trace = summary["usage"]["agent_trace"]
    roles = agent_trace["by_role"]
    agent_tokens = {
        field: sum(role["tokens"][field] for role in roles.values())
        for field in (
            "input_uncached",
            "cache_read",
            "output",
            "reasoning",
            "total_without_cache_write",
        )
    }
    agent_tokens.update({"cache_write": None, "total": None})
    judge = summary["usage"]["judge"]
    judge_tokens = {
        **judge["tokens"],
        "cache_write": 0,
        "total_without_cache_write": judge["tokens"]["total"],
    }
    usage = {
        "schema_version": "benchmark-long-context-v2-usage-1",
        "coverage": {
            "status": "complete",
            "generation_records": agent_trace["generation_count"],
            "judge_records": judge["calls"],
        },
        "by_scope": {
            "agent": {
                "available": True,
                "calls": agent_trace["generation_count"],
                "tokens": agent_tokens,
                **summary["cost"]["agent"],
            },
            "judge": {
                "available": True,
                "calls": judge["calls"],
                "tokens": judge_tokens,
                "cost_usd": judge["cost_usd"],
            },
        },
        "by_model": {
            role["mapped_canonical_model"]: {
                "identity": {
                    "requested_profile": (
                        "standard" if name == "principal" else "mini"
                    ),
                    "deployment": role["reported_alias"],
                    "canonical_model": role["mapped_canonical_model"],
                    "provider": role["providers"][0],
                },
                "calls": role["calls"],
                "tokens": role["tokens"],
                **role["cost"],
            }
            for name, role in roles.items()
        },
        "total_cost_usd": None,
        "cost": summary["cost"],
    }
    scores = summary["evaluation"]["scores"]
    item_manifest = _manifest_item(manifest, item_id)
    gate = {
        "status": "passed",
        "failed_dimensions": [],
        "dimensions": {
            "comparability": {"status": "passed"},
            "integrity_technical": {"status": "passed"},
            "observability": {"status": "passed"},
            "quality": {"status": "passed"},
        },
    }
    return (
        {
            "item_id": item_id,
            "question_type": item_manifest["question_type"],
            "case_id": item_manifest["case_id"],
            "run_name": protected["run_name"],
            "execution_id": protected["execution_id"],
            "trace_id": protected["trace_id"],
            "source_artifact_sha256": file_sha256(source_path),
            "quality_status": "passed",
            "gate_status": "passed",
            "gate": gate,
            "evaluation_status": "evaluated",
            "trace_status": "complete",
            "failed_dimensions": [],
            "fresh_comparable": True,
            "transport": summary["transport"],
            "no_cache": no_cache,
            "latency": summary["latency"],
            "evaluation": {
                "numeric": scores["numeric"],
                "boolean": scores["boolean"],
                "auxiliary": scores["auxiliary"],
                "quality_gate": scores["gate"],
            },
            "tool_calls": protected.get("tool_calls"),
            "usage": usage,
            "trace": {"status": "complete", "dataset_linked": True},
            "technical_failures": [],
        },
        None,
        sorted(
            item["item_id"] for item in manifest["items"] if item["item_id"] != item_id
        ),
    )


def _battery_process_id(
    manifest: dict[str, Any], protected_root: Path, item_id: str
) -> str:
    item_manifest = _manifest_item(manifest, item_id)
    corpus = _corpus(manifest, item_manifest["case_id"])
    process_metadata = load_protected_json(
        corpus["process_metadata_ref"], protected_root
    )
    rows = process_metadata.get("id_procedimentos")
    if not isinstance(rows, list) or len(rows) != 1:
        raise CanaryV2Error("Preflight da bateria exige processo protegido único")
    process_id = str(rows[0].get("id_procedimento") or "")
    if not process_id:
        raise CanaryV2Error("Processo da bateria está ausente")
    return process_id


def _battery_ledger_reference(result: dict[str, Any]) -> dict[str, Any]:
    reference = {
        key: result[key]
        for key in (
            "item_id",
            "execution_id",
            "trace_id",
            "source_artifact_sha256",
            "gate_status",
            "fresh_comparable",
        )
    }
    if "reuse_technical_status" in result:
        reference["reuse_technical_status"] = result["reuse_technical_status"]
    return reference


def _battery_predecessor_reference(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in (
            "item_id",
            "execution_id",
            "trace_id",
            "source_artifact_sha256",
            "quality_status",
            "fresh_comparable",
            "replacement_reason",
        )
    }


def _battery_continuation(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("result_status") in _NON_FATAL_CASE_ERROR_STATUSES:
        return {
            "continue": True,
            "classification": result["result_status"],
        }
    gate = result.get("gate") or {}
    dimensions = gate.get("dimensions") or {}
    comparability = dimensions.get("comparability") or {}
    integrity = dimensions.get("integrity_technical") or {}
    integrity_checks = integrity.get("checks") or {}
    technical = result.get("technical_failures") or []
    non_isolated = [
        failure
        for failure in technical
        if failure.get("stage") not in _ISOLATED_TECHNICAL_STAGES
    ]
    if comparability.get("status") != "passed":
        return {
            "continue": False,
            "classification": "systemic_comparability_failure",
        }
    trace = result.get("trace") or {}
    transport = result.get("transport") or {}
    isolated_postprocessing_unavailable = (
        technical
        and not non_isolated
        and transport.get("http_status") == 200
        and transport.get("terminal_type") == "end"
        and trace.get("read_status") == "complete"
        and trace.get("dataset_linked") is True
    )
    if technical and not isolated_postprocessing_unavailable:
        return {
            "continue": False,
            "classification": "technical_failure_fail_fast",
        }
    if (
        integrity_checks.get("single_item") is not True
        or integrity_checks.get("transport_http_200_terminal_end") is not True
        or non_isolated
    ):
        return {"continue": False, "classification": "integrity_failure"}
    if (
        dimensions.get("observability", {}).get("status") != "passed"
        and not isolated_postprocessing_unavailable
    ):
        return {
            "continue": False,
            "classification": "observability_failure_fail_fast",
        }
    if isolated_postprocessing_unavailable:
        classification = "isolated_postprocessing_unavailable"
    elif dimensions.get("quality", {}).get("status") != "passed":
        classification = "quality_failure_non_blocking"
    else:
        classification = "passed"
    return {"continue": True, "classification": classification}


def _case_error_cooldown_s(result: dict[str, Any]) -> float:
    if result.get("result_status") not in {
        "provider_rate_limited",
        "ocr_provider_rate_limited",
        "document_fetch_failed",
    }:
        return 0.0
    retry_after_s = (result.get("provider_rate_limit") or {}).get("retry_after_s")
    if isinstance(retry_after_s, (int, float)) and retry_after_s > 0:
        return float(retry_after_s)
    return float(RATE_LIMIT_COOLDOWN_S)


def _synchronize_external_quality_gate(result: dict[str, Any]) -> Any:
    """Propaga a quality aceita sem alterar as demais dimensões do gate externo."""
    gate = deepcopy(result.get("gate"))
    evaluation = result.get("evaluation")
    if (
        not isinstance(gate, dict)
        or not isinstance(gate.get("dimensions"), dict)
        or result.get("evaluation_status") != "evaluated"
        or not isinstance(evaluation, dict)
    ):
        return gate
    accepted_quality = evaluation.get("gate") or evaluation.get("quality_gate")
    if not isinstance(accepted_quality, dict):
        return gate
    dimensions = gate["dimensions"]
    dimensions["quality"] = deepcopy(accepted_quality)
    failed_dimensions = [
        name
        for name, dimension in dimensions.items()
        if not isinstance(dimension, dict) or dimension.get("status") != "passed"
    ]
    gate["failed_dimensions"] = failed_dimensions
    gate["status"] = "failed" if failed_dimensions else "passed"
    return gate


def _summarize_battery_item(result: dict[str, Any], *, source: str) -> dict[str, Any]:
    evaluation = result.get("evaluation") or {}
    return {
        "item_id": result["item_id"],
        "case_id": result.get("case_id"),
        "question_type": result.get("question_type"),
        "source": source,
        "result_status": result.get("result_status", "completed"),
        "provider_rate_limit": result.get("provider_rate_limit"),
        "case_error": result.get("case_error"),
        "run_name": result.get("run_name"),
        "execution_id": result.get("execution_id"),
        "trace_id": result.get("trace_id"),
        "transport": result.get("transport"),
        "no_cache": result.get("no_cache"),
        "latency": result.get("latency"),
        "evaluation_status": result.get("evaluation_status", "evaluated"),
        "trace_status": result.get("trace_status", "complete"),
        "evaluation": {
            "numeric": evaluation.get("numeric"),
            "boolean": evaluation.get("boolean"),
            "auxiliary": evaluation.get("auxiliary"),
            "gate": evaluation.get("gate") or evaluation.get("quality_gate"),
            "claim_verdict_counts": evaluation.get("claim_verdict_counts"),
        },
        "tool_calls": result.get("tool_calls"),
        "usage": result.get("usage"),
        "trace": result.get("trace"),
        "technical_failures": result.get("technical_failures") or [],
        "recovery": result.get("recovery"),
        "gate": _synchronize_external_quality_gate(result),
    }


def _add_known_cost(known_cost: dict[str, float], value: Any) -> None:
    if isinstance(value, (int, float)):
        for regime in known_cost:
            known_cost[regime] += float(value)


def _aggregate_battery_usage(items: list[dict[str, Any]]) -> dict[str, Any]:
    token_fields = ("input_uncached", "cache_read", "output", "reasoning", "total")
    by_scope: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    total_cost = 0.0
    known_cost = {"short_context": 0.0, "long_context": 0.0}
    missing_cache_write = False
    coverage_complete = True
    cost_complete = True
    explicit_nulls: Counter[str] = Counter()
    for item in items:
        usage = item.get("usage")
        if not isinstance(usage, dict):
            coverage_complete = False
            cost_complete = False
            continue
        cost = usage.get("total_cost_usd")
        if not isinstance(cost, (int, float)):
            cost_complete = False
            partial = (usage.get("cost") or {}).get(
                "known_subtotal_excluding_cache_write_usd"
            )
            if isinstance(partial, dict):
                missing_cache_write = True
                for regime in known_cost:
                    known_cost[regime] += float(
                        partial.get(f"if_all_requests_{regime}")
                        or partial.get(regime)
                        or 0
                    )
            explicit_agent_subtotal = (usage.get("cost") or {}).get(
                "known_subtotal_excluding_agent_usage_usd"
            )
            _add_known_cost(known_cost, explicit_agent_subtotal)
        else:
            total_cost += float(cost)
            for regime in known_cost:
                known_cost[regime] += float(cost)
        for scope, row in (usage.get("by_scope") or {}).items():
            bucket = by_scope.setdefault(
                scope,
                {
                    "calls": 0,
                    "tokens": dict.fromkeys(token_fields, 0),
                    "cost_usd": 0.0,
                    "available_items": 0,
                },
            )
            if row.get("available") is not True or not isinstance(
                row.get("tokens"), dict
            ):
                explicit_agent_null = (
                    scope == "agent"
                    and row.get("reason") == _AGENT_USAGE_UNAVAILABLE_REASON
                )
                bucket["null_items"] = int(bucket.get("null_items") or 0) + int(
                    explicit_agent_null
                )
                explicit_nulls["agent_usage"] += int(explicit_agent_null)
                coverage_complete = coverage_complete and explicit_agent_null
                continue
            bucket["available_items"] += 1
            bucket["calls"] += int(row.get("calls") or 0)
            bucket["cost_usd"] += float(row.get("cost_usd") or 0)
            for field in token_fields:
                bucket["tokens"][field] += int(row["tokens"].get(field) or 0)
        for model, row in (usage.get("by_model") or {}).items():
            bucket = by_model.setdefault(
                model,
                {
                    "calls": 0,
                    "tokens": dict.fromkeys(token_fields, 0),
                    "cost_usd": 0.0,
                },
            )
            bucket["calls"] += int(row.get("calls") or 0)
            bucket["cost_usd"] += float(row.get("cost_usd") or 0)
            for field in token_fields:
                bucket["tokens"][field] += int(row.get("tokens", {}).get(field) or 0)
    return {
        "coverage": "complete" if coverage_complete else "partial",
        "by_scope": by_scope,
        "by_model": by_model,
        "total_cost_usd": total_cost if cost_complete else None,
        "known_subtotal_excluding_cache_write_usd": (
            {f"if_all_requests_{regime}": value for regime, value in known_cost.items()}
            if missing_cache_write
            else None
        ),
        "missing_only": ["cache_write"] if missing_cache_write else [],
        "metric_nulls": dict(explicit_nulls),
    }


def _failed_battery_item_summary(
    *, output_root: Path, run_name: str, item_id: str, exc: Exception
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = output_root / "runs" / run_name / "items" / item_id / "result-protected.json"
    result = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.is_file() and not path.is_symlink()
        else {"item_id": item_id, "run_name": run_name}
    )
    no_cache = result.get("no_cache") or {}
    transport = result.get("transport") or {}
    comparable_transport = (
        no_cache.get("cold_start_comparable") is True
        and transport.get("http_status") == 200
        and transport.get("terminal_type") == "end"
    )
    empty_answer = (
        isinstance(result.get("answer"), str) and not result["answer"].strip()
    )
    continuation = {
        "continue": comparable_transport,
        "classification": (
            "quality_failure_empty_response_non_blocking"
            if comparable_transport and empty_answer
            else (
                "isolated_post_transport_failure"
                if comparable_transport
                else "systemic_or_integrity_failure"
            )
        ),
    }
    summary = {
        "item_id": item_id,
        "case_id": result.get("case_id"),
        "run_name": run_name,
        "execution_id": result.get("execution_id"),
        "trace_id": result.get("trace_id"),
        "source": "fresh_execution",
        "transport": transport,
        "no_cache": no_cache,
        "latency": result.get("latency"),
        "evaluation_status": result.get("evaluation_status"),
        "trace_status": result.get("trace_status"),
        "evaluation": None,
        "tool_calls": result.get("tool_calls"),
        "usage": result.get("usage"),
        "trace": result.get("trace"),
        "technical_failures": [
            *(result.get("technical_failures") or []),
            {
                "stage": "battery_item",
                "error_type": type(exc).__name__,
                "error_sha256": _sha256_text(str(exc)),
            },
        ],
        "gate": None,
        "failure_classification": continuation["classification"],
    }
    return summary, continuation


def _recover_sse_outcome(raw_path: Path) -> SSEOutcome:
    content: list[str] = []
    metadata = None
    status_frames = preparation_heartbeats = reasoning_frames = content_frames = 0
    first_timestamp = terminal_timestamp = None
    terminal_type = None
    terminal_status_code = None
    terminal_detail = None
    for block in raw_path.read_text(encoding="utf-8").split("\n\n"):
        data = next(
            (line[6:] for line in block.splitlines() if line.startswith("data: ")),
            None,
        )
        if data is None:
            continue
        frame = json.loads(data)
        timestamp = frame.get("timestamp")
        if isinstance(timestamp, (int, float)):
            first_timestamp = timestamp if first_timestamp is None else first_timestamp
        frame_type = frame.get("type")
        if frame_type == "status":
            status_frames += 1
            if (
                frame.get("stage") == "session_preparation"
                and frame.get("heartbeat") is True
            ):
                preparation_heartbeats += 1
        elif frame_type == "reasoning":
            reasoning_frames += 1
        elif frame_type == "content" and isinstance(frame.get("data"), str):
            content_frames += 1
            content.append(frame["data"])
        elif frame_type == "metadata" and isinstance(frame.get("data"), dict):
            metadata = frame["data"]
        if frame_type in {"end", "error"}:
            terminal_type = frame_type
            terminal_timestamp = timestamp
            terminal_status_code = frame.get("status_code")
            terminal_detail = frame.get("detail")
    if terminal_type is None:
        raise CanaryV2Error("SSE preservado não possui terminal recuperável")
    duration = (
        max(0.0, float(terminal_timestamp) - float(first_timestamp))
        if isinstance(first_timestamp, (int, float))
        and isinstance(terminal_timestamp, (int, float))
        else 0.0
    )
    return SSEOutcome(
        terminal_type=terminal_type,
        observed_response_time_s=duration,
        content="".join(content),
        metadata=metadata,
        status_frames=status_frames,
        preparation_heartbeat_frames=preparation_heartbeats,
        reasoning_frames=reasoning_frames,
        content_frames=content_frames,
        terminal_status_code=terminal_status_code,
        terminal_detail=terminal_detail,
    )


def _pre_agent_retry_proof(
    raw_path: Path, execution_rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    frame_types: list[str] = []
    diagnostic = None
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("data: "):
            continue
        frame = json.loads(line[6:])
        frame_type = frame.get("type")
        if isinstance(frame_type, str):
            frame_types.append(frame_type)
        if frame_type == "error":
            diagnostic = frame.get("diagnostic")
    diagnostic_category = (
        diagnostic.get("category") if isinstance(diagnostic, dict) else None
    )
    diagnostic_stage = diagnostic.get("stage") if isinstance(diagnostic, dict) else None
    retryable_diagnostic = (
        diagnostic_category == "document_fetch_failed"
        and diagnostic_stage == "fetch_validate_before_write"
    ) or (
        diagnostic_category == "fresh_process_metadata_missing"
        and diagnostic_stage is None
    )
    if (
        not frame_types
        or frame_types[-1] != "error"
        or set(frame_types).difference({"status", "error"})
        or not isinstance(diagnostic, dict)
        or not retryable_diagnostic
        or not any(
            row.get("event_type") == "agent_failed"
            and row.get("post_attempted") is True
            and row.get("evaluation_status") == "technical_unavailable"
            and row.get("trace_status") == "technical_unavailable"
            for row in execution_rows
        )
    ):
        return None
    return {
        "failure_stage": "pre_agent",
        "failure_category": diagnostic_category,
        "technical_failure": True,
        "zero_generations": True,
        "zero_tools": True,
        "zero_judge_calls": True,
        "zero_tokens": True,
        "zero_cost": True,
        "diagnostic_fingerprint": diagnostic.get("fingerprint"),
        "raw_sse_sha256": file_sha256(raw_path),
    }


def _rate_limit_retry_proof(
    raw_path: Path,
    execution_rows: list[dict[str, Any]],
    *,
    now_s: float | None = None,
) -> dict[str, Any] | None:
    terminal: dict[str, Any] | None = None
    frame_counts: Counter[str] = Counter()
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("data: "):
            continue
        frame = json.loads(line[6:])
        frame_type = frame.get("type")
        if isinstance(frame_type, str):
            frame_counts[frame_type] += 1
        if frame_type == "error":
            terminal = frame
    if not isinstance(terminal, dict):
        return None
    detail = terminal.get("detail")
    terminal_timestamp = terminal.get("timestamp")
    if (
        not isinstance(detail, str)
        or "exceeded rate limit" not in detail.lower()
        or terminal.get("status_code") not in {429, 500, 502}
        or not isinstance(terminal_timestamp, (int, float))
        or not any(
            row.get("event_type") == "agent_failed"
            and row.get("post_attempted") is True
            and row.get("evaluation_status") == "technical_unavailable"
            and row.get("trace_status") == "technical_unavailable"
            for row in execution_rows
        )
    ):
        return None
    elapsed_s = max(
        0.0, (now_s if now_s is not None else time.time()) - terminal_timestamp
    )
    return {
        "failure_stage": "agent",
        "failure_category": "model_rate_limit",
        "technical_failure": True,
        "terminal_status_code": terminal["status_code"],
        "reasoning_frames": frame_counts["reasoning"],
        "content_frames": frame_counts["content"],
        "cooldown_required_s": RATE_LIMIT_COOLDOWN_S,
        "cooldown_elapsed_s": elapsed_s,
        "cooldown_satisfied": elapsed_s >= RATE_LIMIT_COOLDOWN_S,
        "detail_sha256": _sha256_text(detail),
        "raw_sse_sha256": file_sha256(raw_path),
    }


def recover_battery_item_postprocessing(  # noqa: C901, PLR0912, PLR0915
    *,
    manifest: dict[str, Any],
    contract: dict[str, Any],
    protected_bundle_root: Path,
    output_root: Path,
    item: Any,
    item_id: str,
    run_name: str,
    langfuse: Any,
    project_id: str,
    judge_client: OpenAI,
    judge_model: str,
    trace_wait_s: float,
    trace_poll_s: float,
    trace_max_retries: int,
    trace_backoff_factor: float,
    trace_backoff_max_s: float,
    judge_max_attempts: int,
    judge_backoff_s: float,
) -> dict[str, Any]:
    """Completa evidence/judge/readback de SSE terminal sem novo POST ou OCR."""
    item_manifest = _manifest_item(manifest, item_id)
    case_id = item_manifest["case_id"]
    item_root = output_root / "runs" / run_name / "items" / item_id
    raw_sse_path = item_root / "stream.raw.sse"
    fresh_path = item_root / "fresh-evidence-recovery.json"
    protected_result_path = item_root / "result-protected.json"
    if not raw_sse_path.is_file() or not protected_result_path.is_file():
        raise CanaryV2Error("Recuperação da bateria sem SSE/resultado preservado")
    source_result_sha256 = file_sha256(protected_result_path)
    existing = json.loads(protected_result_path.read_text(encoding="utf-8"))
    persisted_evidence = existing.get("evidence_package")
    if not fresh_path.is_file() and not isinstance(persisted_evidence, list):
        raise CanaryV2Error("Recuperação da bateria sem evidência preservada")
    outcome = _recover_sse_outcome(raw_sse_path)
    recovery_metadata_path = item_root / "recovery-metadata.json"
    recovered_export_error = (
        outcome.terminal_type == "error"
        and outcome.terminal_status_code == 409
        and outcome.terminal_detail
        == "benchmark evidence preflight failed: fresh_evidence_export_hash_mismatch"
        and recovery_metadata_path.is_file()
    )
    if (
        outcome.terminal_type != "end" and not recovered_export_error
    ) or not outcome.content.strip():
        raise CanaryV2Error("Resposta da bateria não é recuperável sem replay")
    response_metadata = outcome.metadata if isinstance(outcome.metadata, dict) else {}
    if not response_metadata and recovery_metadata_path.is_file():
        response_metadata = json.loads(
            recovery_metadata_path.read_text(encoding="utf-8")
        )
    fresh_evidence = (
        json.loads(fresh_path.read_text(encoding="utf-8"))
        if fresh_path.is_file()
        else None
    )
    ledger = V2Ledger(output_root / "execution-ledger.jsonl")
    reservations = [
        event
        for event in ledger.events()
        if event.get("event_type") == "reservation"
        and event.get("item_id") == item_id
        and event.get("run_name") == run_name
    ]
    if len(reservations) != 1:
        raise CanaryV2Error("Reserva da recuperação não é única")
    reservation = reservations[0]
    execution_id = str(reservation["execution_id"])
    rows = [
        event for event in ledger.events() if event.get("execution_id") == execution_id
    ]
    if any(event.get("event_type") == "official_evaluation" for event in rows):
        raise CanaryV2Error("Recuperação não pode duplicar avaliação oficial")
    trace_ids = {str(event["trace_id"]) for event in rows if event.get("trace_id")}
    if len(trace_ids) != 1:
        raise CanaryV2Error("Trace da recuperação não é único")
    trace_id = next(iter(trace_ids))
    if existing.get("answer") not in {None, outcome.content}:
        raise CanaryV2Error("Resposta preservada diverge do SSE recuperado")
    evidence_diagnostic = response_metadata.get("benchmark_evidence_preflight") or {}
    preparation_s = response_metadata.get("preparation_duration_s")
    terminal_s = (
        existing.get("transport", {}).get("response_time_s")
        or outcome.observed_response_time_s
    )
    result: dict[str, Any] = {
        **existing,
        "schema_version": "benchmark-long-context-v2-canary-protected-1",
        "run_name": run_name,
        "item_id": item_id,
        "case_id": case_id,
        "execution_id": execution_id,
        "trace_id": trace_id,
        "execution_contract_sha256": reservation["contract_sha256"],
        "telemetry_contract_sha256": manifest["evaluation_contract"]["sha256"],
        "answer": outcome.content,
        "evaluation": None,
        "evaluation_status": "pending_evaluation",
        "trace_status": "pending_trace",
        "technical_failures": [],
        "recovery": {
            "post": False,
            "agent_inference": False,
            "ocr": False,
            "sse_terminal_reused": True,
            "fresh_materialized_evidence_reused": fresh_evidence is not None,
            "persisted_evidence_package_reused": fresh_evidence is None,
        },
        "no_cache": {
            "requested": True,
            "effective": response_metadata.get("no_cache"),
            "document_source": evidence_diagnostic.get("runtime_document_source"),
            "snapshot_role": evidence_diagnostic.get("snapshot_role"),
            "process_source": response_metadata.get("benchmark_process_source"),
            "session_reset": response_metadata.get("benchmark_session_reset"),
            "cold_start_comparable": (
                response_metadata.get("no_cache") is True
                and evidence_diagnostic.get("runtime_document_source") == "sei_no_cache"
                and evidence_diagnostic.get("snapshot_role") == "validation_only"
                and response_metadata.get("benchmark_process_source") == "sei_no_cache"
                and response_metadata.get("benchmark_session_reset") is True
            ),
        },
        "latency": {
            "session_preparation_s": preparation_s,
            "stream_terminal_s": terminal_s,
            "post_preparation_stream_s": (
                max(0.0, terminal_s - preparation_s)
                if isinstance(terminal_s, (int, float))
                and isinstance(preparation_s, (int, float))
                else None
            ),
            "evaluation_s": None,
            "trace_readback_s": None,
            "inference_latency_scope": "session_preparation + post_preparation_stream",
            "excluded_from_inference_latency": ["evaluation_s", "trace_readback_s"],
        },
        "transport": {
            "http_status": 200,
            "content_type": "text/event-stream",
            "terminal_type": outcome.terminal_type,
            "recovered_after_post_agent_export_error": recovered_export_error,
            "original_terminal_status_code": outcome.terminal_status_code,
            "response_time_s": terminal_s,
            "preparation_heartbeat_frames": outcome.preparation_heartbeat_frames,
            "no_cache_effective": response_metadata.get("no_cache"),
            "answer_sha256": _sha256_text(outcome.content),
        },
    }
    if result["no_cache"]["cold_start_comparable"] is not True:
        raise CanaryV2Error("Recuperação não comprovou cold start fresh")
    benchmark_metrics = response_metadata.get("benchmark_metrics")
    tool_summary = _sanitized_tool_summary(benchmark_metrics)
    result["tool_calls"] = {
        "total": tool_summary["total_calls"],
        "by_name": tool_summary["calls_by_name"],
    }
    result["context_disclosure_observed"] = _context_disclosure_observed(
        item=item,
        metadata=response_metadata,
        tool_summary=tool_summary,
    )
    if not result["context_disclosure_observed"]:
        raise CanaryV2Error("Recuperação sem context disclosure")
    material = load_judge_material(item_manifest, protected_bundle_root)
    if fresh_evidence is not None:
        opened_evidence, evidence_observability = build_evidence_package(
            index_path=protected_bundle_root / "evidence-index.json",
            case_id=case_id,
            answer=outcome.content,
            tool_summary=tool_summary,
            fresh_evidence=fresh_evidence,
        )
        evidence_package = merge_evidence_package(
            material.source_evidence, opened_evidence
        )
    else:
        evidence_package = persisted_evidence
        evidence_observability = existing.get("evidence_observability")
        if not isinstance(evidence_observability, dict):
            raise CanaryV2Error("Observabilidade da evidência preservada está ausente")
    result["evidence_package"] = evidence_package
    result["evidence_observability"] = evidence_observability
    write_private_json(protected_result_path, result)
    ledger.transition(
        execution_id,
        event_type="evidence_recovered_without_inference",
        trace_id=trace_id,
        post_attempted=True,
        evaluation_status="pending_evaluation",
        artifact_sha256=file_sha256(protected_result_path),
        detail={
            "source_result_sha256": source_result_sha256,
            "fresh_evidence_sha256": (
                file_sha256(fresh_path) if fresh_evidence is not None else None
            ),
        },
    )
    judge_started = time.monotonic()
    score, judge_usage, judge_attempts, accepted_raw = _judge_with_retries(
        client=judge_client,
        model=judge_model,
        contract=contract,
        item=item_manifest,
        material=material,
        answer=outcome.content,
        evidence_package=evidence_package,
        max_attempts=judge_max_attempts,
        backoff_s=judge_backoff_s,
        attempts_path=(
            item_root / "judge-recovery-attempts-protected.json"
            if (item_root / "judge-attempts-protected.json").exists()
            else item_root / "judge-attempts-protected.json"
        ),
    )
    result["latency"]["evaluation_s"] = max(0.0, time.monotonic() - judge_started)
    result["judge_attempts"] = judge_attempts
    result["judge_accepted_raw"] = accepted_raw
    if score is None:
        raise CanaryV2Error("Juiz da recuperação permaneceu indisponível")
    result["evaluation"] = score.as_dict()
    result["evaluation_status"] = "evaluated"
    write_private_json(protected_result_path, result)
    ledger.transition(
        execution_id,
        event_type="official_evaluation",
        trace_id=trace_id,
        evaluation_status="evaluated",
        artifact_sha256=file_sha256(protected_result_path),
        detail={
            "recovered_without_inference": True,
            "judge_attempts": len(judge_attempts),
        },
    )
    langfuse.flush()
    read_started = time.monotonic()
    trace_read = _fetch_trace_stable(
        langfuse,
        trace_id,
        max_wait_s=trace_wait_s,
        poll_s=trace_poll_s,
        max_retries=trace_max_retries,
        backoff_factor=trace_backoff_factor,
        backoff_max_s=trace_backoff_max_s,
    )
    result["latency"]["trace_readback_s"] = max(0.0, time.monotonic() - read_started)
    if trace_read.status != "complete" or trace_read.trace is None:
        raise CanaryV2Error(f"Trace da recuperação indisponível: {trace_read.status}")
    full_trace = trace_read.trace
    live_project = getattr(full_trace, "project_id", None)
    if live_project is not None and live_project != project_id:
        raise CanaryV2Error("Trace recuperado pertence a projeto divergente")
    dataset_linked = _dataset_run_linked(
        langfuse,
        dataset_id=str(getattr(item, "dataset_id", "")),
        run_name=run_name,
        item_id=item_id,
        trace_id=trace_id,
        max_wait_s=trace_wait_s,
        poll_s=trace_poll_s,
        max_retries=trace_max_retries,
        backoff_factor=trace_backoff_factor,
        backoff_max_s=trace_backoff_max_s,
    )
    if not dataset_linked:
        raise CanaryV2Error("Trace recuperado não está associado ao dataset")
    raw_trace_path = item_root / "trace.raw.json"
    write_private_json(raw_trace_path, plain(full_trace))
    agent_usage = agent_usage_records(
        normalize(list(getattr(full_trace, "observations", None) or [])),
        trace_id=trace_id,
        contract=contract,
    )
    rate_card = json.loads(
        (EXPERIMENT_ROOT / contract["rate_card"]["ref"]).read_text(encoding="utf-8")
    )
    result["usage"] = summarize_usage(
        [
            *agent_usage,
            *ocr_usage_records(result.get("ocr_usage") or [], contract=contract),
            *judge_usage,
        ],
        rate_card=rate_card,
        rate_card_ref=contract["rate_card"],
    )
    result["trace_status"] = "complete"
    result["trace"] = {
        "status": "complete",
        "read_status": trace_read.status,
        "read_attempts": trace_read.attempts,
        "project": TARGET_PROJECT,
        "dataset_linked": True,
    }
    _emit_scores(langfuse, trace_id, reservation["contract_sha256"], score)
    langfuse.flush()
    result["gate"] = _build_canary_gate(
        result,
        canary_item_id=item_id,
        quality_gate=_quality_gate_from_result(
            result, question_type=item_manifest["question_type"], contract=contract
        ),
        trace_ok=True,
        usage_coverage=True,
        cold_start_required=True,
        full_battery_authorized=True,
    )
    write_private_json(protected_result_path, result)
    report_path = output_root / "runs" / run_name / "canary-report-protected.md"
    report_path.write_text(_protected_report(result), encoding="utf-8")
    report_path.chmod(0o600)
    sanitized = _sanitized_result(result)
    sanitized["protected_report_sha256"] = file_sha256(report_path)
    write_private_json(
        output_root / "runs" / run_name / "canary-result-sanitized.json", sanitized
    )
    ledger.transition(
        execution_id,
        event_type="battery_item_completed",
        trace_id=trace_id,
        post_attempted=True,
        evaluation_status="evaluated",
        trace_status="complete",
        artifact_sha256=file_sha256(protected_result_path),
        detail={"recovered_without_inference": True},
    )
    return sanitized


def execute_full_battery(  # noqa: C901, PLR0912, PLR0915
    *,
    manifest: dict[str, Any],
    contract: dict[str, Any],
    protected_bundle_root: Path,
    output_root: Path,
    battery_run_name: str,
    reused_results: list[dict[str, Any]],
    excluded_predecessor: dict[str, Any] | None,
    missing_item_ids: list[str],
    authorization_sha256: str,
    live_preflight: dict[str, Any],
    items: list[Any],
    langfuse: Any,
    langfuse_host: str,
    project_id: str,
    http_client: Any,
    base_url: str,
    judge_client: OpenAI,
    judge_model: str,
    trace_wait_s: float,
    trace_poll_s: float,
    trace_max_retries: int,
    trace_backoff_factor: float,
    trace_backoff_max_s: float,
    judge_max_attempts: int,
    judge_backoff_s: float,
    runtime_preflight: dict[str, Any],
    sei_preflight_expectation: dict[str, str],
    resume: bool = False,
) -> dict[str, Any]:
    battery_root = output_root / "batteries" / battery_run_name
    ledger = V2Ledger(output_root / "execution-ledger.jsonl")
    if resume:
        if not battery_root.is_dir() or battery_root.is_symlink():
            raise CanaryV2Error("Root da bateria não existe para retomada")
        battery_root.chmod(0o700)
        battery_root.parent.chmod(0o700)
        authorizations = [
            event
            for event in ledger.events()
            if event.get("event_type") == "full_battery_authorized"
            and event.get("detail", {}).get("authorization_sha256")
            == authorization_sha256
        ]
        if len(authorizations) != 1:
            raise CanaryV2Error("Autorização append-only da retomada não é única")
        authorization = authorizations[0]
    else:
        battery_root.mkdir(parents=True, exist_ok=False, mode=0o700)
        battery_root.chmod(0o700)
        battery_root.parent.chmod(0o700)
        reused_references = [
            _battery_ledger_reference(result) for result in reused_results
        ]
        authorization = ledger.authorize_full_battery(
            authorization_sha256=authorization_sha256,
            policy_version=QUALITY_GATE_POLICY_VERSION,
            reused_results=reused_references,
            excluded_predecessors=(
                [_battery_predecessor_reference(excluded_predecessor)]
                if excluded_predecessor is not None
                else []
            ),
            missing_item_ids=missing_item_ids,
            expected_item_ids=set(EXPECTED_ITEM_IDS),
            fresh_all_items=not reused_results,
        )
        for reused_result in reused_results:
            ledger.record_reused_official_result(
                authorization_event_id=authorization["event_id"],
                item_id=reused_result["item_id"],
                execution_id=reused_result["execution_id"],
                trace_id=reused_result["trace_id"],
                source_artifact_sha256=reused_result["source_artifact_sha256"],
            )
        if excluded_predecessor is not None:
            ledger.record_excluded_predecessor(
                authorization_event_id=authorization["event_id"],
                item_id=excluded_predecessor["item_id"],
                execution_id=excluded_predecessor["execution_id"],
                trace_id=excluded_predecessor["trace_id"],
                source_artifact_sha256=excluded_predecessor["source_artifact_sha256"],
            )
    official_items = [
        _summarize_battery_item(result, source="reused_fresh")
        for result in reused_results
    ]
    attempts: list[dict[str, Any]] = []
    events = ledger.events()
    completed_ids: set[str] = set()
    for item_id in missing_item_ids:
        reservations = [
            event
            for event in events
            if event.get("event_type") == "reservation"
            and event.get("item_id") == item_id
        ]
        if not reservations:
            continue
        official_reservations = [
            reservation
            for reservation in reservations
            if any(
                event.get("event_type")
                in {
                    "official_evaluation",
                    "evaluation_unavailable",
                    "provider_rate_limited",
                    "case_error_recorded",
                }
                and event.get("execution_id") == reservation["execution_id"]
                for event in events
            )
        ]
        if len(official_reservations) > 1:
            raise CanaryV2Error(f"Item possui avaliações duplicadas: {item_id}")
        if not official_reservations:
            if resume:
                invalidated = {
                    str(event["execution_id"])
                    for event in events
                    if event.get("event_type") == "battery_item_invalidated_for_retry"
                }
                if any(
                    str(reservation["execution_id"]) not in invalidated
                    for reservation in reservations
                ):
                    raise CanaryV2Error(
                        f"Item reservado sem recuperação oficial: {item_id}"
                    )
            continue
        reservation = official_reservations[0]
        result_path = (
            output_root
            / "runs"
            / str(reservation["run_name"])
            / "items"
            / item_id
            / "result-protected.json"
        )
        protected = json.loads(result_path.read_text(encoding="utf-8"))
        provider_rate_limited = any(
            event.get("event_type") == "provider_rate_limited"
            and event.get("execution_id") == reservation["execution_id"]
            for event in ledger.events()
        )
        if provider_rate_limited and protected.get("result_status") != (
            "provider_rate_limited"
        ):
            outcome = _recover_sse_outcome(result_path.with_name("stream.raw.sse"))
            if not _mark_provider_rate_limited_result(protected, outcome=outcome):
                raise CanaryV2Error("Evento 429 diverge do SSE preservado")
            write_private_json(result_path, protected)
            write_private_json(
                result_path.parents[2] / "canary-result-sanitized.json",
                _sanitized_result(protected),
            )
        trace_usage_reclassified = _reclassify_agent_usage_from_persisted_trace(
            protected,
            trace_path=result_path.with_name("trace.raw.json"),
            contract=contract,
        )
        metric_null_reclassified = (
            not trace_usage_reclassified
            and _reclassify_missing_agent_usage(protected, canary_item_id=item_id)
        )
        if trace_usage_reclassified or metric_null_reclassified:
            write_private_json(result_path, protected)
            write_private_json(
                result_path.parents[2] / "canary-result-sanitized.json",
                _sanitized_result(protected),
            )
            event_type = (
                "agent_usage_recalculated"
                if trace_usage_reclassified
                else "agent_usage_metric_null_recorded"
            )
            if not any(
                event.get("event_type") == event_type
                and event.get("execution_id") == reservation["execution_id"]
                for event in ledger.events()
            ):
                ledger.transition(
                    str(reservation["execution_id"]),
                    event_type=event_type,
                    trace_id=protected.get("trace_id"),
                    post_attempted=True,
                    evaluation_status="evaluated",
                    trace_status="complete",
                    artifact_sha256=file_sha256(result_path),
                    detail=(
                        {
                            "agent_usage": "calculated",
                            "usage_source": "persisted_trace",
                            "offline_reclassification": True,
                        }
                        if trace_usage_reclassified
                        else {
                            "agent_usage": None,
                            "agent_usage_reason": _AGENT_USAGE_UNAVAILABLE_REASON,
                            "offline_reclassification": True,
                        }
                    ),
                )
        summary = _summarize_battery_item(protected, source="fresh_execution")
        item_manifest = _manifest_item(manifest, item_id)
        summary["case_id"] = item_manifest["case_id"]
        summary["question_type"] = item_manifest["question_type"]
        summary["sequence"] = missing_item_ids.index(item_id) + 1
        summary["continuation"] = _battery_continuation(protected)
        if not any(
            event.get("event_type") == "battery_item_completed"
            and event.get("execution_id") == reservation["execution_id"]
            for event in events
        ):
            ledger.transition(
                str(reservation["execution_id"]),
                event_type="battery_item_completed",
                trace_id=protected.get("trace_id"),
                post_attempted=True,
                evaluation_status=protected.get("evaluation_status"),
                trace_status=protected.get("trace_status"),
                artifact_sha256=file_sha256(result_path),
                detail={"reconstructed_from_official_artifact": True},
            )
        attempts.append(summary)
        official_items.append(summary)
        completed_ids.add(item_id)
    remaining_item_ids = [
        item_id for item_id in missing_item_ids if item_id not in completed_ids
    ]
    stopped = False
    for item_id in remaining_item_ids:
        sequence = missing_item_ids.index(item_id) + 1
        item_reservations = [
            event
            for event in ledger.events()
            if event.get("event_type") == "reservation"
            and event.get("item_id") == item_id
        ]
        retry_of_execution_id = None
        item_run_name = f"{battery_run_name}--{item_id}"
        if item_reservations:
            if not resume:
                raise CanaryV2Error(f"Item já reservado fora de retomada: {item_id}")
            retry_of_execution_id = str(item_reservations[-1]["execution_id"])
            item_run_name += f"--retry-{len(item_reservations)}"
        elif (output_root / "runs" / item_run_name).exists():
            if not resume:
                raise CanaryV2Error(f"Run pré-reserva já existe: {item_id}")
            prefix = item_run_name + "--resume-pre-reservation"
            item_run_name = prefix
            suffix = 2
            while (output_root / "runs" / item_run_name).exists():
                item_run_name = f"{prefix}-{suffix}"
                suffix += 1
        try:
            result = execute_canary(
                manifest=manifest,
                contract=contract,
                protected_bundle_root=protected_bundle_root,
                output_root=output_root,
                run_name=item_run_name,
                item=_item_by_id(items, item_id),
                langfuse=langfuse,
                langfuse_host=langfuse_host,
                project_id=project_id,
                http_client=http_client,
                base_url=base_url,
                judge_client=judge_client,
                judge_model=judge_model,
                trace_wait_s=trace_wait_s,
                trace_poll_s=trace_poll_s,
                trace_max_retries=trace_max_retries,
                trace_backoff_factor=trace_backoff_factor,
                trace_backoff_max_s=trace_backoff_max_s,
                judge_max_attempts=judge_max_attempts,
                judge_backoff_s=judge_backoff_s,
                runtime_preflight=runtime_preflight,
                sei_preflight_expectation=sei_preflight_expectation,
                canary_item_id=item_id,
                full_battery_authorization_event_id=authorization["event_id"],
                full_battery_retry_of_execution_id=retry_of_execution_id,
                full_battery_live_preflight=live_preflight,
                full_battery_mode=True,
            )
            summary = _summarize_battery_item(result, source="fresh_execution")
            continuation = _battery_continuation(result)
            execution_id = str(result.get("execution_id") or "")
            if execution_id:
                ledger.transition(
                    execution_id,
                    event_type="battery_item_completed",
                    trace_id=result.get("trace_id"),
                    post_attempted=True,
                    evaluation_status=result.get("evaluation_status"),
                    trace_status=result.get("trace_status"),
                    detail={
                        "sequence": sequence,
                        "continuation": continuation,
                    },
                )
        except Exception as exc:  # noqa: BLE001 - classificação fail-closed da campanha
            summary, continuation = _failed_battery_item_summary(
                output_root=output_root,
                run_name=item_run_name,
                item_id=item_id,
                exc=exc,
            )
            execution_id = summary.get("execution_id")
            if isinstance(execution_id, str):
                ledger.transition(
                    execution_id,
                    event_type="battery_item_failed_classified",
                    trace_id=summary.get("trace_id"),
                    post_attempted=True,
                    evaluation_status=(
                        summary.get("evaluation_status") or "technical_unavailable"
                    ),
                    trace_status=(
                        summary.get("trace_status") or "technical_unavailable"
                    ),
                    detail={
                        "sequence": sequence,
                        "continuation": continuation,
                    },
                )
        item_manifest = _manifest_item(manifest, item_id)
        summary["case_id"] = item_manifest["case_id"]
        summary["question_type"] = item_manifest["question_type"]
        summary["sequence"] = sequence
        summary["continuation"] = continuation
        attempts.append(summary)
        official_items.append(summary)
        cooldown_s = _case_error_cooldown_s(summary)
        if cooldown_s and item_id != remaining_item_ids[-1]:
            summary["cooldown_before_next_item_s"] = cooldown_s
        write_private_json(battery_root / "progress-sanitized.json", attempts)
        if not continuation["continue"]:
            stopped = True
            break
        if cooldown_s and item_id != remaining_item_ids[-1]:
            time.sleep(cooldown_s)

    aggregate = {
        "schema_version": "benchmark-long-context-v2-full-battery-1",
        "run_name": battery_run_name,
        "authorization_sha256": authorization_sha256,
        "authorization_event_id": authorization["event_id"],
        "policy_version": QUALITY_GATE_POLICY_VERSION,
        "execution_contract": {
            "endpoint": SESSION_ENDPOINT,
            "n": 1,
            "sequential": True,
            "max_concurrency": 1,
            "no_cache": True,
            "inference_retries": 0,
            "warmups": 0,
            "websearch": False,
            "fresh_comparable_required": True,
        },
        "excluded_historical_predecessor": excluded_predecessor,
        "official_items": official_items,
        "attempted_fresh_items": len(
            [
                event
                for event in ledger.events()
                if event.get("event_type") == "reservation"
            ]
        ),
        "expected_fresh_posts": len(missing_item_ids),
        "official_item_count": len(official_items),
        "status": (
            "completed"
            if len(attempts) == len(missing_item_ids) and not stopped
            else "stopped"
        ),
        "stopped_on_systemic_or_integrity_failure": stopped,
        "quality_failures_non_blocking": [
            item["item_id"]
            for item in official_items
            if (item.get("gate") or {})
            .get("dimensions", {})
            .get("quality", {})
            .get("status")
            == "failed"
        ],
        "usage": _aggregate_battery_usage(official_items),
    }
    write_private_json(battery_root / "full-battery-result-protected.json", aggregate)
    sanitized = {
        **aggregate,
        "excluded_historical_predecessor": (
            {
                key: excluded_predecessor.get(key)
                for key in (
                    "item_id",
                    "execution_id",
                    "trace_id",
                    "source_artifact_sha256",
                    "quality_status",
                    "fresh_comparable",
                    "replacement_reason",
                )
            }
            if excluded_predecessor is not None
            else None
        ),
        "protected_result_sha256": file_sha256(
            battery_root / "full-battery-result-protected.json"
        ),
    }
    write_private_json(battery_root / "full-battery-result-sanitized.json", sanitized)
    assert_private_tree(output_root)
    return sanitized


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--execute-canary", action="store_true")
    mode.add_argument("--resume-readback", action="store_true")
    mode.add_argument("--reclassify-existing", action="store_true")
    mode.add_argument("--full-battery-dry-run", action="store_true")
    mode.add_argument("--execute-full-battery", action="store_true")
    mode.add_argument("--resume-full-battery", action="store_true")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--protected-bundle-root", type=Path)
    parser.add_argument("--protected-output-root", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--sei-env-file", type=Path)
    parser.add_argument("--base-url", default=ISOLATED_BASE_URL)
    parser.add_argument("--run-name")
    parser.add_argument("--canary-item-id", default=CANARY_ITEM_ID)
    parser.add_argument("--replace-invalid-execution-id")
    parser.add_argument("--provider-internal-error-execution-id")
    parser.add_argument("--full-battery-authorization", type=Path)
    parser.add_argument("--fresh-all-items", action="store_true")
    parser.add_argument("--rate-limit-successor", action="store_true")
    parser.add_argument("--reused-output-root", action="append", type=Path, default=[])
    parser.add_argument("--timeout-s", type=float, default=7200.0)
    parser.add_argument("--trace-wait-s", type=float, default=900.0)
    parser.add_argument("--trace-poll-s", type=float, default=4.0)
    parser.add_argument("--trace-max-retries", type=int, default=120)
    parser.add_argument("--trace-backoff-factor", type=float, default=1.5)
    parser.add_argument("--trace-backoff-max-s", type=float, default=30.0)
    parser.add_argument("--judge-max-attempts", type=int, default=3)
    parser.add_argument("--judge-backoff-s", type=float, default=4.0)
    parser.add_argument("--reused-canary-summary", type=Path)
    add_model_campaign_args(parser, include_rate_card=True)
    return parser.parse_args()


def _main() -> int:  # noqa: C901, PLR0912, PLR0915
    args = _parse_args()
    canary_item_id = _select_canary_item_id(args.canary_item_id)
    protected_root = (
        args.protected_bundle_root.expanduser().resolve()
        if args.protected_bundle_root
        else None
    )
    manifest = validate_manifest(args.manifest.resolve(), protected_root=protected_root)
    frozen_contract = _load_contract(manifest)
    campaign = campaign_from_args(args) if campaign_requested(args) else None
    contract = (
        runtime_contract(frozen_contract, campaign)
        if campaign is not None
        else frozen_contract
    )
    if campaign is not None:
        campaign.apply_environment()
    if args.plan_only:
        if not campaign.reuse_historical_baseline:
            raise CanaryV2Error("--plan-only exige baseline histórico")
        print(
            json.dumps(
                plan_long_context_cells(
                    {item["item_id"] for item in manifest["items"]},
                    campaign,
                    reused_summary_path=args.reused_canary_summary,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    full_battery_mode = (
        args.full_battery_dry_run
        or args.execute_full_battery
        or args.resume_full_battery
    )
    if args.provider_internal_error_execution_id and not args.resume_full_battery:
        raise CanaryV2Error(
            "Classificação explícita de 500 exige --resume-full-battery"
        )
    if args.fresh_all_items and not full_battery_mode:
        raise CanaryV2Error("--fresh-all-items exige modo de bateria completa")
    if args.rate_limit_successor and not full_battery_mode:
        raise CanaryV2Error("--rate-limit-successor exige modo de bateria completa")
    if not (
        args.execute_canary
        or args.resume_readback
        or args.reclassify_existing
        or full_battery_mode
    ):
        print(
            json.dumps(
                {
                    "status": "validated",
                    "manifest_sha256": file_sha256(args.manifest.resolve()),
                    "contract_sha256": manifest["evaluation_contract"]["sha256"],
                    "items": len(manifest["items"]),
                    "selected_canary_item_id": canary_item_id,
                    "protected_bundle_validated": protected_root is not None,
                    "execution_attempted": False,
                }
            )
        )
        return 0

    if protected_root is None or args.protected_output_root is None:
        raise CanaryV2Error("Bundle e output protegidos são obrigatórios")
    if (args.resume_readback or args.reclassify_existing or full_battery_mode) and (
        args.replace_invalid_execution_id
    ):
        raise CanaryV2Error(
            "Retomada/reclassificação/bateria não aceita substituição do canário"
        )
    replacement_policy = None
    if args.replace_invalid_execution_id:
        policies = {
            policy["predecessor_execution_id"]: policy
            for policy in (FACTUAL_REPLACEMENT_POLICY, OCR_REMEDIATION_POLICY)
        }
        replacement_policy = policies.get(args.replace_invalid_execution_id)
        if canary_item_id != SECOND_CANARY_ITEM_ID or replacement_policy is None:
            raise CanaryV2Error("Substituição solicitada não está autorizada")
    sei_preflight_expectation = (
        _load_sei_preflight_expectation(args.sei_env_file)
        if args.execute_canary or full_battery_mode
        else None
    )
    if (
        any(
            value <= 0
            for value in (
                args.timeout_s,
                args.trace_wait_s,
                args.trace_poll_s,
                args.trace_backoff_max_s,
                args.judge_max_attempts,
                args.judge_backoff_s,
            )
        )
        or args.trace_max_retries < 0
        or args.trace_backoff_factor < 1
    ):
        raise CanaryV2Error("Timeout/retry/backoff inválido")
    if (
        args.resume_readback or args.reclassify_existing or full_battery_mode
    ) and not args.run_name:
        raise CanaryV2Error(
            "Run name explícito é obrigatório na retomada/reclassificação/bateria"
        )
    run_name = args.run_name or (
        "long-context-v2-canary-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    )
    output_root = args.protected_output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_root.chmod(0o700)
    if args.reclassify_existing:
        result = reclassify_existing_canary(
            manifest=manifest,
            contract=contract,
            output_root=output_root,
            run_name=run_name,
            canary_item_id=canary_item_id,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["gate"]["status"] == "passed" else 2

    authorization_sha256 = None
    reused_results: list[dict[str, Any]] = []
    excluded_predecessor = None
    missing_item_ids = None
    if full_battery_mode:
        authorization_sha256 = _load_full_battery_authorization(
            args.full_battery_authorization,
            fresh_all_items=args.fresh_all_items,
            rate_limit_successor=args.rate_limit_successor,
        )
        if args.fresh_all_items:
            _validate_fresh_campaign(contract, campaign)
            if args.reused_canary_summary is not None or args.reused_output_root:
                raise CanaryV2Error("Bateria 0+9 não aceita resultado reutilizado")
            reused_results = []
            excluded_predecessor = None
            missing_item_ids = _select_full_battery_missing_items(
                manifest, fresh_all_items=True
            )
        elif args.rate_limit_successor:
            if campaign is None:
                raise CanaryV2Error("Sucessor 3+6 exige campanha de modelos explícita")
            if args.reused_canary_summary is not None:
                raise CanaryV2Error("Sucessor 3+6 não aceita resumo de canário")
            reused_results, excluded_predecessor, missing_item_ids = (
                _confirm_successor_reused_partition(
                    reused_output_roots=args.reused_output_root,
                    manifest=manifest,
                    contract=contract,
                )
            )
        elif campaign is not None and args.reused_canary_summary is not None:
            source_factual, excluded_predecessor, missing_item_ids = (
                _confirm_configured_reused_partition(
                    reused_output_roots=args.reused_output_root,
                    reused_summary_path=args.reused_canary_summary,
                    manifest=manifest,
                    campaign=campaign,
                )
            )
            reused_results = [source_factual]
        else:
            source_factual, excluded_predecessor, missing_item_ids = (
                _confirm_full_battery_partition(
                    reused_output_roots=args.reused_output_root,
                    manifest=manifest,
                    contract=contract,
                )
            )
            reused_results = [source_factual]

    base_url = _guard_isolated_base_url(args.base_url)
    credentials = _load_langfuse_credentials(args.env_file)
    project_id = _project_gate(credentials)
    langfuse = _langfuse_client(credentials)
    dataset = langfuse.get_dataset(DATASET_NAME, fetch_items_page_size=100)
    items = validate_dataset(dataset, project_id)
    item = _item_by_id(items, canary_item_id)

    with _http_client(args.timeout_s, isolated=True) as http_client:
        runtime_preflight = _preflight(base_url, http_client)
        _validate_v2_runtime_preflight(runtime_preflight, manifest, contract)
        if full_battery_mode:
            if not all(
                value is not None
                for value in (
                    authorization_sha256,
                    missing_item_ids,
                    sei_preflight_expectation,
                )
            ) or (not reused_results and not args.fresh_all_items):
                raise CanaryV2Error("Readiness da bateria está incompleto")
            process_id = _battery_process_id(
                manifest, protected_root, missing_item_ids[0]
            )
            live_preflight = _run_live_sei_preflight(
                http_client=http_client,
                base_url=base_url,
                process_id=process_id,
                expectation=sei_preflight_expectation,
            )
            _validate_live_sei_preflight(live_preflight, sei_preflight_expectation)
            judge_config = _guard_judge_config(contract, args.env_file)
            readiness = {
                "schema_version": "benchmark-long-context-v2-full-battery-readiness-1",
                "status": "passed",
                "run_name": run_name,
                "authorization_sha256": authorization_sha256,
                "reused_fresh_item_ids": [
                    result["item_id"] for result in reused_results
                ],
                "excluded_predecessor_item_id": (
                    excluded_predecessor["item_id"]
                    if excluded_predecessor is not None
                    else None
                ),
                "excluded_predecessor_reason": (
                    excluded_predecessor["replacement_reason"]
                    if excluded_predecessor is not None
                    else None
                ),
                "missing_item_ids": missing_item_ids,
                "expected_fresh_posts": len(missing_item_ids),
                "runtime_preflight": runtime_preflight,
                "live_preflight": live_preflight,
                "post_attempted": False,
            }
            write_private_json(
                output_root / "full-battery-readiness-sanitized.json", readiness
            )
            if args.full_battery_dry_run:
                result = readiness
            else:
                judge_url, judge_key, judge_model = judge_config
                judge_client = OpenAI(
                    base_url=judge_url, api_key=judge_key, timeout=300.0
                )
                if args.resume_full_battery:
                    ledger = V2Ledger(output_root / "execution-ledger.jsonl")
                    events = ledger.events()
                    pending_reservations = [
                        event
                        for event in events
                        if event.get("event_type") == "reservation"
                        and not any(
                            row.get("event_type")
                            in {
                                "official_evaluation",
                                "evaluation_unavailable",
                                "battery_item_invalidated_for_retry",
                                "provider_rate_limited",
                                "case_error_recorded",
                            }
                            and row.get("execution_id") == event.get("execution_id")
                            for row in events
                        )
                    ]
                    provider_error_classified = 0
                    for reservation in pending_reservations:
                        recovery_item_id = str(reservation["item_id"])
                        recovery_run_name = str(reservation["run_name"])
                        raw_sse_path = (
                            output_root
                            / "runs"
                            / recovery_run_name
                            / "items"
                            / recovery_item_id
                            / "stream.raw.sse"
                        )
                        try:
                            recovered_outcome = _recover_sse_outcome(raw_sse_path)
                        except CanaryV2Error as exc:
                            if (
                                str(exc)
                                != "SSE preservado não possui terminal recuperável"
                                or not raw_sse_path.is_file()
                                or raw_sse_path.stat().st_size == 0
                            ):
                                raise
                            ledger.transition(
                                str(reservation["execution_id"]),
                                event_type="battery_item_invalidated_for_retry",
                                trace_id=next(
                                    (
                                        str(row["trace_id"])
                                        for row in events
                                        if row.get("execution_id")
                                        == reservation["execution_id"]
                                        and row.get("trace_id")
                                    ),
                                    None,
                                ),
                                post_attempted=True,
                                evaluation_status="technical_unavailable",
                                trace_status="technical_unavailable",
                                artifact_sha256=file_sha256(raw_sse_path),
                                detail={
                                    "reason": "interrupted_stream_without_terminal",
                                    "error_sha256": _sha256_text(str(exc)),
                                },
                            )
                            continue
                        if (
                            args.provider_internal_error_execution_id
                            == reservation["execution_id"]
                        ):
                            result_path = raw_sse_path.with_name(
                                "result-protected.json"
                            )
                            protected = json.loads(
                                result_path.read_text(encoding="utf-8")
                            )
                            if not _mark_case_error_result(
                                protected,
                                outcome=recovered_outcome,
                                raw_path=raw_sse_path,
                                result_status="provider_internal_error",
                            ):
                                raise CanaryV2Error(
                                    "Classificação explícita não corresponde a terminal 500"
                                )
                            write_private_json(result_path, protected)
                            write_private_json(
                                result_path.parents[2] / "canary-result-sanitized.json",
                                _sanitized_result(protected),
                            )
                            ledger.transition(
                                str(reservation["execution_id"]),
                                event_type="case_error_recorded",
                                trace_id=next(
                                    (
                                        str(row["trace_id"])
                                        for row in events
                                        if row.get("execution_id")
                                        == reservation["execution_id"]
                                        and row.get("trace_id")
                                    ),
                                    None,
                                ),
                                post_attempted=True,
                                evaluation_status="technical_unavailable",
                                trace_status="technical_unavailable",
                                artifact_sha256=file_sha256(result_path),
                                detail={"result_status": "provider_internal_error"},
                            )
                            provider_error_classified += 1
                            continue
                        execution_rows = [
                            row
                            for row in events
                            if row.get("execution_id") == reservation["execution_id"]
                        ]
                        retry_proof = _pre_agent_retry_proof(
                            raw_sse_path, execution_rows
                        )
                        if retry_proof is not None:
                            ledger.transition(
                                str(reservation["execution_id"]),
                                event_type="battery_item_invalidated_for_retry",
                                trace_id=next(
                                    (
                                        str(row["trace_id"])
                                        for row in execution_rows
                                        if row.get("trace_id")
                                    ),
                                    None,
                                ),
                                post_attempted=True,
                                evaluation_status="technical_unavailable",
                                trace_status="technical_unavailable",
                                artifact_sha256=file_sha256(raw_sse_path),
                                detail={
                                    "reason": "pre_agent_transport_failure",
                                    "proof": retry_proof,
                                },
                            )
                            continue
                        if any(
                            row.get("event_type") == "provider_rate_limited"
                            for row in execution_rows
                        ):
                            continue
                        rate_limit_proof = _rate_limit_retry_proof(
                            raw_sse_path, execution_rows
                        )
                        if rate_limit_proof is not None:
                            if not rate_limit_proof["cooldown_satisfied"]:
                                remaining_s = max(
                                    0.0,
                                    RATE_LIMIT_COOLDOWN_S
                                    - rate_limit_proof["cooldown_elapsed_s"],
                                )
                                raise CanaryV2Error(
                                    "Cooldown de rate limit ainda não satisfeito: "
                                    f"{remaining_s:.0f}s restantes"
                                )
                            ledger.transition(
                                str(reservation["execution_id"]),
                                event_type="battery_item_invalidated_for_retry",
                                trace_id=next(
                                    (
                                        str(row["trace_id"])
                                        for row in execution_rows
                                        if row.get("trace_id")
                                    ),
                                    None,
                                ),
                                post_attempted=True,
                                evaluation_status="technical_unavailable",
                                trace_status="technical_unavailable",
                                artifact_sha256=file_sha256(raw_sse_path),
                                detail={
                                    "reason": "model_rate_limit_after_cooldown",
                                    "proof": rate_limit_proof,
                                },
                            )
                            continue
                        recover_battery_item_postprocessing(
                            manifest=manifest,
                            contract=contract,
                            protected_bundle_root=protected_root,
                            output_root=output_root,
                            item=_item_by_id(items, recovery_item_id),
                            item_id=recovery_item_id,
                            run_name=recovery_run_name,
                            langfuse=langfuse,
                            project_id=project_id,
                            judge_client=judge_client,
                            judge_model=judge_model,
                            trace_wait_s=args.trace_wait_s,
                            trace_poll_s=args.trace_poll_s,
                            trace_max_retries=args.trace_max_retries,
                            trace_backoff_factor=args.trace_backoff_factor,
                            trace_backoff_max_s=args.trace_backoff_max_s,
                            judge_max_attempts=args.judge_max_attempts,
                            judge_backoff_s=args.judge_backoff_s,
                        )
                    if args.provider_internal_error_execution_id and (
                        provider_error_classified != 1
                    ):
                        raise CanaryV2Error(
                            "Execução 500 explícita não corresponde a uma reserva pendente"
                        )
                result = execute_full_battery(
                    manifest=manifest,
                    contract=contract,
                    protected_bundle_root=protected_root,
                    output_root=output_root,
                    battery_run_name=run_name,
                    reused_results=reused_results,
                    excluded_predecessor=excluded_predecessor,
                    missing_item_ids=missing_item_ids,
                    authorization_sha256=authorization_sha256,
                    live_preflight=live_preflight,
                    items=items,
                    langfuse=langfuse,
                    langfuse_host=credentials["LANGFUSE_URL"],
                    project_id=project_id,
                    http_client=http_client,
                    base_url=base_url,
                    judge_client=judge_client,
                    judge_model=judge_model,
                    trace_wait_s=args.trace_wait_s,
                    trace_poll_s=args.trace_poll_s,
                    trace_max_retries=args.trace_max_retries,
                    trace_backoff_factor=args.trace_backoff_factor,
                    trace_backoff_max_s=args.trace_backoff_max_s,
                    judge_max_attempts=args.judge_max_attempts,
                    judge_backoff_s=args.judge_backoff_s,
                    runtime_preflight=runtime_preflight,
                    sei_preflight_expectation=sei_preflight_expectation,
                    resume=args.resume_full_battery,
                )
        elif args.resume_readback:
            write_private_json(
                output_root / "runtime-preflight-readback.json", runtime_preflight
            )
            result = resume_readback(
                manifest=manifest,
                contract=contract,
                output_root=output_root,
                run_name=run_name,
                item=item,
                langfuse=langfuse,
                project_id=project_id,
                trace_wait_s=args.trace_wait_s,
                trace_poll_s=args.trace_poll_s,
                trace_max_retries=args.trace_max_retries,
                trace_backoff_factor=args.trace_backoff_factor,
                trace_backoff_max_s=args.trace_backoff_max_s,
                canary_item_id=canary_item_id,
            )
        else:
            judge_url, judge_key, judge_model = _guard_judge_config(
                contract, args.env_file
            )
            judge_client = OpenAI(base_url=judge_url, api_key=judge_key, timeout=300.0)
            result = execute_canary(
                manifest=manifest,
                contract=contract,
                protected_bundle_root=protected_root,
                output_root=output_root,
                run_name=run_name,
                item=item,
                langfuse=langfuse,
                langfuse_host=credentials["LANGFUSE_URL"],
                project_id=project_id,
                http_client=http_client,
                base_url=base_url,
                judge_client=judge_client,
                judge_model=judge_model,
                trace_wait_s=args.trace_wait_s,
                trace_poll_s=args.trace_poll_s,
                trace_max_retries=args.trace_max_retries,
                trace_backoff_factor=args.trace_backoff_factor,
                trace_backoff_max_s=args.trace_backoff_max_s,
                judge_max_attempts=args.judge_max_attempts,
                judge_backoff_s=args.judge_backoff_s,
                runtime_preflight=runtime_preflight,
                sei_preflight_expectation=sei_preflight_expectation or {},
                replacement_policy=replacement_policy,
                canary_item_id=canary_item_id,
            )
    print(json.dumps(result, ensure_ascii=False))
    if args.full_battery_dry_run:
        return 0
    if args.execute_full_battery or args.resume_full_battery:
        return 0 if result["status"] == "completed" else 2
    return 0 if result["gate"]["authorized_canary"]["status"] == "passed" else 2


def main() -> int:
    try:
        return _main()
    except Exception as exc:  # noqa: BLE001 - CLI não imprime conteúdo protegido
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error_sha256": _sha256_text(str(exc)),
                }
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
