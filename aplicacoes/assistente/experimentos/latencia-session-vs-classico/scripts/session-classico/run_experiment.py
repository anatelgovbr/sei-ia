"""Runner do experimento session vs stream tradicional sobre o dataset `comparativo`.

Para cada item do dataset:
  - dispara os 2 endpoints LOCAIS (app que ja roda em container) com item.input,
    parseando o SSE e medindo latencia (TTFC/total) + chars/frames;
  - linka 1 trace Langfuse por (item, endpoint) via item.run(run_name=...) — fica
    associado ao dataset run no projeto;
  - chama o juiz (judge.judge_response) e emite as 6 metricas como scores no trace;
  - emite o score derivado `win_session` por item (qual endpoint teve overall maior).

Ambiente: bate no app rodando em https://127.0.0.1:8088 (TLS self-signed -> verify=False
SO para esse host local; nao e fallback de producao, e config de cliente p/ cert self-signed).
Proxy do juiz e Langfuse vem do .env raiz (rhgicdpdin02). Rodar via uv de dentro de
aplicacoes/assistente, com as vars do .env raiz exportadas (LITELLM_*, LF_*).

Sem fallback: se um endpoint falhar, registra o erro real no trace e nas metricas como
0/erro; nao tenta caminho alternativo.

Uso:
    uv run python experimentos/latencia-session-vs-classico/scripts/session-classico/run_experiment.py --only Q01   # dry-run
    uv run python experimentos/latencia-session-vs-classico/scripts/session-classico/run_experiment.py --decision-suite
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
EXPERIMENT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(EXPERIMENT_ROOT / "scripts" / "shared"))

from model_campaign import (  # noqa: E402
    ModelCampaign,
    add_model_campaign_args,
    campaign_from_args,
    campaign_requested,
    plan_session_cells,
)


def _load_env(*, app: Path | None = None, worktree: Path | None = None) -> None:
    """Carrega a mesma configuração de credenciais usada pelo upsert do dataset."""
    app = app or EXPERIMENT_ROOT.parents[1]
    worktree = worktree or EXPERIMENT_ROOT.parents[3]
    for env_file in (worktree / "security.env", worktree / ".env", app / ".env"):
        if env_file.exists():
            load_dotenv(env_file, override=env_file == app / ".env")
    os.environ["LF_SECRET"] = os.environ.get("LANGFUSE_SECRET_KEY", "")
    os.environ["LF_PUBLIC"] = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    os.environ["LF_HOST"] = os.environ.get("LANGFUSE_URL") or os.environ.get(
        "LANGFUSE_HOST", ""
    )
    # Alguns shells de desenvolvimento exportam o placeholder "not-needed". Para
    # o juiz externo isso vira uma credencial inválida; use a chave padrão real
    # carregada da configuração quando o placeholder estiver presente.
    if os.environ.get("LITELLM_PROXY_API_KEY") in (None, "", "not-needed"):
        standard_key = os.environ.get("LITELLM_STANDARD_API_KEY")
        if standard_key:
            os.environ["LITELLM_PROXY_API_KEY"] = standard_key


_load_env()


def _apply_model_campaign_before_settings_import() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    add_model_campaign_args(parser)
    parser.add_argument("--rate-card")
    args, _ = parser.parse_known_args()
    if campaign_requested(args):
        campaign_from_args(args).apply_environment()


_apply_model_campaign_before_settings_import()

# PD override ANTES de importar o app/settings: o endpoint classico materializa via
# ETL/retrieval que cai em SEI_ADDRESS (envs.py usa SEI_ADDRESS como fallback de
# SEI_API_DB_ADDRESS). No .env, SEI_ADDRESS resolve para seisu (staging) -> o classico
# devolve "documentos sem conteudo" (204). Forcamos os dois enderecos para PD aqui.
PD_SEI = "https://sei.anatel.gov.br"
PD_SEI_API_DB = "https://sei.anatel.gov.br/sei/controlador_ws.php"
if os.environ.get("EXP_FORCE_PD", "1") == "1":
    os.environ["SEI_ADDRESS"] = PD_SEI
    os.environ["SEI_API_DB_ADDRESS"] = PD_SEI_API_DB

# Redis: o .env aponta redis://infra-redis:6379 (hostname Docker) que NAO resolve do
# host sob TestClient -> circuit breaker abre e o cache do classico desliga. O mesmo
# Redis do SEI-IA esta publicado no host em localhost:8091. Mesma logica do SEI_ADDRESS:
# apontar pro servico publicado pra o app ficar saudavel (cache ligado). Guarded por flag.
if os.environ.get("EXP_FORCE_REDIS", "1") == "1":
    os.environ["REDIS_URI"] = os.environ.get(
        "EXP_REDIS_URI", "redis://localhost:8091/0"
    )

# Liga a instrumentacao Langfuse SO no processo do experimento (guarded por flag).
# O app le ASSISTENTE_USE_LANGFUSE + LANGFUSE_{PUBLIC_KEY,SECRET_KEY,URL}. Apontamos
# para o MESMO projeto do experimento (onde o juiz grava os scores) para que a arvore
# interna e os scores caiam no mesmo trace. Nao toca .env de producao.
if os.environ.get("EXP_INSTRUMENT", "1") == "1":
    os.environ["ASSISTENTE_USE_LANGFUSE"] = "true"
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", os.environ.get("LF_PUBLIC", ""))
    os.environ.setdefault("LANGFUSE_SECRET_KEY", os.environ.get("LF_SECRET", ""))
    os.environ.setdefault("LANGFUSE_URL", os.environ.get("LF_HOST", ""))
    # Auto-instrument OTel de httpx+requests SO no processo do experimento: captura
    # o tempo de rede (send/receive) de cada chamada HTTP — SEI API, OCR, proxy LLM —
    # na mesma timeline. Em prod (sem esta flag) os scopes seguem bloqueados.
    os.environ.setdefault("EXP_OTEL_HTTP", "1")

import httpx  # noqa: E402
from langfuse import Langfuse  # noqa: E402

from sei_ia.configs.langfuse_config import truncate_large_fields  # noqa: E402

sys.path.insert(0, str(SCRIPT_DIR))
from benchmark_checkpoint import (  # noqa: E402
    SessionExecutionLedger,
    append_progress,
    historical_topic_ids,
)
from benchmark_reporting import cited_urls, write_artifacts  # noqa: E402
from judge import JudgeConfig, emit_scores, judge_response  # noqa: E402
from trace_metrics import (  # noqa: E402
    analyze_trace,
    emit_metrics,
    emit_tokens_by_model,
)

HERE = EXPERIMENT_ROOT
DECISION_SUITE_PATH = (
    HERE / "dataset" / "session-classico" / "benchmark-decision-v2.json"
)
DATASET_NAME = os.environ.get("EXP_DATASET_NAME", "benchmark-decision-v2")
APP_BASE = os.environ.get("EXP_APP_BASE", "https://127.0.0.1:8088")
ENDPOINTS = {
    "session": "/llm_lang/session_stream",
    "classic": "/llm_lang/stream",
}


def _positive_float_env(name: str, default: float) -> float:
    """Lê um timeout opcional sem aceitar zero, negativo ou valor inválido."""
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


DEFAULT_LANGFUSE_TIMEOUT_S = _positive_float_env("EXP_LANGFUSE_TIMEOUT", 30.0)
DEFAULT_TRACE_METRICS_WAIT_S = _positive_float_env("EXP_LANGFUSE_TRACE_MAX_WAIT", 180.0)

# transporte: "testclient" (in-process FastAPI carregando o .env + SEI_ADDRESS->PD)
# ou "http" (bate no container ja rodando em APP_BASE). Default: testclient.
TRANSPORT = os.environ.get("EXP_TRANSPORT", "testclient")
_TEST_CLIENT = None


def _decision_qids() -> set[str]:
    data = json.loads(DECISION_SUITE_PATH.read_text(encoding="utf-8"))
    return set(data["qids"])


def _git_commit() -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        return subprocess.check_output(  # noqa: S603 - git vem de shutil.which
            [git, "rev-parse", "HEAD"], cwd=HERE.parents[3], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _get_test_client():
    """Sobe a app FastAPI in-process via TestClient (importa apos o override de env)."""
    global _TEST_CLIENT
    if _TEST_CLIENT is None:
        from starlette.testclient import TestClient

        from sei_ia.main import app

        _TEST_CLIENT = TestClient(app)
    return _TEST_CLIENT


def _validate_http_model_campaign(campaign: ModelCampaign) -> None:
    response = httpx.get(
        APP_BASE + "/llm_lang/session_benchmark_preflight",
        verify=False,
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    expected = {
        "session_main_model_profile": "standard",
        "session_main_model": campaign.standard.deployment,
        "session_classifier_model_profile": "mini",
        "session_classifier_model": campaign.mini.deployment,
        "session_explorer_model_profile": "nano",
        "session_explorer_model": campaign.nano.deployment,
        "session_ocr_model": campaign.mini.deployment,
        "session_reasoning_effort_requested": campaign.reasoning_effort,
        "session_main_model_client_retries": 0,
        "session_main_model_context_window_tokens": (
            campaign.standard_context_window_tokens
        ),
        "session_classifier_model_context_window_tokens": (
            campaign.mini_context_window_tokens
        ),
        "session_explorer_model_context_window_tokens": (
            campaign.nano_context_window_tokens
        ),
        "benchmark_no_cache_required": True,
        "benchmark_process_source": "sei_no_cache",
    }
    if not campaign.ocr_supports_image_url:
        raise RuntimeError("Campanha não declara suporte image_url para OCR Luna")
    if any(payload.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Preflight HTTP diverge da configuração de modelos")


def _parse_sse_lines(  # noqa: C901, PLR0912, PLR0915 - protocolo SSE explícito
    lines, t0: float, deadline_s: float, *, raw_sse_path: Path | None = None
) -> dict:
    """Parser SSE com deadline absoluto, inclusive quando há heartbeats."""
    ttfc = None
    content_parts: list[str] = []
    n_status = n_reasoning = 0
    benchmark_metrics = None
    benchmark_ocr_usage = None
    benchmark_contract = None
    err = None
    terminal_type = None
    frame_types: list[str] = []
    raw_handle = None
    if raw_sse_path is not None:
        raw_sse_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        raw_sse_path.parent.chmod(0o700)
        raw_handle = raw_sse_path.open("a", encoding="utf-8")
        raw_sse_path.chmod(0o600)
    try:
        for raw in lines:
            if time.perf_counter() - t0 >= deadline_s:
                err = f"deadline_exceeded: {deadline_s:.0f}s"
                break
            line = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
            if raw_handle is not None:
                raw_handle.write(line + ("" if line.endswith("\n") else "\n"))
                raw_handle.flush()
                os.fsync(raw_handle.fileno())
            if not line or not line.startswith("data: "):
                continue
            frame = json.loads(line[6:])
            ft = frame.get("type")
            frame_types.append(str(ft))
            if ft == "status":
                n_status += 1
            elif ft == "reasoning":
                n_reasoning += 1
            elif ft == "content":
                if ttfc is None:
                    ttfc = round(time.perf_counter() - t0, 2)
                content_parts.append(frame.get("data", ""))
            elif ft == "error":
                terminal_type = "error"
                err = f"{frame.get('status_code')}: {frame.get('detail')}"
            elif ft == "end" and terminal_type != "error":
                terminal_type = "end"
            elif ft == "metadata":
                data = frame.get("data") or {}
                if isinstance(data, dict):
                    benchmark_metrics = data.get("benchmark_metrics")
                    benchmark_ocr_usage = data.get("benchmark_ocr_usage")
                    benchmark_contract = {
                        key: data.get(key)
                        for key in (
                            "no_cache",
                            "benchmark_process_source",
                            "benchmark_session_reset",
                        )
                    }
    finally:
        if raw_handle is not None:
            raw_handle.close()
    if terminal_type is None and err is None:
        err = "truncated_sse_missing_terminal_end"
    content = "".join(content_parts)
    return {
        "ttfc_s": ttfc,
        "total_s": round(time.perf_counter() - t0, 2),
        "content": content,
        "content_chars": len(content),
        "status_frames": n_status,
        "reasoning_frames": n_reasoning,
        "error": err,
        "terminal_type": terminal_type,
        "frame_types": frame_types,
        "benchmark_metrics": benchmark_metrics,
        "benchmark_ocr_usage": benchmark_ocr_usage,
        "benchmark_contract": benchmark_contract,
    }


def _err_result(t0: float, status: int, body: str) -> dict:
    return {
        "ttfc_s": None,
        "total_s": round(time.perf_counter() - t0, 2),
        "content": "",
        "content_chars": 0,
        "status_frames": 0,
        "reasoning_frames": 0,
        "error": f"HTTP {status}: {body[:300]}",
        "terminal_type": None,
        "frame_types": [],
        "benchmark_metrics": None,
        "benchmark_ocr_usage": None,
        "benchmark_contract": None,
    }


def stream_endpoint(
    path: str,
    payload: dict,
    timeout: float,
    trace_id: str | None = None,
    *,
    raw_sse_path: Path | None = None,
) -> dict:
    """Dispara um endpoint SSE pelo transporte ativo, mede latencia e coleta content.

    Se `trace_id` vier, manda no header X-Langfuse-Trace-Id para o app fixar a arvore
    de spans interna NESSE trace (mesmo do dataset run + scores do juiz).
    """
    t0 = time.perf_counter()
    headers = {"X-Experiment-Collect-Tools": "1"}
    if trace_id:
        headers["X-Langfuse-Trace-Id"] = trace_id
    try:
        if TRANSPORT == "testclient":
            client = _get_test_client()
            with client.stream("POST", path, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    return _err_result(
                        t0, resp.status_code, resp.read().decode("utf-8", "ignore")
                    )
                return _parse_sse_lines(
                    resp.iter_lines(), t0, timeout, raw_sse_path=raw_sse_path
                )
        else:  # http -> container self-signed
            url = APP_BASE + path
            with httpx.stream(
                "POST",
                url,
                json=payload,
                # O read timeout cobre stream silencioso; o parser aplica o
                # deadline total quando heartbeats continuam chegando.
                timeout=httpx.Timeout(timeout, connect=min(timeout, 30.0)),
                verify=False,
                headers=headers,
            ) as resp:
                if resp.status_code != 200:
                    return _err_result(
                        t0, resp.status_code, resp.read().decode("utf-8", "ignore")
                    )
                return _parse_sse_lines(
                    resp.iter_lines(), t0, timeout, raw_sse_path=raw_sse_path
                )
    except Exception as e:  # noqa: BLE001 — relatorio fiel do erro real
        return {
            "ttfc_s": None,
            "total_s": round(time.perf_counter() - t0, 2),
            "content": "",
            "content_chars": 0,
            "status_frames": 0,
            "reasoning_frames": 0,
            "error": f"{type(e).__name__}: {e}",
            "terminal_type": None,
            "frame_types": [],
            "benchmark_metrics": None,
            "benchmark_ocr_usage": None,
            "benchmark_contract": None,
        }


def _record_langfuse_error(out: dict, stage: str, exc: Exception) -> None:
    error = f"{type(exc).__name__}: {exc}"
    out.setdefault("langfuse_errors", []).append({"stage": stage, "error": error})
    print(f"[runner]   Langfuse {stage} falhou: {error}", file=sys.stderr, flush=True)


def _merge_ocr_usage(
    tokens_by_model: dict[str, dict],
    raw_calls: list[dict] | None,
    *,
    expected_deployment: str | None,
    expected_canonical_model: str | None,
) -> dict[str, dict]:
    """Inclui OCR fora do trace uma vez, preservando cache_write ausente."""
    if not raw_calls:
        return {}
    by_model: dict[str, dict] = {}
    seen: set[str] = set()
    for call in raw_calls:
        key = call.get("call_key_sha256")
        deployment = call.get("deployment")
        if (
            call.get("role") != "ocr"
            or deployment != expected_deployment
            or not isinstance(key, str)
            or key in seen
        ):
            raise RuntimeError("Telemetria OCR Session diverge da campanha")
        reported_model = call.get("reported_model")
        if expected_canonical_model is not None and not (
            reported_model == expected_canonical_model
            or (
                isinstance(reported_model, str)
                and reported_model.startswith(expected_canonical_model + "-20")
            )
        ):
            raise RuntimeError("Modelo canônico OCR Session diverge da campanha")
        seen.add(key)
        usage = call.get("usage") or {}
        prompt = int(usage.get("prompt_tokens") or 0)
        cache_read = int(usage.get("cached_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        reasoning = int(usage.get("reasoning_tokens") or 0)
        if cache_read > prompt or reasoning > completion:
            raise RuntimeError("Telemetria OCR Session contém tokens inválidos")
        bucket = by_model.setdefault(
            str(deployment),
            {
                "input": 0,
                "cache_read": 0,
                "cache_write": 0,
                "output": 0,
                "reasoning": 0,
                "total": 0,
                "generations": 0,
                "ocr_calls": 0,
            },
        )
        bucket["input"] += prompt - cache_read
        bucket["cache_read"] += cache_read
        # No agregador Session, `output` mantém a semântica Langfuse: inclui
        # reasoning. A precificação remove a parcela antes de chamar price_usage.
        bucket["output"] += completion
        bucket["reasoning"] += reasoning
        bucket["total"] += prompt + completion
        bucket["ocr_calls"] += 1
        if usage.get("cache_write_tokens") is None:
            bucket["cache_write"] = None
        elif bucket["cache_write"] is not None:
            bucket["cache_write"] += int(usage["cache_write_tokens"])
    for deployment, ocr_bucket in by_model.items():
        combined = tokens_by_model.setdefault(
            deployment,
            {
                "input": 0,
                "cache_read": 0,
                "output": 0,
                "reasoning": 0,
                "total": 0,
                "generations": 0,
            },
        )
        for field in ("input", "cache_read", "output", "reasoning", "total"):
            combined[field] = int(combined.get(field, 0) or 0) + int(ocr_bucket[field])
        trace_cache_write = combined.get("cache_write")
        ocr_cache_write = ocr_bucket["cache_write"]
        combined["cache_write"] = (
            None
            if trace_cache_write is None or ocr_cache_write is None
            else int(trace_cache_write or 0) + int(ocr_cache_write)
        )
        combined["ocr_calls"] = ocr_bucket["ocr_calls"]
    return by_model


def _safe_langfuse(out: dict, stage: str, fn, *args, **kwargs):
    """Observabilidade não pode derrubar uma medição já concluída."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - API externa é não fatal no benchmark
        _record_langfuse_error(out, stage, exc)
        return None


