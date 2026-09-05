"""
Testes unitários para o módulo counter.py
"""

import pytest
import tiktoken

from sei_ia.services.counter import token_counter

_ENC = tiktoken.get_encoding("o200k_base")


class TestTokenCounter:
    """Testes para a função token_counter."""

    def test_counter_with_normal_text(self):
        """Testa contagem de tokens com texto normal."""
        text = "Este é um texto de exemplo para testar a contagem de tokens."
        result = token_counter(text)

        assert isinstance(result, int)
        assert result > 0
        # Deve casar com o tokenizer real (o200k_base), num unico chunk
        assert result == len(_ENC.encode(text, disallowed_special=()))

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
        text = "palavra " * 1000  # 8000 caracteres, um unico chunk
        result = token_counter(text)

        assert isinstance(result, int)
        assert result > 0
        assert result == len(_ENC.encode(text, disallowed_special=()))

    def test_counter_chunks_large_text_without_panic(self):
        """Texto acima de _CHUNK_CHARS e encodado em pedacos, sem panic."""
        text = "Oficio no 1110/2024/COGE/SCO-ANATEL. " * 30_000  # ~1.1M chars
        result = token_counter(text)

        assert isinstance(result, int)
        assert result > 100_000

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
