"""Carrega suites versionadas do benchmark sem alterar os casos historicos."""

from __future__ import annotations

import copy
import json
from pathlib import Path

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = EXPERIMENT_ROOT / "dataset" / "session-classico"
DEFAULT_SUITE = "benchmark-decision-v2"


def suite_path(selector: str) -> Path:
    """Resolve nome curto ou caminho explicito de um manifesto de suite."""
    candidate = Path(selector)
    if candidate.suffix == ".json" or candidate.parent != Path("."):
        return (
            candidate
            if candidate.is_absolute()
            else (EXPERIMENT_ROOT / candidate).resolve()
        )
    return DATASET_DIR / f"{selector}.json"


def _deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_suite(selector: str = DEFAULT_SUITE) -> tuple[dict, list[dict]]:
    """Materializa os casos completos de uma suite, aplicando overrides versionados."""
    path = suite_path(selector)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    qids = manifest["qids"]
    assert qids and len(qids) == len(set(qids)), f"QIDs invalidos em {path}"

    base_path = DATASET_DIR / manifest.get("base_cases_file", "cases.json")
    base = json.loads(base_path.read_text(encoding="utf-8"))["cases"]
    by_qid = {case["qid"]: case for case in base}
    missing = set(qids) - set(by_qid)
    assert not missing, f"QIDs ausentes em {base_path}: {sorted(missing)}"

    overrides = manifest.get("overrides", {})
    unknown_overrides = set(overrides) - set(qids)
    assert not unknown_overrides, (
        f"overrides fora da suite em {path}: {sorted(unknown_overrides)}"
    )
    item_metadata = manifest.get("item_metadata", {})
    cases = []
    for qid in qids:
        case = _deep_merge(by_qid[qid], overrides.get(qid, {}))
        case["metadata"] = _deep_merge(case["metadata"], item_metadata)
        cases.append(case)
    return manifest, cases
