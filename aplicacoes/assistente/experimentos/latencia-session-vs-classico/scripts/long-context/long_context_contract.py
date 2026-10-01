"""Contratos puros do benchmark auditável de context disclosure."""

from __future__ import annotations

import codecs
import copy
import hashlib
import json
import secrets
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, BinaryIO

DATASET_NAME = "benchmark-long-context"
DATASET_ID = "cmrwgt0dr008nrv07dg0y73im"
TARGET_PROJECT = "comparativo-deepagents-classico"
SESSION_ENDPOINT = "/llm_lang/session_stream"
PREFLIGHT_ENDPOINT = "/llm_lang/session_benchmark_preflight"
CONTEXT_DISCLOSURE_THRESHOLD = 200000
EVALUATION_DESIGN_VERSION = "benchmark-long-context-evidence-v3-20260723"
RUNTIME_EVIDENCE_DESIGN_VERSION = (
    "benchmark-long-context-evidence-v4-ocr-fresh-20260724"
)
EXPECTED_ITEM_CASES = {
    "case-0960k-q1-factual": "case-0960k",
    "case-0960k-q2-synthesis": "case-0960k",
    "case-0960k-q3-insufficient-evidence": "case-0960k",
    "case-5120k-q1-factual": "case-5120k",
    "case-5120k-q2-synthesis": "case-5120k",
    "case-5120k-q3-insufficient-evidence": "case-5120k",
    "case-6260k-q1-factual": "case-6260k",
    "case-6260k-q2-synthesis": "case-6260k",
    "case-6260k-q3-insufficient-evidence": "case-6260k",
}
EXPECTED_ITEM_IDS = frozenset(EXPECTED_ITEM_CASES)
EXPECTED_TARGET_ANCHOR_KINDS = {
    "case-0960k-q1-factual": "unique_regulatory_obligation",
    "case-0960k-q2-synthesis": "official_document_pair",
    "case-0960k-q3-insufficient-evidence": "corpus_wide_period_scope",
    "case-5120k-q1-factual": "named_regulatory_initiative",
    "case-5120k-q2-synthesis": "named_participation_sequence",
    "case-5120k-q3-insufficient-evidence": "numbered_consultation_scope",
    "case-6260k-q1-factual": "numbered_inspection_scope",
    "case-6260k-q2-synthesis": "origin_request_final_report_pair",
    "case-6260k-q3-insufficient-evidence": "whole_requested_document_universe",
}
EXPECTED_ITEM_TYPES = {
    "case-0960k-q1-factual": ("factual", "factual"),
    "case-0960k-q2-synthesis": ("synthesis", "cross-document"),
    "case-0960k-q3-insufficient-evidence": ("insufficient-evidence", "negativa"),
    "case-5120k-q1-factual": ("factual", "factual"),
    "case-5120k-q2-synthesis": ("synthesis", "cross-document"),
    "case-5120k-q3-insufficient-evidence": ("insufficient-evidence", "negativa"),
    "case-6260k-q1-factual": ("factual", "factual"),
    "case-6260k-q2-synthesis": ("synthesis", "cross-document"),
    "case-6260k-q3-insufficient-evidence": ("insufficient-evidence", "negativa"),
}
# SHA-256 UTF-8 confirmados pelo readback protegido da versão natural aprovada.
EXPECTED_NATURAL_TEXT_HASHES = {
    "case-0960k-q1-factual": {
        "question": "4419405b009f8b4697a10dfd4cb5878e763ffad8a5f36ba9746ae594e3bbf988",
        "gold": "39a09c56bc099551be232e02f14ae68d3a3c2d83a27ab103df8f9dde7ce83fbb",
    },
    "case-0960k-q2-synthesis": {
        "question": "df01c3aed7a08e962c2473af90df67796cf6b6ea16b5fcfb65a0a1f0c8a59f7f",
        "gold": "3af21ac3bba2bb5cd90a2e9c1572e7fb5ff4474a74f08f67489b7bd21265b745",
    },
    "case-0960k-q3-insufficient-evidence": {
        "question": "f22de7c67bf944041ed1bc5154c264330c6e7899882904afdd6dd77c067344d7",
        "gold": "88195119935db89cf2ad8ee3f17483a83e7f50fccc46a819c11d6e8d58c96836",
    },
    "case-5120k-q1-factual": {
        "question": "4fa2e2d9c3b422dd7eb64c7a5330fd31cb88e24a128899560a72011c9535bc34",
        "gold": "d58d542091e716b0071c47face1f40a495c35fd6755afb90eac3380994649568",
    },
    "case-5120k-q2-synthesis": {
        "question": "154d5ec4f0a20a12cedd5293348feb2f4ee04e24eff51a4d7d3c6bc9f4fb7c3f",
        "gold": "7152fec141eb06f93e8816ef15a1d4b3f0e9c6019ef0ecf4c3e1d3ebc32a311e",
    },
    "case-5120k-q3-insufficient-evidence": {
        "question": "9425032450ea64a431a1a16507f69b2685917b3a66882814e9dfe36f8ec98e4e",
        "gold": "71b697d53d8d3564d599d08bb48145757719a8a1430fe4605ff554f4a1c6a3a0",
    },
    "case-6260k-q1-factual": {
        "question": "17d03926e1ef6eab822b21109c4316fd42680b759130827b5fe359c573704f81",
        "gold": "7808e3b735fea80f160555dd81e284a08be78824d809f195583dda4594ca0f01",
    },
    "case-6260k-q2-synthesis": {
        "question": "a4ec45e268d5507f28a500b5e9e0f8b1fc10ecd1cbd92a40fd0986aa487a48a4",
        "gold": "cccee4f32faa9f075bfea0436895945d11735f74208ff17671bf42078e70aef2",
    },
    "case-6260k-q3-insufficient-evidence": {
        "question": "49d98d4ebbc03c724249d53e20762c22168bae10638971517c86804e116dd00e",
        "gold": "c462821edc4bda0c03b0d82a0b0a2814187af87ae4675ac5eadc5eb67cadf21a",
    },
}
EXPECTED_PAYLOAD_HASHES = {
    "case-0960k": "ee60917ba35f6aff06e313a7460f22b997e25f67c93b3a96d5821243a0ad2aa8",
    "case-5120k": "7cb1ba5480b317ba52d4fedfccf19f175c06713c6eb8b2450f4c3aa04b163bb4",
    "case-6260k": "47f25dcc091a4f3bc1be9f8d82b6320b82048ce50eec05269cd945545af2dfb5",
}
EXPECTED_CASE_METRICS = {
    "case-0960k": {"documents": 59, "tokens": 960682},
    "case-5120k": {"documents": 331, "tokens": 5120866},
    "case-6260k": {"documents": 61, "tokens": 6260548},
}
_COMPONENTS = ("main", "subagent", "classifier", "planner", "summarizer", "unknown")


