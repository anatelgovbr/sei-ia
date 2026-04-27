"""Módulo de extração de documentos externos."""

import inspect
import logging
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd
from docling.document_converter import DocumentConverter

from sei_ia.configs.settings_config import settings
from sei_ia.data.database.sei_db_handlers import SeiDBAPIError, SEIDBHandler
from sei_ia.data.etl.extract.pdf_ocr_extractor import (
    extract_text_hybrid_sync,
    has_scanned_pages,
)
from sei_ia.data.etl.text_preprocess import pre_processamento_pdf
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException204,
    HTTPException404,
    HTTPException406,
    HTTPException408,
    HTTPException409,
    HTTPException500,
    HTTPException503,
)
from sei_ia.services.exceptions.pdf_exceptions import (
    OCRExtractionError,
    PDFExtractionError,
)

logger = logging.getLogger(__name__)

ERRO500 = "Erro de conexão ao BD para busca do conteúdo do documento id {id_documento}."

EXT_PAGINADOS = ["pdf", "ods", "xls", "xlsb", "xlsm", "xlsx"]
EXT_DOCLING_SUPPORTED = ["html", "htm", "docx", "pptx", "md", "asciidoc"]
EXT_PLAIN_TEXT = ["txt", "json", "csv", "xml"]
EXT_UNSTRUCTURED = ["rtf", "odt", "doc", "ppt"]
EXT_ODP = ["odp"]


def raise_http_exception(exc_class: Exception, message: str) -> Exception:
    """Função de workaround para erros pylint.

    Esta função centraliza o lançamento de exceções HTTP personalizadas
    e a geração de logs de exceção, permitindo que o código fique mais
    organizado e atenda às regras de estilo pylint, como TRY301.

    Args:
        exc_class (Exception): A classe da exceção HTTP a ser lançada.
        message (str): A mensagem de erro que será registrada no log e
                       associada à exceção.

    Raises:
        exc_class: Lança a exceção especificada pelo argumento `exc_class`.
    """
    logger.exception(message)
    raise exc_class


