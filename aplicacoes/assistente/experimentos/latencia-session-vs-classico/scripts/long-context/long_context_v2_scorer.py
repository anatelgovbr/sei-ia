"""Contrato de julgamento por claim e scorer canônico da campanha long-context v2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from long_context_v2_manifest import (
    ManifestContractError,
    file_sha256,
    load_protected_json,
    load_protected_text,
)

CANONICAL_METRICS = (
    "groundedness",
    "completeness",
    "citation_quality",
    "hallucination",
    "negativa_correta",
    "overall",
)
AUXILIARY_METRICS = ("target_alignment", "hallucination_count")
EVALUATION_STATUSES = (
    "pending_trace",
    "pending_evaluation",
    "evaluated",
    "technical_unavailable",
)
QUALITY_GATE_POLICY_VERSION = "long-context-v2-canary-gates-v2-20260724"


class JudgeV2ContractError(RuntimeError):
    """Saída do juiz não é publicável segundo o contrato v2."""


@dataclass(frozen=True)
class JudgeMaterial:
    question: str
    gold: str
    rubric: dict[str, Any]
    target: dict[str, Any]
    source_evidence: list[dict[str, Any]]
    protected_absence: dict[str, Any] | None


@dataclass(frozen=True)
class ScoreV2:
    numeric: dict[str, float]
    boolean: dict[str, bool | None]
    auxiliary: dict[str, bool | int]
    claims: list[dict[str, Any]]
    checklist: list[dict[str, Any]]
    rationale: str
    gate: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "evaluated",
            "numeric": self.numeric,
            "boolean": self.boolean,
            "auxiliary": self.auxiliary,
            "claims": self.claims,
            "checklist": self.checklist,
            "rationale": self.rationale,
            "gate": self.gate,
        }


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise JudgeV2ContractError(f"Objeto JSON esperado: {path}")
    return value


def load_judge_material(item: dict[str, Any], protected_root: Path) -> JudgeMaterial:
    """Carrega pergunta/gold/rubrica/evidência somente por refs hasheadas."""
    source_evidence = [
        load_protected_json(entry, protected_root)
        for entry in item["evidence"]["source_refs"]
    ]
    absence_entry = item["absence_evidence"]["ref"]
    protected_absence = (
        load_protected_json(absence_entry, protected_root)
        if absence_entry is not None
        else None
    )
    return JudgeMaterial(
        question=load_protected_text(item["question"], protected_root),
        gold=load_protected_text(item["gold"], protected_root),
        rubric=load_protected_json(item["rubric"], protected_root),
        target=load_protected_json(item["target"]["anchor_ref"], protected_root),
        source_evidence=source_evidence,
        protected_absence=protected_absence,
    )


def merge_evidence_package(
    source_evidence: list[dict[str, Any]],
    opened_evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Combina verdade de referência e excertos abertos, com índices sem colisão."""
    merged: list[dict[str, Any]] = []
    for role, entries in (
        ("protected_reference", source_evidence),
        ("agent_opened", opened_evidence),
    ):
        for entry in entries:
            excerpt = entry.get("excerpt")
            if not isinstance(excerpt, str) or not excerpt:
                raise JudgeV2ContractError("Evidência sem excerto textual explícito")
            merged.append(
                {
                    "reference": len(merged) + 1,
                    "role": role,
                    "document_ref_sha256": entry.get("document_ref_sha256")
                    or entry.get("document_sha256"),
                    "excerpt": excerpt,
                    "excerpt_sha256": entry.get("excerpt_sha256"),
                    "opened": role == "agent_opened",
                    "cited": bool(entry.get("cited"))
                    if role == "agent_opened"
                    else False,
                }
            )
    if not merged:
        raise JudgeV2ContractError("Pacote de evidência vazio")
    return merged


