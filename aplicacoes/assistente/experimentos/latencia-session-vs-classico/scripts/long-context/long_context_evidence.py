"""Pacote protegido de evidências abertas/citadas para o judge de contexto longo."""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from long_context_contract import EVALUATION_DESIGN_VERSION, ContractError

_INDEX_SCHEMA = "benchmark-long-context-evidence-index-v1"
_CITATION_RE = re.compile(
    r'title="Documento [^\"]*?n[ºo]\s*(?P<label>[^\"]+)"', re.IGNORECASE
)
_TAG_RE = re.compile(r"<[^>]+>")
_STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "essa",
    "esse",
    "esta",
    "este",
    "foi",
    "mais",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "que",
    "se",
    "sem",
    "sua",
    "suas",
    "seu",
    "seus",
    "uma",
    "um",
}


def _sha256(value: str | bytes) -> str:
    encoded = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_virtual_path(path: str) -> str:
    normalized = str(path).replace("\\", "/")
    if normalized in {"", ".", "/"}:
        return "/"
    return "/" + normalized.lstrip("/")


def _fold(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    )


def _tokens(value: str) -> Counter[str]:
    return Counter(
        token
        for token in re.findall(r"[a-z]{4,}", _fold(value))
        if token not in _STOPWORDS
    )