def _emit_endpoint_trace_metrics(
    lf: Langfuse,
    trace_id: str,
    endpoint: str,
    endpoint_out: dict,
    result: dict,
    *,
    max_wait_s: float,
    profile_deployments: dict[str, str] | None,
    profile_canonical_models: dict[str, str] | None,
) -> dict | None:
    """Lê tokens do trace vinculado e etapas detalhadas quando o endpoint é session."""
    want_session = endpoint == "session"
    try:
        res = analyze_trace(
            lf,
            trace_id,
            want_session=want_session,
            profile_deployments=profile_deployments,
            max_wait_s=max_wait_s,
            poll_s=8.0,
            settle_reads=1,
        )
    except Exception as exc:  # noqa: BLE001 - coleta posterior não invalida a resposta
        _record_langfuse_error(result, "trace_metrics_read", exc)
        return None
    if res is None:
        print(
            f"[runner]   {endpoint}: trace nao ingerido a tempo",
            file=sys.stderr,
            flush=True,
        )
        return None
    tbm = res["tokens_by_model"]
    ocr_by_model = _merge_ocr_usage(
        tbm,
        endpoint_out.get("ocr_usage"),
        expected_deployment=(profile_deployments or {}).get("mini"),
        expected_canonical_model=(profile_canonical_models or {}).get("mini"),
    )
    _safe_langfuse(
        result, "trace_token_scores", emit_tokens_by_model, lf, trace_id, tbm
    )
    stage = res["session"]
    if stage:
        _safe_langfuse(result, "trace_stage_scores", emit_metrics, lf, trace_id, stage)
        st = stage["stage_timings"]
        harness_total = endpoint_out.get("latency", {}).get("total_s")
        print(
            f"[runner]   {endpoint} stage_timings: pre={st['pre_agent_s']}s "
            f"agent={st['agent_s']}s (principal={st['principal_llm_s']}s "
            f"sub={st['subagent_s']}s web={st['web_search_s']}s) "
            f"| soma_particao={st['pre_agent_s'] + st['agent_s'] + st['post_agent_s']:.2f}s "
            f"vs harness_total={harness_total}s",
            file=sys.stderr,
            flush=True,
        )
    san = res["sanity_input_tokens"]
    tok_resumo = "  ".join(
        f"{mid}[in={b['input']} cr={b['cache_read']} out={b['output']} "
        f"reas={b['reasoning']} g={b['generations']}]"
        for mid, b in sorted(tbm.items())
    )
    print(
        f"[runner]   {endpoint} tokens/modelo: {tok_resumo or '(nenhuma GENERATION)'}\n"
        f"[runner]   {endpoint} sanidade input: faturado={san['billed_input_plus_cache']} "
        f"vs token_counter={san['counted_input_tiktoken']} "
        f"(razao={san['ratio_counted_over_billed']} mesma_ordem={san['same_order_of_magnitude']})",
        file=sys.stderr,
        flush=True,
    )
    return {
        "stage": stage,
        "tokens_by_model": tbm,
        "tokens_by_scope": {"ocr": ocr_by_model},
        "sanity_input_tokens": san,
    }


