"""Configuração centralizada do Langfuse com filtragem de traces.

BASEADO NA ISSUE OFICIAL: https://github.com/orgs/langfuse/discussions/8492

SOLUÇÃO: Criar o cliente Langfuse com blocked_instrumentation_scopes NO INÍCIO
do main.py, ANTES de importar qualquer router que use CallbackHandler().
"""

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from pydantic import BaseModel

from sei_ia.configs.settings_config import settings

logger = logging.getLogger(__name__)

os.environ.setdefault("LANGFUSE_MEDIA_UPLOAD_ENABLED", "False")

_langfuse_client: list[Any] = [None]


TRUNCATE_LIMITS = {
    "content": 3000,
    "last_prompt": 5000,
    "user_request": 2000,
    "text": 2000,
    "web_body": 3000,
    "default": 10_000,
}

_WEB_BODY_FIELDS = {
    "body",
    "html",
    "markdown",
    "page_content",
    "rawHtml",
    "raw_content",
    "raw_html",
    "response",
    "response_body",
    "result",
    "tool_output",
    "tool_result",
    "web_content",
    "output",
}

_REQUEST_BODY_FIELDS = ("original_request_body", "original_request")

MAX_LANGFUSE_PAYLOAD_CHARS = 100_000
SUMMARY_FIELDS = (
    "id_request",
    "id_topico",
    "all_tokens_counter",
    "intent",
    "use_websearch",
    "use_thinking",
    "doc_rag",
    "rag_method",
)


def _redact_data_url(url: str) -> str:
    """Redacta base64 grande, preservando MIME e tamanho aproximado."""
    if not isinstance(url, str) or not url.startswith("data:"):
        return url
    try:
        prefix, payload = url.split(";base64,", 1)
    except ValueError:
        return url
    if len(payload) < 256:
        return url
    approx_bytes = (len(payload) * 3) // 4
    if approx_bytes < 1024:
        size_human = f"{approx_bytes} B"
    elif approx_bytes < 1024 * 1024:
        size_human = f"{approx_bytes / 1024:.1f} KB"
    else:
        size_human = f"{approx_bytes / (1024 * 1024):.1f} MB"
    return f"{prefix};base64,<redacted:{size_human}>"


def _truncate_str(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value

    last_line = value.rsplit("\n", 1)[-1]
    if last_line.startswith("[truncado: ") and last_line.endswith(" caracteres]"):
        return value

    truncated = len(value) - max_length
    return value[:max_length] + f"\n[truncado: {truncated} caracteres]"


def truncate_langfuse_request_body(value: str) -> str:
    """Aplica o limite textual global preservando o body como uma string."""
    return _truncate_str(value, MAX_LANGFUSE_PAYLOAD_CHARS)


def _truncate_web_body(value: str) -> str:
    max_length = TRUNCATE_LIMITS["web_body"]
    if len(value) <= max_length:
        return value
    truncated = len(value) - max_length
    return (
        value[:max_length]
        + f"\n\n... [TRUNCATED: {truncated:,} chars omitted, "
        + f"original size: {len(value):,} chars]"
    )


def _is_request_body_json(value: str) -> bool:
    """Reconhece o body textual dos endpoints sem liberar JSON arbitrário."""
    candidate = value
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, str):
        candidate = parsed
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            parsed = None
    if (
        isinstance(parsed, dict)
        and "id_usuario" in parsed
        and "text" in parsed
        and ("id_topico" in parsed or "id_request" in parsed)
    ):
        return True

    last_line = candidate.rsplit("\n", 1)[-1]
    return (
        candidate.lstrip().startswith("{")
        and last_line.startswith("[truncado: ")
        and last_line.endswith(" caracteres]")
    )


def _normalize_structured(data: Any) -> Any:
    """Converte `BaseModel`/dataclass em dict puro; demais tipos passam intactos."""
    if isinstance(data, BaseModel):
        return data.model_dump(mode="python")
    if is_dataclass(data) and not isinstance(data, type):
        return asdict(data)
    return data


def _sanitize_str(
    data: str,
    field: str | None,
    *,
    path: tuple[str, ...],
    truncate_text: bool = True,
) -> str:
    if data.startswith("data:") and ";base64," in data:
        data = _redact_data_url(data)
    if not truncate_text:
        return data
    if field in _REQUEST_BODY_FIELDS:
        escaped_body = data.removeprefix("\\")
        if data.startswith("\\") and _is_request_body_json(escaped_body):
            return truncate_langfuse_request_body(data)
    if path[-2:] == ("response", "output"):
        return data
    if field is None and _is_request_body_json(data):
        return data
    if field in _WEB_BODY_FIELDS:
        return _truncate_web_body(data)
    return _truncate_str(
        data, TRUNCATE_LIMITS.get(field or "", TRUNCATE_LIMITS["default"])
    )