class ContractError(RuntimeError):
    """Falha fechada de identidade/configuração do benchmark."""


class SSEProtocolError(RuntimeError):
    """Stream SSE inválido ou sem frame terminal."""


@dataclass(frozen=True)
class ExecutionPolicy:
    """Política imutável da rodada futura."""

    endpoint: str = SESSION_ENDPOINT
    transport: str = "http"
    n: int = 1
    max_concurrency: int = 1
    retries: int = 0
    warmups: int = 0
    use_websearch: bool = False
    classic_enabled: bool = False
    rate_card_enabled: bool = False
    threshold_override_enabled: bool = False


@dataclass(frozen=True)
class SSEOutcome:
    """Resultado do consumo até o primeiro terminal ``end`` ou ``error``."""

    terminal_type: str
    observed_response_time_s: float
    content: str
    metadata: dict[str, Any] | None
    status_frames: int
    preparation_heartbeat_frames: int
    reasoning_frames: int
    content_frames: int
    terminal_status_code: int | None
    terminal_detail: str | None


class TopicFactory:
    """Gera tópicos inteiros novos e não repetidos no processo do runner."""

    def __init__(self) -> None:
        self._issued: set[int] = set()

    def new(self) -> int:
        while True:
            topic = 100_000_000_000 + secrets.randbelow(900_000_000_000)
            if topic not in self._issued:
                self._issued.add(topic)
                return topic


def stable_digest(value: Any) -> str:
    """SHA-256 de JSON canônico UTF-8."""
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def text_digest(value: str) -> str:
    """SHA-256 do texto UTF-8, compatível com o readback natural aprovado."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def plain(value: Any) -> Any:
    """Converte modelos do SDK para valores JSON."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return value