def _endpoint_latency(metrics: dict) -> dict:
    return {
        key: metrics[key]
        for key in (
            "ttfc_s",
            "total_s",
            "content_chars",
            "status_frames",
            "reasoning_frames",
            "error",
        )
    }


def _execute_endpoint(  # noqa: C901, PLR0912 - fronteiras POST/judge explícitas
    *,
    lf: Langfuse,
    span,
    trace_id: str,
    endpoint: str,
    path: str,
    item,
    fresh_topico: int,
    question_text: str,
    expected: dict,
    judge_cfg: JudgeConfig,
    timeout: float,
    out: dict,
    benchmark_no_cache: bool,
    model_campaign: ModelCampaign | None = None,
    execution_ledger: SessionExecutionLedger | None = None,
    cell_id: str | None = None,
    raw_sse_path: Path | None = None,
) -> tuple[dict, float]:
    """Mede e julga um endpoint; chamadas Langfuse são opcionais após o stream."""
    payload = dict(item.input)
    payload["id_topico"] = fresh_topico
    if benchmark_no_cache:
        payload["no_cache"] = True
    if execution_ledger is not None:
        if cell_id is None:
            raise RuntimeError("Ledger Session exige cell_id")
        execution_ledger.reserve_post(cell_id, fresh_topico)
        execution_ledger.mark_post_started(cell_id)
    stream_kwargs = {"trace_id": trace_id}
    if raw_sse_path is not None:
        stream_kwargs["raw_sse_path"] = raw_sse_path
    try:
        metrics = stream_endpoint(path, payload, timeout, **stream_kwargs)
    except Exception as exc:
        if execution_ledger is None:
            raise
        return (
            {
                "latency": {
                    "ttfc_s": None,
                    "total_s": None,
                    "content_chars": 0,
                    "status_frames": 0,
                    "reasoning_frames": 0,
                    "error": f"post_started_exception:{type(exc).__name__}",
                },
                "trace_id": trace_id,
                "judge": None,
                "recovery_only": True,
                "response": "",
            },
            -1.0,
        )
    if benchmark_no_cache:
        expected_contract = {
            "no_cache": True,
            "benchmark_process_source": "sei_no_cache",
            "benchmark_session_reset": True,
        }
        observed_contract = metrics.get("benchmark_contract") or {}
        if observed_contract != expected_contract and metrics.get("error") is None:
            metrics["error"] = "benchmark_response_contract_mismatch"
        try:
            _merge_ocr_usage(
                {},
                metrics.get("benchmark_ocr_usage"),
                expected_deployment=(
                    model_campaign.mini.deployment if model_campaign else None
                ),
                expected_canonical_model=(
                    model_campaign.mini.canonical_model if model_campaign else None
                ),
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            metrics["error"] = "benchmark_ocr_identity_mismatch"
    if execution_ledger is not None:
        execution_ledger.mark_post_terminal(
            cell_id,
            valid=(metrics.get("terminal_type") == "end" and not metrics.get("error")),
        )

    if span is not None:
        _safe_langfuse(
            out,
            "trace_update",
            span.update_trace,
            input={"endpoint": endpoint, "request": item.input},
            output={"content": metrics["content"][:5000], "error": metrics["error"]},
            metadata={key: value for key, value in metrics.items() if key != "content"},
        )
        for lat_name in ("ttfc_s", "total_s", "content_chars"):
            value = metrics.get(lat_name)
            if value is not None:
                _safe_langfuse(
                    out,
                    f"score_{lat_name}",
                    lf.create_score,
                    name=lat_name,
                    value=float(value),
                    trace_id=trace_id,
                    data_type="NUMERIC",
                )

    endpoint_out = {
        "latency": _endpoint_latency(metrics),
        "tool_metrics": metrics.get("benchmark_metrics"),
        "ocr_usage": metrics.get("benchmark_ocr_usage"),
        "benchmark_contract": metrics.get("benchmark_contract"),
        "terminal_type": metrics.get("terminal_type"),
        "frame_types": metrics.get("frame_types"),
        "cited_urls": cited_urls(metrics["content"]),
        "trace_id": trace_id,
        # Mantém a resposta no artefato local para auditoria; o trace recebe só
        # o trecho já truncado acima.
        "response": metrics["content"],
    }
    if metrics["error"] or not metrics["content"].strip():
        if span is not None:
            _safe_langfuse(
                out,
                "score_endpoint_error",
                lf.create_score,
                name="endpoint_error",
                value=1,
                trace_id=trace_id,
                data_type="BOOLEAN",
                comment=metrics["error"] or "resposta vazia",
            )
        endpoint_out["judge"] = None
        return endpoint_out, -1.0

    try:
        judge_result = judge_response(
            question_text, expected, metrics["content"], judge_cfg
        )
    except Exception as exc:  # noqa: BLE001 - preserva a resposta se o juiz indisponível
        endpoint_out["judge"] = None
        endpoint_out["judge_error"] = f"{type(exc).__name__}: {exc}"
        return endpoint_out, -1.0

    if span is not None:
        _safe_langfuse(out, "judge_scores", emit_scores, lf, trace_id, judge_result)
    endpoint_out["judge"] = {
        "numeric": judge_result.scores_numeric,
        "bool": judge_result.scores_bool,
        "rationale": judge_result.rationale,
        "usage": judge_result.usage,
    }
    return endpoint_out, judge_result.scores_numeric["overall"]


def run_item(
    lf: Langfuse,
    item,
    run_name: str,
    judge_cfg: JudgeConfig,
    timeout: float,
    endpoints: dict[str, str],
    *,
    model_campaign: ModelCampaign | None = None,
    fresh_topico: int | None = None,
    execution_ledger: SessionExecutionLedger | None = None,
    cell_id: str | None = None,
) -> dict:
    """Roda os endpoints selecionados para um item, linka trace e julga."""
    question_text = item.input.get("text", "")
    expected = item.expected_output or {}
    out = {
        "qid": item.metadata.get("qid"),
        "case": dict(item.metadata or {}),
        "question": question_text,
        "endpoints": {},
        "langfuse_errors": [],
    }

    # id_topico FRESCO por run/caso (mesmo valor pros 2 endpoints, comparável):
    # o id fixo do dataset REUSA sessão entre runs — no session isso herda web/
    # + histórico do checkpointer e contamina a medição (auditoria de 2026-07-07:
    # 87/93 páginas herdadas no WEB-FII). Fresco = medição fria de verdade.
    fresh_topico = fresh_topico or (800_000_000 + int(time.time() * 10) % 100_000_000)
    out["id_topico_fresco"] = fresh_topico

    overall_by_ep: dict[str, float] = {}
    trace_ids: dict[str, str] = {}

    for ep_key, path in endpoints.items():
        benchmark_no_cache = model_campaign is not None and ep_key == "session"
        run_metadata = {
            "endpoint": ep_key,
            "path": path,
            "transport": TRANSPORT,
            "sei_address": os.environ.get("SEI_ADDRESS"),
            "warmup_applied": TRANSPORT == "testclient",
            "latency_caveat": (
                "transporte=testclient in-process: latencia e ORDINAL (qual e mais "
                "lento), NAO comparavel com container/producao; warmup aplicado 1x "
                "antes do run para absorver cold-start de modelo. Qualidade nao afetada."
            )
            if TRANSPORT == "testclient"
            else None,
        }
        trace_id: str | None = None
        endpoint_out: dict | None = None
        dataset_run_started = False
        endpoint_execution_entered = False

        try:
            # A chamada síncrona de create do SDK ocorre ao entrar neste contexto.
            # Se ela falhar, a medição ainda segue com um trace não associado ao dataset.
            with item.run(
                run_name=f"{run_name}-{ep_key}", run_metadata=run_metadata
            ) as span:
                dataset_run_started = True
                trace_id = span.trace_id
                trace_ids[ep_key] = trace_id
                endpoint_execution_entered = True
                endpoint_out, overall_by_ep[ep_key] = _execute_endpoint(
                    lf=lf,
                    span=span,
                    trace_id=trace_id,
                    endpoint=ep_key,
                    path=path,
                    item=item,
                    fresh_topico=fresh_topico,
                    question_text=question_text,
                    expected=expected,
                    judge_cfg=judge_cfg,
                    timeout=timeout,
                    out=out,
                    benchmark_no_cache=benchmark_no_cache,
                    model_campaign=model_campaign,
                    execution_ledger=execution_ledger,
                    cell_id=cell_id,
                    raw_sse_path=(
                        execution_ledger.path.parent / "streams" / f"{cell_id}.sse"
                        if execution_ledger is not None and cell_id is not None
                        else None
                    ),
                )
        except Exception as exc:  # noqa: BLE001 - API de observabilidade não aborta a bateria
            _record_langfuse_error(
                out,
                "dataset_run_item_finalize"
                if dataset_run_started
                else "dataset_run_item_create",
                exc,
            )
            if endpoint_out is None and not endpoint_execution_entered:
                trace_id = trace_id or uuid.uuid4().hex
                trace_ids[ep_key] = trace_id
                endpoint_execution_entered = True
                endpoint_out, overall_by_ep[ep_key] = _execute_endpoint(
                    lf=lf,
                    span=None,
                    trace_id=trace_id,
                    endpoint=ep_key,
                    path=path,
                    item=item,
                    fresh_topico=fresh_topico,
                    question_text=question_text,
                    expected=expected,
                    judge_cfg=judge_cfg,
                    timeout=timeout,
                    out=out,
                    benchmark_no_cache=benchmark_no_cache,
                    model_campaign=model_campaign,
                    execution_ledger=execution_ledger,
                    cell_id=cell_id,
                    raw_sse_path=(
                        execution_ledger.path.parent / "streams" / f"{cell_id}.sse"
                        if execution_ledger is not None and cell_id is not None
                        else None
                    ),
                )
            elif endpoint_out is None:
                endpoint_out = {
                    "latency": {
                        "ttfc_s": None,
                        "total_s": None,
                        "content_chars": 0,
                        "status_frames": 0,
                        "reasoning_frames": 0,
                        "error": "post_started_exception_recovery_only",
                    },
                    "trace_id": trace_id,
                    "judge": None,
                    "recovery_only": True,
                    "response": "",
                }
                overall_by_ep[ep_key] = -1.0
        out["endpoints"][ep_key] = endpoint_out
    # Só existe vencedor quando os dois endpoints participaram da mesma rodada.
    win = None
    if {"session", "classic"}.issubset(overall_by_ep):
        s, c = overall_by_ep["session"], overall_by_ep["classic"]
        win = 1.0 if s > c else (0.0 if s < c else 0.5)
    if win is not None and trace_ids.get("session"):
        _safe_langfuse(
            out,
            "score_win_session",
            lf.create_score,
            name="win_session",
            value=win,
            trace_id=trace_ids["session"],
            data_type="NUMERIC",
            comment=f"overall session={s} vs classic={c}",
        )
    out["win_session"] = win
    out["overall_by_ep"] = overall_by_ep
    out["trace_ids"] = trace_ids
    return out


def _result_allows_next_cell(result: dict) -> bool:
    """Fail-fast: qualquer célula incompleta encerra novas inferências."""
    endpoints = result.get("endpoints") or {}
    if not endpoints or result.get("run_error"):
        return False
    return all(
        not (data.get("latency") or {}).get("error")
        and data.get("terminal_type") == "end"
        and data.get("judge") is not None
        for data in endpoints.values()
    )


_REQUIRED_TOKEN_COUNTERS = (
    "input",
    "cache_read",
    "output",
    "reasoning",
    "total",
    "generations",
)


def _has_required_token_metrics(metrics: object) -> bool:
    if not isinstance(metrics, dict):
        return False
    tokens_by_model = metrics.get("tokens_by_model")
    if not isinstance(tokens_by_model, dict) or not tokens_by_model:
        return False
    generations = 0
    for usage in tokens_by_model.values():
        if not isinstance(usage, dict):
            return False
        for field in _REQUIRED_TOKEN_COUNTERS:
            value = usage.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return False
        generations += usage["generations"]
    return generations > 0


def _campaign_results_complete(results: list[dict], planned_count: int) -> bool:
    """Confere células, terminal SSE, judge e telemetria após o readback."""
    if len(results) != planned_count:
        return False
    return all(
        _result_allows_next_cell(result)
        and all(
            _has_required_token_metrics(endpoint.get("metrics"))
            for endpoint in (result.get("endpoints") or {}).values()
        )
        for result in results
    )


def _new_topic_plan(cell_ids: list[str], used: set[int]) -> dict[str, int]:
    """Gera tópicos opacos distintos do histórico antes da primeira célula."""
    plan: dict[str, int] = {}
    unavailable = set(used)
    for cell_id in cell_ids:
        for _ in range(1_000):
            topic_id = 800_000_000 + secrets.randbelow(100_000_000)
            if topic_id not in unavailable:
                unavailable.add(topic_id)
                plan[cell_id] = topic_id
                break
        else:
            raise RuntimeError("Não foi possível reservar tópico Session único")
    return plan


def collect_trace_metrics(
    lf: Langfuse,
    results: list[dict],
    *,
    max_wait_s: float,
    profile_deployments: dict[str, str] | None = None,
    profile_canonical_models: dict[str, str] | None = None,
) -> None:
    """Enriquece a bateria depois de todos os streams e checkpoints estarem seguros."""
    for result in results:
        for endpoint, endpoint_out in result.get("endpoints", {}).items():
            trace_id = endpoint_out.get("trace_id")
            endpoint_out["metrics"] = (
                _emit_endpoint_trace_metrics(
                    lf,
                    trace_id,
                    endpoint,
                    endpoint_out,
                    result,
                    max_wait_s=max_wait_s,
                    profile_deployments=profile_deployments,
                    profile_canonical_models=profile_canonical_models,
                )
                if trace_id
                else None
            )


def _resume_trace_metrics(
    *,
    lf: Langfuse,
    artifact_dir: Path,
    rate_card_path: Path,
    max_wait_s: float,
    profile_deployments: dict[str, str],
    profile_canonical_models: dict[str, str] | None = None,
) -> dict:
    """Retoma somente o readback de traces a partir do checkpoint já persistido."""
    artifact_dir = artifact_dir.expanduser().resolve(strict=True)
    progress_path = artifact_dir / "progress.jsonl"
    run_path = artifact_dir / "run.json"
    results = [
        json.loads(line)
        for line in progress_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    run_context = json.loads(run_path.read_text(encoding="utf-8"))
    collect_trace_metrics(
        lf,
        results,
        max_wait_s=max_wait_s,
        profile_deployments=profile_deployments,
        profile_canonical_models=profile_canonical_models,
    )
    traced = [
        endpoint
        for result in results
        for endpoint in result.get("endpoints", {}).values()
        if endpoint.get("trace_id")
    ]
    if not traced or any(endpoint.get("metrics") is None for endpoint in traced):
        raise RuntimeError("Trace metrics continuam ausentes após o readback")
    lf.flush()
    run_context["trace_metrics_wait_s"] = max_wait_s
    run_context["trace_metrics_resumed"] = True
    artifact_paths = write_artifacts(
        artifact_dir,
        run_context,
        results,
        rate_card_path,
    )
    return {
        "result_count": len(results),
        "trace_count": len(traced),
        "metrics_complete": True,
        "artifacts": {name: str(path) for name, path in artifact_paths.items()},
    }


def main() -> int:  # noqa: C901, PLR0912, PLR0915 - CLI mantém fluxo visível
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dataset", default=DATASET_NAME, help="dataset Langfuse a executar"
    )
    ap.add_argument(
        "--decision-suite",
        action="store_true",
        help="executa os 10 QIDs versionados de benchmark-decision-v2",
    )
    ap.add_argument(
        "--only",
        default=None,
        help="rodar so estes qids (um, ou varios separados por virgula: Q01,Q02)",
    )
    ap.add_argument("--run-name", default=None)
    ap.add_argument(
        "--canary",
        action="store_true",
        help="executa exatamente um QID da suíte, sem relaxar o contrato da bateria",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=900.0,
        help="deadline total de cada endpoint, em segundos",
    )
    ap.add_argument(
        "--langfuse-timeout",
        type=float,
        default=DEFAULT_LANGFUSE_TIMEOUT_S,
        help="timeout HTTP do SDK Langfuse, em segundos",
    )
    ap.add_argument(
        "--trace-metrics-wait",
        type=float,
        default=DEFAULT_TRACE_METRICS_WAIT_S,
        help="espera máxima pela ingestão de cada trace, em segundos",
    )
    ap.add_argument(
        "--endpoints",
        nargs="+",
        choices=tuple(ENDPOINTS),
        default=list(ENDPOINTS),
        help="endpoints a executar; use --endpoints classic para uma rodada isolada",
    )
    ap.add_argument("--no-warmup", action="store_true", help="pula a chamada de warmup")
    ap.add_argument(
        "--rate-card",
        default=str(HERE / "rate_cards" / "v2.json"),
        help="JSON com preços por milhão de tokens e câmbio USD/BRL",
    )
    ap.add_argument(
        "--artifacts-dir",
        default=str(HERE / "artifacts"),
        help="diretório raiz dos artefatos do benchmark",
    )
    ap.add_argument(
        "--resume-trace-metrics-from",
        type=Path,
        help="retoma apenas métricas Langfuse de um diretório já executado",
    )
    add_model_campaign_args(ap)
    args = ap.parse_args()
    campaign = campaign_from_args(args) if campaign_requested(args) else None
    if campaign is not None:
        campaign.apply_environment()
    if args.resume_trace_metrics_from is not None:
        if campaign is None:
            raise ValueError("Readback exige configuração explícita da campanha")
        lf = Langfuse(
            secret_key=os.environ["LF_SECRET"],
            public_key=os.environ["LF_PUBLIC"],
            host=os.environ["LF_HOST"],
            timeout=args.langfuse_timeout,
            mask=truncate_large_fields,
        )
        assert lf.auth_check(), "Langfuse auth_check falhou"
        summary = _resume_trace_metrics(
            lf=lf,
            artifact_dir=args.resume_trace_metrics_from,
            rate_card_path=Path(args.rate_card),
            max_wait_s=args.trace_metrics_wait,
            profile_deployments=campaign.profile_deployments,
            profile_canonical_models=campaign.profile_canonical_models,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if args.reuse_historical_baseline:
        args.decision_suite = True
        args.endpoints = ["session"]
        args.no_warmup = True
    if args.plan_only:
        if campaign is None or not campaign.reuse_historical_baseline:
            raise ValueError(
                "--plan-only exige configuração de modelos e baseline histórico"
            )
        print(
            json.dumps(
                plan_session_cells(_decision_qids(), campaign),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if campaign is not None and TRANSPORT == "http":
        _validate_http_model_campaign(campaign)
    selected_endpoints = {name: ENDPOINTS[name] for name in args.endpoints}

    only_ids = (
        {q.strip() for q in args.only.split(",") if q.strip()} if args.only else None
    )
    if args.decision_suite:
        decision_ids = _decision_qids()
        only_ids = decision_ids if only_ids is None else only_ids & decision_ids
        assert only_ids, "--only não contém QIDs da decision suite"
    if campaign is not None and (
        list(selected_endpoints) != ["session"] or not args.no_warmup
    ):
        raise ValueError("Campanha exige somente Session e zero warmup")

    run_name = args.run_name or f"exp-{time.strftime('%Y%m%d-%H%M%S')}"
    if only_ids:
        # 1 qid -> sufixo com o qid; varios -> sufixo curto com a contagem
        run_name += (
            f"-{next(iter(only_ids))}"
            if len(only_ids) == 1
            else f"-{len(only_ids)}cells"
        )

    lf = Langfuse(
        secret_key=os.environ["LF_SECRET"],
        public_key=os.environ["LF_PUBLIC"],
        host=os.environ["LF_HOST"],
        timeout=args.langfuse_timeout,
        # Langfuse é singleton por public key. No TestClient o runner nasce antes da
        # app, então a máscara precisa estar aqui para os callbacks do agente também.
        mask=truncate_large_fields,
    )
    assert lf.auth_check(), "Langfuse auth_check falhou"
    judge_cfg = JudgeConfig()
    print(
        f"[runner] run_name={run_name} transport={TRANSPORT} sei_address={os.environ.get('SEI_ADDRESS')} "
        f"judge={judge_cfg.model}@{judge_cfg.base_url}",
        file=sys.stderr,
    )

    ds = lf.get_dataset(args.dataset)
    items = ds.items
    if only_ids:
        items = [it for it in items if it.metadata.get("qid") in only_ids]
        found = {it.metadata.get("qid") for it in items}
        missing = only_ids - found
        assert not missing, f"qids nao encontrados no dataset: {sorted(missing)}"
    if campaign is not None:
        expected_items = 1 if args.canary else 10
        if len(items) != expected_items:
            label = "Canário" if args.canary else "Bateria Session"
            raise ValueError(f"{label} da campanha exige {expected_items} célula(s)")

    artifact_dir = Path(args.artifacts_dir).expanduser().resolve() / run_name
    progress_path = artifact_dir / "progress.jsonl"
    execution_ledger = None
    topic_plan: dict[str, int] = {}
    if campaign is not None:
        cell_ids = [str(item.metadata.get("qid")) for item in items]
        used_topics = historical_topic_ids(Path(args.artifacts_dir).expanduser())
        execution_ledger = SessionExecutionLedger(
            artifact_dir / "session-execution-ledger.jsonl"
        )
        topic_plan = execution_ledger.reserve_topics(
            cell_ids,
            topic_ids=_new_topic_plan(cell_ids, used_topics),
            historical_topic_ids=used_topics,
        )

    # Warmup: 1 chamada DESCARTADA por endpoint (tira a carga inicial de modelo do
    # TestClient da medicao). Usa o input do 1o item; nao linka trace nem conta metrica.
    if TRANSPORT == "testclient" and not args.no_warmup:
        wpayload = dict(items[0].input)
        for ep_key, path in selected_endpoints.items():
            print(
                f"[runner] warmup {ep_key} (descartado) ...",
                file=sys.stderr,
                flush=True,
            )
            w = stream_endpoint(path, wpayload, args.timeout)
            print(
                f"[runner] warmup {ep_key}: total={w['total_s']}s err={w['error']}",
                file=sys.stderr,
                flush=True,
            )

    results = []
    for it in items:
        qid = it.metadata.get("qid")
        print(f"[runner] {qid} ...", file=sys.stderr, flush=True)
        try:
            result = run_item(
                lf,
                it,
                run_name,
                judge_cfg,
                args.timeout,
                selected_endpoints,
                model_campaign=campaign,
                fresh_topico=topic_plan.get(str(qid)),
                execution_ledger=execution_ledger,
                cell_id=str(qid) if execution_ledger is not None else None,
            )
        except Exception as exc:  # noqa: BLE001 - salva a bateria e segue para o próximo caso
            result = {
                "qid": qid,
                "case": dict(it.metadata or {}),
                "question": it.input.get("text", ""),
                "endpoints": {},
                "run_error": f"{type(exc).__name__}: {exc}",
            }
            print(
                f"[runner] {qid}: falha isolada, bateria continua: {result['run_error']}",
                file=sys.stderr,
                flush=True,
            )
        results.append(result)
        append_progress(progress_path, result)
        if campaign is not None and not _result_allows_next_cell(result):
            print(
                f"[runner] {qid}: fail-fast; nenhuma célula posterior será iniciada",
                file=sys.stderr,
                flush=True,
            )
            break

    _safe_langfuse({"langfuse_errors": []}, "flush_before_trace_metrics", lf.flush)
    collect_trace_metrics(
        lf,
        results,
        max_wait_s=args.trace_metrics_wait,
        profile_deployments=(
            campaign.profile_deployments if campaign is not None else None
        ),
        profile_canonical_models=(
            campaign.profile_canonical_models if campaign is not None else None
        ),
    )
    _safe_langfuse({"langfuse_errors": []}, "flush_after_trace_metrics", lf.flush)
    campaign_complete = campaign is None or _campaign_results_complete(
        results, len(items)
    )
    run_context = {
        "run_name": run_name,
        "dataset": args.dataset,
        "commit": _git_commit(),
        "transport": TRANSPORT,
        "app_base": APP_BASE if TRANSPORT == "http" else None,
        "latency_comparable": TRANSPORT == "http",
        "decision_suite": args.decision_suite,
        "decision_suite_manifest": (
            str(DECISION_SUITE_PATH) if args.decision_suite else None
        ),
        "qids": [result["qid"] for result in results],
        "planned_qids": [str(item.metadata.get("qid")) for item in items],
        "fail_fast_triggered": len(results) != len(items),
        "telemetry_complete": campaign_complete,
        "session_ledger": (
            str(execution_ledger.path) if execution_ledger is not None else None
        ),
        "endpoint_order": list(selected_endpoints),
        "langfuse_timeout_s": args.langfuse_timeout,
        "trace_metrics_wait_s": args.trace_metrics_wait,
        "progress_path": str(progress_path),
        "model_campaign": (
            {
                "models": campaign.model_profiles,
                "reasoning_effort": campaign.reasoning_effort,
                "n": campaign.n,
                "rate_card_sha256": campaign.rate_card_sha256,
                "rate_card": campaign.rate_card_reference,
                "context_windows": campaign.profile_context_windows,
                "judge_temperature": campaign.judge_temperature,
                "historical_baseline_reused": (campaign.reuse_historical_baseline),
            }
            if campaign is not None
            else None
        ),
        "config": {
            key: os.environ.get(key)
            for key in (
                "ASSISTENTE_SESSION_INJECT_TOKENS_THRESHOLD",
                "ASSISTENTE_SESSION_REASONING_EFFORT",
                "ASSISTENTE_SESSION_WEB_TOOL",
                "ASSISTENTE_SESSION_WEBRESEARCH_MAX_CALLS",
                "ASSISTENTE_SESSION_WEBRESEARCH_CRAWL_CONCURRENCY",
                "ASSISTENTE_SESSION_WEBRESEARCH_EVIDENCE_GATE_ENABLED",
                "ASSISTENTE_SESSION_WEBRESEARCH_EVIDENCE_GATE_INPUT_CHARS",
                "ASSISTENTE_CTX_LEN_STANDARD_MODEL",
                "ASSISTENTE_CTX_LEN_MINI_MODEL",
                "ASSISTENTE_CTX_LEN_NANO_MODEL",
                "ASSISTENTE_OCR_MODEL",
                "LITELLM_STANDARD_MODEL",
                "LITELLM_MINI_MODEL",
                "LITELLM_NANO_MODEL",
                "EXP_JUDGE_MODEL_ALIAS",
            )
        },
    }
    artifact_paths = write_artifacts(
        artifact_dir,
        run_context,
        results,
        args.rate_card,
    )
    print(
        json.dumps(
            {
                "run_name": run_name,
                "host": os.environ["LF_HOST"],
                "artifacts": {name: str(path) for name, path in artifact_paths.items()},
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if campaign_complete else 1


if __name__ == "__main__":
    sys.exit(main())
