"""Superfície pública de texto: limpeza canônica, HTML→Markdown e extensão de arquivo.

Estes três helpers são consumidos identicamente pelo ETL e pelo assistente,
garantindo a mesma saída de limpeza para a mesma entrada.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Comment

from sei_extraction.exceptions import OfficeExtractionError
from sei_extraction.html_to_md import HtmlTxtmd
from sei_extraction.html_to_md.html.tag_types import HtmlTagTypes

logger = logging.getLogger(__name__)

_CONTROL_CHARS = re.compile(r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]")
_MULTIPLE_NEWLINES = re.compile(r"\n{3,}")
_HORIZONTAL_WHITESPACE = re.compile(r"[ \t]+")
_WHITESPACE_AROUND_NEWLINE = re.compile(r"[ \t]*\n[ \t]*")

_NON_CONTENT_TAGS = list(
    (set(HtmlTagTypes.IGNORE) | {"head", "script", "style", "noscript", "template"})
    - {"font"}
)
_BLOCK_TAGS = [
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "div",
    "blockquote",
    "pre",
    "section",
    "article",
    "header",
    "footer",
    "aside",
    "nav",
]


def _fallback_html_to_text(html: str) -> str:
    """Extrai texto legível de HTML usando BeautifulSoup com html.parser."""
    soup = BeautifulSoup(html, "html.parser")

    for comment in list(soup.find_all(string=lambda s: isinstance(s, Comment))):
        comment.extract()

    for font_tag in list(soup.find_all("font")):
        font_tag.unwrap()

    for tag in list(soup.find_all(_NON_CONTENT_TAGS)):
        tag.decompose()

    for element in list(soup.select("[style]")):
        if not element.attrs:
            continue
        style = element.attrs.get("style", "")
        if "display:none" in "".join(style.split()).lower():
            element.decompose()

    for br in list(soup.find_all("br")):
        br.replace_with("\n")

    for hr in list(soup.find_all("hr")):
        hr.replace_with("\n\n")

    for cell in list(soup.find_all(["td", "th"])):
        cell.append(" ")

    for tr in list(soup.find_all("tr")):
        tr.append("\n")

    for li in list(soup.find_all("li")):
        li.insert(0, "- ")
        li.append("\n")

    for block in list(soup.find_all(_BLOCK_TAGS)):
        block.insert(0, "\n")
        block.append("\n\n")

    text = soup.get_text()
    return clean_text(text)


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
    """Converte HTML de documentos SEI para Markdown usando HtmlTxtmd, com fallback BeautifulSoup."""
    if not html:
        return ""

    try:
        html_txtmd = HtmlTxtmd()
        html_txtmd.processa(html)
        return html_txtmd.output
    except Exception as custom_exc:
        logger.warning(
            "Falha no parser principal HtmlTxtmd (%s); utilizando fallback BeautifulSoup html.parser.",
            type(custom_exc).__name__,
        )
        try:
            output = _fallback_html_to_text(html)
        except Exception as fallback_exc:
            logger.exception(
                "Fallback BeautifulSoup html.parser falhou na extração de HTML."
            )
            raise OfficeExtractionError(
                f"Falha na extração de HTML (primário: {type(custom_exc).__name__}, fallback: {type(fallback_exc).__name__})"
            ) from fallback_exc

        if not output.strip() and bool(html.strip()):
            logger.error(
                "Fallback BeautifulSoup html.parser não produziu texto para entrada não vazia."
            )
            raise OfficeExtractionError(
                f"Fallback de extração de HTML não produziu texto para conteúdo não vazio (primário: {type(custom_exc).__name__})."
            ) from custom_exc

        return output


def get_file_extension(filename: str) -> str:
    """Extrai a extensão em minúsculas do nome do arquivo, ou 'html' se não houver."""
    parts = filename.split(".")
    return parts[-1].lower() if len(parts) > 1 else "html"