def project_id_from_response(payload: Any) -> str:
    """Exige exatamente uma ocorrência do projeto autorizado."""
    projects = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(projects, list):
        raise ContractError("resposta de projetos não contém uma lista")
    matches = [
        project
        for project in projects
        if isinstance(project, dict) and project.get("name") == TARGET_PROJECT
    ]
    if len(matches) != 1:
        raise ContractError("projeto autorizado não foi retornado exatamente uma vez")
    project_id = matches[0].get("id") or matches[0].get("project_id")
    if not project_id:
        raise ContractError("projeto autorizado sem ID")
    return str(project_id)


def _item_value(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _validate_document_tree(
    item_id: str, item_input: dict[str, Any], metadata: dict[str, Any]
) -> None:
    procedures = item_input.get("id_procedimentos")
    if not isinstance(procedures, list) or not procedures:
        raise ContractError(f"{item_id}: árvore de procedimentos ausente")
    document_count = 0
    for procedure in procedures:
        if not isinstance(procedure, dict) or not procedure.get("id_procedimento"):
            raise ContractError(f"{item_id}: procedimento inválido")
        documents = procedure.get("id_documentos")
        if not isinstance(documents, list):
            raise ContractError(f"{item_id}: lista de documentos inválida")
        for document in documents:
            if not isinstance(document, dict) or not document.get("id_documento"):
                raise ContractError(f"{item_id}: documento inválido")
            if not isinstance(document.get("download_ext"), bool):
                raise ContractError(f"{item_id}: download_ext não canônico")
        document_count += len(documents)
    if document_count != metadata.get("document_count"):
        raise ContractError(f"{item_id}: cardinalidade documental divergente")
    if len(procedures) != metadata.get("procedure_count"):
        raise ContractError(f"{item_id}: cardinalidade de procedimentos divergente")


def _validate_dataset_header(dataset: Any, project_id: str) -> list[Any]:
    if _item_value(dataset, "name") != DATASET_NAME:
        raise ContractError("nome de dataset divergente")
    if str(_item_value(dataset, "id")) != DATASET_ID:
        raise ContractError("ID de dataset divergente")
    if str(_item_value(dataset, "project_id")) != str(project_id):
        raise ContractError("dataset pertence a outro projeto")
    items = list(_item_value(dataset, "items") or [])
    if len(items) != 9:
        raise ContractError("dataset deve conter exatamente nove itens")
    ids = [str(_item_value(item, "id")) for item in items]
    if len(set(ids)) != 9 or set(ids) != EXPECTED_ITEM_IDS:
        raise ContractError("identidade ou unicidade dos nove itens divergiu")
    return items


def _validated_item_parts(
    item: Any,
) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    item_id = str(_item_value(item, "id"))
    item_input = plain(_item_value(item, "input"))
    expected = plain(_item_value(item, "expected_output"))
    metadata = plain(_item_value(item, "metadata"))
    if not isinstance(item_input, dict) or not isinstance(expected, dict):
        raise ContractError(f"{item_id}: input/expected_output inválido")
    if not isinstance(metadata, dict):
        raise ContractError(f"{item_id}: metadata inválida")
    return item_id, item_input, expected, metadata


def _validate_natural_identity(  # noqa: PLR0912
    item_id: str,
    item_input: dict[str, Any],
    expected: dict[str, Any],
    metadata: dict[str, Any],
) -> bool:
    expected_case_id = EXPECTED_ITEM_CASES.get(item_id)
    if expected_case_id is None or metadata.get("case_id") != expected_case_id:
        raise ContractError(f"{item_id}: caso associado divergente")
    expected_types = EXPECTED_ITEM_TYPES.get(item_id)
    if expected_types is None:
        raise ContractError(f"{item_id}: tipo aprovado ausente")
    expected_question_type, expected_category = expected_types
    if metadata.get("question_type") != expected_question_type:
        raise ContractError(f"{item_id}: question_type divergente")
    if expected.get("categoria") != expected_category:
        raise ContractError(f"{item_id}: categoria divergente")

    question = item_input.get("text")
    gold = expected.get("gold_answer")
    if not isinstance(question, str) or not question.strip():
        raise ContractError(f"{item_id}: pergunta vazia")
    if not isinstance(gold, str) or not gold.strip():
        raise ContractError(f"{item_id}: gold vazio")
    approved_hashes = EXPECTED_NATURAL_TEXT_HASHES.get(item_id)
    if approved_hashes is None:
        raise ContractError(f"{item_id}: hashes naturais aprovados ausentes")
    if text_digest(question) != approved_hashes["question"]:
        raise ContractError(f"{item_id}: pergunta natural aprovada divergente")
    if text_digest(gold) != approved_hashes["gold"]:
        raise ContractError(f"{item_id}: gold natural aprovado divergente")
    redundant_hashes = {
        "canonical_question_sha256": approved_hashes["question"],
        "canonical_gold_answer_sha256": approved_hashes["gold"],
    }
    for key, approved_hash in redundant_hashes.items():
        metadata_hash = metadata.get(key)
        if metadata_hash is not None and metadata_hash != approved_hash:
            raise ContractError(f"{item_id}: {key} redundante divergente")
    anchor = metadata.get("target_anchor")
    expected_anchor = EXPECTED_TARGET_ANCHOR_KINDS.get(item_id)
    if not isinstance(anchor, dict) or anchor.get("kind") != expected_anchor:
        raise ContractError(f"{item_id}: âncora do alvo divergente")
    references = anchor.get("reference_sha256")
    expected_count = 2 if item_id == "case-0960k-q2-synthesis" else 0
    if (
        anchor.get("reference_count") != expected_count
        or not isinstance(references, list)
        or len(references) != expected_count
        or not all(
            isinstance(reference, str)
            and len(reference) == 64
            and set(reference) <= set("0123456789abcdef")
            for reference in references
        )
    ):
        raise ContractError(f"{item_id}: referências da âncora divergentes")
    return expected_category == "negativa"


def _validate_evaluation_contract(
    item_id: str,
    item_input: dict[str, Any],
    expected: dict[str, Any],
    metadata: dict[str, Any],
) -> bool:
    is_negative = _validate_natural_identity(item_id, item_input, expected, metadata)
    required = expected.get("elementos_obrigatorios")
    if not isinstance(required, list) or not required:
        raise ContractError(f"{item_id}: checklist vazio")
    if not isinstance(expected.get("indicadores_alucinacao"), list):
        raise ContractError(f"{item_id}: indicadores de alucinação inválidos")
    if not isinstance(expected.get("entendimento_abstrato"), str):
        raise ContractError(f"{item_id}: critério abstrato ausente")
    scoring = expected.get("scoring")
    if not isinstance(scoring, dict) or scoring.get("target_alignment") != "boolean":
        raise ContractError(f"{item_id}: target_alignment ausente")
    if scoring.get("groundedness") != "supported_over_verified_claims":
        raise ContractError(f"{item_id}: groundedness divergente")
    if scoring.get("unverified_claim") != "metric_nd":
        raise ContractError(f"{item_id}: claim não verificável sem N/D")
    if scoring.get("hallucination_count") != "contradicted_or_invented_claims":
        raise ContractError(f"{item_id}: hallucination divergente")
    versions = {
        expected.get("evaluation_design_version"),
        metadata.get("evaluation_design_version"),
    }
    if versions != {EVALUATION_DESIGN_VERSION}:
        raise ContractError(f"{item_id}: versão da avaliação divergente")
    return is_negative


def _validate_execution_contract(
    item_id: str, item_input: dict[str, Any], metadata: dict[str, Any]
) -> None:
    if metadata.get("n") != 1:
        raise ContractError(f"{item_id}: N deve ser 1")
    if metadata.get("context_disclosure_threshold") != CONTEXT_DISCLOSURE_THRESHOLD:
        raise ContractError(f"{item_id}: threshold divergente")
    if "inject_tokens_threshold" in item_input:
        raise ContractError(f"{item_id}: payload não pode conter override de threshold")
    if item_input.get("use_websearch") is not False:
        raise ContractError(f"{item_id}: websearch deve estar desligada")


def _validated_payload_identity(
    item_id: str, item_input: dict[str, Any], metadata: dict[str, Any]
) -> tuple[str, str]:
    case_id = str(metadata.get("case_id"))
    expected_hash = EXPECTED_PAYLOAD_HASHES.get(case_id)
    expected_metrics = EXPECTED_CASE_METRICS.get(case_id)
    actual_hash = stable_digest(
        {"id_procedimentos": item_input.get("id_procedimentos")}
    )
    if (
        expected_hash is None
        or expected_metrics is None
        or actual_hash != expected_hash
    ):
        raise ContractError(f"{item_id}: payload canônico divergente")
    if metadata.get("document_count") != expected_metrics["documents"]:
        raise ContractError(f"{item_id}: documentos medidos divergentes")
    if metadata.get("independent_document_tokens") != expected_metrics["tokens"]:
        raise ContractError(f"{item_id}: tokens medidos divergentes")
    if metadata.get("canonical_payload_hash") != expected_hash:
        raise ContractError(f"{item_id}: hash canônico em metadata divergente")
    _validate_document_tree(item_id, item_input, metadata)
    return case_id, actual_hash


def _validate_evidence_contract(
    item_id: str, expected: dict[str, Any], *, is_negative: bool
) -> None:
    if is_negative:
        absence = expected.get("absence_evidence")
        if not isinstance(absence, dict):
            raise ContractError(f"{item_id}: referência negativa ausente")
        if absence.get("limitation") != "lexical_method_only_not_universal_absence":
            raise ContractError(f"{item_id}: referência negativa sem limitação lexical")
    elif not expected.get("evidence"):
        raise ContractError(f"{item_id}: evidência positiva ausente")


def validate_dataset(dataset: Any, project_id: str) -> list[Any]:
    """Prova projeto, dataset, nove identidades, payloads e desenho aprovado."""
    items = _validate_dataset_header(dataset, project_id)
    case_counts: Counter[str] = Counter()
    payload_hashes: dict[str, str] = {}
    for item in items:
        item_id, item_input, expected, metadata = _validated_item_parts(item)
        is_negative = _validate_evaluation_contract(
            item_id, item_input, expected, metadata
        )
        _validate_execution_contract(item_id, item_input, metadata)
        case_id, actual_hash = _validated_payload_identity(
            item_id, item_input, metadata
        )
        previous_hash = payload_hashes.setdefault(case_id, actual_hash)
        if previous_hash != actual_hash:
            raise ContractError(f"{item_id}: itens do caso não compartilham payload")
        _validate_evidence_contract(item_id, expected, is_negative=is_negative)
        case_counts[case_id] += 1

    if case_counts != Counter(dict.fromkeys(EXPECTED_PAYLOAD_HASHES, 3)):
        raise ContractError("distribuição de três perguntas por caso divergiu")
    if payload_hashes != EXPECTED_PAYLOAD_HASHES:
        raise ContractError("conjunto final de hashes canônicos divergiu")
    return sorted(items, key=lambda item: str(_item_value(item, "id")))


def build_execution_payload(item_input: Any, topic_id: int) -> dict[str, Any]:
    """Troca o tópico e aplica apenas controles fixos da execução session."""
    source = plain(item_input)
    if not isinstance(source, dict):
        raise ContractError("input do item não é objeto")
    payload = copy.deepcopy(source)
    payload["id_topico"] = topic_id
    payload["no_cache"] = True
    payload["trace"] = True
    payload["skip_memory"] = True
    payload["use_websearch"] = False
    if "inject_tokens_threshold" in payload:
        raise ContractError("override de threshold proibido")
    return payload


def validate_preflight(payload: Any) -> None:
    """Confirma rota, threshold e versão de telemetria do deployment."""
    if not isinstance(payload, dict) or payload.get("status") != "ready":
        raise ContractError("preflight session não está pronto")
    if payload.get("endpoint") != SESSION_ENDPOINT:
        raise ContractError("preflight aponta para endpoint divergente")
    if payload.get("context_disclosure_threshold") != CONTEXT_DISCLOSURE_THRESHOLD:
        raise ContractError("threshold efetivo do deployment diverge de 200000")
    if payload.get("benchmark_no_cache_required") is not True:
        raise ContractError("deployment não exige no_cache no benchmark")
    if (
        payload.get("benchmark_document_source")
        != "sei_no_cache_with_pinned_validation"
    ):
        raise ContractError("deployment não busca documentos fresh no SEI")
    if payload.get("benchmark_process_source") != "sei_no_cache":
        raise ContractError("deployment não busca processos fresh no SEI")
    if payload.get("tool_telemetry_schema") != "benchmark-tool-telemetry-v2":
        raise ContractError("deployment sem telemetria sanitizada v2")
    heartbeat = payload.get("preparation_heartbeat_interval_s")
    if not isinstance(heartbeat, (int, float)) or not 0 < heartbeat < 600:
        raise ContractError("intervalo de heartbeat da preparação é inválido")
    if payload.get("benchmark_evidence_pin_enabled") is not True:
        raise ContractError("deployment sem fonte de evidência pinada")
    if payload.get("benchmark_evidence_design") != RUNTIME_EVIDENCE_DESIGN_VERSION:
        raise ContractError("design da evidência pinada divergiu")


def _iter_sse_payloads(
    chunks: Iterable[bytes | str], raw: BinaryIO | None
) -> Iterable[str]:
    decoder = codecs.getincrementaldecoder("utf-8")()
    buffer = ""
    data_lines: list[str] = []

    def consume_line(line: str) -> str | None:
        nonlocal data_lines
        line = line.removesuffix("\r")
        if not line:
            if not data_lines:
                return None
            payload = "\n".join(data_lines)
            data_lines = []
            return payload
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip(" "))
        return None

    for chunk in chunks:
        raw_bytes = chunk.encode("utf-8") if isinstance(chunk, str) else bytes(chunk)
        if raw is not None:
            raw.write(raw_bytes)
            raw.flush()
        buffer += decoder.decode(raw_bytes)
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if (payload := consume_line(line)) is not None:
                yield payload
    buffer += decoder.decode(b"", final=True)
    if buffer and (payload := consume_line(buffer)) is not None:
        yield payload
    if data_lines:
        yield "\n".join(data_lines)


