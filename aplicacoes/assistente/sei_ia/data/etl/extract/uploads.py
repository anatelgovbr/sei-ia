"""Módulo para download e extração de texto de uploads do Assistente IA."""

import asyncio
import logging

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.database.sei_db_handlers import SEIDBHandler
from sei_ia.data.etl.extract.external import (
    EXT_DOCLING_SUPPORTED,
    EXT_ODP,
    EXT_PLAIN_TEXT,
    EXT_UNSTRUCTURED,
    _get_text_from_file_with_docling,
    _get_text_from_odp_file,
    _get_text_from_plain_text_file,
    _get_text_pdf_from_file,
    _get_text_with_unstructured,
)
from sei_ia.data.pydantic_models import UploadItem
from sei_ia.services.exceptions.pdf_exceptions import PDFExtractionError
from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

setup_logging()
logger = logging.getLogger(__name__)

EXT_SPREADSHEETS = ["ods", "xls", "xlsb", "xlsm", "xlsx"]
EXT_AUDIO = ["mp3", "mp4", "wav", "ogg", "m4a", "webm", "flac", "aac", "opus", "wma"]

AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION = (
    "\n\nAtenção: um ou mais arquivos de áudio foram enviados pelo usuário e transcritos "
    "automaticamente. O conteúdo transcrito está disponível na seção <uploads> da mensagem. "
    "Considere o texto transcrito como parte da comunicação do usuário ao formular sua resposta."
)

UPLOAD_BLOCK_TEMPLATE = """---
# Arquivo: {nome_original}
{conteudo}"""

UPLOADS_WRAPPER_TEMPLATE = """<uploads>
{blocos}
</uploads>"""


def extract_text_from_file(file_path: str, extensao: str) -> str:
    """Extrai texto de um arquivo local baseado na sua extensão.

    Args:
        file_path: Caminho completo para o arquivo em /tmp/.
        extensao: Extensão do arquivo (sem ponto), ex: "pdf", "docx", "png".

    Returns:
        Texto extraído, ou mensagem indicando formato não suportado.
    """
    ext = extensao.lower().strip(".")

    if ext == "pdf":
        try:
            return _get_text_pdf_from_file(file_path, None, None)
        except (PDFExtractionError, IndexError, RuntimeError) as pdf_error:
            logger.warning(
                f"PyMuPDF falhou ao processar PDF '{file_path}' ({type(pdf_error).__name__}). "
                f"Tentando fallback com Docling..."
            )
            try:
                content = _get_text_from_file_with_docling(file_path)
                logger.info(f"Docling conseguiu extrair conteúdo do PDF '{file_path}'")
                return content
            except Exception as docling_error:
                logger.error(
                    f"Ambos PyMuPDF e Docling falharam para PDF '{file_path}'. "
                    f"Erro Docling: {docling_error}"
                )
                raise pdf_error from docling_error

    if ext in EXT_SPREADSHEETS:
        from sei_ia.data.etl.extract.external import _get_spreadsheets_from_file

        return _get_spreadsheets_from_file(file_path)

    if ext in EXT_DOCLING_SUPPORTED:
        return _get_text_from_file_with_docling(file_path)

    if ext in EXT_PLAIN_TEXT:
        return _get_text_from_plain_text_file(file_path)

    if ext in EXT_UNSTRUCTURED:
        return _get_text_with_unstructured(file_path)

    if ext in EXT_ODP:
        return _get_text_from_odp_file(file_path)

    logger.warning(f"Extensão '{ext}' não suportada para extração de texto em uploads.")
    return f"[Formato .{ext} não suportado para extração de texto]"


async def download_and_extract_upload(upload: UploadItem) -> tuple[str, str]:
    """Faz download e extrai texto (ou transcreve áudio) de um único upload.

    O arquivo é baixado via SEIDBHandler e salvo em /tmp/. Para arquivos de
    áudio (extensões em EXT_AUDIO), a transcrição é realizada via LiteLLM Proxy
    antes de retornar. Para demais tipos, o texto é extraído diretamente.

    Args:
        upload: Item de upload com id_upload, nome_original e extensao.

    Returns:
        Tupla (nome_original, conteudo) onde conteudo é o texto extraído ou
        transcrito.
    """
    loop = asyncio.get_running_loop()
    ext = upload.extensao.lower().strip(".")
    try:
        file_path = await loop.run_in_executor(
            None,
            SEIDBHandler.md_ia_download_arquivo_upload_assistente,
            upload.id_upload,
            upload.extensao,
        )
        logger.debug(
            f"Upload {upload.id_upload} ({upload.nome_original}) salvo em '{file_path}'"
        )

        if ext in EXT_AUDIO:
            logger.info(
                f"Upload {upload.id_upload} ({upload.nome_original}) identificado como "
                f"arquivo de áudio (.{ext}). Iniciando transcrição."
            )
            conteudo = await transcribe_audio_file(file_path, upload.extensao)
            return (upload.nome_original, conteudo)

        conteudo = await loop.run_in_executor(
            None,
            extract_text_from_file,
            file_path,
            upload.extensao,
        )
        return (upload.nome_original, conteudo)

    except Exception:
        logger.exception(
            f"Erro ao processar upload {upload.id_upload} ({upload.nome_original})"
        )
        return (
            upload.nome_original,
            f"[Erro ao processar o arquivo {upload.nome_original}]",
        )


async def process_uploads(uploads: list[UploadItem]) -> str:
    """Processa todos os uploads em paralelo e retorna o conteúdo formatado.

    Os downloads, extrações e transcrições ocorrem em paralelo via asyncio.gather.
    Arquivos de áudio são transcritos automaticamente antes de serem formatados
    junto aos demais uploads.

    Args:
        uploads: Lista de itens de upload.

    Returns:
        String formatada com o conteúdo de todos os uploads, ou string vazia
        se a lista for vazia/None.
    """
    if not uploads:
        return ""

    tasks = [download_and_extract_upload(upload) for upload in uploads]
    results = await asyncio.gather(*tasks)

    blocos = [
        UPLOAD_BLOCK_TEMPLATE.format(nome_original=nome, conteudo=conteudo)
        for nome, conteudo in results
    ]

    return UPLOADS_WRAPPER_TEMPLATE.format(blocos="\n".join(blocos))
