"""Document reader module for extracting content from SEI documents."""

import logging
from pathlib import Path

from jobs.db_models.sei_db_handlers import SEIDBHandler
from jobs.document_extraction.parsers import (
    office_parser,
    pdf_parser,
    spreadsheet_parser,
)
from jobs.document_extraction.text_processor import html_to_markdown

logger = logging.getLogger(__name__)

SPREADSHEET_EXTENSIONS = ["xlsx", "xls", "xlsb", "xlsm", "ods"]
OFFICE_EXTENSIONS = [
    "docx",
    "pptx",
    "html",
    "htm",
    "csv",
    "odt",
    "odp",
    "doc",
    "json",
    "ppt",
    "rtf",
    "xlm",
    "txt",
]
PDF_EXTENSION = "pdf"


async def get_document_content(id_documento: str) -> str:
    """Extrai o conteúdo de um documento SEI.

    Fluxo:
    1. Consulta metadados do documento no banco de dados
    2. Identifica o tipo: interno (HTML) ou externo (arquivo)
    3. Chama o leitor apropriado para processar o conteúdo
    4. Retorna o texto extraído

    Args:
        id_documento: ID do documento no SEI.

    Returns:
        Conteúdo do documento extraído em texto/markdown.

    Raises:
        Exception: Erro ao processar o documento.
    """
    logger.debug(f"Getting content for document {id_documento}")

    try:
        df_doc_info = SEIDBHandler.md_ia_consulta_documento(
            id_documentos=id_documento, conteudo=False
        )

        if df_doc_info.empty:
            logger.error(f"Document {id_documento} not found")
            msg = f"Document {id_documento} not found"
            raise Exception(msg)

        doc_info = df_doc_info.iloc[0]
        content_type = doc_info.get("content_type", "html")

        if content_type.lower() in ["html", ""]:
            logger.debug(f"Document {id_documento} is internal (HTML)")
            return await read_internal_document(id_documento)
        logger.debug(f"Document {id_documento} is external ({content_type})")
        return read_external_document(id_documento, content_type)

    except Exception as e:
        logger.exception(f"Error getting content for document {id_documento}")
        msg = f"Failed to get document content: {e}"
        raise Exception(msg) from e


async def read_internal_document(id_documento: str) -> str:
    """Lê documento interno do SEI (HTML).

    Fluxo:
    1. Consulta conteúdo HTML do documento via API SEI
    2. Verifica se há conteúdo disponível
    3. Converte HTML para Markdown usando processador de texto
    4. Retorna o texto convertido

    Args:
        id_documento: ID do documento no SEI.

    Returns:
        Conteúdo do documento convertido para markdown.
    """
    logger.debug(f"Reading internal document {id_documento}")

    try:
        result = await SEIDBHandler.md_ia_consulta_conteudo_documento_async(
            id_documento
        )
        html_content = result.get("content_doc", "")

        if not html_content:
            logger.warning(f"Document {id_documento} has no content")
            return ""

        return html_to_markdown(html_content)

    except Exception as e:
        logger.exception(f"Error reading internal document {id_documento}")
        msg = f"Failed to read internal document: {e}"
        raise Exception(msg) from e


def read_external_document(id_documento: str, extension: str) -> str:
    """Lê documento externo do SEI (arquivo).

    Fluxo:
    1. Faz download do arquivo da API SEI para arquivo temporário
    2. Identifica o parser apropriado com base na extensão
    3. Extrai o conteúdo usando o parser específico (PDF, Office ou Planilha)
    4. Remove o arquivo temporário após processamento
    5. Retorna o texto extraído

    Args:
        id_documento: ID do documento no SEI.
        extension: Extensão do arquivo (pdf, docx, xlsx, etc.).

    Returns:
        Conteúdo extraído do documento.
    """
    logger.debug(f"Reading external document {id_documento} with extension {extension}")

    file_path = None
    try:
        file_path = SEIDBHandler.md_ia_download_arquivo_documento_externo(
            id_documento=id_documento, doc_extension=extension, id_anexo=None
        )

        extension_lower = extension.lower()

        if extension_lower == PDF_EXTENSION:
            content = pdf_parser.extract_text(file_path)
        elif extension_lower in OFFICE_EXTENSIONS:
            content = office_parser.extract_text(file_path)
        elif extension_lower in SPREADSHEET_EXTENSIONS:
            content = spreadsheet_parser.extract_text(file_path)
        else:
            msg = f"Unsupported file extension: {extension}"
            raise Exception(msg)

        return content

    except Exception:
        logger.exception(f"Error reading external document {id_documento}")
        raise
    finally:
        if file_path and Path(file_path).exists():
            try:
                Path(file_path).unlink()
                logger.debug(f"Cleaned up temporary file {file_path}")
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to cleanup temporary file {file_path}: {cleanup_error}"
                )
