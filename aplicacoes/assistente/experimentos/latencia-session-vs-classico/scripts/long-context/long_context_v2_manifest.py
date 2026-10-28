"""Manifesto reproduzível e resolução fail-closed do bundle protegido da campanha v2."""

from __future__ import annotations

import hashlib
import json
import stat
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from long_context_contract import (
    EXPECTED_CASE_METRICS,
    EXPECTED_ITEM_CASES,
    EXPECTED_ITEM_TYPES,
    EXPECTED_NATURAL_TEXT_HASHES,
    EXPECTED_PAYLOAD_HASHES,
    EXPECTED_TARGET_ANCHOR_KINDS,
    stable_digest,
)

SCHEMA_VERSION = "benchmark-long-context-v2-manifest-1"
PROTECTED_PREFIX = "protected://benchmark-long-context-v2/"
EXPECTED_CORPUS_SNAPSHOT_HASHES = {
    "case-0960k": {
        "canonical_manifest_sha256": "0983d6e6613f03a102cf3727c98477d4d3df0fd5e2864bcc5934c547f0bc8cb6",
        "document_inventory_sha256": "15f6af1a50070f35181baebbe97e2e97aa62ce757e2e18e3f9207dfa5eedf652",
    },
    "case-5120k": {
        "canonical_manifest_sha256": "eef63f9a7127ff9417b5f0c24a409f4e195247469f07b215e8c9badc9848eeae",
        "document_inventory_sha256": "d82a497ac3d7a28cf14739864d00c970c5ba1c6b15ed41397694f145989533b0",
    },
    "case-6260k": {
        "canonical_manifest_sha256": "43665a6faabb1bb5403cd84d285378531baeffd333f92e388c4cd2e806cdd101",
        "document_inventory_sha256": "3a36c4407c07222159afb20a0e554e6170ba752320e917ad351d2f83df05a279",
    },
}
EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = EXPERIMENT_ROOT / "dataset" / "long-context"
MANIFEST_PATH = DATASET_DIR / "benchmark-long-context-v2.json"
MANIFEST_SCHEMA_PATH = DATASET_DIR / "benchmark-long-context-v2.schema.json"
CONTRACT_SCHEMA_PATH = (
    DATASET_DIR / "benchmark-long-context-v2-evaluation-contract.schema.json"
)


