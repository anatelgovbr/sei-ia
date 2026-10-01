"""Checkpoint JSONL durável para execuções longas do benchmark."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class SessionLedgerError(RuntimeError):
    """O ledger Session recusou uma segunda tentativa ou estado ambíguo."""


class SessionExecutionLedger:
    """Ledger append-only de tópicos e da fronteira irreversível do POST."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        if self.path.exists():
            self.path.chmod(0o600)

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _append(self, event: dict[str, Any]) -> None:
        payload = {
            "schema_version": "benchmark-session-execution-ledger-v1",
            "recorded_at": datetime.now(UTC).isoformat(),
            **event,
        }
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.path.chmod(0o600)

    def reserve_topics(
        self,
        cell_ids: list[str],
        *,
        topic_ids: dict[str, int],
        historical_topic_ids: set[int] | None = None,
    ) -> dict[str, int]:
        """Reserva toda a matriz antes da primeira célula, sem reutilizar tópico."""
        if set(cell_ids) != set(topic_ids) or len(cell_ids) != len(set(cell_ids)):
            raise SessionLedgerError("plano de tópicos não corresponde às células")
        existing = {
            int(event["topic_id"])
            for event in self.events()
            if event.get("event_type") == "topic_reserved"
        }
        unavailable = existing | set(historical_topic_ids or set())
        proposed = list(topic_ids.values())
        if len(proposed) != len(set(proposed)):
            raise SessionLedgerError("tópicos propostos não são únicos")
        if unavailable.intersection(proposed):
            raise SessionLedgerError("tópico já usado em ledger histórico")
        for cell_id in cell_ids:
            topic_id = topic_ids[cell_id]
            if not isinstance(topic_id, int) or topic_id <= 0:
                raise SessionLedgerError("id de tópico inválido")
            self._append(
                {
                    "event_type": "topic_reserved",
                    "cell_id": cell_id,
                    "topic_id": topic_id,
                }
            )
        return dict(topic_ids)

    def reserve_post(self, cell_id: str, topic_id: int) -> None:
        events = self.events()
        if any(
            event.get("cell_id") == cell_id
            and event.get("event_type") in {"post_reserved", "post_started"}
            for event in events
        ):
            raise SessionLedgerError(f"POST já iniciado ou reservado para {cell_id}")
        if not any(
            event.get("event_type") == "topic_reserved"
            and event.get("cell_id") == cell_id
            and event.get("topic_id") == topic_id
            for event in events
        ):
            raise SessionLedgerError("POST não corresponde a tópico reservado")
        self._append(
            {
                "event_type": "post_reserved",
                "cell_id": cell_id,
                "topic_id": topic_id,
            }
        )

    def mark_post_started(self, cell_id: str) -> None:
        events = self.events()
        reservations = [
            event
            for event in events
            if event.get("event_type") == "post_reserved"
            and event.get("cell_id") == cell_id
        ]
        if len(reservations) != 1 or self.post_started_count(cell_id):
            raise SessionLedgerError("fronteira post_started inválida")
        self._append(
            {
                "event_type": "post_started",
                "cell_id": cell_id,
                "topic_id": reservations[0]["topic_id"],
            }
        )

    def mark_post_terminal(self, cell_id: str, *, valid: bool) -> None:
        if self.post_started_count(cell_id) != 1:
            raise SessionLedgerError("terminal sem post_started único")
        if any(
            event.get("event_type") == "post_terminal"
            and event.get("cell_id") == cell_id
            for event in self.events()
        ):
            raise SessionLedgerError("terminal já persistido")
        self._append(
            {
                "event_type": "post_terminal",
                "cell_id": cell_id,
                "valid": valid,
            }
        )

    def post_started_count(self, cell_id: str) -> int:
        return sum(
            event.get("event_type") == "post_started"
            and event.get("cell_id") == cell_id
            for event in self.events()
        )


def historical_topic_ids(root: str | Path) -> set[int]:
    """Lê somente IDs de ledgers Session anteriores sob a raiz privada."""
    base = Path(root)
    if not base.exists():
        return set()
    used: set[int] = set()
    for path in base.rglob("session-execution-ledger.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("event_type") == "topic_reserved":
                used.add(int(event["topic_id"]))
    return used


def append_progress(path: str | Path, result: dict[str, Any]) -> Path:
    """Anexa um item concluído e sincroniza o arquivo antes de seguir a bateria."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(result, ensure_ascii=False) + "\n"
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    return target


def read_progress(path: str | Path) -> list[dict[str, Any]]:
    """Lê checkpoints válidos na ordem em que a bateria os concluiu."""
    target = Path(path)
    if not target.exists():
        return []
    return [
        json.loads(line)
        for line in target.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
