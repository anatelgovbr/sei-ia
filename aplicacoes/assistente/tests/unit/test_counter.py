"""
Testes unitários para o módulo counter.py
"""

import pytest

from sei_ia.services.counter import token_counter


class TestTokenCounter:
    """Testes para a função token_counter."""

    def test_counter_with_normal_text(self):
        """Testa contagem de tokens com texto normal."""
        text = "Este é um texto de exemplo para testar a contagem de tokens."
        result = token_counter(text)

        assert isinstance(result, int)
        assert result > 0
        # Deve ser aproximadamente len(text) / 3.5
        expected = int(len(text) / 3.5)
        assert result == expected

    def test_counter_with_empty_string(self):
        """Testa contagem de tokens com string vazia."""
        text = ""
        result = token_counter(text)

        assert result == 0

    def test_counter_with_none(self):
        """Testa contagem de tokens com None."""
        result = token_counter(None)

        assert result == 0

    def test_counter_with_long_text(self):
        """Testa contagem de tokens com texto longo."""
        text = "palavra " * 1000  # 8000 caracteres
        result = token_counter(text)

        assert isinstance(result, int)
        assert result > 0
        expected = int(len(text) / 3.5)
        assert result == expected

    def test_counter_with_special_characters(self):
        """Testa contagem de tokens com caracteres especiais."""
        text = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        result = token_counter(text)

        assert isinstance(result, int)
        assert result > 0

    def test_counter_with_unicode_characters(self):
        """Testa contagem de tokens com caracteres unicode."""
        text = "Olá, mundo! 你好世界 🌍🌎🌏"
        result = token_counter(text)

        assert isinstance(result, int)
        assert result > 0

    def test_counter_with_newlines(self):
        """Testa contagem de tokens com quebras de linha."""
        text = "Linha 1\nLinha 2\nLinha 3"
        result = token_counter(text)

        assert isinstance(result, int)
        assert result > 0

    def test_counter_consistency(self):
        """Testa se a contagem é consistente para o mesmo texto."""
        text = "Teste de consistência"
        result1 = token_counter(text)
        result2 = token_counter(text)

        assert result1 == result2

    def test_counter_with_whitespace_only(self):
        """Testa contagem de tokens com apenas espaços em branco."""
        text = "     "
        result = token_counter(text)

        assert isinstance(result, int)
        assert result >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