class ManifestContractError(RuntimeError):
    """Manifesto, contrato ou bundle protegido divergiu do snapshot aprovado."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestContractError(f"JSON inválido ou ilegível: {path}") from exc
    if not isinstance(value, dict):
        raise ManifestContractError(f"Objeto JSON esperado: {path}")
    return value


def _validate_schema(value: dict[str, Any], schema_path: Path, label: str) -> None:
    schema = _load_json(schema_path)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise ManifestContractError(f"{label} inválido em {location}: {first.message}")


def resolve_protected_ref(ref: str, protected_root: Path) -> Path:
    """Resolve ``protected://`` sem aceitar escape, symlink ou arquivo ausente."""
    if not ref.startswith(PROTECTED_PREFIX):
        raise ManifestContractError(f"Referência protegida inválida: {ref!r}")
    relative = Path(ref.removeprefix(PROTECTED_PREFIX))
    if relative.is_absolute() or ".." in relative.parts:
        raise ManifestContractError(f"Referência protegida insegura: {ref!r}")
    root = protected_root.resolve(strict=True)
    candidate = root.joinpath(relative)
    if candidate.is_symlink():
        raise ManifestContractError(f"Symlink proibido no bundle protegido: {ref!r}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ManifestContractError(f"Referência escapou do bundle: {ref!r}")
    return resolved


def _assert_private_path(path: Path, root: Path) -> None:
    for candidate in (path, *path.parents):
        if candidate == root.parent:
            break
        mode = stat.S_IMODE(candidate.stat().st_mode)
        expected = 0o700 if candidate.is_dir() else 0o600
        if mode != expected:
            raise ManifestContractError(
                f"Permissão privada inválida em {candidate}: {mode:o}, esperado {expected:o}"
            )
        if candidate == root:
            break


def _validate_ref_hash(entry: dict[str, Any], root: Path) -> Path:
    path = resolve_protected_ref(str(entry["ref"]), root)
    if not path.is_file():
        raise ManifestContractError(f"Arquivo protegido esperado: {entry['ref']}")
    _assert_private_path(path, root)
    observed = file_sha256(path)
    if observed != entry["sha256"]:
        raise ManifestContractError(
            f"Hash protegido divergente para {entry['ref']}: {observed}"
        )
    return path


def _inventory_digest(corpus_dir: Path) -> tuple[str, int]:
    entries = {
        str(path.relative_to(corpus_dir)): file_sha256(path)
        for path in sorted(corpus_dir.rglob("*.txt"))
    }
    return stable_digest(entries), len(entries)


def validate_manifest(  # noqa: C901, PLR0912, PLR0915
    manifest_path: Path = MANIFEST_PATH,
    *,
    protected_root: Path | None = None,
) -> dict[str, Any]:
    """Valida schema, invariantes congeladas, hashes Git e, opcionalmente, o bundle."""
    manifest = _load_json(manifest_path)
    _validate_schema(manifest, MANIFEST_SCHEMA_PATH, "manifesto v2")

    item_ids = [item["item_id"] for item in manifest["items"]]
    if len(item_ids) != len(set(item_ids)) or set(item_ids) != set(EXPECTED_ITEM_CASES):
        raise ManifestContractError(
            "O manifesto deve conter exatamente os nove itens naturais"
        )
    case_ids = [corpus["case_id"] for corpus in manifest["corpora"]]
    if len(case_ids) != len(set(case_ids)) or set(case_ids) != set(
        EXPECTED_CASE_METRICS
    ):
        raise ManifestContractError(
            "O manifesto deve conter exatamente os três corpora"
        )

    distribution = Counter(item["question_type"] for item in manifest["items"])
    if distribution != Counter(
        {"factual": 3, "synthesis": 3, "insufficient-evidence": 3}
    ):
        raise ManifestContractError(
            f"Distribuição 3/3/3 divergente: {dict(distribution)}"
        )

    for corpus in manifest["corpora"]:
        case_id = corpus["case_id"]
        expected = EXPECTED_CASE_METRICS[case_id]
        if corpus["payload_sha256"] != EXPECTED_PAYLOAD_HASHES[case_id]:
            raise ManifestContractError(f"Payload congelado divergente: {case_id}")
        snapshot_hashes = EXPECTED_CORPUS_SNAPSHOT_HASHES[case_id]
        if any(corpus[key] != value for key, value in snapshot_hashes.items()):
            raise ManifestContractError(f"Snapshot congelado divergente: {case_id}")
        if (corpus["document_count"], corpus["token_count"]) != (
            expected["documents"],
            expected["tokens"],
        ):
            raise ManifestContractError(f"Métricas congeladas divergentes: {case_id}")

    for item in manifest["items"]:
        item_id = item["item_id"]
        if item["case_id"] != EXPECTED_ITEM_CASES[item_id]:
            raise ManifestContractError(f"Case divergente: {item_id}")
        expected_type, _ = EXPECTED_ITEM_TYPES[item_id]
        if item["question_type"] != expected_type:
            raise ManifestContractError(f"Tipo divergente: {item_id}")
        if (
            item["question"]["sha256"]
            != EXPECTED_NATURAL_TEXT_HASHES[item_id]["question"]
        ):
            raise ManifestContractError(
                f"Hash independente da pergunta divergente: {item_id}"
            )
        if item["gold"]["sha256"] != EXPECTED_NATURAL_TEXT_HASHES[item_id]["gold"]:
            raise ManifestContractError(
                f"Hash independente do gold divergente: {item_id}"
            )
        if item["target"]["anchor_kind"] != EXPECTED_TARGET_ANCHOR_KINDS[item_id]:
            raise ManifestContractError(f"Target anchor divergente: {item_id}")
        is_negative = item["question_type"] == "insufficient-evidence"
        absence = item["absence_evidence"]
        if absence["required"] is not is_negative:
            raise ManifestContractError(f"Política de ausência divergente: {item_id}")
        if is_negative != (absence["ref"] is not None):
            raise ManifestContractError(f"Referência de ausência divergente: {item_id}")

    contract_path = EXPERIMENT_ROOT / manifest["evaluation_contract"]["ref"]
    if file_sha256(contract_path) != manifest["evaluation_contract"]["sha256"]:
        raise ManifestContractError("Hash do contrato de avaliação divergiu")
    contract = _load_json(contract_path)
    _validate_schema(contract, CONTRACT_SCHEMA_PATH, "contrato de avaliação v2")
    base = EXPERIMENT_ROOT
    for key in ("system_prompt", "user_prompt", "response_schema"):
        ref = contract["judge"][f"{key}_ref"]
        if file_sha256(base / ref) != contract["judge"][f"{key}_sha256"]:
            raise ManifestContractError(f"Hash do artefato do juiz divergiu: {ref}")
    rate = contract["rate_card"]
    rate_path = base / rate["ref"]
    if file_sha256(rate_path) != rate["sha256"]:
        raise ManifestContractError("Hash da rate card divergiu")
    rate_models = _load_json(rate_path).get("models") or {}
    for identity in contract["model_profiles"].values():
        configured = rate_models.get(identity["deployment"])
        if (
            not isinstance(configured, dict)
            or configured.get("source_model") != identity["canonical_model"]
        ):
            raise ManifestContractError(
                f"Rate card não resolve {identity['canonical_model']}"
            )

    if protected_root is not None:
        _assert_private_path(
            protected_root.resolve(strict=True), protected_root.resolve()
        )
        for corpus in manifest["corpora"]:
            _validate_ref_hash(corpus["process_metadata_ref"], protected_root)
            corpus_dir = resolve_protected_ref(corpus["corpus_ref"], protected_root)
            _assert_private_path(corpus_dir, protected_root.resolve())
            digest, count = _inventory_digest(corpus_dir)
            if (
                digest != corpus["runtime_bundle_inventory_sha256"]
                or count != corpus["document_count"]
            ):
                raise ManifestContractError(
                    f"Inventário protegido divergente: {corpus['case_id']}"
                )
        for item in manifest["items"]:
            for key in ("question", "gold", "rubric"):
                _validate_ref_hash(item[key], protected_root)
            _validate_ref_hash(item["target"]["anchor_ref"], protected_root)
            for source in item["evidence"]["source_refs"]:
                _validate_ref_hash(source, protected_root)
            if item["absence_evidence"]["ref"] is not None:
                _validate_ref_hash(item["absence_evidence"]["ref"], protected_root)

    return manifest


def load_protected_json(entry: dict[str, Any], protected_root: Path) -> dict[str, Any]:
    """Lê JSON protegido somente depois de confirmar seu hash de manifesto."""
    return _load_json(_validate_ref_hash(entry, protected_root))


def load_protected_text(entry: dict[str, Any], protected_root: Path) -> str:
    """Lê texto protegido somente depois de confirmar seu hash de manifesto."""
    return _validate_ref_hash(entry, protected_root).read_text(encoding="utf-8")
