"""Tests for the public text surface: clean_text, html_to_markdown, get_file_extension."""

from __future__ import annotations

from sei_extraction.text import clean_text, get_file_extension, html_to_markdown


class TestCleanText:
    def test_empty_string(self):
        assert clean_text("") == ""

    def test_none_content(self):
        assert clean_text(None) == ""

    def test_normal_text_unchanged(self):
        text = "Este é um texto normal sem problemas."
        assert clean_text(text) == text

    def test_removes_null_character(self):
        assert clean_text("Texto com\x00caractere nulo") == "Texto comcaractere nulo"

    def test_removes_control_characters(self):
        assert clean_text("a\x01b\x02c\x03d\x04e") == "abcde"

    def test_normalizes_windows_line_breaks(self):
        assert (
            clean_text("Linha 1\r\nLinha 2\r\nLinha 3") == "Linha 1\nLinha 2\nLinha 3"
        )

    def test_normalizes_mac_line_breaks(self):
        assert clean_text("Linha 1\rLinha 2\rLinha 3") == "Linha 1\nLinha 2\nLinha 3"

    def test_collapses_three_or_more_newlines_to_paragraph(self):
        assert (
            clean_text("Parágrafo 1\n\n\n\nParágrafo 2") == "Parágrafo 1\n\nParágrafo 2"
        )

    def test_preserves_double_newlines(self):
        text = "Parágrafo 1\n\nParágrafo 2"
        assert clean_text(text) == text

    def test_preserves_single_newlines(self):
        text = "Linha 1\nLinha 2\nLinha 3"
        assert clean_text(text) == text

    def test_collapses_multiple_spaces(self):
        assert clean_text("Texto    com    espaços") == "Texto com espaços"

    def test_collapses_tabs(self):
        assert clean_text("Texto\t\tcom\t\ttabs") == "Texto com tabs"

    def test_strips_whitespace_around_newlines(self):
        assert clean_text("Linha 1   \n   Linha 2") == "Linha 1\nLinha 2"

    def test_strips_leading_trailing(self):
        assert clean_text("   Texto   ") == "Texto"

    def test_preserves_unicode_and_emoji(self):
        text = "café, açúcar, ñ 😀 🌍"
        assert clean_text(text) == text

    def test_idempotent(self):
        text = "  a\x00b  \r\n\r\n\r\n  c  \t d  "
        once = clean_text(text)
        assert clean_text(once) == once

    def test_complex_content(self):
        text = (
            "   Parágrafo 1\x00com\x01problemas   \r\n\r\n\r\n"
            "   Parágrafo 2    com    espaços  \t  extras   \r"
            "Parágrafo 3   "
        )
        result = clean_text(text)
        assert "\x00" not in result
        assert "\x01" not in result
        assert "\r" not in result
        assert "\n\n\n" not in result
        assert "  " not in result
        assert result == result.strip()


class TestHtmlToMarkdown:
    def test_returns_str(self):
        assert isinstance(html_to_markdown("<html><body></body></html>"), str)

    def test_converts_h1(self):
        assert "# Título" in html_to_markdown(
            "<html><body><h1>Título</h1></body></html>"
        )

    def test_converts_h2(self):
        result = html_to_markdown("<html><body><h2>Subtítulo</h2></body></html>")
        assert "## Subtítulo" in result

    def test_converts_unordered_list(self):
        html = "<html><body><ul><li>Item 1</li><li>Item 2</li></ul></body></html>"
        result = html_to_markdown(html)
        assert "- Item 1" in result
        assert "- Item 2" in result

    def test_converts_ordered_list(self):
        html = "<html><body><ol><li>Primeiro</li><li>Segundo</li></ol></body></html>"
        assert "1. Primeiro" in html_to_markdown(html)

    def test_converts_hr(self):
        assert "---" in html_to_markdown("<html><body><hr/></body></html>")


class TestGetFileExtension:
    def test_lowercases(self):
        assert get_file_extension("documento.PDF") == "pdf"

    def test_html(self):
        assert get_file_extension("arquivo.html") == "html"

    def test_no_extension_defaults_to_html(self):
        assert get_file_extension("arquivo") == "html"

    def test_multiple_dots_returns_last(self):
        assert get_file_extension("arquivo.v2.txt") == "txt"

    def test_returns_str(self):
        assert isinstance(get_file_extension("doc.pdf"), str)