def consume_sse(
    chunks: Iterable[bytes | str],
    *,
    started_at: float,
    clock: Callable[[], float],
    raw: BinaryIO | None = None,
) -> SSEOutcome:
    """Consome SSE incremental e mede no frame terminal com relógio injetável."""
    content: list[str] = []
    metadata: dict[str, Any] | None = None
    status_frames = preparation_heartbeat_frames = reasoning_frames = content_frames = 0
    for payload in _iter_sse_payloads(chunks, raw):
        try:
            frame = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise SSEProtocolError("frame SSE não contém JSON válido") from exc
        if not isinstance(frame, dict) or not isinstance(frame.get("type"), str):
            raise SSEProtocolError("frame SSE sem tipo")
        frame_type = frame["type"]
        if frame_type == "status":
            status_frames += 1
            if (
                frame.get("stage") == "session_preparation"
                and frame.get("heartbeat") is True
            ):
                preparation_heartbeat_frames += 1
        elif frame_type == "reasoning":
            reasoning_frames += 1
        elif frame_type == "content":
            content_frames += 1
            value = frame.get("data")
            if isinstance(value, str):
                content.append(value)
        elif frame_type == "metadata":
            value = frame.get("data")
            if isinstance(value, dict):
                metadata = value
        if frame_type in {"end", "error"}:
            return SSEOutcome(
                terminal_type=frame_type,
                observed_response_time_s=max(0.0, clock() - started_at),
                content="".join(content),
                metadata=metadata,
                status_frames=status_frames,
                preparation_heartbeat_frames=preparation_heartbeat_frames,
                reasoning_frames=reasoning_frames,
                content_frames=content_frames,
                terminal_status_code=(
                    int(frame["status_code"])
                    if frame_type == "error"
                    and isinstance(frame.get("status_code"), int)
                    else None
                ),
                terminal_detail=(
                    str(frame.get("detail", "")) if frame_type == "error" else None
                ),
            )
    raise SSEProtocolError("stream encerrou sem frame terminal")


