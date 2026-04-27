"""
Testes unitários para funções utilitárias de sei_ia/routers/chat/__init__.py.

Cobre:
1. _build_langfuse_tags — caminho de exceção (state.get() lança exceção)
2. _build_langfuse_tags — caminhos normais (com e sem tags)
3. create_user_state — body decode error (state.body não é bytes decodificáveis UTF-8)
"""

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# 1. _build_langfuse_tags
# ---------------------------------------------------------------------------


def test_build_langfuse_tags_excecao_retorna_lista_vazia():
    """
    Se state.get() lança exceção, _build_langfuse_tags deve capturar e retornar [].
    """
    from sei_ia.routers.chat import _build_langfuse_tags

    bad_state = MagicMock()
    bad_state.get.side_effect = RuntimeError("state corrompido")

    tags = _build_langfuse_tags(bad_state)

    assert tags == []


def test_build_langfuse_tags_sem_campos_retorna_lista_vazia():
    """State sem campos relevantes deve retornar lista vazia."""
    from sei_ia.routers.chat import _build_langfuse_tags

    state = {
        "intent": None,
        "use_websearch": False,
        "use_thinking": False,
        "doc_rag": False,
        "rag_method": None,
    }

    tags = _build_langfuse_tags(state)

    assert tags == []


def test_build_langfuse_tags_com_intent():
    """State com intent deve incluir tag 'intent:<valor>'."""
    from sei_ia.routers.chat import _build_langfuse_tags

    state = {
        "intent": "pesquisa",
        "use_websearch": False,
        "use_thinking": False,
        "doc_rag": False,
        "rag_method": None,
    }
    tags = _build_langfuse_tags(state)

    assert "intent:pesquisa" in tags


def test_build_langfuse_tags_com_websearch():
    """State com use_websearch=True deve incluir tag 'websearch'."""
    from sei_ia.routers.chat import _build_langfuse_tags

    state = {
        "intent": None,
        "use_websearch": True,
        "use_thinking": False,
        "doc_rag": False,
        "rag_method": None,
    }
    tags = _build_langfuse_tags(state)

    assert "websearch" in tags


def test_build_langfuse_tags_com_thinking():
    """State com use_thinking=True deve incluir tag 'thinking'."""
    from sei_ia.routers.chat import _build_langfuse_tags

    state = {
        "intent": None,
        "use_websearch": False,
        "use_thinking": True,
        "doc_rag": False,
        "rag_method": None,
    }
    tags = _build_langfuse_tags(state)

    assert "thinking" in tags


def test_build_langfuse_tags_com_rag_method():
    """State com rag_method deve incluir tag 'rag_method:<valor>'."""
    from sei_ia.routers.chat import _build_langfuse_tags

    state = {
        "intent": None,
        "use_websearch": False,
        "use_thinking": False,
        "doc_rag": True,
        "rag_method": "hybrid",
    }
    tags = _build_langfuse_tags(state)

    assert "rag" in tags
    assert "rag_method:hybrid" in tags


# ---------------------------------------------------------------------------
# 2. create_user_state — body decode error path
# ---------------------------------------------------------------------------


def test_create_user_state_body_decode_error():
    """
    Quando state.body não pode ser decodificado como UTF-8,
    create_user_state deve usar str(body) como fallback e não lançar exceção.
    """
    from sei_ia.data.pydantic_models import ChatRequest
    from sei_ia.routers.chat import create_user_state

    mock_request_starlette = MagicMock()
    mock_request_starlette.state.body = b"\xff\xfe bytes inv\xe1lidos"  # não é UTF-8

    chat_request = ChatRequest(id_usuario=1, id_topico=0, text="Olá")

    model_data = {
        "model_type": "mini",
        "max_ctx_len": 128_000,
        "max_output_tokens": 16_000,
        "model_name": "gpt-4o-mini",
    }

    mock_model_params = {
        "max_ctx_len": 128_000,
        "max_output_tokens": 16_000,
        "model_name": "gpt-4o-mini",
    }

    with patch("sei_ia.routers.chat.get_model_config", return_value=mock_model_params):
        # Deve funcionar sem lançar exceção mesmo com bytes inválidos
        user_state = create_user_state(chat_request, mock_request_starlette, model_data)

    assert user_state is not None
    # O campo original_request_body deve ser uma string (fallback para str(bytes))
    assert isinstance(user_state.get("original_request_body"), str)