def get_doc_ext_from_id(
    id_documento: str,
    pag_ini: int | None = None,
    pag_fim: int | None = None,
    doc_extension: str | None = None,
    force_download: bool = False,
) -> str:
    """Extrai o conteúdo textual de um documento a partir de seu ID.

    Parâmetros:
    id_documento (str): Identificador do documento.
    pag_ini (int | None, opcional): Número da página inicial para extração, se aplicável. Padrão é None.
    pag_fim (int | None, opcional): Número da página final para extração, se aplicável. Padrão é None.
    doc_extension (str | None = None): extensão do arquivo que contém o conteúdo do documento
    force_download (bool): Flag para forçar download do arquivo externo ao invés de consultar conteúdo

    Retorna:
    str: Conteúdo do documento.

    Exceções:
    Exception: Lança uma exceção se ocorrer um erro ao buscar o conteúdo do documento.
    HTTPException404: Lança uma exceção se o documento não for encontrado.
    HTTPException204: Lança uma exceção se o documento não tiver conteúdo.
    HTTPException409: Lança uma exceção se mais de um documento for encontrado para o ID fornecido.
    HTTPException500: Lança uma exceção se ocorrer um erro de conexão ao Solr do SEI.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    # Cenário 1 e 3: Usar download forçado quando force_download=True
    if force_download:
        logger.debug(f"Force download habilitado para documento {id_documento}")
        return get_paged_doc_from_id(id_documento, pag_ini, pag_fim, doc_extension)

    # Cenário 3: Paginação normal, extensões paginadas, formatos Docling, texto simples ou unstructured
    if (
        pag_ini
        or pag_fim
        or doc_extension in EXT_PAGINADOS
        or doc_extension in EXT_DOCLING_SUPPORTED
        or doc_extension in EXT_PLAIN_TEXT
        or doc_extension in EXT_UNSTRUCTURED
        or doc_extension in EXT_ODP
    ):
        msg = (
            f"{inspect.currentframe().f_code.co_name}: "
            f"paginação do {doc_extension} id {id_documento} "
            "([{pag_ini}:{pag_fim}])"
        )
        logger.debug(msg)
        return get_paged_doc_from_id(id_documento, pag_ini, pag_fim, doc_extension)

    # Cenário padrão: consulta conteúdo via API
    df_conteudo = SEIDBHandler.md_ia_consulta_conteudo_documento(id_documento)
    content = df_conteudo.loc[0, "content_doc"]
    if df_conteudo.empty:
        msg = f"Documento id {id_documento} não encontrado!"
        raise_http_exception(HTTPException404, msg)
    if not bool(content and str(content).strip()):
        msg = f"Documento id {id_documento} está sem conteúdo!"
        raise_http_exception(HTTPException204, msg)

    return pre_processamento_pdf(content)


def get_paged_doc_from_id(
    id_documento: str,
    pag_ini: int | None,
    pag_fim: int | None,
    doc_extension: str,  # noqa: C901, PLR0912
) -> str:
    """Obtém o conteúdo de um documento a partir do seu ID usando diferentes parsers.

    Suporta PDF (com paginação), planilhas Excel/ODS (com paginação por abas),
    e documentos DOCX, PPTX, HTML, CSV, imagens, etc. via Docling (sem paginação).

    Parâmetros:
    id_documento (str): Identificador do documento.
    pag_ini (int | None): Número da página/aba inicial para extração. Padrão é None.
    pag_fim (int | None): Número da página/aba final para extração. Padrão é None.
    doc_extension (str): Extensão do arquivo (pdf, docx, xlsx, etc.).

    Retorna:
    str: Texto extraído do documento.

    Exceções:
    HTTPException406: Lança uma exceção se a seleção de páginas for solicitada para um documento que não suporta paginação.
    HTTPException500: Lança uma exceção se ocorrer um erro no processo de buscar e extrair conteúdo do documento.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    try:
        # Verificar se é arquivo de texto simples (sem paginação)
        if (
            doc_extension in EXT_PLAIN_TEXT
            or doc_extension in EXT_DOCLING_SUPPORTED
            or doc_extension in EXT_UNSTRUCTURED
            or doc_extension in EXT_ODP
        ):
            if pag_ini or pag_fim:
                msg = f"Documento {doc_extension.upper()} id {id_documento} não suporta paginação!"
                logger.error(msg)
                msg = "Não posso definir um intervalo de páginas para esse documento"
                raise_http_exception(HTTPException406, msg)
        elif doc_extension not in EXT_PAGINADOS:
            msg = (
                f"Documento {doc_extension.upper()} id {id_documento} não é suportado!"
            )
            logger.error(msg)
            msg = "Formato de documento não suportado"
            raise_http_exception(HTTPException406, msg)
        file_name = SEIDBHandler.md_ia_download_arquivo_documento_externo(
            id_documento, doc_extension, None
        )
        try:
            if doc_extension in EXT_PLAIN_TEXT:
                # Arquivos de texto simples: ler diretamente sem parser
                file_content = _get_text_from_plain_text_file(file_name)
            elif doc_extension == "pdf":
                try:
                    file_content = _get_text_pdf_from_file(file_name, pag_ini, pag_fim)
                except (PDFExtractionError, IndexError, RuntimeError) as pdf_error:
                    logger.warning(
                        f"PyMuPDF falhou ao processar PDF {id_documento} ({type(pdf_error).__name__}). "
                        f"Tentando fallback com Docling..."
                    )
                    try:
                        if pag_ini or pag_fim:
                            logger.warning(
                                f"Paginação ({pag_ini}-{pag_fim}) será ignorada no fallback Docling para PDF {id_documento}"
                            )
                        file_content = _get_text_from_file_with_docling(file_name)
                        logger.info(
                            f"✓ Docling conseguiu extrair conteúdo do PDF corrompido {id_documento}"
                        )
                    except Exception as docling_error:
                        logger.error(
                            f"Ambos PyMuPDF e Docling falharam para PDF {id_documento}. "
                            f"Docling error: {docling_error}"
                        )
                        raise pdf_error from docling_error
            elif doc_extension in EXT_DOCLING_SUPPORTED:
                file_content = _get_text_from_file_with_docling(file_name)
            elif doc_extension in EXT_UNSTRUCTURED:
                file_content = _get_text_with_unstructured(file_name)
            elif doc_extension in EXT_ODP:
                file_content = _get_text_from_odp_file(file_name)
            else:
                file_content = _get_spreadsheets_from_file(file_name, pag_ini, pag_fim)
        finally:
            # Sempre remover o arquivo, mesmo se houver erro
            try:
                if file_name and Path(file_name).exists():
                    Path(file_name).unlink()
            except Exception as cleanup_error:
                logger.warning(
                    f"Erro ao remover arquivo temporário {file_name}: {cleanup_error}"
                )
    except (
        HTTPException204,
        HTTPException404,
        HTTPException408,
        HTTPException409,
        HTTPException500,
        HTTPException503,
    ) as exc:
        logger.exception(
            f"Ocorreu um erro ao executar {inspect.currentframe().f_code.co_name}"
        )
        raise exc from exc
    except HTTPException406 as exc:
        msg = "Não posso definir um intervalo de páginas para esse documento"
        raise HTTPException406(detail=msg) from exc
    except SeiDBAPIError as exc:
        if str(exc).startswith(
            "[404] Falha na requisição à API SEI DB: 404 Client Error: Not Found"
        ):
            msg = f"Documento id {id_documento} não encontrado no repositório: {exc!s}"
            logger.exception(msg)
            msg = f"Documento id {id_documento} não encontrado no repositório do SEI!"
            raise HTTPException404(detail=msg) from exc
        msg = f"Erro não esperado ao acionar API DB SEI: {exc!s}"
        raise HTTPException500(detail=msg) from exc
    except Exception as exc:
        logger.debug(
            f"Excecao generica tipo {type(exc)} do {inspect.currentframe().f_code.co_name} {exc!s}"
        )
        if "num_documento" not in locals():
            msg = f"Erro ao buscar o número do documento id {id_documento} no SEI!"
        elif "nome_documento" not in locals():
            msg = f"Erro ao buscar o nome do documento id {id_documento} no SEI!"
        elif "pdf_file" not in locals():
            msg = f"Erro ao baixar o PDF do documento id {id_documento}!"
        else:
            msg = f"Erro ao extrair o conteúdo do PDF do documento id {id_documento}!"
        raise HTTPException500(detail=msg) from exc
    else:
        return file_content


