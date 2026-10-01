"""Normalização auditável de modelo, tokens e custo do long-context v2."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from model_campaign import ModelIdentity as CampaignIdentity, price_usage
from trace_metrics import Obs

_SCOPES = ("agent", "ocr", "judge")
_COMPONENTS = ("main", "subagent", "classifier", "planner", "summarizer", "unknown")


class TelemetryContractError(RuntimeError):
    """Telemetria ausente, duplicada ou semanticamente ambígua."""


class AgentUsageUnavailableError(TelemetryContractError):
    """O trace é válido, mas não expõe métricas de uso do agente."""


@dataclass(frozen=True)
class ModelIdentity:
    requested_profile: str
    deployment: str
    canonical_model: str
    provider: str


@dataclass(frozen=True)
class CanonicalUsage:
    input_uncached: int
    cache_read: int
    cache_write: int | None
    output: int
    reasoning: int

    @property
    def total_without_cache_write(self) -> int:
        return self.input_uncached + self.cache_read + self.output + self.reasoning

    @property
    def total(self) -> int | None:
        if self.cache_write is None:
            return None
        return self.total_without_cache_write + self.cache_write

    @property
    def billed_output(self) -> int:
        return self.output + self.reasoning

    def as_dict(self) -> dict[str, int | None]:
        return {
            "input_uncached": self.input_uncached,
            "cache_read": self.cache_read,
            "cache_write": self.cache_write,
            "output": self.output,
            "reasoning": self.reasoning,
            "total_without_cache_write": self.total_without_cache_write,
            "total": self.total,
        }


def _non_negative(value: Any, name: str) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise TelemetryContractError(f"Token inválido em {name}") from exc
    if number < 0:
        raise TelemetryContractError(f"Token negativo em {name}")
    return number


def resolve_model(model: str | None, contract: dict[str, Any]) -> ModelIdentity:
    profiles = contract["model_profiles"]
    ordered = sorted(
        profiles.items(), key=lambda row: len(row[1]["canonical_model"]), reverse=True
    )
    for profile, identity in ordered:
        canonical = identity["canonical_model"]
        accepted = {profile, identity["deployment"], canonical}
        dated_canonical = isinstance(model, str) and model.startswith(canonical + "-20")
        if model in accepted or dated_canonical:
            return ModelIdentity(profile, **identity)
    raise TelemetryContractError(f"Modelo não mapeado pela campanha: {model!r}")


def normalize_agent_usage(raw: dict[str, Any]) -> CanonicalUsage:
    """Langfuse: input/output são visíveis; cache e reasoning vêm separados."""
    input_uncached = _non_negative(raw.get("input"), "input")
    cache_read = _non_negative(raw.get("input_cache_read"), "input_cache_read")
    raw_cache_write = raw.get("input_cache_write")
    if raw_cache_write is None:
        raw_cache_write = raw.get("input_cache_creation")
    cache_write = (
        _non_negative(raw_cache_write, "input_cache_write")
        if raw_cache_write is not None
        else None
    )
    raw_output = _non_negative(raw.get("output"), "output")
    reasoning = _non_negative(raw.get("output_reasoning"), "output_reasoning")
    return CanonicalUsage(
        input_uncached=input_uncached,
        cache_read=cache_read,
        cache_write=cache_write,
        output=raw_output,
        reasoning=reasoning,
    )


def normalize_judge_usage(raw: dict[str, Any]) -> CanonicalUsage:
    """OpenAI compatível: prompt/completion incluem cache/reasoning e são decompostos."""
    prompt = _non_negative(raw.get("prompt_tokens"), "prompt_tokens")
    cache_read = _non_negative(raw.get("cached_tokens"), "cached_tokens")
    completion = _non_negative(raw.get("completion_tokens"), "completion_tokens")
    reasoning = _non_negative(raw.get("reasoning_tokens"), "reasoning_tokens")
    if cache_read > prompt or reasoning > completion:
        raise TelemetryContractError("Detalhes de usage excedem seus totais")
    return CanonicalUsage(
        input_uncached=prompt - cache_read,
        cache_read=cache_read,
        cache_write=0,
        output=completion - reasoning,
        reasoning=reasoning,
    )


def normalize_ocr_usage(raw: dict[str, Any]) -> CanonicalUsage:
    """OCR OpenAI compatível, preservando cache_write ausente como N/D."""
    prompt = _non_negative(raw.get("prompt_tokens"), "prompt_tokens")
    cache_read = _non_negative(raw.get("cached_tokens"), "cached_tokens")
    completion = _non_negative(raw.get("completion_tokens"), "completion_tokens")
    reasoning = _non_negative(raw.get("reasoning_tokens"), "reasoning_tokens")
    cache_write = (
        _non_negative(raw["cache_write_tokens"], "cache_write_tokens")
        if raw.get("cache_write_tokens") is not None
        else None
    )
    if cache_read > prompt or reasoning > completion:
        raise TelemetryContractError("Detalhes de usage OCR excedem seus totais")
    return CanonicalUsage(
        input_uncached=prompt - cache_read,
        cache_read=cache_read,
        cache_write=cache_write,
        output=completion - reasoning,
        reasoning=reasoning,
    )


def _ancestor_names(observation: Obs, by_id: dict[str, Obs]) -> list[str]:
    names: list[str] = []
    current = by_id.get(observation.parent_id) if observation.parent_id else None
    seen: set[str] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        names.append(current.name.lower())
        current = by_id.get(current.parent_id) if current.parent_id else None
    return names


def generation_component(observation: Obs, by_id: dict[str, Obs]) -> str:
    names = [observation.name.lower(), *_ancestor_names(observation, by_id)]
    joined = " ".join(names)
    if any(marker in joined for marker in ("summarizer", "summarization", "summary")):
        return "summarizer"
    if any(marker in joined for marker in ("planner", "planning", "plan_speculative")):
        return "planner"
    if any(marker in joined for marker in ("classifier", "classify", "complexity")):
        return "classifier"
    namespace_parts = [part for part in observation.ns.split("|") if part]
    if len(namespace_parts) >= 2 or "task" in names:
        return "subagent"
    if "session_agent" in names or "model" in names:
        return "main"
    return "unknown"


def _observation_key(trace_id: str, observation_id: str) -> str:
    return hashlib.sha256(f"{trace_id}:{observation_id}".encode()).hexdigest()


def agent_usage_records(
    observations: list[Obs], *, trace_id: str, contract: dict[str, Any]
) -> list[dict[str, Any]]:
    """Uma linha por GENERATION; repetições idênticas deduplicam, divergentes falham."""
    by_id = {observation.id: observation for observation in observations}
    records_by_key: dict[str, dict[str, Any]] = {}
    for observation in observations:
        if "GENERATION" not in observation.type.upper():
            continue
        identity = resolve_model(observation.model, contract)
        usage = normalize_agent_usage(observation.usage)
        key = _observation_key(trace_id, observation.id)
        record = {
            "call_key_sha256": key,
            "scope": "agent",
            "component": generation_component(observation, by_id),
            "model": identity.__dict__,
            "reported_model": observation.model,
            "usage": usage.as_dict(),
        }
        existing = records_by_key.get(key)
        if existing is not None and existing != record:
            raise TelemetryContractError(
                f"Generation duplicada com usage divergente: {key}"
            )
        records_by_key[key] = record
    if not records_by_key:
        raise AgentUsageUnavailableError("Trace sem GENERATIONs contabilizáveis")
    return list(records_by_key.values())


def judge_usage_record(
    raw_usage: dict[str, Any],
    *,
    call_id: str,
    reported_model: str | None = None,
    contract: dict[str, Any],
) -> dict[str, Any]:
    judge = contract["judge"]
    resolution_source = "response_model"
    if reported_model is None:
        reported_model = judge["deployment"]
        resolution_source = "requested_deployment"
    identity = resolve_model(reported_model, contract)
    if (
        identity.deployment != judge["deployment"]
        or identity.canonical_model != judge["canonical_model"]
        or identity.provider != judge["provider"]
    ):
        raise TelemetryContractError("Modelo do juiz diverge do profile mini congelado")
    return {
        "call_key_sha256": hashlib.sha256(call_id.encode()).hexdigest(),
        "scope": "judge",
        "component": "judge",
        "model": identity.__dict__,
        "reported_model": reported_model,
        "model_resolution_source": resolution_source,
        "usage": normalize_judge_usage(raw_usage).as_dict(),
    }


def ocr_usage_records(
    raw_records: list[dict[str, Any]], *, contract: dict[str, Any]
) -> list[dict[str, Any]]:
    """Normaliza chamadas OCR coletadas fora do trace sem duplicá-las."""
    expected = contract.get("ocr")
    if not isinstance(expected, dict):
        raise TelemetryContractError("Contrato OCR ausente")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    accepted_models = {
        expected.get("deployment"),
        expected.get("canonical_model"),
    }
    for raw in raw_records:
        if raw.get("schema_version") != "sei-extraction-ocr-usage-v1":
            raise TelemetryContractError("Schema de usage OCR desconhecido")
        if raw.get("role") != "ocr" or raw.get("deployment") != expected.get(
            "deployment"
        ):
            raise TelemetryContractError("Papel ou deployment OCR divergente")
        reported_model = raw.get("reported_model")
        dated_model = isinstance(reported_model, str) and reported_model.startswith(
            str(expected.get("canonical_model")) + "-20"
        )
        if reported_model not in accepted_models and not dated_model:
            raise TelemetryContractError("Modelo canônico OCR divergente")
        key = raw.get("call_key_sha256")
        if (
            not isinstance(key, str)
            or len(key) != 64
            or any(char not in "0123456789abcdef" for char in key)
        ):
            raise TelemetryContractError("Identidade de chamada OCR inválida")
        if key in seen:
            raise TelemetryContractError("Chamada OCR duplicada")
        seen.add(key)
        records.append(
            {
                "call_key_sha256": key,
                "scope": "ocr",
                "component": "ocr",
                "model": {
                    name: expected[name]
                    for name in (
                        "requested_profile",
                        "deployment",
                        "canonical_model",
                        "provider",
                    )
                },
                "reported_model": reported_model,
                "usage": normalize_ocr_usage(raw.get("usage") or {}).as_dict(),
            }
        )
    return records


def _cost_result(record: dict[str, Any], rate_card: dict[str, Any]) -> dict[str, Any]:
    deployment = record["model"]["deployment"]
    rate = (rate_card.get("models") or {}).get(deployment)
    if isinstance(rate, dict) and "short_context" not in rate:
        usage = record["usage"]
        output_billed = _non_negative(usage["output"], "output") + _non_negative(
            usage["reasoning"], "reasoning"
        )
        cost = (
            Decimal(usage["input_uncached"])
            * Decimal(str(rate["input_per_million_usd"]))
            + Decimal(usage["cache_read"])
            * Decimal(str(rate["cache_read_per_million_usd"]))
            + Decimal(output_billed) * Decimal(str(rate["output_per_million_usd"]))
        ) / Decimal(1_000_000)
        return {"available": True, "cost_usd": float(cost)}
    try:
        return price_usage(
            CampaignIdentity(**record["model"]), record["usage"], rate_card
        )
    except ValueError as exc:
        raise TelemetryContractError(
            f"Modelo sem preço na rate card: {deployment}"
        ) from exc


def _cost_summary(
    records: list[dict[str, Any]], rate_card: dict[str, Any]
) -> dict[str, Any]:
    results = [_cost_result(record, rate_card) for record in records]
    exact = [row for row in results if row["available"]]
    partial = [row for row in results if not row["available"]]
    exact_sum = sum((Decimal(str(row["cost_usd"])) for row in exact), Decimal(0))
    if not partial:
        return {"cost_usd": float(exact_sum)}
    subtotals = {
        regime: float(
            exact_sum
            + sum(
                (
                    Decimal(
                        str(
                            row["known_subtotal_excluding_cache_write_usd"][
                                f"if_all_requests_{regime}"
                            ]
                        )
                    )
                    for row in partial
                ),
                Decimal(0),
            )
        )
        for regime in ("short_context", "long_context")
    }
    return {
        "cost_usd": None,
        "known_subtotal_excluding_cache_write_usd": subtotals,
        "missing_usage": ["cache_write"],
    }


def _token_summary(records: list[dict[str, Any]]) -> dict[str, int | None]:
    totals: dict[str, int | None] = {
        field: sum(
            record["usage"].get(
                field,
                record["usage"].get("total", 0)
                if field == "total_without_cache_write"
                else 0,
            )
            for record in records
        )
        for field in (
            "input_uncached",
            "cache_read",
            "output",
            "reasoning",
            "total_without_cache_write",
        )
    }
    cache_writes = [record["usage"].get("cache_write", 0) for record in records]
    totals["cache_write"] = (
        sum(cache_writes) if all(value is not None for value in cache_writes) else None
    )
    totals["total"] = (
        int(totals["total_without_cache_write"]) + int(totals["cache_write"])
        if totals["cache_write"] is not None
        else None
    )
    return totals


def summarize_usage(
    records: list[dict[str, Any]],
    *,
    rate_card: dict[str, Any],
    rate_card_ref: dict[str, Any],
) -> dict[str, Any]:
    """Consolida sem estimar lacunas; agente, OCR e juiz ficam separados."""
    expected_identity = {
        key: rate_card_ref.get(key)
        for key in (
            "version",
            "effective_on",
            "aggregation_compatibility_key",
        )
    }
    observed_identity = {
        key: rate_card.get(key)
        for key in (
            "version",
            "effective_on",
            "aggregation_compatibility_key",
        )
    }
    if expected_identity != observed_identity:
        raise TelemetryContractError("Rate card incompatível com o contrato")
    if not records:
        raise TelemetryContractError("Nenhum usage record para consolidar")
    keys = [record["call_key_sha256"] for record in records]
    if len(keys) != len(set(keys)):
        raise TelemetryContractError("Usage records duplicados")
    if any(record["scope"] not in _SCOPES for record in records):
        raise TelemetryContractError("Scope de usage desconhecido")

    by_scope: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    for bucket_key, selector in (
        (scope, lambda row, scope=scope: row["scope"] == scope) for scope in _SCOPES
    ):
        selected = [record for record in records if selector(record)]
        if not selected:
            by_scope[bucket_key] = {
                "available": False,
                "calls": 0,
                "tokens": None,
                "cost_usd": None,
            }
            continue
        totals = _token_summary(selected)
        cost = _cost_summary(selected, rate_card)
        by_scope[bucket_key] = {
            "available": True,
            "calls": len(selected),
            "tokens": totals,
            **cost,
        }

    model_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        model_groups[record["model"]["canonical_model"]].append(record)
    for model, selected in sorted(model_groups.items()):
        identities = {tuple(record["model"].values()) for record in selected}
        if len(identities) != 1:
            raise TelemetryContractError(f"Identidade inconsistente para {model}")
        by_model[model] = {
            "identity": selected[0]["model"],
            "calls": len(selected),
            "calls_by_scope": dict(Counter(record["scope"] for record in selected)),
            "tokens": _token_summary(selected),
            **_cost_summary(selected, rate_card),
        }

    agent_components = Counter(
        record["component"] for record in records if record["scope"] == "agent"
    )
    return {
        "schema_version": "benchmark-long-context-v2-usage-1",
        "coverage": {
            "status": "complete",
            "deduplication_key": "sha256(trace_id:observation_id)|sha256(judge_call_id)",
            "generation_records": by_scope["agent"]["calls"],
            "ocr_records": by_scope["ocr"]["calls"],
            "judge_records": by_scope["judge"]["calls"],
        },
        "canonical_total_formula": (
            "input_uncached + cache_read + cache_write + output + reasoning"
        ),
        "rate_card": rate_card_ref,
        "by_scope": by_scope,
        "by_model": by_model,
        "agent_calls_by_component": {
            component: agent_components.get(component, 0) for component in _COMPONENTS
        },
        "total_cost_usd": _cost_summary(records, rate_card)["cost_usd"],
        "cost": _cost_summary(records, rate_card),
    }