def _sanitize_value(
    data: Any,
    field: str | None = None,
    *,
    path: tuple[str, ...] = (),
    truncate_text: bool = True,
) -> Any:
    """Converte valores estruturados e opcionalmente trunca strings."""
    data = _normalize_structured(data)

    if isinstance(data, bytes):
        return f"[bytes: {len(data)}]"

    if isinstance(data, str):
        return _sanitize_str(
            data,
            field,
            path=path,
            truncate_text=truncate_text,
        )

    if isinstance(data, Mapping):
        return {
            str(key): _sanitize_value(
                value,
                field=str(key),
                path=(*path, str(key)),
                truncate_text=truncate_text,
            )
            for key, value in data.items()
        }

    if isinstance(data, (list, tuple, set)):
        return [
            _sanitize_value(item, path=path, truncate_text=truncate_text)
            for item in data
        ]

    if data is None or isinstance(data, (bool, int, float)):
        return data

    value = str(data)
    return _truncate_str(value, TRUNCATE_LIMITS["default"]) if truncate_text else value


def _payload_summary(data: Any, total_chars: int) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "_truncated": (
            f"[truncado: {total_chars} caracteres; "
            f"limite: {MAX_LANGFUSE_PAYLOAD_CHARS}]"
        )
    }
    if isinstance(data, Mapping):
        for field in SUMMARY_FIELDS:
            value = data.get(field)
            if value is None or isinstance(value, (str, bool, int, float)):
                summary[field] = value
    return summary


def truncate_large_fields(data: Any) -> Any:
    """Sanitiza e limita payloads antes de enviá-los ao Langfuse."""
    sanitized = _sanitize_value(data)
    serialized = json.dumps(sanitized, ensure_ascii=False, default=str)

    response = sanitized.get("response") if isinstance(sanitized, Mapping) else None
    preserves_agent_output = isinstance(response, Mapping) and isinstance(
        response.get("output"), str
    )
    request_bodies = (
        (sanitized.get(field) for field in _REQUEST_BODY_FIELDS)
        if isinstance(sanitized, Mapping)
        else ()
    )
    preserves_request_body = any(
        isinstance(request_body, str)
        and _is_request_body_json(request_body.removeprefix("\\"))
        for request_body in request_bodies
    )
    if isinstance(sanitized, str) and _is_request_body_json(sanitized):
        preserves_request_body = True
    if len(serialized) > MAX_LANGFUSE_PAYLOAD_CHARS and not (
        preserves_agent_output or preserves_request_body
    ):
        return _payload_summary(sanitized, len(serialized))

    return sanitized


def mask_langfuse_payload(data: Any) -> Any:
    """Aplica a máscara do SDK, mantendo redaction de mídia no opt-out textual."""
    if settings.LANGFUSE_TRUNCATE_PAYLOADS:
        return truncate_large_fields(data)
    return _sanitize_value(data, truncate_text=False)


def initialize_langfuse_singleton():
    """Cria o cliente Langfuse com os escopos automáticos bloqueados."""
    if _langfuse_client[0] is not None:
        logger.debug("Langfuse já inicializado")
        return _langfuse_client[0]

    try:
        if not settings.USE_LANGFUSE:
            logger.info("Langfuse desabilitado (USE_LANGFUSE=False)")
            return None

        from langfuse import Langfuse

        blocked_scopes = [
            "opentelemetry.instrumentation.requests",
            "opentelemetry.instrumentation.httpx",
            "opentelemetry.instrumentation.sqlalchemy",
            "opentelemetry.instrumentation.fastapi",
        ]

        _langfuse_client[0] = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_URL,
            blocked_instrumentation_scopes=blocked_scopes,
            mask=mask_langfuse_payload,
        )

        if settings.LANGFUSE_TRUNCATE_PAYLOADS:
            logger.info(
                "✅ Langfuse inicializado com truncamento automático de campos "
                f"grandes (content: {TRUNCATE_LIMITS['content']:,} chars, "
                f"last_prompt: {TRUNCATE_LIMITS['last_prompt']:,} chars)"
            )
        else:
            logger.info(
                "Langfuse inicializado sem truncamento textual; redaction de mídia "
                "permanece ativa"
            )

        return _langfuse_client[0]  # noqa: TRY300

    except Exception as e:
        logger.error(f"❌ Erro ao configurar Langfuse: {e}")  # noqa: TRY400
        return None


def get_configured_langfuse_client():
    """Retorna o cliente Langfuse."""
    if _langfuse_client[0] is None:
        return initialize_langfuse_singleton()
    return _langfuse_client[0]