def _get_text_pdf_from_file(
    pdf_file: str, pag_ini: int | None, pag_fim: int | None
) -> str:
    """Extrai o texto de um arquivo PDF especificado entre as págs indicadas.

    Usa estrategia hibrida: extrai texto nativo com PyMuPDF e, se detectar
    paginas escaneadas (pouco texto + imagens), envia para OCR via LLM com visao (LiteLLM proxy).

    Args:
        pdf_file (str): Caminho para o arquivo PDF do qual o texto será extraído.
        pag_ini (int): Número da página inicial (1-based).
        pag_fim (int): Número da página final (inclusive).

    Returns:
        str: Texto extraído e processado.

    Raises:
        PDFExtractionError: Se houver erro ao extrair o texto do PDF.
        IndexError: Se o índice da página for inválido.
        RuntimeError: Se o PDF estiver corrompido.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug(f">> DEBUG: Processing PDF file: {pdf_file}")
    logger.debug(f">> DEBUG: Page range: {pag_ini} to {pag_fim}")

    pdf = None
    try:
        pdf = fitz.open(pdf_file)

        if pdf.is_encrypted:
            logger.warning(f"PDF {pdf_file} está criptografado")
            msg = "PDF está criptografado e não pode ser processado"
            raise PDFExtractionError(msg)

        if pdf.page_count == 0:
            logger.warning(f"PDF {pdf_file} não tem páginas")
            msg = "PDF não tem páginas"
            raise PDFExtractionError(msg)

        logger.debug(f">> DEBUG: PDF has {pdf.page_count} pages")

        if settings.OCR_ENABLED and has_scanned_pages(pdf_file):
            logger.info(
                f"[OCR] PDF {pdf_file} tem paginas escaneadas, usando extracao hibrida"
            )
            pdf.close()
            pdf = None
            text = extract_text_hybrid_sync(pdf_file, pag_ini, pag_fim)
            return pre_processamento_pdf(text)

        start_page = (pag_ini - 1) if pag_ini else 0
        end_page = pag_fim if pag_fim and pag_fim <= pdf.page_count else pdf.page_count

        pages = []
        for page_index in range(start_page, end_page):
            try:
                page = pdf[page_index]
                text = page.get_text()
                pages.append(text)
                logger.debug(
                    f">> DEBUG: Page {page_index + 1} extracted {len(text)} chars"
                )
            except IndexError as idx_err:
                logger.error(
                    f"Página {page_index + 1} não existe no PDF (total: {pdf.page_count})"
                )
                raise idx_err
            except Exception as page_err:
                logger.error(f"Erro ao processar página {page_index + 1}: {page_err}")
                pages.append(f"\n[Erro ao processar página {page_index + 1}]\n")

        text = "\n".join(pages)
        logger.debug(f">> DEBUG: Total extracted {len(text)} chars")
        return pre_processamento_pdf(text)

    except OCRExtractionError as e:
        logger.exception(f">> Erro no OCR do PDF {pdf_file}: {e}")
        msg = f"Erro no OCR do PDF: {e}"
        raise PDFExtractionError(msg) from e
    except (FileNotFoundError, OSError, ValueError, IndexError, RuntimeError) as e:
        logger.exception(
            f">> Erro ao extrair conteúdo do PDF {pdf_file}: {type(e).__name__}"
        )
        msg = f"Erro ao extrair o texto do PDF: {type(e).__name__}"
        raise PDFExtractionError(msg) from e
    except Exception as e:
        logger.exception(f">> Erro inesperado ao processar PDF {pdf_file}")
        msg = f"Erro inesperado ao processar PDF: {type(e).__name__}"
        raise PDFExtractionError(msg) from e
    finally:
        if pdf is not None:
            try:
                pdf.close()
            except Exception as close_err:
                logger.warning(f"Erro ao fechar PDF: {close_err}")


def _get_spreadsheets_from_file(
    file_name: str,
    start_sheet: int | None,
    end_sheet: int | None,
    engine: str | None = "calamine",
    max_rows_per_sheet: int | None = settings.MAX_ROWS_PER_SHEET,
    max_sheets: int | None = settings.MAX_SHEETS_TO_PROCESS,
) -> str:
    """Carrega um arquivo de planilha e retorna o conteúdo de cada aba especificada em formato CSV compacto.

    Esta função implementa várias otimizações para reduzir drasticamente o uso de tokens:
    - Formato CSV ao invés de Markdown (reduz ~22% dos tokens)
    - Limite configurável de linhas por aba (previne explosão de contexto)
    - Limite de número de abas processadas (controla tamanho total)
    - Limite de colunas para planilhas mal formatadas
    - Logs informativos sobre truncamento

    :param file_name: Nome do arquivo que contém a planilha.
    :param start_sheet: Número da aba inicial (1-based).
    :param end_sheet: Número da aba final (1-based, inclusivo).
    :param engine: Motor de leitura do arquivo. Padrão é "calamine".
    :param max_rows_per_sheet: Limite de linhas por aba. Se None, usa settings.MAX_ROWS_PER_SHEET.
    :param max_sheets: Limite de abas a processar. Se None, usa settings.MAX_SHEETS_TO_PROCESS.
    :return: String contendo o conteúdo de todas as abas especificadas em formato CSV.
    """

    logger.debug(">> entrou em get_spreadsheets_from_file")
    logger.debug(f">> DEBUG: Processing spreadsheet file: {file_name}")
    logger.debug(f">> DEBUG: Sheet range: {start_sheet} to {end_sheet}")
    logger.debug(f">> DEBUG: Engine: {engine}")
    logger.debug(f">> DEBUG: Max rows per sheet: {max_rows_per_sheet}")
    logger.debug(f">> DEBUG: Max sheets to process: {max_sheets}")

    try:
        # Carregar o arquivo da planilha
        xls = pd.ExcelFile(file_name, engine=engine)

        # Lista para armazenar os DataFrames em formato CSV
        csv_sheets = []

        # Ajustando índices de abas para 0-based
        start_sheet = start_sheet - 1 if start_sheet else 0
        if not end_sheet or end_sheet >= len(xls.sheet_names):
            end_sheet = len(xls.sheet_names)

        # Aplicar limite de número de abas a processar
        total_sheets = end_sheet - start_sheet
        if total_sheets > max_sheets:
            logger.warning(
                f">> WARNING: Total sheets ({total_sheets}) exceeds max_sheets limit ({max_sheets}). "
                f"Only first {max_sheets} sheets will be processed."
            )
            end_sheet = start_sheet + max_sheets

        # Iterar sobre as abas especificadas
        for sheet_num in range(start_sheet, end_sheet):
            # Nome da aba
            sheet_name = xls.sheet_names[sheet_num]

            # Carregar a aba como DataFrame
            df_sheet = pd.read_excel(xls, sheet_name=sheet_num, engine=engine)
            original_rows = df_sheet.shape[0]
            original_cols = df_sheet.shape[1]

            logger.debug(
                f">> DEBUG: Sheet {sheet_name} loaded. Original shape: ({original_rows}, {original_cols})"
            )

            # Limitar número de colunas para evitar planilhas mal formatadas
            max_columns = 100  # Limite razoável para documentos corporativos
            if df_sheet.shape[1] > max_columns:
                logger.warning(
                    f">> WARNING: Sheet {sheet_name} has {original_cols} columns. Limiting to {max_columns} columns."
                )
                df_sheet = df_sheet.iloc[:, :max_columns]

            # Limitar número de linhas por aba
            truncated = False
            if df_sheet.shape[0] > max_rows_per_sheet:
                logger.warning(
                    f">> WARNING: Sheet {sheet_name} has {original_rows} rows. "
                    f"Limiting to {max_rows_per_sheet} rows."
                )
                df_sheet = df_sheet.head(max_rows_per_sheet)
                truncated = True

            # Converter o DataFrame para CSV (muito mais compacto que Markdown)
            csv_text = df_sheet.to_csv(index=False)

            # Adicionar indicação de truncamento se aplicável
            truncation_note = (
                f" [Truncado: mostrando {max_rows_per_sheet} de {original_rows} linhas]"
                if truncated
                else ""
            )

            # Adicionar o nome da aba e o texto CSV à lista
            formatted_sheet = f"\n\n=== Aba número {sheet_num + 1}: {sheet_name}{truncation_note} ===\n{csv_text}"
            csv_sheets.append(formatted_sheet)

            logger.debug(
                f">> DEBUG: Sheet {sheet_name} processed. Final shape: {df_sheet.shape}, "
                f"CSV size: {len(csv_text)} chars"
            )

        # Concatenar todos os textos CSV em uma única string
        final_text = "\n\n".join(csv_sheets)

        logger.info(
            f">> INFO: Processed {len(csv_sheets)} sheets. Total size: {len(final_text)} chars"
        )

        return final_text

    except Exception as e:
        logger.exception(">> ocorreu um erro ao extrair o conteúdo da planilha!")
        msg = "Erro ao extrair conteúdo da planilha!"
        raise Exception(msg) from e  # noqa: TRY002


def _get_text_from_plain_text_file(file_name: str) -> str:
    """Lê conteúdo de arquivo de texto simples (.txt) diretamente.

    Args:
        file_name (str): Caminho para o arquivo a ser lido.

    Returns:
        str: Texto extraído do arquivo.

    Raises:
        HTTPException500: Se houver erro ao ler o arquivo.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug(f">> DEBUG: Reading plain text file: {file_name}")

    try:
        # Tentar diferentes encodings
        encodings = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]

        for encoding in encodings:
            try:
                with open(file_name, encoding=encoding) as f:
                    text_content = f.read()
                logger.debug(
                    f">> DEBUG: Successfully read {len(text_content)} characters with encoding {encoding}"
                )
                return pre_processamento_pdf(text_content)
            except UnicodeDecodeError:
                if encoding == encodings[-1]:
                    # Última tentativa: ler como binário e decodificar ignorando erros
                    logger.warning(
                        f">> WARNING: Failed to decode {file_name} with common encodings, using fallback"
                    )
                    with open(file_name, encoding="utf-8", errors="ignore") as f:
                        text_content = f.read()
                    return pre_processamento_pdf(text_content)
                continue

    except Exception as e:
        logger.exception(f">> ocorreu um erro ao ler arquivo de texto {file_name}!")
        msg = f"Erro ao ler conteúdo do arquivo de texto {file_name}!"
        raise HTTPException500(detail=msg) from e  # noqa: TRY002


