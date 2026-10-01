"""Pinning fail-fast dos bytes congelados no harness de benchmark."""

import hashlib
import json
from pathlib import Path

import pytest

from sei_ia.services.session_fs.benchmark_evidence import (
    BenchmarkEvidenceError,
    load_benchmark_evidence_snapshot,
)

_DESIGN = "benchmark-long-context-evidence-v3-20260723"
_FRESH_DESIGN = "benchmark-long-context-evidence-v4-ocr-fresh-20260724"


def _build_index(tmp_path: Path) -> tuple[Path, list[tuple[str, str]]]:
    docs = [("proc-a", "doc-1"), ("proc-a", "doc-2")]
    records = []
    for position, (_proc, doc_id) in enumerate(docs, start=1):
        virtual_path = f"proc_proc-a/{doc_id}.txt"
        source = tmp_path / "evidence-sources" / "case-a" / "session" / virtual_path
        source.parent.mkdir(parents=True, exist_ok=True)
        raw = f"conteúdo congelado {position}".encode()
        source.write_bytes(raw)
        records.append(
            {
                "document_id": doc_id,
                "formatted_id": f"Documento {position}",
                "virtual_path": virtual_path,
                "source_path": "/host/path/que-nao-deve-ser-usado",
                "document_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    index = {
        "schema_version": "benchmark-long-context-evidence-index-v1",
        "evaluation_design_version": _DESIGN,
        "cases": {
            "case-a": {
                "documents": records,
                "document_count": len(records),
            }
        },
    }
    path = tmp_path / "evidence-index.json"
    path.write_text(json.dumps(index))
    (tmp_path / "fresh-binary-index.json").write_text(
        json.dumps(
            {
                "schema_version": "benchmark-long-context-fresh-binary-index-v1",
                "evaluation_design_version": _FRESH_DESIGN,
                "cases": {"case-a": {"documents": []}},
            }
        )
    )
    return path, docs


def test_evidence_snapshot_pins_exact_bytes_and_safe_inventory(tmp_path):
    index_path, specs = _build_index(tmp_path)

    snapshot = load_benchmark_evidence_snapshot(index_path, specs)

    assert snapshot.document_count == 2
    assert not hasattr(snapshot, "read_document")
    assert snapshot.diagnostic["status"] == "passed"
    assert snapshot.diagnostic["documents"] == 2
    assert len(snapshot.diagnostic["inventory_sha256"]) == 64
    assert set(snapshot.diagnostic) == {
        "schema_version",
        "status",
        "case_id_sha256",
        "documents",
        "inventory_sha256",
        "source",
        "identity_contract",
        "fresh_binary_documents",
    }


def test_evidence_snapshot_accepts_fresh_sei_bytes_only_when_identical(tmp_path):
    index_path, specs = _build_index(tmp_path)
    snapshot = load_benchmark_evidence_snapshot(index_path, specs)

    snapshot.validate_fresh_document("doc-1", "conteúdo congelado 1")

    with pytest.raises(BenchmarkEvidenceError) as caught:
        snapshot.validate_fresh_document("doc-1", "conteúdo stale ou divergente")
    assert caught.value.diagnostic["category"] == "fresh_content_hash_mismatch"
    assert "conteúdo stale" not in json.dumps(
        caught.value.diagnostic, ensure_ascii=False
    )


def test_ocr_fresh_uses_binary_and_pipeline_identity_not_frozen_text(tmp_path):
    index_path, specs = _build_index(tmp_path)
    pipeline_sha256 = "a" * 64
    binary_sha256 = hashlib.sha256(b"fresh-pdf").hexdigest()
    (tmp_path / "fresh-binary-index.json").write_text(
        json.dumps(
            {
                "schema_version": "benchmark-long-context-fresh-binary-index-v1",
                "evaluation_design_version": _FRESH_DESIGN,
                "cases": {
                    "case-a": {
                        "documents": [
                            {
                                "document_id": "doc-2",
                                "fresh_binary_sha256": binary_sha256,
                                "fresh_pipeline_sha256": pipeline_sha256,
                            }
                        ]
                    }
                },
            }
        )
    )
    snapshot = load_benchmark_evidence_snapshot(
        index_path,
        [("proc-a", "doc-1", False), ("proc-a", "doc-2", True)],
    )

    with pytest.raises(BenchmarkEvidenceError) as caught:
        snapshot.validate_fresh_document(
            "doc-2",
            "OCR fresh não determinístico",
            {
                "fresh_binary_sha256": "b" * 64,
                "fresh_extraction_pipeline_sha256": pipeline_sha256,
            },
        )
    assert caught.value.diagnostic["category"] == "fresh_binary_hash_mismatch"

    fresh_ocr = "OCR fresh não determinístico"
    snapshot.validate_fresh_document(
        "doc-2",
        fresh_ocr,
        {
            "fresh_binary_sha256": binary_sha256,
            "fresh_extraction_pipeline_sha256": pipeline_sha256,
        },
    )
    session_root = tmp_path / "session"
    proc_root = session_root / "proc_proc-a"
    proc_root.mkdir(parents=True)
    (proc_root / "doc-1.txt").write_text("conteúdo congelado 1")
    (proc_root / "doc-2.txt").write_text(fresh_ocr)

    diagnostic = snapshot.validate_materialized(session_root)

    assert diagnostic["materialized_status"] == "passed"
    assert diagnostic["fresh_binary_documents"] == 1
    assert diagnostic["text_identity_documents"] == 1


def test_evidence_snapshot_validates_materialized_bytes(tmp_path):
    index_path, specs = _build_index(tmp_path)
    snapshot = load_benchmark_evidence_snapshot(index_path, specs)
    session_root = tmp_path / "session"
    for position, (_proc, document_id) in enumerate(specs, start=1):
        target = session_root / "proc_proc-a" / f"{document_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"conteúdo congelado {position}")

    diagnostic = snapshot.validate_materialized(session_root)

    assert diagnostic["materialized_status"] == "passed"
    assert diagnostic["materialized_inventory_sha256"] == diagnostic["inventory_sha256"]


def test_evidence_snapshot_rejects_materialized_drift(tmp_path):
    index_path, specs = _build_index(tmp_path)
    snapshot = load_benchmark_evidence_snapshot(index_path, specs)
    session_root = tmp_path / "session"
    for position, (_proc, document_id) in enumerate(specs, start=1):
        target = session_root / "proc_proc-a" / f"{document_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"conteúdo congelado {position}")
    (session_root / "proc_proc-a" / "doc-2.txt").write_text("drift")

    with pytest.raises(BenchmarkEvidenceError) as caught:
        snapshot.validate_materialized(session_root)

    assert caught.value.diagnostic["category"] == "materialized_hash_mismatch"


def test_evidence_snapshot_rejects_drift_of_same_path(tmp_path):
    index_path, specs = _build_index(tmp_path)
    source = (
        tmp_path
        / "evidence-sources"
        / "case-a"
        / "session"
        / "proc_proc-a"
        / "doc-1.txt"
    )
    source.write_text("conteúdo reextraído diferente")

    with pytest.raises(BenchmarkEvidenceError) as caught:
        load_benchmark_evidence_snapshot(index_path, specs)

    diagnostic = caught.value.diagnostic
    assert diagnostic["category"] == "content_hash_mismatch"
    assert len(diagnostic["path_sha256"]) == 64
    assert "conteúdo" not in json.dumps(diagnostic, ensure_ascii=False)
    assert str(tmp_path) not in json.dumps(diagnostic, ensure_ascii=False)


def test_evidence_snapshot_rejects_missing_source_path(tmp_path):
    index_path, specs = _build_index(tmp_path)
    source = (
        tmp_path
        / "evidence-sources"
        / "case-a"
        / "session"
        / "proc_proc-a"
        / "doc-2.txt"
    )
    source.unlink()

    with pytest.raises(BenchmarkEvidenceError) as caught:
        load_benchmark_evidence_snapshot(index_path, specs)

    assert caught.value.diagnostic["category"] == "source_missing"


def test_evidence_snapshot_rejects_request_tree_mismatch(tmp_path):
    index_path, specs = _build_index(tmp_path)

    with pytest.raises(BenchmarkEvidenceError) as caught:
        load_benchmark_evidence_snapshot(index_path, [*specs, ("proc-b", "doc-3")])

    assert caught.value.diagnostic["category"] == "request_tree_mismatch"
