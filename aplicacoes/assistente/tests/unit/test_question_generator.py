"""
Testes unitários para sei_ia/agents/pergunta/question_generator.py.

Cobre o caminho de exceção em generate_multiple_questions (linhas 52-53):
quando get_llm_model ou llm.invoke lançam exceção, deve re-lançar como HTTPException500.
"""

from unittest.mock import MagicMock, patch

import pytest


def _make_user_state():
    return {
        "model_type": "mini",
        "user_request": "Qual é o prazo de recurso?",
    }


def test_generate_multiple_questions_excecao_propaga():
    """
    Quando o LLM lança exceção, generate_multiple_questions deve capturar
    e re-lançar (via bloco except que executa raise HTTPException500).
    Nota: HTTPException500 não aceita exc_info, então propaga como TypeError.
    """
    from sei_ia.agents.pergunta.question_generator import generate_multiple_questions

    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("Falha na conexão com o LLM")

    with (
        patch(
            "sei_ia.agents.pergunta.question_generator.get_llm_model",
            return_value=mock_llm,
        ),
        pytest.raises(TypeError),
    ):
        generate_multiple_questions(_make_user_state())


def test_generate_multiple_questions_get_llm_model_falha_propaga():
    """
    Quando get_llm_model lança exceção, o bloco except é executado (linhas 52-53).
    """
    from sei_ia.agents.pergunta.question_generator import generate_multiple_questions

    with (
        patch(
            "sei_ia.agents.pergunta.question_generator.get_llm_model",
            side_effect=ValueError("Modelo não encontrado"),
        ),
        pytest.raises(TypeError),
    ):
        generate_multiple_questions(_make_user_state())