def _get_text_from_file_with_docling(file_name: str) -> str:
    """Extrai texto de arquivo usando Docling para formatos suportados.

    Args:
        file_name (str): Caminho para o arquivo a ser processado.

    Returns:
        str: Texto extraído do arquivo.

    Raises:
        Exception: Se houver erro no processamento do arquivo.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug(f">> DEBUG: Processing file with Docling: {file_name}")

    try:
        # Inicializar o converter do Docling
        converter = DocumentConverter()

        # Converter o arquivo
        result = converter.convert(Path(file_name))

        # Extrair o texto como markdown
        text_content = result.document.export_to_markdown()

        logger.debug(f">> DEBUG: Successfully extracted {len(text_content)} characters")
        return pre_processamento_pdf(text_content)

    except Exception as e:
        logger.exception(
            f">> ocorreu um erro ao extrair conteúdo com Docling do arquivo {file_name}!"
        )
        msg = f"Erro ao extrair conteúdo do arquivo {file_name} com Docling!"
        raise HTTPException500(detail=msg) from e  # noqa: TRY002


def _get_text_with_unstructured(file_name: str) -> str:
    """Extrai texto usando biblioteca unstructured para formatos legados.

    Suporta formatos como RTF, ODT, ODP, DOC e PPT que requerem
    conversores externos (pandoc, libreoffice).

    Args:
        file_name (str): Caminho para o arquivo a ser processado.

    Returns:
        str: Texto extraído do arquivo.

    Raises:
        HTTPException500: Se houver erro no processamento do arquivo.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug(f">> DEBUG: Processing file with Unstructured: {file_name}")

    try:
        from unstructured.partition.auto import partition

        elements = partition(filename=file_name)
        text_content = "\n\n".join([str(el) for el in elements])

        logger.debug(
            f">> DEBUG: Successfully extracted {len(text_content)} characters with Unstructured"
        )
        return pre_processamento_pdf(text_content)

    except Exception as e:
        logger.exception(
            f">> ocorreu um erro ao extrair conteúdo com Unstructured do arquivo {file_name}!"
        )
        msg = f"Erro ao extrair conteúdo do arquivo {file_name} com Unstructured!"
        raise HTTPException500(detail=msg) from e  # noqa: TRY002


