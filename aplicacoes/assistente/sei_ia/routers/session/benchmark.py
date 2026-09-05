"""Preflights sanitizados da stack experimental do Session.

Este módulo é o único adaptador HTTP específico do benchmark. O fluxo normal de
``session_stream`` não importa política de campanha, rate card, ledger ou custo.
"""

from __future__ import annotations

import hashlib
import time
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Header, HTTPException

from sei_ia.configs.settings_config import settings
from sei_ia.routers.session.stream import ENDPOINT_NAME
from sei_ia.services.llm_models.get_model import get_model_config

BENCHMARK_PREFLIGHT_ENDPOINT = "/llm_lang/session_benchmark_preflight"
BENCHMARK_LIVE_PREFLIGHT_ENDPOINT = "/llm_lang/session_benchmark_live_preflight"
BENCHMARK_EVIDENCE_DESIGN = "benchmark-long-context-evidence-v4-ocr-fresh-20260724"

router = APIRouter()


@router.get(
    BENCHMARK_PREFLIGHT_ENDPOINT,
    tags=["llm_lang"],
    summary="Preflight sem corpus do benchmark de contexto longo",
    include_in_schema=False,
)
def session_benchmark_preflight() -> dict[str, object]:
    """Expõe somente fatos não sensíveis do runtime efetivo."""
    model_profile = settings.SESSION_MAIN_MODEL
    model_config = get_model_config(model_profile)
    classifier_profile = settings.SESSION_CLASSIFIER_MODEL
    classifier_config = get_model_config(classifier_profile)
    explorer_profile = settings.SESSION_EXPLORER_MODEL
    explorer_config = get_model_config(explorer_profile)
    return {
        "status": "ready",
        "endpoint": ENDPOINT_NAME,
        "context_disclosure_threshold": settings.SESSION_INJECT_TOKENS_THRESHOLD,
        "session_main_model_profile": model_profile,
        "session_main_model": model_config["model"],
        "session_main_model_context_window_tokens": model_config["max_ctx_len"],
        "session_main_model_client_retries": model_config["max_retries"],
        "session_reasoning_effort_requested": settings.SESSION_REASONING_EFFORT,
        "session_classifier_model_profile": classifier_profile,
        "session_classifier_model": classifier_config["model"],
        "session_classifier_model_context_window_tokens": classifier_config[
            "max_ctx_len"
        ],
        "session_explorer_model_profile": explorer_profile,
        "session_explorer_model": explorer_config["model"],
        "session_explorer_model_context_window_tokens": explorer_config["max_ctx_len"],
        "session_ocr_model": settings.OCR_MODEL,
        "benchmark_no_cache_required": True,
        "benchmark_document_source": "sei_no_cache_with_pinned_validation",
        "benchmark_process_source": "sei_no_cache",
        "tool_telemetry_schema": "benchmark-tool-telemetry-v2",
        "preparation_heartbeat_interval_s": (
            settings.SESSION_PREPARATION_HEARTBEAT_INTERVAL_SECONDS
        ),
        "benchmark_evidence_pin_enabled": bool(
            settings.SESSION_BENCHMARK_EVIDENCE_INDEX
        ),
        "benchmark_evidence_design": (
            BENCHMARK_EVIDENCE_DESIGN
            if settings.SESSION_BENCHMARK_EVIDENCE_INDEX
            else None
        ),
    }


def _normalized_endpoint(value: str, *, origin_only: bool) -> str:
    """Normaliza endpoint para comparação/hash sem devolver credenciais."""
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(status_code=503, detail="configuração SEI inválida")
    host = parsed.hostname.lower()
    default_port = 443 if parsed.scheme == "https" else 80
    netloc = host if parsed.port in {None, default_port} else f"{host}:{parsed.port}"
    path = "" if origin_only else parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


@router.get(
    BENCHMARK_LIVE_PREFLIGHT_ENDPOINT,
    tags=["llm_lang"],
    summary="Autenticação live do SEI antes do benchmark de contexto longo",
    include_in_schema=False,
)
async def session_benchmark_live_preflight(
    process_id: Annotated[str, Header(alias="X-Benchmark-Process-Id")],
) -> dict[str, object]:
    """Consulta um processo no SEI efetivo e devolve somente prova sanitizada."""
    if not settings.SESSION_BENCHMARK_EVIDENCE_INDEX:
        raise HTTPException(status_code=404, detail="preflight live indisponível")
    if not process_id.strip() or len(process_id) > 128:
        raise HTTPException(status_code=422, detail="processo de preflight inválido")
    if not settings.SEI_ADDRESS:
        raise HTTPException(status_code=503, detail="endereço público SEI ausente")
    credential = settings.SEI_API_DB_IDENTIFIER_SERVICE
    if not credential:
        raise HTTPException(status_code=503, detail="credencial SEI ausente")

    public_endpoint = _normalized_endpoint(settings.SEI_ADDRESS, origin_only=True)
    api_endpoint = _normalized_endpoint(settings.SEI_API_DB_ADDRESS, origin_only=False)
    api_origin = _normalized_endpoint(settings.SEI_API_DB_ADDRESS, origin_only=True)
    if public_endpoint != api_origin:
        raise HTTPException(
            status_code=409, detail="escopo público/API do SEI divergente"
        )

    from sei_ia.data.database.sei_client import SeiDBAPIError, sei_client

    started = time.monotonic()
    try:
        response = await sei_client.md_ia_consulta_processo_async(process_id)
    except SeiDBAPIError as exc:
        status_code = exc.status_code if exc.status_code in {401, 403} else 502
        raise HTTPException(
            status_code=status_code,
            detail=f"preflight live SEI recusado ({status_code})",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - contrato externo vira erro sanitizado
        raise HTTPException(
            status_code=502, detail="preflight live SEI falhou"
        ) from exc
    duration_s = max(0.0, time.monotonic() - started)
    if type(response).__name__ != "DataFrame" or not hasattr(response, "empty"):
        raise HTTPException(status_code=502, detail="contrato live SEI inválido")
    if response.empty:
        raise HTTPException(status_code=424, detail="resposta live SEI vazia")
    if "id_procedimento" not in response.columns or process_id not in {
        str(value) for value in response["id_procedimento"].tolist()
    }:
        raise HTTPException(status_code=424, detail="processo live SEI divergente")

    return {
        "schema_version": "benchmark-sei-live-preflight-v1",
        "status": "passed",
        "live_query_performed": True,
        "public_api_scope_coherent": True,
        "credential_present": True,
        "public_endpoint_sha256": hashlib.sha256(
            public_endpoint.encode("utf-8")
        ).hexdigest(),
        "api_endpoint_sha256": hashlib.sha256(api_endpoint.encode("utf-8")).hexdigest(),
        "api_origin_sha256": hashlib.sha256(api_origin.encode("utf-8")).hexdigest(),
        "credential_sha256": hashlib.sha256(credential.encode("utf-8")).hexdigest(),
        "response_type": "dataframe",
        "response_nonempty": True,
        "process_matched": True,
        "duration_s": duration_s,
    }
