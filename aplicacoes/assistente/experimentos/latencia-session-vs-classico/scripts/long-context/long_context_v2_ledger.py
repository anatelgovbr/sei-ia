"""Ledger privado, append-only e idempotente da campanha long-context v2."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class LedgerContractError(RuntimeError):
    """Reserva N=1 ou transição oficial inválida."""


_EVALUATION_STATUSES = ("pending_evaluation", "evaluated", "technical_unavailable")
_TRACE_STATUSES = ("pending_trace", "complete", "technical_unavailable")


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def write_private_json(path: Path, value: Any) -> None:
    """Escreve JSON por replace atômico, com diretório 0700 e arquivo 0600."""
    _private_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                value,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                default=str,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


class V2Ledger:
    """Serializa reserva pré-POST e impede segunda avaliação oficial da mesma chave."""

    def __init__(self, path: Path) -> None:
        self.path = path
        _private_directory(path.parent)
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        for candidate in (self.path, self.lock_path):
            if not candidate.exists():
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
            candidate.chmod(0o600)

    def _events_unlocked(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerContractError(
                    f"Ledger corrompido na linha {number}"
                ) from exc
            if not isinstance(event, dict):
                raise LedgerContractError(f"Ledger inválido na linha {number}")
            events.append(event)
        return events

    def events(self) -> list[dict[str, Any]]:
        return self._events_unlocked()

    def _append(self, event: dict[str, Any], validator) -> dict[str, Any]:
        with self.lock_path.open("r+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            events = self._events_unlocked()
            validator(events)
            row = {
                "schema_version": "benchmark-long-context-v2-ledger-event-1",
                "event_id": str(uuid.uuid4()),
                "recorded_at": datetime.now(UTC).isoformat(),
                **event,
            }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return row

    @staticmethod
    def _execution_rows(
        events: list[dict[str, Any]], execution_id: str
    ) -> list[dict[str, Any]]:
        return [event for event in events if event.get("execution_id") == execution_id]

    def reserve(
        self,
        *,
        run_name: str,
        item_id: str,
        contract_sha256: str,
        request_identity_sha256: str,
    ) -> dict[str, Any]:
        """Reserva N=1 antes do POST; qualquer reserva anterior bloqueia nova inferência."""
        execution_id = str(uuid.uuid4())

        def validate(events: list[dict[str, Any]]) -> None:
            if any(
                event.get("event_type") == "reservation"
                and event.get("item_id") == item_id
                for event in events
            ):
                raise LedgerContractError(
                    f"N=1 já reservado para a campanha: {item_id}"
                )

        return self._append(
            {
                "event_type": "reservation",
                "execution_id": execution_id,
                "run_name": run_name,
                "item_id": item_id,
                "trace_id": None,
                "contract_sha256": contract_sha256,
                "request_identity_sha256": request_identity_sha256,
                "post_attempted": False,
                "evaluation_status": "pending_evaluation",
                "trace_status": "pending_trace",
            },
            validate,
        )

    def authorize_replacement(
        self,
        *,
        predecessor_execution_id: str,
        predecessor_trace_id: str,
        item_id: str,
        reason: str,
        captain_authorization: str,
        proof: dict[str, Any],
    ) -> dict[str, Any]:
        """Invalida uma tentativa pré-agente e autoriza uma única substituição."""
        required_proof = {
            "failure_stage": "pre_agent",
            "technical_failure": True,
            "zero_generations": True,
            "zero_tools": True,
            "zero_judge_calls": True,
            "zero_tokens": True,
            "zero_cost": True,
        }
        if any(proof.get(key) != value for key, value in required_proof.items()):
            raise LedgerContractError("prova da tentativa inválida está incompleta")
        artifacts = proof.get("artifacts_sha256")
        if artifacts is not None and (
            not isinstance(artifacts, dict)
            or not artifacts
            or any(
                not isinstance(value, str) or len(value) != 64
                for value in artifacts.values()
            )
        ):
            raise LedgerContractError("hashes da prova de substituição são inválidos")
        if reason != "wrong_sei_environment_pre_agent":
            raise LedgerContractError("motivo de substituição não autorizado")
        if not captain_authorization.strip():
            raise LedgerContractError("autorização do capitão ausente")

        def validate(events: list[dict[str, Any]]) -> None:
            rows = self._execution_rows(events, predecessor_execution_id)
            reservations = [
                row for row in rows if row.get("event_type") == "reservation"
            ]
            if len(reservations) != 1 or reservations[0].get("item_id") != item_id:
                raise LedgerContractError("predecessor não possui reserva única")
            bound_traces = {row.get("trace_id") for row in rows if row.get("trace_id")}
            if bound_traces != {predecessor_trace_id}:
                raise LedgerContractError("trace do predecessor não é único")
            failures = [
                row
                for row in rows
                if row.get("event_type") == "agent_failed"
                and row.get("post_attempted") is True
                and row.get("evaluation_status") == "technical_unavailable"
                and row.get("trace_status") == "technical_unavailable"
            ]
            if len(failures) != 1:
                raise LedgerContractError("falha técnica pré-agente não comprovada")
            if any(row.get("event_type") == "official_evaluation" for row in rows):
                raise LedgerContractError("predecessor possui avaliação oficial")
            if any(
                event.get("event_type") == "replacement_authorized"
                and event.get("execution_id") == predecessor_execution_id
                for event in events
            ):
                raise LedgerContractError("substituição já autorizada")
            if any(
                event.get("event_type") == "reservation"
                and event.get("replacement_of_execution_id") == predecessor_execution_id
                for event in events
            ):
                raise LedgerContractError("substituição já consumida")

        return self._append(
            {
                "event_type": "replacement_authorized",
                "execution_id": predecessor_execution_id,
                "item_id": item_id,
                "trace_id": predecessor_trace_id,
                "post_attempted": True,
                "evaluation_status": "technical_unavailable",
                "trace_status": "technical_unavailable",
                "detail": {
                    "reason": reason,
                    "captain_authorization": captain_authorization,
                    "proof": proof,
                },
            },
            validate,
        )

    def reserve_replacement(
        self,
        *,
        authorization_event_id: str,
        predecessor_execution_id: str,
        run_name: str,
        item_id: str,
        contract_sha256: str,
        request_identity_sha256: str,
    ) -> dict[str, Any]:
        """Reserva uma única substituição previamente autorizada no ledger."""
        execution_id = str(uuid.uuid4())

        def validate(events: list[dict[str, Any]]) -> None:
            authorizations = [
                event
                for event in events
                if event.get("event_id") == authorization_event_id
                and event.get("event_type") == "replacement_authorized"
                and event.get("execution_id") == predecessor_execution_id
                and event.get("item_id") == item_id
            ]
            if len(authorizations) != 1:
                raise LedgerContractError("autorização de substituição inválida")
            replacements = [
                event
                for event in events
                if event.get("event_type") == "reservation"
                and event.get("replacement_of_execution_id") == predecessor_execution_id
            ]
            if replacements:
                raise LedgerContractError("substituição já consumida")
            predecessor = next(
                (
                    event
                    for event in events
                    if event.get("event_type") == "reservation"
                    and event.get("execution_id") == predecessor_execution_id
                ),
                None,
            )
            if predecessor is None or predecessor.get("run_name") == run_name:
                raise LedgerContractError("run substituto deve diferir do predecessor")
            item_reservations = [
                event
                for event in events
                if event.get("event_type") == "reservation"
                and event.get("item_id") == item_id
            ]
            if item_reservations != [predecessor]:
                raise LedgerContractError("item possui reserva alheia ao predecessor")

        return self._append(
            {
                "event_type": "reservation",
                "execution_id": execution_id,
                "run_name": run_name,
                "item_id": item_id,
                "trace_id": None,
                "contract_sha256": contract_sha256,
                "request_identity_sha256": request_identity_sha256,
                "post_attempted": False,
                "evaluation_status": "pending_evaluation",
                "trace_status": "pending_trace",
                "replacement_of_execution_id": predecessor_execution_id,
                "replacement_authorization_event_id": authorization_event_id,
            },
            validate,
        )

    def authorize_remediation_replay(
        self,
        *,
        predecessor_execution_id: str,
        predecessor_trace_id: str,
        item_id: str,
        reason: str,
        captain_authorization: str,
        proof: dict[str, Any],
    ) -> dict[str, Any]:
        """Autoriza uma única repetição após falha OCR pré-agente comprovada."""
        required = {
            "failure_stage": "pre_agent",
            "failure_category": "materialized_missing",
            "technical_failure": True,
            "zero_generations": True,
            "zero_tools": True,
            "zero_judge_calls": True,
            "zero_tokens": True,
            "zero_cost": True,
        }
        if any(proof.get(key) != value for key, value in required.items()):
            raise LedgerContractError("prova da falha OCR está incompleta")
        if reason != "ocr_materialization_pre_agent":
            raise LedgerContractError("motivo de remediação não autorizado")
        if not captain_authorization.strip():
            raise LedgerContractError("autorização do capitão ausente")

        def validate(events: list[dict[str, Any]]) -> None:
            rows = self._execution_rows(events, predecessor_execution_id)
            reservations = [
                row for row in rows if row.get("event_type") == "reservation"
            ]
            if (
                len(reservations) != 1
                or reservations[0].get("item_id") != item_id
                or not reservations[0].get("replacement_of_execution_id")
            ):
                raise LedgerContractError(
                    "predecessor OCR não é a substituição esperada"
                )
            bound_traces = {row.get("trace_id") for row in rows if row.get("trace_id")}
            if bound_traces != {predecessor_trace_id}:
                raise LedgerContractError("trace OCR predecessor não é único")
            if not any(
                row.get("event_type") == "agent_failed"
                and row.get("post_attempted") is True
                and row.get("evaluation_status") == "technical_unavailable"
                for row in rows
            ):
                raise LedgerContractError("falha OCR pré-agente não comprovada")
            if any(row.get("event_type") == "official_evaluation" for row in rows):
                raise LedgerContractError("predecessor OCR possui avaliação oficial")
            if any(
                event.get("event_type") == "ocr_remediation_authorized"
                and event.get("execution_id") == predecessor_execution_id
                for event in events
            ):
                raise LedgerContractError("remediação OCR já autorizada")
            if any(
                event.get("event_type") == "reservation"
                and event.get("remediation_of_execution_id") == predecessor_execution_id
                for event in events
            ):
                raise LedgerContractError("remediação OCR já consumida")

        return self._append(
            {
                "event_type": "ocr_remediation_authorized",
                "execution_id": predecessor_execution_id,
                "item_id": item_id,
                "trace_id": predecessor_trace_id,
                "post_attempted": True,
                "evaluation_status": "technical_unavailable",
                "trace_status": "technical_unavailable",
                "detail": {
                    "reason": reason,
                    "captain_authorization": captain_authorization,
                    "proof": proof,
                },
            },
            validate,
        )

    def reserve_remediation_replay(
        self,
        *,
        authorization_event_id: str,
        predecessor_execution_id: str,
        run_name: str,
        item_id: str,
        contract_sha256: str,
        request_identity_sha256: str,
    ) -> dict[str, Any]:
        """Reserva a única repetição autorizada após a substituição OCR falhar."""
        execution_id = str(uuid.uuid4())

        def validate(events: list[dict[str, Any]]) -> None:
            authorization = next(
                (
                    event
                    for event in events
                    if event.get("event_id") == authorization_event_id
                    and event.get("event_type") == "ocr_remediation_authorized"
                    and event.get("execution_id") == predecessor_execution_id
                    and event.get("item_id") == item_id
                ),
                None,
            )
            if authorization is None:
                raise LedgerContractError("autorização da remediação OCR inválida")
            if any(
                event.get("event_type") == "reservation"
                and event.get("remediation_of_execution_id") == predecessor_execution_id
                for event in events
            ):
                raise LedgerContractError("remediação OCR já consumida")
            item_reservations = [
                event
                for event in events
                if event.get("event_type") == "reservation"
                and event.get("item_id") == item_id
            ]
            if (
                len(item_reservations) != 2
                or item_reservations[-1].get("execution_id") != predecessor_execution_id
                or item_reservations[-1].get("run_name") == run_name
            ):
                raise LedgerContractError("cadeia N=1 da remediação OCR é inválida")

        return self._append(
            {
                "event_type": "reservation",
                "execution_id": execution_id,
                "run_name": run_name,
                "item_id": item_id,
                "trace_id": None,
                "contract_sha256": contract_sha256,
                "request_identity_sha256": request_identity_sha256,
                "post_attempted": False,
                "evaluation_status": "pending_evaluation",
                "trace_status": "pending_trace",
                "replacement_of_execution_id": predecessor_execution_id,
                "remediation_of_execution_id": predecessor_execution_id,
                "replacement_authorization_event_id": authorization_event_id,
            },
            validate,
        )

    def transition(
        self,
        execution_id: str,
        *,
        event_type: str,
        trace_id: str | None = None,
        post_attempted: bool | None = None,
        evaluation_status: str | None = None,
        trace_status: str | None = None,
        artifact_sha256: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if (
            evaluation_status is not None
            and evaluation_status not in _EVALUATION_STATUSES
        ):
            raise LedgerContractError(
                f"Status de avaliação inválido: {evaluation_status}"
            )
        if trace_status is not None and trace_status not in _TRACE_STATUSES:
            raise LedgerContractError(f"Status de trace inválido: {trace_status}")

        def validate(events: list[dict[str, Any]]) -> None:
            rows = self._execution_rows(events, execution_id)
            if not rows or rows[0].get("event_type") != "reservation":
                raise LedgerContractError("Execução sem reserva pré-POST")
            if event_type == "official_evaluation" and any(
                row.get("event_type") == "official_evaluation" for row in rows
            ):
                raise LedgerContractError("Avaliação oficial duplicada")
            bound = {row.get("trace_id") for row in rows if row.get("trace_id")}
            if trace_id is not None and bound and trace_id not in bound:
                raise LedgerContractError("Trace divergente para a execução reservada")

        base = {
            "event_type": event_type,
            "execution_id": execution_id,
            "trace_id": trace_id,
            "post_attempted": post_attempted,
            "evaluation_status": evaluation_status,
            "trace_status": trace_status,
            "artifact_sha256": artifact_sha256,
            "detail": detail or {},
        }
        return self._append(base, validate)

    def authorize_full_battery(
        self,
        *,
        authorization_sha256: str,
        policy_version: str,
        reused_results: list[dict[str, Any]],
        excluded_predecessors: list[dict[str, Any]],
        missing_item_ids: list[str],
        expected_item_ids: set[str],
        fresh_all_items: bool = False,
    ) -> dict[str, Any]:
        """Autoriza uma campanha fresh com reuso válido e predecessor não comparável."""
        reused_ids = [str(row.get("item_id") or "") for row in reused_results]
        predecessor_ids = [
            str(row.get("item_id") or "") for row in excluded_predecessors
        ]
        missing_ids = [str(item_id) for item_id in missing_item_ids]
        fresh_partition_valid = (
            len(reused_ids) == 0
            and len(predecessor_ids) == 0
            and len(missing_ids) == 9
            and len(set(missing_ids)) == 9
            and set(missing_ids) == expected_item_ids
        )
        historical_partition_valid = (
            len(reused_ids) == 1
            and len(set(reused_ids)) == 1
            and len(predecessor_ids) <= 1
            and len(set(predecessor_ids)) == len(predecessor_ids)
            and len(missing_ids) == 8
            and len(set(missing_ids)) == 8
            and not set(reused_ids).intersection(missing_ids)
            and set(predecessor_ids).issubset(missing_ids)
            and set(reused_ids).union(missing_ids) == expected_item_ids
        )
        successor_partition_valid = (
            len(reused_ids) == 3
            and len(set(reused_ids)) == 3
            and len(predecessor_ids) == 0
            and len(missing_ids) == 6
            and len(set(missing_ids)) == 6
            and not set(reused_ids).intersection(missing_ids)
            and set(reused_ids).union(missing_ids) == expected_item_ids
        )
        if (
            len(authorization_sha256) != 64
            or (fresh_all_items and not fresh_partition_valid)
            or (
                not fresh_all_items
                and not historical_partition_valid
                and not successor_partition_valid
            )
        ):
            raise LedgerContractError("Partição fresh da bateria é inválida")
        for result in reused_results:
            if (
                not isinstance(result.get("trace_id"), str)
                or not isinstance(result.get("source_artifact_sha256"), str)
                or len(result["source_artifact_sha256"]) != 64
                or (
                    result.get("gate_status") != "passed"
                    and not (
                        successor_partition_valid
                        and result.get("reuse_technical_status") == "passed"
                    )
                )
                or result.get("fresh_comparable") is not True
            ):
                raise LedgerContractError("Resultado reutilizado não é válido")
        for predecessor in excluded_predecessors:
            if (
                predecessor.get("quality_status") != "passed"
                or predecessor.get("fresh_comparable") is not False
                or predecessor.get("replacement_reason")
                != "frozen_evidence_snapshot_not_fresh_comparable"
                or not isinstance(predecessor.get("source_artifact_sha256"), str)
                or len(predecessor["source_artifact_sha256"]) != 64
            ):
                raise LedgerContractError("Predecessor não comparável é inválido")

        def validate(events: list[dict[str, Any]]) -> None:
            if events:
                raise LedgerContractError("Ledger da bateria deve começar vazio")

        return self._append(
            {
                "event_type": "full_battery_authorized",
                "execution_id": None,
                "trace_id": None,
                "post_attempted": False,
                "evaluation_status": None,
                "trace_status": None,
                "detail": {
                    "authorization_sha256": authorization_sha256,
                    "policy_version": policy_version,
                    "reused_results": reused_results,
                    "excluded_predecessors": excluded_predecessors,
                    "missing_item_ids": missing_ids,
                    "partition": (
                        "0+9"
                        if fresh_all_items
                        else "3+6"
                        if successor_partition_valid
                        else "1+8"
                    ),
                    "expected_fresh_posts": len(missing_ids),
                    "sequential": True,
                    "max_concurrency": 1,
                    "inference_retries": 0,
                },
            },
            validate,
        )

    def record_excluded_predecessor(
        self,
        *,
        authorization_event_id: str,
        item_id: str,
        execution_id: str,
        trace_id: str,
        source_artifact_sha256: str,
    ) -> dict[str, Any]:
        """Preserva o predecessor frozen sem contá-lo na bateria oficial fresh."""

        def validate(events: list[dict[str, Any]]) -> None:
            authorization = next(
                (
                    event
                    for event in events
                    if event.get("event_id") == authorization_event_id
                    and event.get("event_type") == "full_battery_authorized"
                ),
                None,
            )
            predecessors = (
                authorization.get("detail", {}).get("excluded_predecessors", [])
                if authorization is not None
                else []
            )
            if not any(
                row.get("item_id") == item_id
                and row.get("execution_id") == execution_id
                and row.get("trace_id") == trace_id
                and row.get("source_artifact_sha256") == source_artifact_sha256
                for row in predecessors
            ):
                raise LedgerContractError("Predecessor excluído diverge da autorização")
            if any(
                event.get("event_type") == "frozen_predecessor_excluded"
                and event.get("item_id") == item_id
                for event in events
            ):
                raise LedgerContractError("Predecessor frozen já foi registrado")

        return self._append(
            {
                "event_type": "frozen_predecessor_excluded",
                "execution_id": execution_id,
                "item_id": item_id,
                "trace_id": trace_id,
                "post_attempted": False,
                "evaluation_status": "evaluated",
                "trace_status": "complete",
                "artifact_sha256": source_artifact_sha256,
                "detail": {
                    "authorization_event_id": authorization_event_id,
                    "replacement_reason": (
                        "frozen_evidence_snapshot_not_fresh_comparable"
                    ),
                    "historical_quality_and_cost_preserved": True,
                    "included_in_official_fresh_aggregate": False,
                },
            },
            validate,
        )

    def record_reused_official_result(
        self,
        *,
        authorization_event_id: str,
        item_id: str,
        execution_id: str,
        trace_id: str,
        source_artifact_sha256: str,
    ) -> dict[str, Any]:
        """Referencia um resultado oficial sem copiar reserva ou avaliação histórica."""

        def validate(events: list[dict[str, Any]]) -> None:
            authorization = next(
                (
                    event
                    for event in events
                    if event.get("event_id") == authorization_event_id
                    and event.get("event_type") == "full_battery_authorized"
                ),
                None,
            )
            if authorization is None:
                raise LedgerContractError("Autorização da bateria ausente")
            reused = authorization.get("detail", {}).get("reused_results", [])
            if not any(
                row.get("item_id") == item_id
                and row.get("execution_id") == execution_id
                and row.get("trace_id") == trace_id
                and row.get("source_artifact_sha256") == source_artifact_sha256
                for row in reused
            ):
                raise LedgerContractError(
                    "Referência reutilizada diverge da autorização"
                )
            if any(
                event.get("event_type") == "official_result_reused"
                and event.get("item_id") == item_id
                for event in events
            ):
                raise LedgerContractError("Resultado oficial já referenciado")

        return self._append(
            {
                "event_type": "official_result_reused",
                "execution_id": execution_id,
                "item_id": item_id,
                "trace_id": trace_id,
                "post_attempted": False,
                "evaluation_status": "evaluated",
                "trace_status": "complete",
                "artifact_sha256": source_artifact_sha256,
                "detail": {
                    "authorization_event_id": authorization_event_id,
                    "inference_reused": True,
                },
            },
            validate,
        )

    def reserve_full_battery_item(
        self,
        *,
        authorization_event_id: str,
        run_name: str,
        item_id: str,
        contract_sha256: str,
        request_identity_sha256: str,
    ) -> dict[str, Any]:
        """Reserva um item faltante autorizado, uma única vez e antes do POST."""
        execution_id = str(uuid.uuid4())

        def validate(events: list[dict[str, Any]]) -> None:
            authorization = next(
                (
                    event
                    for event in events
                    if event.get("event_id") == authorization_event_id
                    and event.get("event_type") == "full_battery_authorized"
                ),
                None,
            )
            if authorization is None:
                raise LedgerContractError("Autorização da bateria ausente")
            if item_id not in authorization.get("detail", {}).get(
                "missing_item_ids", []
            ):
                raise LedgerContractError("Item não pertence à bateria autorizada")
            if any(
                event.get("item_id") == item_id
                and event.get("event_type") in {"reservation", "official_result_reused"}
                for event in events
            ):
                raise LedgerContractError("Item da bateria já foi consumido")
            if any(
                event.get("event_type") == "reservation"
                and not any(
                    row.get("event_type")
                    in {
                        "post_completed",
                        "agent_failed",
                        "battery_item_completed",
                        "battery_item_failed_classified",
                        "battery_item_invalidated_for_retry",
                    }
                    for row in self._execution_rows(
                        events, str(event.get("execution_id"))
                    )
                )
                for event in events
            ):
                raise LedgerContractError("Bateria contém item anterior em andamento")

        return self._append(
            {
                "event_type": "reservation",
                "execution_id": execution_id,
                "run_name": run_name,
                "item_id": item_id,
                "trace_id": None,
                "contract_sha256": contract_sha256,
                "request_identity_sha256": request_identity_sha256,
                "post_attempted": False,
                "evaluation_status": "pending_evaluation",
                "trace_status": "pending_trace",
                "full_battery_authorization_event_id": authorization_event_id,
            },
            validate,
        )

    def reserve_full_battery_retry(
        self,
        *,
        authorization_event_id: str,
        predecessor_execution_id: str,
        run_name: str,
        item_id: str,
        contract_sha256: str,
        request_identity_sha256: str,
    ) -> dict[str, Any]:
        """Reserva uma repetição após tentativa técnica inválida e comprovada."""
        execution_id = str(uuid.uuid4())

        def validate(events: list[dict[str, Any]]) -> None:
            authorization = next(
                (
                    event
                    for event in events
                    if event.get("event_id") == authorization_event_id
                    and event.get("event_type") == "full_battery_authorized"
                ),
                None,
            )
            predecessor = next(
                (
                    event
                    for event in events
                    if event.get("event_type") == "reservation"
                    and event.get("execution_id") == predecessor_execution_id
                    and event.get("item_id") == item_id
                ),
                None,
            )
            if (
                authorization is None
                or item_id
                not in authorization.get("detail", {}).get("missing_item_ids", [])
                or predecessor is None
                or predecessor.get("full_battery_authorization_event_id")
                != authorization_event_id
            ):
                raise LedgerContractError("Predecessor da repetição não é autorizado")
            predecessor_rows = self._execution_rows(events, predecessor_execution_id)
            if not any(
                row.get("event_type") == "battery_item_invalidated_for_retry"
                and row.get("post_attempted") is True
                for row in predecessor_rows
            ):
                raise LedgerContractError("Tentativa inválida não foi comprovada")
            item_execution_ids = {
                str(event["execution_id"])
                for event in events
                if event.get("event_type") == "reservation"
                and event.get("item_id") == item_id
            }
            if any(
                event.get("event_type") == "official_evaluation"
                and str(event.get("execution_id")) in item_execution_ids
                for event in events
            ):
                raise LedgerContractError("Item já possui avaliação oficial")
            if any(
                event.get("event_type") == "reservation"
                and event.get("retry_of_execution_id") == predecessor_execution_id
                for event in events
            ):
                raise LedgerContractError("Repetição técnica já foi consumida")
            if any(
                event.get("event_type") == "reservation"
                and not any(
                    row.get("event_type")
                    in {
                        "post_completed",
                        "agent_failed",
                        "battery_item_completed",
                        "battery_item_failed_classified",
                        "battery_item_invalidated_for_retry",
                    }
                    for row in self._execution_rows(
                        events, str(event.get("execution_id"))
                    )
                )
                for event in events
            ):
                raise LedgerContractError("Bateria contém item anterior em andamento")

        return self._append(
            {
                "event_type": "reservation",
                "execution_id": execution_id,
                "run_name": run_name,
                "item_id": item_id,
                "trace_id": None,
                "contract_sha256": contract_sha256,
                "request_identity_sha256": request_identity_sha256,
                "post_attempted": False,
                "evaluation_status": "pending_evaluation",
                "trace_status": "pending_trace",
                "full_battery_authorization_event_id": authorization_event_id,
                "retry_of_execution_id": predecessor_execution_id,
            },
            validate,
        )

    def record_gate_reclassification(
        self,
        *,
        execution_id: str,
        trace_id: str,
        policy_version: str,
        authorization: str,
        source_artifact_sha256: str,
        derived_artifact_sha256: str,
    ) -> dict[str, Any]:
        """Anexa derivação de gate sem criar avaliação oficial ou nova execução."""
        for value in (source_artifact_sha256, derived_artifact_sha256):
            if not isinstance(value, str) or len(value) != 64:
                raise LedgerContractError("Hash da reclassificação é inválido")
        if not policy_version.strip() or not authorization.strip():
            raise LedgerContractError("Política/autorização da reclassificação ausente")

        def validate(events: list[dict[str, Any]]) -> None:
            rows = self._execution_rows(events, execution_id)
            if not rows or rows[0].get("event_type") != "reservation":
                raise LedgerContractError("Reclassificação sem execução reservada")
            bound = {row.get("trace_id") for row in rows if row.get("trace_id")}
            if bound != {trace_id}:
                raise LedgerContractError("Trace da reclassificação divergiu")
            official = [
                row for row in rows if row.get("event_type") == "official_evaluation"
            ]
            if len(official) != 1:
                raise LedgerContractError(
                    "Reclassificação exige uma avaliação oficial preservada"
                )
            if not any(row.get("event_type") == "trace_complete" for row in rows):
                raise LedgerContractError("Reclassificação exige trace completo")
            if any(
                row.get("event_type") == "gate_reclassified"
                and row.get("detail", {}).get("policy_version") == policy_version
                for row in rows
            ):
                raise LedgerContractError("Política de gate já aplicada à execução")

        return self._append(
            {
                "event_type": "gate_reclassified",
                "execution_id": execution_id,
                "trace_id": trace_id,
                "post_attempted": None,
                "evaluation_status": "evaluated",
                "trace_status": "complete",
                "artifact_sha256": derived_artifact_sha256,
                "detail": {
                    "policy_version": policy_version,
                    "authorization": authorization,
                    "source_artifact_sha256": source_artifact_sha256,
                    "derived_without_inference": True,
                    "official_evaluation_reused": True,
                },
            },
            validate,
        )

    def official_key(self, execution_id: str) -> tuple[str, str, str, str] | None:
        """Retorna (run,item,trace,contract) somente após vínculo completo."""
        rows = self._execution_rows(self.events(), execution_id)
        if not rows:
            return None
        reservation = rows[0]
        trace_id = next(
            (row.get("trace_id") for row in reversed(rows) if row.get("trace_id")), None
        )
        if trace_id is None:
            return None
        return (
            reservation["run_name"],
            reservation["item_id"],
            trace_id,
            reservation["contract_sha256"],
        )


def assert_private_tree(root: Path) -> None:
    """Gate final de retenção: diretórios 0700, arquivos 0600, sem symlink."""
    for path in (root, *root.rglob("*")):
        if path.is_symlink():
            raise LedgerContractError(
                f"Symlink proibido no diretório protegido: {path}"
            )
        mode = stat.S_IMODE(path.stat().st_mode)
        expected = 0o700 if path.is_dir() else 0o600
        if mode != expected:
            raise LedgerContractError(f"Permissão inválida em {path}: {mode:o}")
