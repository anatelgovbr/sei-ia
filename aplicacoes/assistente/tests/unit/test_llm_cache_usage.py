from langchain_openai.chat_models.base import _create_usage_metadata_responses
from langfuse.langchain.CallbackHandler import _parse_usage_model


def test_responses_usage_preserves_cache_read_tokens():
    usage = _create_usage_metadata_responses(
        {
            "input_tokens": 4096,
            "input_tokens_details": {"cached_tokens": 1024},
            "output_tokens": 8,
            "output_tokens_details": {"reasoning_tokens": 2},
            "total_tokens": 4104,
        }
    )

    assert usage["input_token_details"] == {"cache_read": 1024}

    assert _parse_usage_model(usage) == {
        "input": 3072,
        "input_cache_read": 1024,
        "output": 6,
        "output_reasoning": 2,
        "total": 4104,
    }
