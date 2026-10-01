"""Agregação de usage dos modelos usados pelo session_stream."""

from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from sei_ia.agents.session_agent.usage import (
    SessionModelUsageHandler,
    aggregate_ocr_usage,
)


def _result(
    model: str,
    *,
    input_total: int,
    output_total: int,
    cache_read: int,
    cache_write: int = 0,
    reasoning: int = 0,
) -> LLMResult:
    return LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(
                        content="ok",
                        usage_metadata={
                            "input_tokens": input_total,
                            "output_tokens": output_total,
                            "total_tokens": input_total + output_total,
                            "input_token_details": {
                                "cache_read": cache_read,
                                "cache_creation": cache_write,
                            },
                            "output_token_details": {"reasoning": reasoning},
                        },
                    )
                )
            ]
        ],
        llm_output={"model_name": model},
    )


def test_model_usage_aggregates_by_configured_profile():
    handler = SessionModelUsageHandler(
        {
            "standard": {
                "model": "seiia-ds",
                "model_name": "openai/seiia-ds",
            },
            "mini": {
                "model": "seiia-ds-mini",
                "model_name": "openai/seiia-ds-mini",
            },
            "nano": {
                "model": "seiia-ds-nano",
                "model_name": "openai/seiia-ds-nano",
            },
        }
    )

    handler.on_llm_end(
        _result(
            "seiia-ds",
            input_total=1_000,
            output_total=40,
            cache_read=250,
        ),
        run_id=None,
    )
    handler.on_llm_end(
        _result(
            "openai/seiia-ds",
            input_total=2_000,
            output_total=60,
            cache_read=750,
        ),
        run_id=None,
    )

    assert handler.config_models == [
        {"model": "standard", "model_name": "openai/seiia-ds"},
        {"model": "mini", "model_name": "openai/seiia-ds-mini"},
        {"model": "nano", "model_name": "openai/seiia-ds-nano"},
    ]
    assert handler.model_usage == [
        {
            "model": "standard",
            "model_name": "openai/seiia-ds",
            "generation_count": 2,
            "input_total_tokens": 3_000,
            "input_uncached_tokens": 2_000,
            "input_cache_read_tokens": 1_000,
            "input_cache_write_tokens": 0,
            "output_tokens": 100,
            "output_reasoning_tokens": 0,
            "output_total_tokens": 100,
            "total_tokens": 3_100,
            "cache_percent": 33.33,
        },
        {
            "model": "mini",
            "model_name": "openai/seiia-ds-mini",
            "generation_count": 0,
            "input_total_tokens": 0,
            "input_uncached_tokens": 0,
            "input_cache_read_tokens": 0,
            "input_cache_write_tokens": 0,
            "output_tokens": 0,
            "output_reasoning_tokens": 0,
            "output_total_tokens": 0,
            "total_tokens": 0,
            "cache_percent": None,
        },
        {
            "model": "nano",
            "model_name": "openai/seiia-ds-nano",
            "generation_count": 0,
            "input_total_tokens": 0,
            "input_uncached_tokens": 0,
            "input_cache_read_tokens": 0,
            "input_cache_write_tokens": 0,
            "output_tokens": 0,
            "output_reasoning_tokens": 0,
            "output_total_tokens": 0,
            "total_tokens": 0,
            "cache_percent": None,
        },
    ]
    assert handler.iteration_usage == {
        "generation_count": 2,
        "input_total_tokens": 3_000,
        "input_uncached_tokens": 2_000,
        "input_cache_read_tokens": 1_000,
        "input_cache_write_tokens": 0,
        "output_tokens": 100,
        "output_reasoning_tokens": 0,
        "output_total_tokens": 100,
        "total_tokens": 3_100,
        "cache_percent": 33.33,
    }


def test_model_usage_falls_back_to_openai_raw_usage():
    handler = SessionModelUsageHandler(
        {
            "standard": {
                "model": "seiia-ds",
                "model_name": "openai/seiia-ds",
            }
        }
    )
    result = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="ok"))]],
        llm_output={
            "model_name": "seiia-ds",
            "token_usage": {
                "prompt_tokens": 500,
                "completion_tokens": 25,
                "prompt_tokens_details": {"cached_tokens": 100},
            },
        },
    )

    handler.on_llm_end(result, run_id=None)

    assert handler.model_usage[0] == {
        "model": "standard",
        "model_name": "openai/seiia-ds",
        "generation_count": 1,
        "input_total_tokens": 500,
        "input_uncached_tokens": 400,
        "input_cache_read_tokens": 100,
        "input_cache_write_tokens": 0,
        "output_tokens": 25,
        "output_reasoning_tokens": 0,
        "output_total_tokens": 25,
        "total_tokens": 525,
        "cache_percent": 20.0,
    }