def _plain_answer(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", value))).strip()


def _citation_contexts(answer: str, label: str) -> str:
    contexts: list[str] = []
    for match in _CITATION_RE.finditer(answer):
        if html.unescape(match.group("label")).strip() != label:
            continue
        contexts.append(answer[max(0, match.start() - 700) : match.end() + 200])
    return _plain_answer(" ".join(contexts))


def _paragraphs(text: str) -> list[str]:
    values = re.split(r"\n\s*\n|(?<=[.!?])\s+(?=[A-ZÀ-Ý])", text)
    return [
        re.sub(r"\s+", " ", value).strip()
        for value in values
        if len(value.strip()) >= 40
    ]


def _ranked_excerpts(
    text: str, query: str, *, max_excerpts: int, max_chars: int
) -> list[str]:
    query_tokens = _tokens(query)
    denominator = sum(query_tokens.values()) or 1
    scored: list[tuple[float, int, str]] = []
    for paragraph in _paragraphs(text):
        paragraph_tokens = _tokens(paragraph)
        overlap = sum(
            min(count, paragraph_tokens[token]) for token, count in query_tokens.items()
        )
        if overlap == 0:
            continue
        score = overlap / denominator
        scored.append((score, -len(paragraph), paragraph[:max_chars]))
    selected: list[str] = []
    seen: set[str] = set()
    for _, _, excerpt in sorted(scored, reverse=True):
        digest = _sha256(excerpt)
        if digest in seen:
            continue
        selected.append(excerpt)
        seen.add(digest)
        if len(selected) >= max_excerpts:
            break
    return selected


def _opened_hashes(tool_summary: dict[str, Any]) -> set[str]:
    return {
        str(reference["path_sha256"])
        for call in tool_summary.get("calls", [])
        if isinstance(call, dict)
        for reference in (call.get("files_opened") or [])
        if isinstance(reference, dict) and reference.get("path_sha256")
    }


def build_evidence_package(  # noqa: C901, PLR0912, PLR0915
    *,
    index_path: Path,
    case_id: str,
    answer: str,
    tool_summary: dict[str, Any],
    fresh_evidence: dict[str, Any],
    max_excerpts_per_document: int = 3,
    max_excerpt_chars: int = 1200,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Lê somente docs abertos e extrai trechos mínimos; conteúdo não sai no resumo."""
    if not index_path.is_file() or index_path.is_symlink():
        raise ContractError("índice protegido de evidências ausente")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if (
        index.get("schema_version") != _INDEX_SCHEMA
        or index.get("evaluation_design_version") != EVALUATION_DESIGN_VERSION
    ):
        raise ContractError("índice protegido de evidências divergente")
    case = index.get("cases", {}).get(case_id)
    if not isinstance(case, dict) or not isinstance(case.get("documents"), list):
        raise ContractError("caso ausente no índice protegido")

    observed_opened_hashes = _opened_hashes(tool_summary)
    runtime_inventory = {
        str(entry["path_sha256"]): str(entry["content_sha256"])
        for entry in tool_summary.get("document_inventory", [])
        if isinstance(entry, dict)
        and entry.get("path_sha256")
        and entry.get("content_sha256")
    }
    opened_hashes = observed_opened_hashes & set(runtime_inventory)
    if not opened_hashes:
        raise ContractError("nenhum documento do corpus foi aberto")
    if (
        not isinstance(fresh_evidence, dict)
        or fresh_evidence.get("schema_version") != "benchmark-fresh-opened-evidence-v1"
        or fresh_evidence.get("source") != "validated_materialized_session"
        or not isinstance(fresh_evidence.get("documents"), list)
    ):
        raise ContractError("evidência fresh materializada está ausente")
    fresh_by_path: dict[str, str] = {}
    for row in fresh_evidence["documents"]:
        if not isinstance(row, dict) or set(row) != {
            "path_sha256",
            "content_sha256",
            "content",
        }:
            raise ContractError("evidência fresh materializada é inválida")
        path_sha256 = row["path_sha256"]
        content = row["content"]
        content_sha256 = row["content_sha256"]
        if (
            not isinstance(path_sha256, str)
            or path_sha256 in fresh_by_path
            or not isinstance(content, str)
            or not content
            or not isinstance(content_sha256, str)
            or _sha256(content) != content_sha256
            or runtime_inventory.get(path_sha256) != content_sha256
        ):
            raise ContractError("evidência fresh materializada divergiu")
        fresh_by_path[path_sha256] = content
    if set(fresh_by_path) != opened_hashes:
        raise ContractError("cobertura da evidência fresh materializada divergiu")
    citation_labels = {
        html.unescape(match.group("label")).strip()
        for match in _CITATION_RE.finditer(answer)
    }
    package: list[dict[str, Any]] = []
    indexed_opened = cited_opened = 0
    for document in case["documents"]:
        if not isinstance(document, dict):
            raise ContractError("documento inválido no índice protegido")
        virtual_path = str(document.get("virtual_path", ""))
        path_hash = _sha256(_normalize_virtual_path(virtual_path))
        if path_hash not in opened_hashes:
            continue
        indexed_opened += 1
        text = fresh_by_path[path_hash]
        label = str(document.get("formatted_id", ""))
        cited = label in citation_labels
        if cited:
            cited_opened += 1
        query = _citation_contexts(answer, label) if cited else ""
        if not query:
            query = _plain_answer(answer)
        for excerpt in _ranked_excerpts(
            text,
            query,
            max_excerpts=max_excerpts_per_document,
            max_chars=max_excerpt_chars,
        ):
            package.append(
                {
                    "reference": len(package) + 1,
                    "document_ref_sha256": _sha256(
                        str(document.get("document_id", ""))
                    ),
                    "path_sha256": path_hash,
                    "opened": True,
                    "cited": cited,
                    "excerpt": excerpt,
                    "excerpt_sha256": _sha256(excerpt),
                }
            )
    if indexed_opened != len(opened_hashes):
        raise ContractError("arquivo aberto não está no índice protegido")
    if not package:
        raise ContractError("evidência aberta não produziu excerto verificável")
    summary = {
        "status": "complete",
        "opened_documents": len(opened_hashes),
        "non_corpus_opened_files": len(observed_opened_hashes - opened_hashes),
        "indexed_opened_documents": indexed_opened,
        "cited_opened_documents": cited_opened,
        "evidence_excerpts": len(package),
        "content_source": "validated_materialized_session",
        "content_persisted_in_sanitized_ledger": False,
    }
    return package, summary