def _observation_value(observation: Any, name: str) -> Any:
    return _item_value(observation, name)


def _observation_type(observation: Any) -> str:
    return str(_observation_value(observation, "type") or "").upper()


def _metadata_namespace(observation: Any) -> str:
    metadata = plain(_observation_value(observation, "metadata"))
    if not isinstance(metadata, dict):
        return ""
    return str(
        metadata.get("langgraph_checkpoint_ns") or metadata.get("checkpoint_ns") or ""
    )


def _ancestor_names(observation: Any, by_id: dict[str, Any]) -> list[str]:
    names: list[str] = []
    parent_id = _observation_value(
        observation, "parent_observation_id"
    ) or _observation_value(observation, "parent_id")
    seen: set[str] = set()
    while parent_id and str(parent_id) not in seen and len(names) < 100:
        key = str(parent_id)
        seen.add(key)
        parent = by_id.get(key)
        if parent is None:
            break
        names.append(str(_observation_value(parent, "name") or "").lower())
        parent_id = _observation_value(
            parent, "parent_observation_id"
        ) or _observation_value(parent, "parent_id")
    return names


def _generation_component(observation: Any, by_id: dict[str, Any]) -> str | None:
    names = [str(_observation_value(observation, "name") or "").lower()]
    names.extend(_ancestor_names(observation, by_id))
    joined = " ".join(names)
    namespace = _metadata_namespace(observation)
    if any(marker in joined for marker in ("judge", "scorer", "evaluator")):
        component = None
    elif any(marker in joined for marker in ("summarizer", "summarization", "summary")):
        component = "summarizer"
    elif any(
        marker in joined for marker in ("planner", "plan_speculative", "planning")
    ):
        component = "planner"
    elif any(marker in joined for marker in ("classifier", "classify", "complexity")):
        component = "classifier"
    elif len([part for part in namespace.split("|") if part]) >= 2 or "task" in names:
        component = "subagent"
    elif "session_agent" in names or "model" in names:
        component = "main"
    else:
        component = "unknown"
    return component