def test_model_usage_reads_stream_usage_from_generation_info():
    handler = SessionModelUsageHandler(
        {
            "standard": {
                "model": "seiia-ds",
                "model_name": "openai/seiia-ds",
            }
        }
    )
    result = LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(content="ok"),
                    generation_info={
                        "usage_metadata": {
                            "input_tokens": 40_712,
                            "output_tokens": 1_066,
                            "total_tokens": 41_778,
                            "input_token_details": {"cache_read": 40_576},
                        }
                    },
                )
            ]
        ],
        llm_output={"model_name": "seiia-ds", "token_usage": {}},
    )

    handler.on_llm_end(result, run_id=None)

    assert handler.model_usage[0] == {
        "model": "standard",
        "model_name": "openai/seiia-ds",
        "generation_count": 1,
        "input_total_tokens": 40_712,
        "input_uncached_tokens": 136,
        "input_cache_read_tokens": 40_576,
        "input_cache_write_tokens": 0,
        "output_tokens": 1_066,
        "output_reasoning_tokens": 0,
        "output_total_tokens": 1_066,
        "total_tokens": 41_778,
        "cache_percent": 99.67,
    }


def test_model_usage_uses_requested_alias_when_proxy_returns_canonical_model():
    handler = SessionModelUsageHandler(
        {
            "standard": {
                "model": "seiia-ds",
                "model_name": "openai/seiia-ds",
            }
        }
    )
    run_id = uuid4()
    handler.on_chat_model_start(
        {},
        [[]],
        run_id=run_id,
        metadata={"ls_model_name": "seiia-ds"},
    )

    handler.on_llm_end(
        _result(
            "gpt-5.4",
            input_total=1_000,
            output_total=50,
            cache_read=900,
        ),
        run_id=run_id,
    )

    assert handler.run_inline is True
    assert handler.model_usage[0] == {
        "model": "standard",
        "model_name": "openai/seiia-ds",
        "generation_count": 1,
        "input_total_tokens": 1_000,
        "input_uncached_tokens": 100,
        "input_cache_read_tokens": 900,
        "input_cache_write_tokens": 0,
        "output_tokens": 50,
        "output_reasoning_tokens": 0,
        "output_total_tokens": 50,
        "total_tokens": 1_050,
        "cache_percent": 90.0,
    }


def test_model_usage_separates_cache_write_and_reasoning():
    handler = SessionModelUsageHandler(
        {
            "standard": {
                "model": "seiia-ds",
                "model_name": "openai/seiia-ds",
            }
        }
    )

    handler.on_llm_end(
        _result(
            "seiia-ds",
            input_total=1_000,
            output_total=100,
            cache_read=300,
            cache_write=200,
            reasoning=40,
        ),
        run_id=None,
    )

    assert handler.model_usage[0] == {
        "model": "standard",
        "model_name": "openai/seiia-ds",
        "generation_count": 1,
        "input_total_tokens": 1_000,
        "input_uncached_tokens": 500,
        "input_cache_read_tokens": 300,
        "input_cache_write_tokens": 200,
        "output_tokens": 60,
        "output_reasoning_tokens": 40,
        "output_total_tokens": 100,
        "total_tokens": 1_100,
        "cache_percent": 30.0,
    }


def test_ocr_usage_uses_same_canonical_token_names():
    assert aggregate_ocr_usage(
        [
            {
                "usage": {
                    "prompt_tokens": 1_000,
                    "cached_tokens": 300,
                    "cache_write_tokens": 200,
                    "completion_tokens": 100,
                    "reasoning_tokens": 40,
                }
            }
        ]
    ) == {
        "call_count": 1,
        "input_total_tokens": 1_000,
        "input_uncached_tokens": 500,
        "input_cache_read_tokens": 300,
        "input_cache_write_tokens": 200,
        "output_tokens": 60,
        "output_reasoning_tokens": 40,
        "output_total_tokens": 100,
        "total_tokens": 1_100,
        "cache_percent": 30.0,
    }
