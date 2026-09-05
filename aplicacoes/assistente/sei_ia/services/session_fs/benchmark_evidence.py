"""Fonte pinada dos bytes v3 usada somente pelo benchmark isolado."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from threading import Lock
from typing import Any

_EVIDENCE_SCHEMA = "benchmark-long-context-evidence-index-v1"
_EVALUATION_DESIGN = "benchmark-long-context-evidence-v3-20260723"
_FRESH_IDENTITY_DESIGN = "benchmark-long-context-evidence-v4-ocr-fresh-20260724"
_FRESH_BINARY_SCHEMA = "benchmark-long-context-fresh-binary-index-v1"
_FRESH_BINARY_FILENAME = "fresh-binary-index.json"
_DIAGNOSTIC_SCHEMA = "benchmark-evidence-preflight-v1"
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _sha256(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _safe_filename(value: str) -> str:
    cleaned = _UNSAFE_FILENAME.sub("_", value).strip("._") or "documento"
    return cleaned[:128]


def _virtual_path(proc_id: str, document_id: str) -> str:
    return f"proc_{_safe_filename(proc_id)}/{_safe_filename(document_id)}.txt"


def _diagnostic(
    category: str, *, path: str | None = None, fields: list[str] | None = None
) -> dict[str, Any]:
    descriptor = {
        "category": category,
        "path_present": path is not None,
        "fields": sorted(fields or []),
    }
    return {
        "schema_version": _DIAGNOSTIC_SCHEMA,
        "category": category,
        "fingerprint": _sha256(
            json.dumps(descriptor, sort_keys=True, separators=(",", ":"))
        ),
        "path_sha256": _sha256("/" + path.lstrip("/")) if path else None,
        "invalid_fields": sorted(fields or []),
        "raw_persisted": False,
    }


class BenchmarkEvidenceError(RuntimeError):
    """Falha fail-fast com diagnóstico que não contém path nem conteúdo bruto."""

    def __init__(self, category: str, *, path: str | None = None) -> None:
        super().__init__(f"benchmark evidence preflight failed: {category}")
        self.diagnostic = _diagnostic(category, path=path)


@dataclass(frozen=True)
class _PinnedDocument:
    virtual_path: str
    content_sha256: str
    fresh_binary_sha256: str | None = None
    fresh_pipeline_sha256: str | None = None


@dataclass(frozen=True)
class BenchmarkEvidenceSnapshot:
    """Hashes de referência em memória para validar bytes fresh e materializados."""

    _documents: dict[str, _PinnedDocument]
    diagnostic: dict[str, Any]
    _runtime_content_sha256: dict[str, str] = field(default_factory=dict)
    _runtime_lock: Lock = field(default_factory=Lock)

    @property
    def document_count(self) -> int:
        return len(self._documents)

    def validate_fresh_document(
        self,
        document_id: str,
        content: str,
        provenance: dict[str, Any] | None = None,
    ) -> None:
        """Valida texto determinístico ou binário+pipeline para extrações com OCR."""
        try:
            document = self._documents[str(document_id)]
        except KeyError as exc:
            raise BenchmarkEvidenceError("document_not_pinned") from exc
        content_sha256 = _sha256(content.encode("utf-8"))
        if document.fresh_binary_sha256 is None:
            if content_sha256 != document.content_sha256:
                raise BenchmarkEvidenceError(
                    "fresh_content_hash_mismatch", path=document.virtual_path
                )
        else:
            if not content.strip():
                raise BenchmarkEvidenceError(
                    "fresh_content_empty", path=document.virtual_path
                )
            provenance = provenance or {}
            if provenance.get("fresh_binary_sha256") != document.fresh_binary_sha256:
                raise BenchmarkEvidenceError(
                    "fresh_binary_hash_mismatch", path=document.virtual_path
                )
            if (
                provenance.get("fresh_extraction_pipeline_sha256")
                != document.fresh_pipeline_sha256
            ):
                raise BenchmarkEvidenceError(
                    "fresh_pipeline_identity_mismatch", path=document.virtual_path
                )
        with self._runtime_lock:
            self._runtime_content_sha256[str(document_id)] = content_sha256

    def validate_materialized(self, session_root: str | Path) -> dict[str, Any]:
        """Prova que o filesystem entregue ao agente preservou os bytes pinados."""
        root = Path(session_root).resolve()
        inventory: list[dict[str, str]] = []
        for document_id, document in self._documents.items():
            materialized = root / document.virtual_path
            resolved = materialized.resolve()
            if not resolved.is_relative_to(root):
                raise BenchmarkEvidenceError(
                    "materialized_outside_root", path=document.virtual_path
                )
            if not materialized.is_file() or materialized.is_symlink():
                raise BenchmarkEvidenceError(
                    "materialized_missing", path=document.virtual_path
                )
            content_sha256 = _sha256(materialized.read_bytes())
            expected_sha256 = document.content_sha256
            if document.fresh_binary_sha256 is not None:
                with self._runtime_lock:
                    expected_sha256 = self._runtime_content_sha256.get(document_id, "")
                if not expected_sha256:
                    raise BenchmarkEvidenceError(
                        "fresh_validation_missing", path=document.virtual_path
                    )
            if content_sha256 != expected_sha256:
                raise BenchmarkEvidenceError(
                    "materialized_hash_mismatch", path=document.virtual_path
                )
            inventory.append(
                {
                    "path_sha256": _sha256("/" + document.virtual_path.lstrip("/")),
                    "content_sha256": content_sha256,
                }
            )
        inventory_sha256 = _sha256(
            json.dumps(
                sorted(inventory, key=lambda row: row["path_sha256"]),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return {
            **self.diagnostic,
            "materialized_status": "passed",
            "materialized_inventory_sha256": inventory_sha256,
            "fresh_binary_documents": sum(
                document.fresh_binary_sha256 is not None
                for document in self._documents.values()
            ),
            "text_identity_documents": sum(
                document.fresh_binary_sha256 is None
                for document in self._documents.values()
            ),
        }


def _load_index(index_path: Path) -> dict[str, Any]:
    if not index_path.is_file() or index_path.is_symlink():
        raise BenchmarkEvidenceError("index_missing")
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkEvidenceError("index_invalid") from exc
    if (
        not isinstance(index, dict)
        or index.get("schema_version") != _EVIDENCE_SCHEMA
        or index.get("evaluation_design_version") != _EVALUATION_DESIGN
        or not isinstance(index.get("cases"), dict)
    ):
        raise BenchmarkEvidenceError("index_contract_mismatch")
    return index


def _load_fresh_binary_case(
    index_path: Path,
    case_id: str,
    force_download_ids: set[str],
) -> dict[str, dict[str, str]]:
    path = index_path.with_name(_FRESH_BINARY_FILENAME)
    if not path.is_file() or path.is_symlink():
        raise BenchmarkEvidenceError("fresh_binary_index_missing")
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkEvidenceError("fresh_binary_index_invalid") from exc
    if not isinstance(index, dict):
        raise BenchmarkEvidenceError("fresh_binary_index_contract_mismatch")
    cases = index.get("cases")
    if (
        index.get("schema_version") != _FRESH_BINARY_SCHEMA
        or index.get("evaluation_design_version") != _FRESH_IDENTITY_DESIGN
        or not isinstance(cases, dict)
        or not isinstance(cases.get(case_id), dict)
    ):
        raise BenchmarkEvidenceError("fresh_binary_index_contract_mismatch")
    rows = cases[case_id].get("documents")
    if not isinstance(rows, list):
        raise BenchmarkEvidenceError("fresh_binary_index_contract_mismatch")
    documents: dict[str, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise BenchmarkEvidenceError("fresh_binary_index_contract_mismatch")
        document_id = str(row.get("document_id") or "")
        binary_sha256 = row.get("fresh_binary_sha256")
        pipeline_sha256 = row.get("fresh_pipeline_sha256")
        if (
            not document_id
            or document_id in documents
            or not isinstance(binary_sha256, str)
            or len(binary_sha256) != 64
            or not isinstance(pipeline_sha256, str)
            or len(pipeline_sha256) != 64
        ):
            raise BenchmarkEvidenceError("fresh_binary_index_contract_mismatch")
        documents[document_id] = {
            "fresh_binary_sha256": binary_sha256,
            "fresh_pipeline_sha256": pipeline_sha256,
        }
    if set(documents) != force_download_ids:
        raise BenchmarkEvidenceError("fresh_binary_request_mismatch")
    return documents


def _match_case(
    index: dict[str, Any], requested: dict[str, str]
) -> tuple[str, dict[str, Any]]:
    requested_ids = set(requested)
    matches = []
    for case_id, case in index["cases"].items():
        documents = case.get("documents") if isinstance(case, dict) else None
        if not isinstance(documents, list):
            continue
        indexed_ids = {
            str(document.get("document_id"))
            for document in documents
            if isinstance(document, dict) and document.get("document_id") is not None
        }
        if indexed_ids == requested_ids and len(indexed_ids) == len(documents):
            matches.append((str(case_id), case))
    if len(matches) != 1:
        raise BenchmarkEvidenceError("request_tree_mismatch")
    return matches[0]


def _parse_requested_specs(
    requested_specs: list[tuple[str, str] | tuple[str, str, bool]],
) -> tuple[dict[str, str], set[str]]:
    requested: dict[str, str] = {}
    force_download_ids: set[str] = set()
    for spec in requested_specs:
        if len(spec) not in {2, 3}:
            raise BenchmarkEvidenceError("request_tree_mismatch")
        proc_id, document_id = spec[:2]
        key = str(document_id)
        if not key or key in requested:
            raise BenchmarkEvidenceError("request_tree_mismatch")
        requested[key] = str(proc_id)
        if len(spec) == 3 and spec[2] is True:
            force_download_ids.add(key)
    if not requested:
        raise BenchmarkEvidenceError("request_tree_mismatch")
    return requested, force_download_ids


def load_benchmark_evidence_snapshot(
    index_path: str | Path,
    requested_specs: list[tuple[str, str] | tuple[str, str, bool]],
) -> BenchmarkEvidenceSnapshot:
    """Fixa hashes textuais ou identidade binário+pipeline conforme a rota fresh."""
    requested, force_download_ids = _parse_requested_specs(requested_specs)

    path = Path(index_path)
    index = _load_index(path)
    case_id, case = _match_case(index, requested)
    fresh_binary_documents = _load_fresh_binary_case(path, case_id, force_download_ids)
    documents = case["documents"]
    if case.get("document_count") != len(documents):
        raise BenchmarkEvidenceError("index_contract_mismatch")

    source_root = (path.parent / "evidence-sources" / case_id / "session").resolve()
    pinned: dict[str, _PinnedDocument] = {}
    inventory: list[dict[str, str]] = []
    for row in documents:
        if not isinstance(row, dict):
            raise BenchmarkEvidenceError("index_contract_mismatch")
        document_id = str(row.get("document_id", ""))
        virtual_path = str(row.get("virtual_path", ""))
        expected_path = _virtual_path(requested.get(document_id, ""), document_id)
        if PurePosixPath(virtual_path).as_posix() != expected_path:
            raise BenchmarkEvidenceError("request_tree_mismatch", path=virtual_path)

        source = source_root / virtual_path
        resolved_source = source.resolve()
        if not resolved_source.is_relative_to(source_root):
            raise BenchmarkEvidenceError("source_outside_root", path=virtual_path)
        if not source.is_file() or source.is_symlink():
            raise BenchmarkEvidenceError("source_missing", path=virtual_path)
        raw = source.read_bytes()
        content_sha256 = _sha256(raw)
        if content_sha256 != row.get("document_sha256"):
            raise BenchmarkEvidenceError("content_hash_mismatch", path=virtual_path)
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            raise BenchmarkEvidenceError("source_not_utf8", path=virtual_path) from None
        fresh_identity = fresh_binary_documents.get(document_id, {})
        pinned[document_id] = _PinnedDocument(
            virtual_path=virtual_path,
            content_sha256=content_sha256,
            fresh_binary_sha256=fresh_identity.get("fresh_binary_sha256"),
            fresh_pipeline_sha256=fresh_identity.get("fresh_pipeline_sha256"),
        )
        inventory.append(
            {
                "path_sha256": _sha256("/" + virtual_path.lstrip("/")),
                "content_sha256": content_sha256,
            }
        )

    inventory_sha256 = _sha256(
        json.dumps(
            sorted(inventory, key=lambda row: row["path_sha256"]),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    diagnostic = {
        "schema_version": _DIAGNOSTIC_SCHEMA,
        "status": "passed",
        "case_id_sha256": _sha256(case_id),
        "documents": len(pinned),
        "inventory_sha256": inventory_sha256,
        "source": "frozen_reference_plus_fresh_binary_identity",
        "identity_contract": _FRESH_IDENTITY_DESIGN,
        "fresh_binary_documents": len(fresh_binary_documents),
    }
    return BenchmarkEvidenceSnapshot(_documents=pinned, diagnostic=diagnostic)
