"""
Testes unitários para sei_ia/agents/pergunta/document_decision.py.

Cobre linhas não cobertas:
- calculate_max_chunks: branch else quando chunk excede o limite (linhas 94, 97)
"""

from unittest.mock import patch


def _make_user_state(max_ctx_len: int = 1000):
    return {
        "general_max_ctx_len": max_ctx_len,
        "user_request": "Pergunta curta",
    }


def _make_chunk(text: str) -> dict:
    return {"text": text}


# ---------------------------------------------------------------------------
# calculate_max_chunks — branch else (chunk excede limite)
# ---------------------------------------------------------------------------


def test_calculate_max_chunks_chunk_excede_limite_para_no_primeiro():
    """
    Quando o primeiro chunk já excede max_tokens, retorna 0 e entra no branch else.
    """
    from sei_ia.agents.pergunta.document_decision import calculate_max_chunks

    # Simular token_counter: pergunta=10, formatação=500 → base=510
    # max_ctx_len=512 → só 2 tokens disponíveis para chunks
    # chunk tem 100 tokens + 50 margem = 150 → não cabe
    def mock_token_counter(text):
        if text == "Pergunta curta":
            return 10
        return 100  # cada chunk tem 100 tokens

    with patch(
        "sei_ia.agents.pergunta.document_decision.token_counter",
        side_effect=mock_token_counter,
    ):
        result = calculate_max_chunks(
            [_make_chunk("texto longo que não cabe")],
            _make_user_state(max_ctx_len=512),
        )

    assert result == 0


def test_calculate_max_chunks_segundo_chunk_excede_limite():
    """
    Quando o segundo chunk excede o limite, retorna 1 (só o primeiro coube).
    """
    from sei_ia.agents.pergunta.document_decision import calculate_max_chunks

    call_count = {"n": 0}

    def mock_token_counter(text):
        if text == "Pergunta curta":
            return 10
        call_count["n"] += 1
        return 50 if call_count["n"] <= 1 else 5000  # 1º chunk pequeno, 2º enorme

    chunks = [_make_chunk("chunk pequeno"), _make_chunk("chunk enorme")]

    with patch(
        "sei_ia.agents.pergunta.document_decision.token_counter",
        side_effect=mock_token_counter,
    ):
        result = calculate_max_chunks(chunks, _make_user_state(max_ctx_len=1000))

    assert result == 1
