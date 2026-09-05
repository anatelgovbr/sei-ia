"""Hybrid native-text-then-OCR PDF extraction."""

from __future__ import annotations

import logging
from typing import Optional

from sei_extraction.config import ExtractionConfig
from sei_extraction.exceptions import OCRExtractionError, PDFExtractionError
from sei_extraction.text import clean_text
from sei_extraction.ports import VisionOCRClient

logger = logging.getLogger(__name__)


def extract_pdf(
    file_path: str,
    config: ExtractionConfig,
    ocr_client: Optional[VisionOCRClient] = None,
    pag_ini: Optional[int] = None,
    pag_fim: Optional[int] = None,
) -> str:
    import fitz

    from sei_extraction.ocr.vision import extract_text_hybrid_sync, has_scanned_pages

    pdf = None
    try:
        pdf = fitz.open(file_path)

        if pdf.is_encrypted:
            msg = "PDF está criptografado e não pode ser processado"
            raise PDFExtractionError(msg)

        if pdf.page_count == 0:
            raise PDFExtractionError("PDF não tem páginas")

        logger.debug("PDF %s has %d pages", file_path, pdf.page_count)

        if config.ocr_enabled and has_scanned_pages(
            file_path, config, pag_ini, pag_fim
        ):
            if ocr_client is None:
                raise PDFExtractionError(
                    "PDF contém páginas escaneadas mas ocr_client não foi fornecido. "
                    "Forneça um VisionOCRClient ou defina ocr_enabled=False."
                )
            logger.info(
                "[OCR] PDF %s tem paginas escaneadas, usando extracao hibrida",
                file_path,
            )
            pdf.close()
            pdf = None
            text = extract_text_hybrid_sync(
                file_path, config, ocr_client, pag_ini, pag_fim
            )
            return clean_text(text)

        start_page = (pag_ini - 1) if pag_ini else 0
        end_page = pag_fim if pag_fim and pag_fim <= pdf.page_count else pdf.page_count

        pages = []
        for page_index in range(start_page, end_page):
            try:
                page = pdf[page_index]
                text = page.get_text()
                pages.append(text)
                logger.debug("Page %d extracted %d chars", page_index + 1, len(text))
            except IndexError:
                logger.error(
                    "Página %d não existe no PDF (total: %d)",
                    page_index + 1,
                    pdf.page_count,
                )
                raise
            except Exception as page_err:
                logger.error(
                    "Erro ao processar página %d: %s", page_index + 1, page_err
                )
                pages.append(f"\n[Erro ao processar página {page_index + 1}]\n")

        text = "\n".join(pages)
        return clean_text(text)

    except OCRExtractionError as exc:
        logger.exception("Erro no OCR do PDF %s", file_path)
        raise PDFExtractionError(f"Erro no OCR do PDF: {exc}") from exc
    except PDFExtractionError:
        raise
    except (FileNotFoundError, OSError, ValueError, IndexError, RuntimeError) as exc:
        logger.exception(
            "Erro ao extrair conteúdo do PDF %s: %s", file_path, type(exc).__name__
        )
        raise PDFExtractionError(
            f"Erro ao extrair o texto do PDF: {type(exc).__name__}"
        ) from exc
    except Exception as exc:
        logger.exception("Erro inesperado ao processar PDF %s", file_path)
        raise PDFExtractionError(
            f"Erro inesperado ao processar PDF: {type(exc).__name__}"
        ) from exc
    finally:
        if pdf is not None:
            try:
                pdf.close()
            except Exception as close_err:
                logger.warning("Erro ao fechar PDF: %s", close_err)