def _get_text_from_odp_file(file_name: str) -> str:
    """Extrai texto de arquivos ODP (OpenDocument Presentation) usando odfpy.

    A biblioteca unstructured não suporta ODP nativamente, então usamos
    odfpy diretamente para extrair o conteúdo textual das apresentações.

    Args:
        file_name (str): Caminho para o arquivo ODP.

    Returns:
        str: Texto extraído da apresentação.

    Raises:
        HTTPException500: Se houver erro no processamento do arquivo.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug(f">> DEBUG: Processing ODP file with odfpy: {file_name}")

    try:
        from odf import draw, text
        from odf.opendocument import load

        doc = load(file_name)
        content = []

        # ODP armazena texto em draw:frame > draw:text-box > text:p
        for frame in doc.getElementsByType(draw.Frame):
            for textbox in frame.getElementsByType(draw.TextBox):
                for paragraph in textbox.getElementsByType(text.P):
                    # Extrair texto recursivamente dos nós
                    def get_text_recursive(node: object) -> str:
                        result = ""
                        for child in node.childNodes:
                            if child.nodeType == child.TEXT_NODE:
                                result += str(child)
                            else:
                                result += get_text_recursive(child)
                        return result

                    txt = get_text_recursive(paragraph).strip()
                    if txt:
                        content.append(txt)

        text_content = "\n\n".join(content)
        logger.debug(
            f">> DEBUG: Successfully extracted {len(text_content)} characters from ODP"
        )
        return pre_processamento_pdf(text_content)

    except Exception as e:
        logger.exception(
            f">> ocorreu um erro ao extrair conteúdo ODP do arquivo {file_name}!"
        )
        msg = f"Erro ao extrair conteúdo do arquivo ODP {file_name}!"
        raise HTTPException500(detail=msg) from e  # noqa: TRY002
