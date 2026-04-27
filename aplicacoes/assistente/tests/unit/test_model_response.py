"""
Testes unitários para sei_ia/routers/chat/model_response.py.

Cobre linhas não cobertas:
- ModelResponse.persist_log_api() → retorna id_request (linha 92)
- ModelResponseWithMetadata.to_dict() com reasoning presente (linha 156)
- ModelResponseWithMetadata.persist_log_api() → retorna id_request (linha 163)
"""

from unittest.mock import patch


def _make_user_state(id_request=42, model_type="mini", reasoning=None):
    return {
        "id_request": id_request,
        "model_type": model_type,
        "response": {
            "response": "Resposta teste",
            "n_tokens": [10, 5],
            "finish_reason": "stop",
            "type_choiced_summary": "Not found",
            "reasoning": reasoning,
        },
        "user_request": "Pergunta",
        "temperature": 0.7,
        "use_websearch": False,
        "use_thinking": False,
        "doc_paged": False,
        "doc_summarized": False,
        "doc_rag": False,
        "doc_false_rag": False,
        "all_tokens_counter": 0,
        "intent": None,
    }


_mock_model_params = {"model_name": "gpt-4o-mini", "max_ctx_len": 128_000}


# ---------------------------------------------------------------------------
# ModelResponse
# ---------------------------------------------------------------------------


def test_model_response_persist_log_api_retorna_id_request():
    """persist_log_api deve retornar o id_request do user_state."""
    from sei_ia.routers.chat.model_response import ModelResponse

    with patch(
        "sei_ia.routers.chat.model_response.get_model_config",
        return_value=_mock_model_params,
    ):
        mr = ModelResponse(_make_user_state(id_request=99))

    result = mr.persist_log_api()

    assert result == 99


# ---------------------------------------------------------------------------
# ModelResponseWithMetadata
# ---------------------------------------------------------------------------


def test_model_response_with_metadata_reasoning_presente_no_dict():
    """Quando reasoning não é None, deve estar no dicionário retornado por to_dict()."""
    from sei_ia.routers.chat.model_response import ModelResponseWithMetadata

    state = _make_user_state(reasoning="Chain of thought aqui")

    with patch(
        "sei_ia.routers.chat.model_response.get_model_config",
        return_value=_mock_model_params,
    ):
        mr = ModelResponseWithMetadata(state)
        result = mr.to_dict()

    assert "reasoning" in result
    assert result["reasoning"] == "Chain of thought aqui"


def test_model_response_with_metadata_reasoning_none_nao_presente():
    """Quando reasoning é None, não deve estar no dicionário."""
    from sei_ia.routers.chat.model_response import ModelResponseWithMetadata

    state = _make_user_state(reasoning=None)

    with patch(
        "sei_ia.routers.chat.model_response.get_model_config",
        return_value=_mock_model_params,
    ):
        mr = ModelResponseWithMetadata(state)
        result = mr.to_dict()

    assert "reasoning" not in result


def test_model_response_with_metadata_persist_log_api_retorna_id_request():
    """persist_log_api deve retornar o id_request do user_state."""
    from sei_ia.routers.chat.model_response import ModelResponseWithMetadata

    with patch(
        "sei_ia.routers.chat.model_response.get_model_config",
        return_value=_mock_model_params,
    ):
        mr = ModelResponseWithMetadata(_make_user_state(id_request=77))

    result = mr.persist_log_api()

    assert result == 77
