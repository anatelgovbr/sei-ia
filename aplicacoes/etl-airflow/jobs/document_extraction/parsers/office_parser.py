"""Office document parser using Docling."""

import logging
from pathlib import Path

from jobs.document_extraction.text_processor import pre_processamento_pdf

logger = logging.getLogger(__name__)


def extract_text(file_path: str) -> str:
    """Extrai texto de documentos Office usando Docling.

    Suporta: DOCX, PPTX, HTML, CSV, ODT, ODP, DOC, JSON, PPT, RTF, XLM

    Fluxo:
    1. Inicializa o conversor Docling
    2. Converte o documento para formato interno do Docling
    3. Exporta o conteúdo para Markdown
    4. Aplica pré-processamento (remove espaços duplos e quebras de linha desnecessárias)
    5. Retorna o texto em Markdown

    Args:
        file_path: Caminho para o arquivo de documento.

    Returns:
        Texto extraído e pré-processado em formato Markdown.

    Raises:
        Exception: Para erros de processamento do documento.
    """
    # Lazy import para evitar ImportError quando docling/deepsearch-toolkit
    # não está disponível (ex: ambiente Airflow sem o extra [toolkit])
    from docling.document_converter import DocumentConverter

    logger.debug(f"Extracting text from office document with Docling: {file_path}")

    try:
        converter = DocumentConverter()
        result = converter.convert(Path(file_path))
        text_content = result.document.export_to_markdown()

        logger.debug(
            f"Successfully extracted {len(text_content)} characters from {file_path}"
        )
        return pre_processamento_pdf(text_content)

    except Exception as e:
        logger.exception(f"Error extracting text from office document {file_path}")
        msg = f"Failed to extract office document content: {e}"
        raise Exception(msg) from e
