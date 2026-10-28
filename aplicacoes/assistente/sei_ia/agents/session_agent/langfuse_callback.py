"""Callback Langfuse do Session sem conteúdo de documentos."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from langchain_core.messages import BaseMessage, ToolMessage
from langfuse.langchain import CallbackHandler
from langfuse.logger import langfuse_logger


def _payload_summary(value: Any) -> dict[str, Any]:
    source = value.content if isinstance(value, BaseMessage) else value
    if isinstance(source, bytes):
        encoded = source
    elif isinstance(source, str):
        encoded = source.encode("utf-8")
    else:
        encoded = repr(source).encode("utf-8")

    summary: dict[str, Any] = {
        "redacted": True,
        "type": type(value).__name__,
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }
    if isinstance(source, str):
        summary["chars"] = len(source)
    elif isinstance(source, Mapping | Sequence) and not isinstance(
        source, bytes | bytearray
    ):
        summary["items"] = len(source)
    if isinstance(value, ToolMessage):
        summary["status"] = value.status
    return summary


def _redacted_text(value: Any) -> str:
    return json.dumps(
        _payload_summary(value), ensure_ascii=False, separators=(",", ":")
    )


def _redact_inputs(kwargs: dict[str, Any]) -> dict[str, Any]:
    if "inputs" not in kwargs:
        return kwargs
    return {**kwargs, "inputs": _payload_summary(kwargs["inputs"])}


def _redacted_error(error: BaseException) -> RuntimeError:
    summary = _payload_summary(str(error))
    return RuntimeError(
        f"{type(error).__name__}: conteúdo removido; "
        f"sha256={summary['sha256']}; bytes={summary['bytes']}"
    )


def _safe_tool_call(tool_call: Any) -> dict[str, Any]:
    if not isinstance(tool_call, Mapping):
        return _payload_summary(tool_call)

    result: dict[str, Any] = {
        key: tool_call[key]
        for key in ("name", "id", "type")
        if isinstance(tool_call.get(key), str)
    }
    arguments = tool_call.get("args", tool_call.get("arguments"))
    if arguments is not None:
        result["arguments"] = _payload_summary(arguments)
    return result


class SessionLangfuseCallback(CallbackHandler):
    """Mantém a árvore automática sem persistir payloads do agente Session."""

    def _convert_message_to_dict(self, message: BaseMessage) -> dict[str, Any]:
        original = super()._convert_message_to_dict(message)
        result: dict[str, Any] = {}
        for key in ("role", "name", "tool_call_id"):
            if isinstance(original.get(key), str):
                result[key] = original[key]
        if "content" in original:
            result["content"] = _payload_summary(original["content"])
        if isinstance(original.get("tool_calls"), list):
            result["tool_calls"] = [
                _safe_tool_call(tool_call) for tool_call in original["tool_calls"]
            ]
        if original.get("additional_kwargs"):
            result["additional_kwargs"] = _payload_summary(
                original["additional_kwargs"]
            )
        return result

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return super().on_chain_start(
            serialized,
            _payload_summary(inputs),
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=tags,
            metadata=metadata,
            **kwargs,
        )

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        return super().on_chain_end(
            _payload_summary(outputs),
            run_id=run_id,
            parent_run_id=parent_run_id,
            **_redact_inputs(kwargs),
        )

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().on_chain_error(
            _redacted_error(error),
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=tags,
            **_redact_inputs(kwargs),
        )

    def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return super().on_llm_start(
            serialized,
            [_redacted_text(prompt) for prompt in prompts],
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=tags,
            metadata=metadata,
            **kwargs,
        )

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        return super().on_llm_end(
            response,
            run_id=run_id,
            parent_run_id=parent_run_id,
            **_redact_inputs(kwargs),
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        return super().on_llm_error(
            _redacted_error(error),
            run_id=run_id,
            parent_run_id=parent_run_id,
            **_redact_inputs(kwargs),
        )

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return super().on_tool_start(
            serialized,
            _redacted_text(input_str),
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=tags,
            metadata=metadata,
            **_redact_inputs(kwargs),
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        summary = _payload_summary(output)
        redacted_kwargs = _redact_inputs(kwargs)
        if not isinstance(output, ToolMessage) or output.status != "error":
            return super().on_tool_end(
                summary,
                run_id=run_id,
                parent_run_id=parent_run_id,
                **redacted_kwargs,
            )

        try:
            self._log_debug_event(
                "on_tool_end",
                run_id,
                parent_run_id,
                output=summary,
            )
            observation = self._detach_observation(run_id)
            if observation is not None:
                observation.update(
                    output=summary,
                    status_message=(
                        "ToolMessage status=error; conteúdo removido; "
                        f"sha256={summary['sha256']}; bytes={summary['bytes']}"
                    ),
                    level="ERROR",
                    input=redacted_kwargs.get("inputs"),
                    cost_details={"total": 0},
                ).end()
        except Exception:
            langfuse_logger.exception("Falha ao encerrar observation de tool")
        return None

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        return super().on_tool_error(
            _redacted_error(error),
            run_id=run_id,
            parent_run_id=parent_run_id,
            **_redact_inputs(kwargs),
        )