def build_judge_input(
    *,
    item: dict[str, Any],
    material: JudgeMaterial,
    answer: str,
    evidence_package: list[dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Monta o payload protegido do juiz sem depender do trace Langfuse."""
    if not answer.strip():
        raise JudgeV2ContractError("Resposta vazia não pode ser julgada")
    return {
        "contract_version": contract["version"],
        "context_adapter": contract["context_adapter"],
        "item_id": item["item_id"],
        "question_type": item["question_type"],
        "question": material.question,
        "answer": answer,
        "gold": material.gold,
        "rubric": material.rubric,
        "target": material.target,
        "evidence_package": evidence_package,
        "protected_absence": material.protected_absence,
    }


def load_judge_artifacts(
    contract: dict[str, Any], experiment_root: Path
) -> tuple[str, str, dict[str, Any]]:
    """Reconfirma hashes de prompt/schema antes de qualquer chamada ao juiz."""
    judge = contract["judge"]
    paths = {
        name: experiment_root / judge[f"{name}_ref"]
        for name in ("system_prompt", "user_prompt", "response_schema")
    }
    for name, path in paths.items():
        if file_sha256(path) != judge[f"{name}_sha256"]:
            raise ManifestContractError(f"Hash do juiz divergiu: {name}")
    return (
        paths["system_prompt"].read_text(encoding="utf-8"),
        paths["user_prompt"].read_text(encoding="utf-8"),
        _json(paths["response_schema"]),
    )


def judge_messages(
    *, system_prompt: str, user_prompt: str, judge_input: dict[str, Any]
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": user_prompt
            + "\n\nOBJETO JSON:\n"
            + json.dumps(judge_input, ensure_ascii=False, sort_keys=True),
        },
    ]


def parse_judge_output(content: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Valida JSON/schema sem reparo textual ou fallback permissivo."""
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise JudgeV2ContractError("Juiz não devolveu JSON válido") from exc
    if not isinstance(value, dict):
        raise JudgeV2ContractError("Juiz deve devolver objeto JSON")
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise JudgeV2ContractError(
            f"Saída do juiz inválida em {location}: {first.message}"
        )
    return value


def _validate_semantics(
    value: dict[str, Any],
    *,
    obligation_count: int,
    evidence_count: int,
    negative: bool,
    absence_reference: str | None,
) -> None:
    indexes = [row["index"] for row in value["checklist"]]
    if indexes != list(range(1, obligation_count + 1)):
        raise JudgeV2ContractError("Checklist do juiz não corresponde à rubrica")
    if negative != isinstance(value["negativa_correta"], bool):
        expected = "boolean" if negative else "null"
        raise JudgeV2ContractError(f"negativa_correta deve ser {expected}")

    for claim in value["claims"]:
        references = claim["evidence_references"]
        if any(reference > evidence_count for reference in references):
            raise JudgeV2ContractError("Claim referencia evidência inexistente")
        verdict = claim["verdict"]
        basis = claim["evidence_basis"]
        absence = claim["absence_evidence_reference"]
        if claim["invented"] and verdict != "contradicted":
            raise JudgeV2ContractError(
                "Invenção deve ser classificada como contradicted"
            )
        if verdict == "supported":
            excerpt_supported = (
                basis == "excerpt" and bool(references) and absence is None
            )
            absence_supported = (
                basis == "protected_absence"
                and not references
                and absence_reference is not None
                and absence == absence_reference
            )
            if not (excerpt_supported or absence_supported):
                raise JudgeV2ContractError("Claim supported não tem evidência válida")
        elif basis == "protected_absence" or absence is not None:
            raise JudgeV2ContractError("Protected absence só sustenta claim supported")
        elif basis == "none" and references:
            raise JudgeV2ContractError("evidence_basis=none não pode ter referência")
        elif basis == "excerpt" and not references:
            raise JudgeV2ContractError("evidence_basis=excerpt exige referência")
        if verdict == "contradicted" and not (references or claim["invented"]):
            raise JudgeV2ContractError("Contradição sem evidência ou marca de invenção")


def classify_quality_gate(
    *,
    numeric: dict[str, float],
    boolean: dict[str, bool | None],
    auxiliary: dict[str, bool | int],
    negative: bool,
    answer_nonempty: bool,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    """Separa invalidade qualitativa de scores contínuos diagnósticos."""
    blocking_checks = {
        "response_nonempty": answer_nonempty,
        "target_alignment": auxiliary.get("target_alignment") is True,
        "hallucination_absent": boolean.get("hallucination") is False,
        "negativa_correta": (
            not negative
            or boolean.get("negativa_correta")
            is thresholds["negativa_correta_for_negative"]
        ),
    }
    historical_thresholds = {
        name: {
            "value": numeric[name],
            "operator": ">=" if thresholds[name] is not None else None,
            "threshold": thresholds[name],
            "met": (
                numeric[name] >= thresholds[name]
                if thresholds[name] is not None
                else None
            ),
            "blocking": False,
        }
        for name in (
            "groundedness",
            "completeness",
            "citation_quality",
            "overall",
        )
    }
    passed = all(blocking_checks.values())
    return {
        "policy_version": QUALITY_GATE_POLICY_VERSION,
        "status": "passed" if passed else "failed",
        "validity": "valid" if passed else "invalid",
        "blocking_checks": blocking_checks,
        "non_blocking_diagnostics": {
            "continuous_scores": {
                name: numeric[name]
                for name in (
                    "groundedness",
                    "completeness",
                    "citation_quality",
                    "overall",
                )
            },
            "historical_thresholds": historical_thresholds,
        },
    }


def score_judge_output(
    value: dict[str, Any],
    *,
    item: dict[str, Any],
    material: JudgeMaterial,
    evidence_count: int,
    thresholds: dict[str, Any],
) -> ScoreV2:
    """Deriva métricas canônicas: unsupported reduz G, mas não liga hallucination."""
    obligations = material.rubric.get("elementos_obrigatorios")
    if not isinstance(obligations, list) or not obligations:
        raise JudgeV2ContractError("Rubrica protegida sem elementos obrigatórios")
    absence_reference = (
        str(material.protected_absence.get("reference"))
        if material.protected_absence is not None
        else None
    )
    negative = item["question_type"] == "insufficient-evidence"
    _validate_semantics(
        value,
        obligation_count=len(obligations),
        evidence_count=evidence_count,
        negative=negative,
        absence_reference=absence_reference,
    )

    claims = value["claims"]
    supported = sum(claim["verdict"] == "supported" for claim in claims)
    contradicted = sum(claim["verdict"] == "contradicted" for claim in claims)
    completeness = sum(row["satisfied"] for row in value["checklist"]) / len(
        value["checklist"]
    )
    groundedness = supported / len(claims)
    hallucination = contradicted > 0
    negativa_correta = value["negativa_correta"] if negative else None
    numeric = {
        "groundedness": groundedness,
        "completeness": completeness,
        "citation_quality": float(value["citation_quality"]),
        "overall": float(value["overall"]),
    }
    boolean = {
        "hallucination": hallucination,
        "negativa_correta": negativa_correta,
    }
    auxiliary = {
        "target_alignment": value["target_alignment"],
        "hallucination_count": contradicted,
    }
    quality_gate = classify_quality_gate(
        numeric=numeric,
        boolean=boolean,
        auxiliary=auxiliary,
        negative=negative,
        answer_nonempty=True,
        thresholds=thresholds,
    )
    return ScoreV2(
        numeric=numeric,
        boolean=boolean,
        auxiliary=auxiliary,
        claims=claims,
        checklist=value["checklist"],
        rationale=value["rationale"],
        gate=quality_gate,
    )
