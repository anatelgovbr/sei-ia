"""Text processing utilities for document extraction."""

import logging
import re

from jobs.document_extraction.html_to_md.html_to_txtmd import HtmlTxtmd

logger = logging.getLogger(__name__)


def html_to_markdown(html: str) -> str:
    """Converte HTML de documentos SEI para Markdown usando HtmlTxtmd.

    Args:
        html: Conteúdo HTML do documento SEI.

    Returns:
        Texto convertido para Markdown.
    """
    try:
        html_txtmd = HtmlTxtmd()
        html_txtmd.processa(html)
        return html_txtmd.output
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Erro na conversão de HTML para Markdown. [{exc!s}]")
        return f"Erro na conversão de HTML para Markdown. [{exc!s}]"


def pre_processamento_pdf(text: str) -> str:
    """Pré-processa texto extraído de PDF: remove espaços duplos e quebras desnecessárias.

    Args:
        text: Texto de entrada.

    Returns:
        Texto pré-processado.
    """
    text = re.sub(r"[ ]{2,}", " ", text.strip())
    return re.sub(r"[ \n]{2,}", "\n", text)


def get_file_extension(filename: str) -> str:
    """Extrai a extensão do arquivo a partir do nome.

    Args:
        filename: Nome do arquivo.

    Returns:
        Extensão em minúsculas, ou 'html' se não houver extensão.
    """
    parts = filename.split(".")
    return parts[-1].lower() if len(parts) > 1 else "html"
