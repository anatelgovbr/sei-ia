"""
Testes unitários para o módulo content_cleaner.py
"""

import pytest

from sei_ia.services.embedder.content_cleaner import clean_document_content


class TestCleanDocumentContent:
    """Testes para a função clean_document_content."""

    def test_clean_empty_string(self):
        """Testa limpeza de string vazia."""
        result = clean_document_content("")
        assert result == ""

    def test_clean_none_content(self):
        """Testa limpeza de conteúdo None."""
        result = clean_document_content(None)
        assert result == ""

    def test_clean_normal_text(self):
        """Testa limpeza de texto normal."""
        text = "Este é um texto normal sem problemas."
        result = clean_document_content(text)
        assert result == text

    def test_clean_null_character(self):
        """Testa remoção de caractere NUL (0x00)."""
        text = "Texto com\x00caractere nulo"
        result = clean_document_content(text)
        assert "\x00" not in result
        assert result == "Texto comcaractere nulo"

    def test_clean_control_characters(self):
        """Testa remoção de caracteres de controle."""
        text = "Texto\x01com\x02caracteres\x03de\x04controle"
        result = clean_document_content(text)
        assert result == "Textocomcaracteresdecontrole"

    def test_clean_windows_line_breaks(self):
        """Testa normalização de quebras de linha Windows."""
        text = "Linha 1\r\nLinha 2\r\nLinha 3"
        result = clean_document_content(text)
        assert "\r\n" not in result
        assert result == "Linha 1\nLinha 2\nLinha 3"

    def test_clean_mac_line_breaks(self):
        """Testa normalização de quebras de linha Mac."""
        text = "Linha 1\rLinha 2\rLinha 3"
        result = clean_document_content(text)
        assert "\r" not in result
        assert result == "Linha 1\nLinha 2\nLinha 3"

    def test_clean_multiple_line_breaks(self):
        """Testa remoção de múltiplas quebras de linha consecutivas."""
        text = "Parágrafo 1\n\n\n\nParágrafo 2"
        result = clean_document_content(text)
        assert result == "Parágrafo 1\n\nParágrafo 2"

    def test_clean_multiple_spaces(self):
        """Testa remoção de múltiplos espaços consecutivos."""
        text = "Texto    com    múltiplos    espaços"
        result = clean_document_content(text)
        assert result == "Texto com múltiplos espaços"

    def test_clean_spaces_around_line_breaks(self):
        """Testa remoção de espaços ao redor de quebras de linha."""
        text = "Linha 1   \n   Linha 2"
        result = clean_document_content(text)
        assert result == "Linha 1\nLinha 2"

    def test_clean_trailing_whitespace(self):
        """Testa remoção de espaços no início e fim."""
        text = "   Texto com espaços   "
        result = clean_document_content(text)
        assert result == "Texto com espaços"

    def test_clean_tabs(self):
        """Testa limpeza de tabs."""
        text = "Texto\t\tcom\t\ttabs"
        result = clean_document_content(text)
        assert result == "Texto com tabs"

    def test_clean_mixed_whitespace(self):
        """Testa limpeza de espaços e tabs misturados."""
        text = "Texto  \t  com  \t  espaços  \t  e  \t  tabs"
        result = clean_document_content(text)
        # Cada sequência de espaços/tabs deve virar um único espaço
        assert "  " not in result
        assert "\t" not in result

    def test_clean_unicode_text(self):
        """Testa que texto unicode é preservado."""
        text = "Texto com acentuação: café, açúcar, ñ"
        result = clean_document_content(text)
        assert result == text

    def test_clean_emoji(self):
        """Testa que emojis são preservados."""
        text = "Texto com emoji 😀 🌍"
        result = clean_document_content(text)
        assert result == text

    def test_clean_complex_content(self):
        """Testa limpeza de conteúdo complexo com vários problemas."""
        text = (
            "   Parágrafo 1\x00com\x01problemas   \r\n"
            "\r\n"
            "\r\n"
            "   Parágrafo 2    com    espaços  \t  extras   \r"
            "Parágrafo 3   "
        )
        result = clean_document_content(text)

        # Deve ter removido caracteres NUL e de controle
        assert "\x00" not in result
        assert "\x01" not in result
        # Deve ter normalizado quebras de linha
        assert "\r\n" not in result
        assert "\r" not in result
        # Não deve ter mais de duas quebras consecutivas
        assert "\n\n\n" not in result
        # Não deve ter múltiplos espaços
        assert "  " not in result
        # Deve ter feito trim
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_clean_special_characters_preserved(self):
        """Testa que caracteres especiais válidos são preservados."""
        text = "Texto com !@#$%^&*()_+-=[]{}|;':\",./<>?"
        result = clean_document_content(text)
        # Caracteres especiais devem ser preservados
        assert "!@#$%^&*()" in result

    def test_clean_preserves_single_newlines(self):
        """Testa que quebras de linha simples são preservadas."""
        text = "Linha 1\nLinha 2\nLinha 3"
        result = clean_document_content(text)
        assert result == text

    def test_clean_preserves_double_newlines(self):
        """Testa que duas quebras de linha são preservadas."""
        text = "Parágrafo 1\n\nParágrafo 2"
        result = clean_document_content(text)
        assert result == text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
