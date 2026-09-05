"""Superfície pública de texto: limpeza canônica, HTML→Markdown e extensão de arquivo.

Estes três helpers são consumidos identicamente pelo ETL e pelo assistente,
garantindo a mesma saída de limpeza para a mesma entrada.
"""

from __future__ import annotations

import logging
import re

from sei_extraction.html_to_md import HtmlTxtmd

logger = logging.getLogger(__name__)

_CONTROL_CHARS = re.compile(r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]")
_MULTIPLE_NEWLINES = re.compile(r"\n{3,}")
_HORIZONTAL_WHITESPACE = re.compile(r"[ \t]+")
_WHITESPACE_AROUND_NEWLINE = re.compile(r"[ \t]*\n[ \t]*")


def clean_text(text: str) -> str:
    """Limpa o conteúdo de um documento, preservando parágrafos.

    Remove NUL e demais caracteres de controle (NUL quebra a escrita de JSON),
    normaliza quebras de linha para `\\n`, colapsa 3+ quebras em `\\n\\n`
    (parágrafos sobrevivem), colapsa espaços/tabs horizontais e dá strip.
    Idempotente: aplicar duas vezes devolve a mesma string.
    """
    if not text:
        return ""
    text = text.replace("\x00", "")
    text = _CONTROL_CHARS.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTIPLE_NEWLINES.sub("\n\n", text)
    text = _HORIZONTAL_WHITESPACE.sub(" ", text)
    text = _WHITESPACE_AROUND_NEWLINE.sub("\n", text)
    return text.strip()


def html_to_markdown(html: str) -> str:
    """Converte HTML de documentos SEI para Markdown usando HtmlTxtmd."""
    try:
        html_txtmd = HtmlTxtmd()
        html_txtmd.processa(html)
        return html_txtmd.output
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Erro na conversão de HTML para Markdown. [{exc!s}]")
        return f"Erro na conversão de HTML para Markdown. [{exc!s}]"


def get_file_extension(filename: str) -> str:
    """Extrai a extensão em minúsculas do nome do arquivo, ou 'html' se não houver."""
    parts = filename.split(".")
    return parts[-1].lower() if len(parts) > 1 else "html"
