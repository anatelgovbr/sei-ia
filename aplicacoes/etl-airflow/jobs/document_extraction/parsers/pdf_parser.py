"""PDF document parser using PyMuPDF."""

import logging

import fitz

from jobs.document_extraction.text_processor import pre_processamento_pdf

logger = logging.getLogger(__name__)


def extract_text(file_path: str) -> str:
    """Extrai todo o texto de um arquivo PDF.

    Fluxo:
    1. Abre o arquivo PDF com PyMuPDF
    2. Itera por todas as páginas extraindo o texto
    3. Concatena o texto de todas as páginas
    4. Aplica pré-processamento (remove espaços duplos e quebras de linha desnecessárias)
    5. Retorna o texto limpo

    Args:
        file_path: Caminho para o arquivo PDF.

    Returns:
        Texto extraído e pré-processado do PDF completo.

    Raises:
        FileNotFoundError: Se o arquivo não existir.
        Exception: Para outros erros de processamento de PDF.
    """
    logger.debug(f"Extracting text from PDF: {file_path}")

    try:
        pdf = fitz.open(file_path)
        pages = []

        for page_index in range(pdf.page_count):
            page = pdf[page_index]
            text = page.get_text()
            pages.append(text)

        pdf.close()

        full_text = "\n".join(pages)
        return pre_processamento_pdf(full_text)

    except FileNotFoundError:
        logger.exception(f"PDF file not found: {file_path}")
        raise
    except Exception as e:
        logger.exception(f"Error extracting text from PDF {file_path}")
        msg = f"Failed to extract PDF content: {e}"
        raise Exception(msg) from e
