"""Checkpoints duráveis para não perder uma bateria longa no meio."""

from __future__ import annotations

import json
import os
import sys

import pytest

_EXP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "experimentos",
    "latencia-session-vs-classico",
)
sys.path.insert(0, os.path.join(_EXP_DIR, "scripts", "shared"))
sys.path.insert(0, os.path.join(_EXP_DIR, "scripts", "session-classico"))

from benchmark_checkpoint import (  # noqa: E402
    SessionExecutionLedger,
    SessionLedgerError,
    append_progress,
    read_progress,
)


def test_append_progress_persiste_cada_item_em_jsonl(tmp_path):
    path = tmp_path / "progress.jsonl"
    append_progress(path, {"qid": "Q17", "endpoints": {"session": {}}})
    append_progress(path, {"qid": "Q19", "endpoints": {"classic": {}}})

    assert [item["qid"] for item in read_progress(path)] == ["Q17", "Q19"]
    assert [json.loads(line)["qid"] for line in path.read_text().splitlines()] == [
        "Q17",
        "Q19",
    ]


def test_session_ledger_reserva_topicos_e_post_de_forma_append_only(tmp_path):
    path = tmp_path / "session-execution-ledger.jsonl"
    ledger = SessionExecutionLedger(path)

    topics = ledger.reserve_topics(
        ["Q01", "Q02"],
        topic_ids={"Q01": 811_000_001, "Q02": 811_000_002},
        historical_topic_ids={810_999_999},
    )
    ledger.reserve_post("Q01", topics["Q01"])
    ledger.mark_post_started("Q01")

    assert topics == {"Q01": 811_000_001, "Q02": 811_000_002}
    assert ledger.post_started_count("Q01") == 1
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700

    with pytest.raises(SessionLedgerError, match="POST já iniciado"):
        ledger.reserve_post("Q01", topics["Q01"])


def test_session_ledger_recusa_topico_historico(tmp_path):
    ledger = SessionExecutionLedger(tmp_path / "session-execution-ledger.jsonl")

    with pytest.raises(SessionLedgerError, match="tópico já usado"):
        ledger.reserve_topics(
            ["Q01"],
            topic_ids={"Q01": 811_000_001},
            historical_topic_ids={811_000_001},
        )
