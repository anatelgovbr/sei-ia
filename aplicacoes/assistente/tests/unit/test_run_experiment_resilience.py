"""Regressão para indisponibilidade transitória do Langfuse no benchmark."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

_EXP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "experimentos",
    "latencia-session-vs-classico",
)
sys.path.insert(0, os.path.join(_EXP_DIR, "scripts", "shared"))
sys.path.insert(0, os.path.join(_EXP_DIR, "scripts", "session-classico"))

import run_experiment  # noqa: E402


class _BrokenDatasetItem:
    input = {"text": "Pergunta"}
    expected_output = {}
    metadata = {"qid": "Q17"}

    def run(self, **_kwargs):
        raise httpx.ReadTimeout("Langfuse lento")


def test_run_item_preserva_medicao_quando_dataset_run_langfuse_falha(monkeypatch):
    monkeypatch.setattr(
        run_experiment,
        "stream_endpoint",
        lambda *_args, **_kwargs: {
            "ttfc_s": 1.0,
            "total_s": 2.0,
            "content": "Resposta disponível",
            "content_chars": 19,
            "status_frames": 0,
            "reasoning_frames": 0,
            "error": None,
            "benchmark_metrics": None,
        },
    )
    monkeypatch.setattr(
        run_experiment,
        "judge_response",
        lambda *_args, **_kwargs: type(
            "Judge",
            (),
            {
                "scores_numeric": {"overall": 0.8},
                "scores_bool": {},
                "rationale": "ok",
                "usage": None,
            },
        )(),
    )

    result = run_experiment.run_item(
        lf=object(),
        item=_BrokenDatasetItem(),
        run_name="test",
        judge_cfg=object(),
        timeout=10,
        endpoints={"session": "/llm_lang/session_stream"},
    )

    endpoint = result["endpoints"]["session"]
    assert endpoint["latency"]["total_s"] == 2.0
    assert endpoint["trace_id"] is not None
    assert result["langfuse_errors"][0]["stage"] == "dataset_run_item_create"


def test_run_item_model_campaign_envia_no_cache_sem_alterar_modo_historico(
    monkeypatch,
):
    payloads = []

    def capture_stream(_path, payload, _timeout, *, trace_id):
        payloads.append(dict(payload))
        return {
            "ttfc_s": None,
            "total_s": 0.1,
            "content": "",
            "content_chars": 0,
            "status_frames": 0,
            "reasoning_frames": 0,
            "error": "erro esperado do stub",
            "benchmark_metrics": None,
        }

    monkeypatch.setattr(run_experiment, "stream_endpoint", capture_stream)

    common = {
        "lf": object(),
        "item": _BrokenDatasetItem(),
        "run_name": "test",
        "judge_cfg": object(),
        "timeout": 10,
        "endpoints": {"session": "/llm_lang/session_stream"},
    }
    run_experiment.run_item(
        **common,
        model_campaign=Mock(spec=run_experiment.ModelCampaign),
    )
    run_experiment.run_item(**common)

    assert payloads[0]["no_cache"] is True
    assert "no_cache" not in payloads[1]


def test_resume_trace_metrics_reprocessa_checkpoint_sem_inferencia(
    monkeypatch, tmp_path: Path
):
    result = {
        "qid": "Q17",
        "endpoints": {"session": {"trace_id": "trace-1", "metrics": None}},
    }
    (tmp_path / "progress.jsonl").write_text(
        json.dumps(result) + "\n", encoding="utf-8"
    )
    (tmp_path / "run.json").write_text(
        json.dumps({"run_name": "test"}), encoding="utf-8"
    )

    def collect(_lf, results, **_kwargs):
        results[0]["endpoints"]["session"]["metrics"] = {"tokens_by_model": {}}

    written = {}

    def write(directory, run_context, results, rate_card):
        written.update(
            {
                "directory": directory,
                "run_context": run_context,
                "results": results,
                "rate_card": rate_card,
            }
        )
        return {"summary": tmp_path / "summary.json"}

    monkeypatch.setattr(run_experiment, "collect_trace_metrics", collect)
    monkeypatch.setattr(run_experiment, "write_artifacts", write)

    summary = run_experiment._resume_trace_metrics(
        lf=Mock(),
        artifact_dir=tmp_path,
        rate_card_path=Path("rate-card.json"),
        max_wait_s=900,
        profile_deployments={"standard": "terra", "mini": "luna"},
    )

    assert summary == {
        "result_count": 1,
        "trace_count": 1,
        "metrics_complete": True,
        "artifacts": {"summary": str(tmp_path / "summary.json")},
    }
    assert written["results"][0]["endpoints"]["session"]["metrics"] is not None


def test_resume_trace_metrics_falha_fechado_se_trace_continuar_ausente(
    monkeypatch, tmp_path: Path
):
    result = {
        "qid": "Q17",
        "endpoints": {"session": {"trace_id": "trace-1", "metrics": None}},
    }
    (tmp_path / "progress.jsonl").write_text(
        json.dumps(result) + "\n", encoding="utf-8"
    )
    (tmp_path / "run.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        run_experiment, "collect_trace_metrics", lambda *_args, **_kwargs: None
    )

    with pytest.raises(RuntimeError, match="Trace metrics continuam ausentes"):
        run_experiment._resume_trace_metrics(
            lf=Mock(),
            artifact_dir=tmp_path,
            rate_card_path=Path("rate-card.json"),
            max_wait_s=900,
            profile_deployments={"standard": "terra", "mini": "luna"},
        )


def test_resume_trace_metrics_valida_credenciais_langfuse(monkeypatch, tmp_path: Path):
    client = Mock()
    campaign = Mock()
    campaign.profile_deployments = {"standard": "terra", "mini": "luna"}
    monkeypatch.setattr(run_experiment, "Langfuse", lambda **_kwargs: client)
    monkeypatch.setattr(run_experiment, "campaign_requested", lambda _args: True)
    monkeypatch.setattr(run_experiment, "campaign_from_args", lambda _args: campaign)
    monkeypatch.setattr(
        run_experiment,
        "_resume_trace_metrics",
        lambda **_kwargs: {
            "result_count": 1,
            "trace_count": 1,
            "metrics_complete": True,
            "artifacts": {},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_experiment.py",
            "--resume-trace-metrics-from",
            str(tmp_path),
            "--reuse-historical-baseline",
        ],
    )

    assert run_experiment.main() == 0
    client.auth_check.assert_called_once_with()


def test_load_env_aprovado_sobrepoe_langfuse_herdado(monkeypatch, tmp_path: Path):
    app = tmp_path / "app"
    worktree = tmp_path / "worktree"
    app.mkdir()
    worktree.mkdir()
    (app / ".env").write_text(
        "\n".join(
            (
                "LANGFUSE_URL=https://approved.invalid",
                "LANGFUSE_PUBLIC_KEY=approved-public",
                "LANGFUSE_SECRET_KEY=approved-secret",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LANGFUSE_URL", "https://inherited.invalid")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "inherited-public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "inherited-secret")
    monkeypatch.setenv("LF_HOST", "https://lf-inherited.invalid")
    monkeypatch.setenv("LF_PUBLIC", "lf-inherited-public")
    monkeypatch.setenv("LF_SECRET", "lf-inherited-secret")

    run_experiment._load_env(app=app, worktree=worktree)

    assert os.environ["LF_HOST"] == "https://approved.invalid"
    assert os.environ["LF_PUBLIC"] == "approved-public"
    assert os.environ["LF_SECRET"] == "approved-secret"


def test_sse_sem_end_terminal_e_invalido():
    frames = [
        'data: {"type":"content","data":"resposta"}',
        'data: {"type":"metadata","data":{"no_cache":true}}',
    ]

    result = run_experiment._parse_sse_lines(frames, 0.0, float("inf"))

    assert result["terminal_type"] is None
    assert result["error"] == "truncated_sse_missing_terminal_end"


def test_excecao_depois_de_post_started_nao_repete_inferencia(
    monkeypatch, tmp_path: Path
):
    from benchmark_checkpoint import SessionExecutionLedger

    calls = 0

    def fail_after_start(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("conexão caiu depois do POST")

    monkeypatch.setattr(run_experiment, "stream_endpoint", fail_after_start)
    ledger = SessionExecutionLedger(tmp_path / "session-execution-ledger.jsonl")
    ledger.reserve_topics(["Q17"], topic_ids={"Q17": 812_345_678})

    result = run_experiment.run_item(
        lf=object(),
        item=_BrokenDatasetItem(),
        run_name="test",
        judge_cfg=object(),
        timeout=10,
        endpoints={"session": "/llm_lang/session_stream"},
        model_campaign=Mock(spec=run_experiment.ModelCampaign),
        fresh_topico=812_345_678,
        execution_ledger=ledger,
        cell_id="Q17",
    )

    assert calls == 1
    assert result["endpoints"]["session"]["recovery_only"] is True
    assert ledger.post_started_count("Q17") == 1


def test_fail_fast_bloqueia_celula_seguinte_apos_resultado_invalido():
    invalid = {
        "endpoints": {
            "session": {
                "latency": {"error": "truncated_sse_missing_terminal_end"},
                "judge": None,
            }
        }
    }

    assert run_experiment._result_allows_next_cell(invalid) is False


def test_bateria_incompleta_ou_sem_metricas_nao_e_considerada_completa():
    complete = {
        "endpoints": {
            "session": {
                "latency": {"error": None},
                "terminal_type": "end",
                "judge": {},
                "metrics": {
                    "tokens_by_model": {
                        "model": {
                            "input": 10,
                            "cache_read": 2,
                            "output": 3,
                            "reasoning": 1,
                            "total": 15,
                            "generations": 1,
                            "cache_write": None,
                        }
                    }
                },
            }
        }
    }

    assert run_experiment._campaign_results_complete([complete], 1) is True
    empty_tokens = {
        **complete,
        "endpoints": {
            "session": {
                **complete["endpoints"]["session"],
                "metrics": {"tokens_by_model": {}},
            }
        },
    }
    assert run_experiment._campaign_results_complete([empty_tokens], 1) is False
    invalid_counter = {
        **complete,
        "endpoints": {
            "session": {
                **complete["endpoints"]["session"],
                "metrics": {
                    "tokens_by_model": {
                        "model": {
                            **complete["endpoints"]["session"]["metrics"][
                                "tokens_by_model"
                            ]["model"],
                            "generations": "1",
                        }
                    }
                },
            }
        },
    }
    assert run_experiment._campaign_results_complete([invalid_counter], 1) is False
    incomplete_metrics = {
        **complete,
        "endpoints": {
            "session": {
                **complete["endpoints"]["session"],
                "metrics": None,
            }
        },
    }
    assert run_experiment._campaign_results_complete([incomplete_metrics], 1) is False
    assert run_experiment._campaign_results_complete([complete], 2) is False


def test_ocr_session_fica_em_bucket_luna_e_valida_modelo_canonico():
    tokens = {"seiia-ds-gpt-luna": {"input": 10, "output": 2}}
    calls = [
        {
            "call_key_sha256": "a" * 64,
            "role": "ocr",
            "deployment": "seiia-ds-gpt-luna",
            "reported_model": "gpt-5.6-luna",
            "usage": {
                "prompt_tokens": 100,
                "cached_tokens": 20,
                "cache_write_tokens": None,
                "completion_tokens": 30,
                "reasoning_tokens": 5,
            },
        }
    ]

    ocr = run_experiment._merge_ocr_usage(
        tokens,
        calls,
        expected_deployment="seiia-ds-gpt-luna",
        expected_canonical_model="gpt-5.6-luna",
    )

    assert ocr["seiia-ds-gpt-luna"]["ocr_calls"] == 1
    assert tokens["seiia-ds-gpt-luna"]["input"] == 90
    assert tokens["seiia-ds-gpt-luna"]["output"] == 32
    assert tokens["seiia-ds-gpt-luna"]["cache_write"] is None


def test_ocr_usage_soma_cache_write_ao_trace_sem_perder_telemetria():
    tokens = {
        "seiia-ds-gpt-luna": {
            "input": 10,
            "cache_read": 2,
            "cache_write": 40,
            "output": 2,
            "reasoning": 1,
            "total": 14,
        }
    }
    calls = [
        {
            "call_key_sha256": "a" * 64,
            "role": "ocr",
            "deployment": "seiia-ds-gpt-luna",
            "reported_model": "gpt-5.6-luna",
            "usage": {
                "prompt_tokens": 10,
                "cached_tokens": 2,
                "cache_write_tokens": 60,
                "completion_tokens": 3,
                "reasoning_tokens": 1,
            },
        }
    ]

    run_experiment._merge_ocr_usage(
        tokens,
        calls,
        expected_deployment="seiia-ds-gpt-luna",
        expected_canonical_model="gpt-5.6-luna",
    )

    assert tokens["seiia-ds-gpt-luna"]["cache_write"] == 100


def test_ocr_session_divergente_invalida_celula_antes_do_judge(monkeypatch):
    campaign = SimpleNamespace(
        mini=SimpleNamespace(
            deployment="seiia-ds-gpt-luna", canonical_model="gpt-5.6-luna"
        )
    )
    monkeypatch.setattr(
        run_experiment,
        "stream_endpoint",
        lambda *_args, **_kwargs: {
            "ttfc_s": 0.1,
            "total_s": 0.2,
            "content": "Resposta",
            "content_chars": 8,
            "status_frames": 0,
            "reasoning_frames": 0,
            "error": None,
            "terminal_type": "end",
            "frame_types": ["content", "end"],
            "benchmark_metrics": None,
            "benchmark_contract": {
                "no_cache": True,
                "benchmark_process_source": "sei_no_cache",
                "benchmark_session_reset": True,
            },
            "benchmark_ocr_usage": [
                {
                    "call_key_sha256": "a" * 64,
                    "role": "ocr",
                    "deployment": "seiia-ds-gpt-luna",
                    "reported_model": "modelo-inesperado",
                    "usage": {},
                }
            ],
        },
    )
    judge = Mock()
    monkeypatch.setattr(run_experiment, "judge_response", judge)

    result = run_experiment.run_item(
        lf=object(),
        item=_BrokenDatasetItem(),
        run_name="test",
        judge_cfg=object(),
        timeout=10,
        endpoints={"session": "/llm_lang/session_stream"},
        model_campaign=campaign,
    )

    endpoint = result["endpoints"]["session"]
    assert endpoint["latency"]["error"] == "benchmark_ocr_identity_mismatch"
    assert endpoint["judge"] is None
    judge.assert_not_called()
    assert run_experiment._result_allows_next_cell(result) is False
