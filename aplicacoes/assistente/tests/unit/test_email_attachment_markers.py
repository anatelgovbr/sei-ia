"""Regressão para marcadores de anexos de e-mail no prompt."""

from sei_extraction.formatting import (
    format_email_with_attachments as _format_email_content_with_attachments,
)
from sei_extraction.text import html_to_markdown


def test_email_attachments_use_square_markers_and_all_attachments_are_kept():
    content = "<html><body><p>Corpo do e-mail</p></body></html>"
    attachments = [
        (1, "primeiro.pdf", "conteúdo do primeiro anexo"),
        (2, "segundo.txt", "conteúdo do segundo anexo"),
        (3, "terceiro.pdf", "conteúdo do terceiro anexo"),
    ]

    formatted = _format_email_content_with_attachments(content, attachments)

    assert "[conteudo_principal_do_email]" in formatted
    assert "[/conteudo_principal_do_email]" in formatted
    assert "[anexo_1 - primeiro.pdf]" in formatted
    assert "[/anexo_1 - primeiro.pdf]" in formatted
    assert "[anexo_2 - segundo.txt]" in formatted
    assert "[/anexo_2 - segundo.txt]" in formatted
    assert "[anexo_3 - terceiro.pdf]" in formatted
    assert "[/anexo_3 - terceiro.pdf]" in formatted
    assert "<anexo_" not in formatted
    assert "</anexo_" not in formatted

    converted = html_to_markdown(formatted)

    assert "[anexo_1 - primeiro.pdf]" in converted
    assert "[/anexo_1 - primeiro.pdf]" in converted
    assert "conteúdo do primeiro anexo" in converted
    assert "[anexo_2 - segundo.txt]" in converted
    assert "[/anexo_2 - segundo.txt]" in converted
    assert "conteúdo do segundo anexo" in converted
    assert "[anexo_3 - terceiro.pdf]" in converted
    assert "[/anexo_3 - terceiro.pdf]" in converted
    assert "conteúdo do terceiro anexo" in converted


def test_email_attachment_marker_sanitizes_filename_brackets():
    formatted = _format_email_content_with_attachments(
        "corpo", [(1, "arquivo[versao].pdf", "conteúdo")]
    )

    assert "[anexo_1 - arquivo(versao).pdf]" in formatted
    assert "[/anexo_1 - arquivo(versao).pdf]" in formatted
    assert "[anexo_1 - arquivo[versao].pdf]" not in formatted
