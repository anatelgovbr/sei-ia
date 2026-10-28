"""Agregação local de tokens por modelo usados pelo ``session_stream``."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from threading import Lock
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, dict) else {}
    return vars(value) if hasattr(value, "__dict__") else {}


def _first_integer(values: dict[str, Any], *names: str) -> int:
    for name in names:
        if name in values and values[name] is not None:
            return _integer(values[name])
    return 0


@dataclass(frozen=True, slots=True)
class _CanonicalUsage:
    input_total_tokens: int
    input_cache_read_tokens: int
    input_cache_write_tokens: int
    output_total_tokens: int
    output_reasoning_tokens: int


def _canonical_usage(
    *,
    input_total: int,
    output_total: int,
    cache_read: int = 0,
    cache_write: int = 0,
    reasoning: int = 0,
) -> _CanonicalUsage:
    input_total = _integer(input_total)
    output_total = _integer(output_total)
    cache_read = min(_integer(cache_read), input_total)
    cache_write = min(_integer(cache_write), input_total - cache_read)
    reasoning = min(_integer(reasoning), output_total)
    return _CanonicalUsage(
        input_total_tokens=input_total,
        input_cache_read_tokens=cache_read,
        input_cache_write_tokens=cache_write,
        output_total_tokens=output_total,
        output_reasoning_tokens=reasoning,
    )


def _standard_usage_metadata(usage: Any) -> _CanonicalUsage | None:
    usage = _mapping(usage)
    if not usage:
        return None
    input_details = _mapping(usage.get("input_token_details"))
    output_details = _mapping(usage.get("output_token_details"))
    return _canonical_usage(
        input_total=_integer(usage.get("input_tokens")),
        output_total=_integer(usage.get("output_tokens")),
        cache_read=_first_integer(input_details, "cache_read", "cached_tokens"),
        cache_write=_first_integer(
            input_details,
            "cache_creation",
            "cache_write",
            "cache_creation_tokens",
            "cache_write_tokens",
        ),
        reasoning=_first_integer(output_details, "reasoning", "reasoning_tokens"),
    )


def _standard_usage(response: LLMResult) -> _CanonicalUsage | None:
    for generation_group in response.generations:
        for generation in generation_group:
            generation_info = _mapping(getattr(generation, "generation_info", None))
            message = getattr(generation, "message", None)
            usage = _standard_usage_metadata(
                generation_info.get("usage_metadata")
            ) or _standard_usage_metadata(getattr(message, "usage_metadata", None))
            if usage is not None:
                return usage
    return None


def _raw_openai_usage(response: LLMResult) -> _CanonicalUsage | None:
    llm_output = _mapping(response.llm_output)
    usage = _mapping(llm_output.get("token_usage"))
    if not usage:
        return None
    prompt_details = _mapping(
        usage.get("prompt_tokens_details") or usage.get("input_tokens_details")
    )
    completion_details = _mapping(
        usage.get("completion_tokens_details") or usage.get("output_tokens_details")
    )
    return _canonical_usage(
        input_total=_first_integer(usage, "prompt_tokens", "input_tokens"),
        output_total=_first_integer(usage, "completion_tokens", "output_tokens"),
        cache_read=_first_integer(prompt_details, "cached_tokens", "cache_read"),
        cache_write=_first_integer(
            prompt_details,
            "cache_write_tokens",
            "cache_creation_tokens",
            "cache_write",
            "cache_creation",
        ),
        reasoning=_first_integer(completion_details, "reasoning_tokens", "reasoning"),
    )


def _empty_usage() -> dict[str, int]:
    return {
        "generation_count": 0,
        "input_total_tokens": 0,
        "input_cache_read_tokens": 0,
        "input_cache_write_tokens": 0,
        "output_total_tokens": 0,
        "output_reasoning_tokens": 0,
    }


def _usage_snapshot(usage: dict[str, int]) -> dict[str, int | float | None]:
    input_total = usage["input_total_tokens"]
    cache_read = usage["input_cache_read_tokens"]
    cache_write = usage["input_cache_write_tokens"]
    output_total = usage["output_total_tokens"]
    output_reasoning = usage["output_reasoning_tokens"]
    return {
        "generation_count": usage["generation_count"],
        "input_total_tokens": input_total,
        "input_uncached_tokens": max(0, input_total - cache_read - cache_write),
        "input_cache_read_tokens": cache_read,
        "input_cache_write_tokens": cache_write,
        "output_tokens": max(0, output_total - output_reasoning),
        "output_reasoning_tokens": output_reasoning,
        "output_total_tokens": output_total,
        "total_tokens": input_total + output_total,
        "cache_percent": (
            round(cache_read / input_total * 100, 2) if input_total else None
        ),
    }


def _add_usage(bucket: dict[str, int], usage: _CanonicalUsage) -> None:
    bucket["generation_count"] += 1
    bucket["input_total_tokens"] += usage.input_total_tokens
    bucket["input_cache_read_tokens"] += usage.input_cache_read_tokens
    bucket["input_cache_write_tokens"] += usage.input_cache_write_tokens
    bucket["output_total_tokens"] += usage.output_total_tokens
    bucket["output_reasoning_tokens"] += usage.output_reasoning_tokens


def aggregate_ocr_usage(
    records: Iterable[Any],
) -> dict[str, int | float | None]:
    """Agrega chamadas OCR diretas usando os mesmos nomes do usage do agente."""
    total = _empty_usage()
    for record in records:
        usage = _mapping(_mapping(record).get("usage"))
        if not usage:
            continue
        _add_usage(
            total,
            _canonical_usage(
                input_total=_first_integer(usage, "prompt_tokens", "input_tokens"),
                output_total=_first_integer(
                    usage, "completion_tokens", "output_tokens"
                ),
                cache_read=_first_integer(
                    usage, "cached_tokens", "cache_read_tokens", "cache_read"
                ),
                cache_write=_first_integer(
                    usage,
                    "cache_write_tokens",
                    "cache_creation_tokens",
                    "cache_write",
                    "cache_creation",
                ),
                reasoning=_first_integer(usage, "reasoning_tokens", "reasoning"),
            ),
        )
    snapshot = _usage_snapshot(total)
    call_count = snapshot.pop("generation_count")
    return {"call_count": call_count, **snapshot}


def _response_model(response: LLMResult) -> str:
    llm_output = _mapping(response.llm_output)
    model = llm_output.get("model_name") or llm_output.get("model")
    if model:
        return str(model)
    for generation_group in response.generations:
        for generation in generation_group:
            message = getattr(generation, "message", None)
            metadata = _mapping(getattr(message, "response_metadata", None))
            model = metadata.get("model_name") or metadata.get("model")
            if model:
                return str(model)
    return "unknown"


class SessionModelUsageHandler(BaseCallbackHandler):
    """Agrega usage canônico por profile sem depender da ingestão do Langfuse."""

    run_inline = True

    def __init__(self, model_configs: dict[str, dict[str, Any]]) -> None:
        self._lock = Lock()
        self._profiles = list(model_configs)
        self._models = {
            profile: str(config["model_name"])
            for profile, config in model_configs.items()
        }
        self._aliases: dict[str, str] = {}
        self._run_profiles: dict[str, str] = {}
        self._usage = {profile: _empty_usage() for profile in self._profiles}
        for profile, config in model_configs.items():
            for identity in (config.get("model"), config.get("model_name")):
                if not identity:
                    continue
                value = str(identity)
                self._aliases[value] = profile
                self._aliases[value.rsplit("/", 1)[-1]] = profile

    def _profile(self, identity: Any) -> str | None:
        if not identity:
            return None
        value = str(identity)
        return self._aliases.get(value) or self._aliases.get(value.rsplit("/", 1)[-1])

    def _remember_profile(
        self,
        run_id: UUID,
        serialized: dict[str, Any] | None,
        metadata: dict[str, Any] | None,
        kwargs: dict[str, Any],
    ) -> None:
        invocation = _mapping(kwargs.get("invocation_params"))
        serialized_kwargs = _mapping(_mapping(serialized).get("kwargs"))
        identities = (
            _mapping(metadata).get("ls_model_name"),
            invocation.get("model"),
            invocation.get("model_name"),
            serialized_kwargs.get("model"),
            serialized_kwargs.get("model_name"),
        )
        profile = next(
            (
                matched
                for identity in identities
                if (matched := self._profile(identity))
            ),
            None,
        )
        if profile is not None:
            with self._lock:
                self._run_profiles[str(run_id)] = profile

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Associa o alias solicitado ao run antes do proxy devolver o modelo real."""
        del messages
        self._remember_profile(run_id, serialized, metadata, kwargs)

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Mesmo vínculo para integrações que disparam o evento LLM genérico."""
        del prompts
        self._remember_profile(run_id, serialized, metadata, kwargs)

    @property
    def config_models(self) -> list[dict[str, str]]:
        """Configuração sanitizada, na ordem standard/mini/nano recebida."""
        return [
            {"model": profile, "model_name": self._models[profile]}
            for profile in self._profiles
        ]

    @property
    def model_usage(self) -> list[dict[str, Any]]:
        """Snapshot canônico por profile, com cache como parcela do input total."""
        with self._lock:
            return [
                {
                    "model": profile,
                    "model_name": self._models[profile],
                    **_usage_snapshot(self._usage[profile]),
                }
                for profile in self._profiles
            ]

    @property
    def iteration_usage(self) -> dict[str, int | float | None]:
        """Soma todas as gerações LangChain concluídas nesta requisição HTTP."""
        with self._lock:
            total = _empty_usage()
            for usage in self._usage.values():
                for key in total:
                    total[key] += usage[key]
            return _usage_snapshot(total)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID | None,
        **_: Any,
    ) -> None:
        """Registra uma geração concluída usando usage padronizado ou raw OpenAI."""
        usage = _standard_usage(response) or _raw_openai_usage(response)
        if usage is None:
            return
        with self._lock:
            profile = self._run_profiles.pop(str(run_id), None)
        profile = profile or self._profile(_response_model(response))
        if profile is None:
            return
        with self._lock:
            bucket = self._usage[profile]
            _add_usage(bucket, usage)
