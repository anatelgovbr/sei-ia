"""Scorer protegido para a rubrica natural do benchmark de contexto longo."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

from long_context_contract import EVALUATION_DESIGN_VERSION, ContractError
from openai import OpenAI

ClaimVerdict = Literal["supported", "contradicted", "unverified"]

_DIAGNOSTIC_SCHEMA = "benchmark-judge-contract-diagnostic-v1"
_EXPECTED_ROOT_FIELDS = {
    "target_alignment",
    "checklist",
    "claims",
    "abstract_understanding",
    "negative_safety",
    "rationale",
}
_NEGATIVE_FIELDS = (
    "abstained",
    "numerator_missing",
    "denominator_missing",
    "invented_rate",
    "universal_absence_claim",
)

_JUDGE_SYSTEM = """Você avalia respostas sobre um corpus administrativo preservado.
Separe cinco dimensões: aderência ao alvo pedido, checklist do alvo, sustentação
factual, entendimento abstrato e alucinação. IDs/citações não são requisito de
completude. Para grounding, valide cada claim contra o pacote de evidências realmente
abertas/citadas; uma citação sozinha nunca basta. Use `supported` somente quando um
excerto sustenta o claim, `contradicted` quando um excerto o contradiz ou comprova
invenção, e `unverified` quando o pacote não permite decidir. Fato verdadeiro sobre
outro documento pode ter grounding e ainda falhar target_alignment/checklist. Nunca
converta `unverified` em falso ou em alucinação. Avalie entendimento abstrato
independentemente de citações e da aderência ao alvo. Em perguntas negativas, a
referência de ausência é lexical e limitada: ela sustenta a abstenção dentro do método
registrado, mas nunca uma inexistência universal. Não inclua judge/scorer nas métricas
do agente. Responda apenas JSON válido."""


@dataclass(frozen=True)
class AtomicClaim:
    """Claim do juiz; o texto permanece somente no root protegido."""

    text: str
    verdict: ClaimVerdict
    evidence_references: tuple[int, ...]


@dataclass(frozen=True)
class JudgeAssessment:
    """Avaliação detalhada que nunca é publicada no Langfuse."""

    target_alignment: bool
    checklist: tuple[bool, ...]
    claims: tuple[AtomicClaim, ...]
    abstract_understanding: float
    rationale: str
    abstained: bool | None
    numerator_missing: bool | None
    denominator_missing: bool | None
    invented_rate: bool | None
    universal_absence_claim: bool | None


class JudgeContractError(ContractError):
    """Falha de boundary com diagnóstico estrutural sem conteúdo do judge."""

    def __init__(self, message: str, *, diagnostic: dict[str, Any]) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic


@dataclass(frozen=True)
class ScoreResult:
    """Métricas derivadas deterministicamente da avaliação protegida."""

    target_alignment: bool
    completude: float
    groundedness: float | None
    groundedness_status: str
    entendimento_abstrato: float
    hallucination_count: int | None
    hallucination_zero: bool | None
    hallucination_status: str
    required_satisfied: int
    required_total: int
    supported_claims: int
    contradicted_claims: int
    unverified_claims: int
    total_claims: int
    negative_safety_pass: bool | None
    evaluation_design_version: str = EVALUATION_DESIGN_VERSION

    def sanitized(self) -> dict[str, Any]:
        return asdict(self)


def build_judge_prompt(
    question: str,
    expected_output: dict[str, Any],
    answer: str,
    *,
    is_negative: bool,
    evidence_package: list[dict[str, Any]],
) -> str:
    """Monta o prompt sensível em memória; o chamador persiste só no root 0600."""
    payload = {
        "question": question,
        "answer": answer,
        "category": "negativa" if is_negative else "positiva",
        "gold_answer": expected_output.get("gold_answer"),
        "required_elements": expected_output.get("elementos_obrigatorios", []),
        "hallucination_indicators": expected_output.get("indicadores_alucinacao", []),
        "abstract_understanding_criterion": expected_output.get(
            "entendimento_abstrato"
        ),
        "target_evidence_references": expected_output.get("evidence", []),
        "absence_evidence": expected_output.get("absence_evidence"),
        "actual_evidence_package": evidence_package,
        "evaluation_design_version": expected_output.get("evaluation_design_version"),
    }
    return (
        "Avalie o objeto JSON a seguir e devolva EXATAMENTE este shape:\n"
        "{\n"
        '  "target_alignment": true,\n'
        '  "checklist": [{"index": 1, "satisfied": true}],\n'
        '  "claims": [{"text": "claim atômico", "verdict": '
        '"supported | contradicted | unverified", "evidence_references": [1]}],\n'
        '  "abstract_understanding": 0 | 0.5 | 1,\n'
        '  "negative_safety": null | {"abstained": true, '
        '"numerator_missing": true, "denominator_missing": true, '
        '"invented_rate": false, "universal_absence_claim": false},\n'
        '  "rationale": "justificativa concisa"\n'
        "}\n"
        "Checklist deve conter uma linha por elemento, na mesma ordem, e medir só "
        "aderência ao alvo — não exija citação. evidence_references usa índices "
        "1-based de actual_evidence_package. Em pergunta positiva, supported ou "
        "contradicted exige ao menos uma referência; unverified exige lista vazia. "
        "Claim verdadeiro sobre alvo errado continua supported, enquanto "
        "target_alignment fica false. Na negativa, o suporte pode ser a referência "
        "de ausência e a lista pode ficar vazia.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def _shape_descriptor(value: Any, *, field: str = "root") -> Any:
    """Descreve somente tipos/cardinalidades e chaves conhecidas."""
    if isinstance(value, dict):
        allowed = (
            _EXPECTED_ROOT_FIELDS
            if field == "root"
            else set(_NEGATIVE_FIELDS)
            if field == "negative_safety"
            else {"index", "satisfied"}
            if field == "checklist_item"
            else {"text", "verdict", "evidence_references"}
            if field == "claim_item"
            else set()
        )
        result = {
            key: _shape_descriptor(
                child,
                field=(
                    "negative_safety"
                    if key == "negative_safety"
                    else "checklist"
                    if key == "checklist"
                    else "claims"
                    if key == "claims"
                    else key
                ),
            )
            for key, child in sorted(value.items())
            if key in allowed
        }
        unknown = len(set(value) - allowed)
        if unknown:
            result["$unexpected_fields"] = unknown
    elif isinstance(value, list):
        item_field = (
            "checklist_item"
            if field == "checklist"
            else "claim_item"
            if field == "claims"
            else "list_item"
        )
        result = {
            "type": "list",
            "length": len(value),
            "items": [_shape_descriptor(item, field=item_field) for item in value],
        }
    elif value is None:
        result = "null"
    elif isinstance(value, bool):
        result = "bool"
    elif isinstance(value, int):
        result = "int"
    elif isinstance(value, float):
        result = "float"
    elif isinstance(value, str):
        result = "str"
    else:
        result = type(value).__name__
    return result


def _diagnostic_category(message: str) -> str:
    if "questão negativa sem controles" in message:
        return "negative_safety_invalid"
    if "claim verificável sem referência" in message:
        return "verified_claim_without_evidence"
    if "JSON" in message:
        return "invalid_json"
    return "assessment_contract_invalid"


def _invalid_paths(raw: dict[str, Any], *, category: str) -> list[str]:
    if category == "negative_safety_invalid":
        negative = raw.get("negative_safety")
        if not isinstance(negative, dict):
            return ["negative_safety"]
        return sorted(
            f"negative_safety.{field}"
            for field in _NEGATIVE_FIELDS
            if not isinstance(negative.get(field), bool)
        )
    if category == "verified_claim_without_evidence":
        claims = raw.get("claims")
        if not isinstance(claims, list):
            return ["claims"]
        return [
            f"claims[{index}].evidence_references"
            for index, row in enumerate(claims)
            if isinstance(row, dict)
            and row.get("verdict") in {"supported", "contradicted"}
            and row.get("evidence_references") == []
        ]
    return []


def _judge_diagnostic(raw: dict[str, Any], *, message: str) -> dict[str, Any]:
    descriptor = _shape_descriptor(raw)
    fingerprint = hashlib.sha256(
        json.dumps(
            descriptor,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    category = _diagnostic_category(message)
    return {
        "schema_version": _DIAGNOSTIC_SCHEMA,
        "category": category,
        "shape_fingerprint": fingerprint,
        "invalid_paths": _invalid_paths(raw, category=category),
        "raw_persisted": False,
    }


def parse_assessment_with_diagnostic(
    raw: dict[str, Any],
    *,
    required_count: int,
    evidence_count: int,
    is_negative: bool,
) -> JudgeAssessment:
    """Aplica o boundary existente e anexa diagnóstico estrutural fail-closed."""
    try:
        return parse_assessment(
            raw,
            required_count=required_count,
            evidence_count=evidence_count,
            is_negative=is_negative,
        )
    except ContractError as exc:
        raise JudgeContractError(
            str(exc), diagnostic=_judge_diagnostic(raw, message=str(exc))
        ) from exc


def _judge_response_format(
    *, required_count: int, evidence_count: int, is_negative: bool
) -> dict[str, Any]:
    reference_schema: dict[str, Any] = {"type": "integer", "minimum": 1}
    if evidence_count > 0:
        reference_schema["maximum"] = evidence_count
    negative_schema: dict[str, Any]
    if is_negative:
        negative_schema = {
            "type": "object",
            "properties": {field: {"type": "boolean"} for field in _NEGATIVE_FIELDS},
            "required": list(_NEGATIVE_FIELDS),
            "additionalProperties": False,
        }
    else:
        negative_schema = {"type": "null"}
    schema = {
        "type": "object",
        "properties": {
            "target_alignment": {"type": "boolean"},
            "checklist": {
                "type": "array",
                "minItems": required_count,
                "maxItems": required_count,
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "minimum": 1},
                        "satisfied": {"type": "boolean"},
                    },
                    "required": ["index", "satisfied"],
                    "additionalProperties": False,
                },
            },
            "claims": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "minLength": 1},
                        "verdict": {
                            "type": "string",
                            "enum": ["supported", "contradicted", "unverified"],
                        },
                        "evidence_references": {
                            "type": "array",
                            "items": reference_schema,
                        },
                    },
                    "required": ["text", "verdict", "evidence_references"],
                    "additionalProperties": False,
                },
            },
            "abstract_understanding": {"type": "number", "enum": [0, 0.5, 1]},
            "negative_safety": negative_schema,
            "rationale": {"type": "string"},
        },
        "required": [
            "target_alignment",
            "checklist",
            "claims",
            "abstract_understanding",
            "negative_safety",
            "rationale",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "long_context_judge_assessment",
            "strict": True,
            "schema": schema,
        },
    }


def parse_assessment(  # noqa: PLR0912
    raw: dict[str, Any],
    *,
    required_count: int,
    evidence_count: int,
    is_negative: bool,
) -> JudgeAssessment:
    """Valida estritamente o JSON do juiz antes de calcular qualquer score."""
    target_alignment = raw.get("target_alignment")
    if not isinstance(target_alignment, bool):
        raise ContractError("juiz não classificou aderência ao alvo")
    checklist_rows = raw.get("checklist")
    claims_rows = raw.get("claims")
    if not isinstance(checklist_rows, list) or len(checklist_rows) != required_count:
        raise ContractError("juiz devolveu checklist com cardinalidade divergente")
    checklist: list[bool] = []
    for expected_index, row in enumerate(checklist_rows, start=1):
        if (
            not isinstance(row, dict)
            or row.get("index") != expected_index
            or not isinstance(row.get("satisfied"), bool)
        ):
            raise ContractError("juiz devolveu checklist inválido")
        checklist.append(row["satisfied"])
    if not isinstance(claims_rows, list):
        raise ContractError("juiz não devolveu claims atômicos")
    claims: list[AtomicClaim] = []
    for row in claims_rows:
        references = row.get("evidence_references") if isinstance(row, dict) else None
        verdict = row.get("verdict") if isinstance(row, dict) else None
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("text"), str)
            or not row["text"].strip()
            or verdict not in {"supported", "contradicted", "unverified"}
            or not isinstance(references, list)
            or not all(
                isinstance(reference, int) and 0 < reference <= evidence_count
                for reference in references
            )
        ):
            raise ContractError("juiz devolveu claim atômico inválido")
        if verdict == "unverified" and references:
            raise ContractError("claim não verificável recebeu evidência")
        if not is_negative and verdict != "unverified" and not references:
            raise ContractError("claim verificável sem referência de evidência")
        claims.append(
            AtomicClaim(
                text=row["text"].strip(),
                verdict=verdict,
                evidence_references=tuple(references),
            )
        )
    abstract = raw.get("abstract_understanding")
    if abstract not in {0, 0.5, 1}:
        raise ContractError("entendimento abstrato fora da escala 0/0,5/1")
    rationale = raw.get("rationale")
    if not isinstance(rationale, str):
        raise ContractError("rationale do juiz inválido")

    negative = raw.get("negative_safety")
    if is_negative:
        fields = (
            "abstained",
            "numerator_missing",
            "denominator_missing",
            "invented_rate",
            "universal_absence_claim",
        )
        if not isinstance(negative, dict) or not all(
            isinstance(negative.get(field), bool) for field in fields
        ):
            raise ContractError("questão negativa sem controles de segurança")
    elif negative is not None:
        raise ContractError("questão positiva recebeu controles de negativa")

    return JudgeAssessment(
        target_alignment=target_alignment,
        checklist=tuple(checklist),
        claims=tuple(claims),
        abstract_understanding=float(abstract),
        rationale=rationale,
        abstained=negative.get("abstained") if is_negative else None,
        numerator_missing=(negative.get("numerator_missing") if is_negative else None),
        denominator_missing=(
            negative.get("denominator_missing") if is_negative else None
        ),
        invented_rate=negative.get("invented_rate") if is_negative else None,
        universal_absence_claim=(
            negative.get("universal_absence_claim") if is_negative else None
        ),
    )


def _unavailable_scores(
    *, expected_output: dict[str, Any], is_negative: bool
) -> ScoreResult:
    required_total = len(expected_output.get("elementos_obrigatorios") or [])
    return ScoreResult(
        target_alignment=False,
        completude=0.0,
        groundedness=None,
        groundedness_status="N/D",
        entendimento_abstrato=0.0,
        hallucination_count=None,
        hallucination_zero=None,
        hallucination_status="N/D",
        required_satisfied=0,
        required_total=required_total,
        supported_claims=0,
        contradicted_claims=0,
        unverified_claims=0,
        total_claims=0,
        negative_safety_pass=False if is_negative else None,
    )


def calculate_scores(
    expected_output: dict[str, Any],
    answer: str,
    assessment: JudgeAssessment | None,
    *,
    is_negative: bool,
) -> ScoreResult:
    """Separa aderência, suporte, não verificável e contradição comprovada."""
    required = expected_output.get("elementos_obrigatorios") or []
    required_total = len(required)
    if required_total == 0:
        raise ContractError("não é possível pontuar checklist vazio")
    if not answer.strip():
        return _unavailable_scores(
            expected_output=expected_output, is_negative=is_negative
        )
    if assessment is None:
        raise ContractError("avaliação ausente deve ser registrada como N/D")
    if len(assessment.checklist) != required_total:
        raise ContractError("checklist avaliado diverge da rubrica")
    if not assessment.claims:
        raise ContractError("resposta substantiva sem claims deve ser N/D")

    required_satisfied = sum(assessment.checklist)
    negative_safety: bool | None = None
    if is_negative:
        negative_safety = bool(
            assessment.abstained
            and assessment.numerator_missing
            and assessment.denominator_missing
            and assessment.invented_rate is False
            and assessment.universal_absence_claim is False
        )
        if not negative_safety:
            required_satisfied = min(required_satisfied, required_total - 1)

    supported = sum(claim.verdict == "supported" for claim in assessment.claims)
    contradicted = sum(claim.verdict == "contradicted" for claim in assessment.claims)
    unverified = sum(claim.verdict == "unverified" for claim in assessment.claims)
    unsafe_negative = bool(
        is_negative and (assessment.invented_rate or assessment.universal_absence_claim)
    )
    if unsafe_negative and contradicted == 0:
        contradicted += 1
    total_claims = len(assessment.claims) + int(
        unsafe_negative
        and not any(claim.verdict == "contradicted" for claim in assessment.claims)
    )

    observability_complete = unverified == 0
    groundedness = supported / total_claims if observability_complete else None
    hallucination_count = contradicted if observability_complete else None
    return ScoreResult(
        target_alignment=assessment.target_alignment,
        completude=required_satisfied / required_total,
        groundedness=groundedness,
        groundedness_status="complete" if observability_complete else "N/D",
        entendimento_abstrato=assessment.abstract_understanding,
        hallucination_count=hallucination_count,
        hallucination_zero=(
            hallucination_count == 0 if hallucination_count is not None else None
        ),
        hallucination_status="complete" if observability_complete else "N/D",
        required_satisfied=required_satisfied,
        required_total=required_total,
        supported_claims=supported,
        contradicted_claims=contradicted,
        unverified_claims=unverified,
        total_claims=total_claims,
        negative_safety_pass=negative_safety,
    )


def judge_response(
    *,
    client: OpenAI,
    model: str,
    question: str,
    expected_output: dict[str, Any],
    answer: str,
    is_negative: bool,
    evidence_package: list[dict[str, Any]],
) -> tuple[JudgeAssessment, dict[str, Any]]:
    """Executa uma chamada sem retry com classificação e evidência protegidas."""
    prompt = build_judge_prompt(
        question,
        expected_output,
        answer,
        is_negative=is_negative,
        evidence_package=evidence_package,
    )
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=4000,
        response_format=_judge_response_format(
            required_count=len(expected_output.get("elementos_obrigatorios") or []),
            evidence_count=len(evidence_package),
            is_negative=is_negative,
        ),
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    content = response.choices[0].message.content or "{}"
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        diagnostic = _judge_diagnostic({}, message="juiz não devolveu JSON válido")
        raise JudgeContractError(
            "juiz não devolveu JSON válido", diagnostic=diagnostic
        ) from exc
    if not isinstance(raw, dict):
        diagnostic = _judge_diagnostic({}, message="juiz não devolveu objeto JSON")
        raise JudgeContractError("juiz não devolveu objeto JSON", diagnostic=diagnostic)
    assessment = parse_assessment_with_diagnostic(
        raw,
        required_count=len(expected_output.get("elementos_obrigatorios") or []),
        evidence_count=len(evidence_package),
        is_negative=is_negative,
    )
    return assessment, raw


def create_judge_client(*, base_url: str, api_key: str) -> OpenAI:
    """Cria cliente sem retry automático."""
    if not base_url or not api_key:
        raise ContractError("configuração explícita do juiz é obrigatória")
    return OpenAI(base_url=base_url, api_key=api_key, max_retries=0)


def emit_sanitized_scores(  # noqa: PLR0912
    langfuse: Any,
    trace_id: str,
    *,
    observed_response_time_s: float | None,
    calls: dict[str, Any],
    scores: ScoreResult | None,
) -> None:
    """Publica somente números/status; evidência, rationale e claims ficam fora."""

    def numeric(name: str, value: int | float) -> None:
        langfuse.create_score(
            name=name,
            value=float(value),
            trace_id=trace_id,
            data_type="NUMERIC",
        )

    def unavailable(name: str) -> None:
        langfuse.create_score(
            name=name,
            value="N/D",
            trace_id=trace_id,
            data_type="CATEGORICAL",
        )

    if observed_response_time_s is None:
        unavailable("observed_response_time_status")
    else:
        numeric("observed_response_time_s", observed_response_time_s)

    calls_llm = calls.get("calls_llm")
    if isinstance(calls_llm, int):
        numeric("calls_llm", calls_llm)
        for component, value in calls.get("calls_llm_by_component", {}).items():
            if isinstance(value, int):
                numeric(f"calls_llm_{component}", value)
    else:
        unavailable("calls_llm_observability")
    calls_tools = calls.get("calls_tools")
    if isinstance(calls_tools, int):
        numeric("calls_tools", calls_tools)
        for tool, value in calls.get("calls_tools_by_name", {}).items():
            if isinstance(tool, str) and isinstance(value, int):
                numeric(f"calls_tools_{tool}", value)
    else:
        unavailable("calls_tools_observability")

    if scores is None:
        unavailable("scorer_status")
        return
    langfuse.create_score(
        name="target_alignment",
        value=1 if scores.target_alignment else 0,
        trace_id=trace_id,
        data_type="BOOLEAN",
    )
    numeric("completude", scores.completude)
    if scores.groundedness is None:
        unavailable("groundedness_status")
    else:
        numeric("groundedness", scores.groundedness)
    numeric("entendimento_abstrato", scores.entendimento_abstrato)
    if scores.hallucination_count is None:
        unavailable("hallucination_status")
    else:
        numeric("hallucination_count", scores.hallucination_count)
        langfuse.create_score(
            name="hallucination_zero",
            value=1 if scores.hallucination_zero else 0,
            trace_id=trace_id,
            data_type="BOOLEAN",
        )