def aggregate_agent_calls(
    observations: Iterable[Any] | None, *, stable: bool
) -> dict[str, Any]:
    """Conta gerações observadas; árvore ausente/parcial é ``N/D``."""
    if observations is None or not stable:
        return {
            "observability_status": "N/D",
            "calls_llm": None,
            "calls_llm_by_component": dict.fromkeys(_COMPONENTS),
        }
    observation_list = list(observations)
    by_id = {
        str(_observation_value(observation, "id")): observation
        for observation in observation_list
        if _observation_value(observation, "id")
    }
    breakdown = dict.fromkeys(_COMPONENTS, 0)
    counted = 0
    for observation in observation_list:
        if "GENERATION" not in _observation_type(observation):
            continue
        component = _generation_component(observation, by_id)
        if component is None:
            continue
        breakdown[component] += 1
        counted += 1
    if counted == 0:
        return {
            "observability_status": "N/D",
            "calls_llm": None,
            "calls_llm_by_component": dict.fromkeys(_COMPONENTS),
        }
    return {
        "observability_status": "complete",
        "calls_llm": counted,
        "calls_llm_by_component": breakdown,
    }


def aggregate_tool_calls(summary: Any) -> dict[str, Any]:
    """Separa tools e rejeita ausência/incompletude como ``N/D``."""
    if (
        not isinstance(summary, dict)
        or summary.get("schema_version") != "benchmark-tool-telemetry-v2"
        or summary.get("collector_active") is not True
        or summary.get("observability_status") != "complete"
        or not isinstance(summary.get("total_calls"), int)
        or not isinstance(summary.get("calls_by_name"), dict)
    ):
        return {
            "observability_status": "N/D",
            "calls_tools": None,
            "calls_tools_by_name": None,
            "disclosure": None,
        }
    return {
        "observability_status": "complete",
        "calls_tools": summary["total_calls"],
        "calls_tools_by_name": summary["calls_by_name"],
        "disclosure": summary.get("calls", []),
    }


def combine_call_metrics(llm: dict[str, Any], tools: dict[str, Any]) -> dict[str, Any]:
    """Mantém LLM/tools separados e explicita a fórmula do total."""
    llm_count = llm.get("calls_llm")
    tool_count = tools.get("calls_tools")
    complete = isinstance(llm_count, int) and isinstance(tool_count, int)
    return {
        **llm,
        **tools,
        "calls_total": llm_count + tool_count if complete else None,
        "calls_total_formula": "calls_llm + calls_tools" if complete else "N/D",
    }
