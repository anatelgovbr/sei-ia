"""PDF OCR helpers: analyze_pdf_pages, render_page_to_base64, extract_text_hybrid_sync."""

from __future__ import annotations

import base64
import logging
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from sei_extraction.config import ExtractionConfig
from sei_extraction.exceptions import OCRExtractionError
from sei_extraction.ports import VisionOCRClient

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class PageAnalysis:
    page_num: int
    is_scanned: bool
    chars_useful: int
    num_images: int
    num_drawings: int
    native_text: str


def analyze_pdf_pages(
    pdf_path: str,
    config: ExtractionConfig,
) -> List[PageAnalysis]:
    import fitz

    doc = fitz.open(pdf_path)
    results = []

    for page_num, page in enumerate(doc):
        text = page.get_text().strip()
        img_list = page.get_images()

        lines = [line for line in text.split("\n") if line.strip()]
        useful_text = "\n".join(
            line
            for line in lines
            if not line.startswith("Portal de Assinaturas") and len(line) > 20
        )

        has_insufficient_text = len(useful_text) < config.ocr_min_text_threshold
        num_drawings = 0
        if has_insufficient_text and not img_list:
            num_drawings = len(page.get_drawings())

        is_scanned = has_insufficient_text and bool(img_list or num_drawings)

        results.append(
            PageAnalysis(
                page_num=page_num + 1,
                is_scanned=is_scanned,
                chars_useful=len(useful_text),
                num_images=len(img_list),
                num_drawings=num_drawings,
                native_text=text,
            )
        )

    doc.close()
    return results


def render_page_to_base64(
    pdf_path: str,
    page_num: int,
    config: ExtractionConfig,
) -> str:
    import fitz

    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    mat = fitz.Matrix(config.ocr_dpi / 72, config.ocr_dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode("utf-8")


def _extract_page_with_ocr(
    pdf_path: str,
    page_num: int,
    config: ExtractionConfig,
    ocr_client: VisionOCRClient,
) -> tuple:
    logger.info("[OCR] Iniciando OCR da pagina %d...", page_num)
    try:
        img_base64 = render_page_to_base64(pdf_path, page_num, config)
        text = ocr_client.extract_page(img_base64, config.ocr_model)
        logger.info("[OCR] Pagina %d concluida", page_num)
        return page_num, text
    except Exception as exc:
        logger.exception("[OCR] Erro ao processar pagina %d: %s", page_num, exc)
        raise OCRExtractionError(f"Falha no OCR da pagina {page_num}: {exc}") from exc


def has_scanned_pages(
    pdf_path: str,
    config: ExtractionConfig,
    pag_ini: Optional[int] = None,
    pag_fim: Optional[int] = None,
) -> bool:
    analysis = analyze_pdf_pages(pdf_path, config)
    start_page = (pag_ini - 1) if pag_ini else 0
    end_page = pag_fim if pag_fim and pag_fim <= len(analysis) else len(analysis)
    return any(page.is_scanned for page in analysis[start_page:end_page])


def extract_text_hybrid_sync(
    pdf_path: str,
    config: ExtractionConfig,
    ocr_client: VisionOCRClient,
    pag_ini: Optional[int] = None,
    pag_fim: Optional[int] = None,
) -> str:
    logger.info("[OCR] Analisando PDF: %s", pdf_path)

    analysis = analyze_pdf_pages(pdf_path, config)
    total_pages = len(analysis)

    start_page = (pag_ini - 1) if pag_ini else 0
    end_page = pag_fim if pag_fim and pag_fim <= total_pages else total_pages

    pages_to_process = analysis[start_page:end_page]
    scanned_pages = [p for p in pages_to_process if p.is_scanned]
    native_pages = [p for p in pages_to_process if not p.is_scanned]

    logger.info(
        "[OCR] Paginas %d-%d: %d escaneadas, %d com texto nativo",
        start_page + 1,
        end_page,
        len(scanned_pages),
        len(native_pages),
    )

    texts_by_page: dict = {}

    for page in native_pages:
        texts_by_page[page.page_num] = page.native_text

    if scanned_pages:
        logger.info(
            "[OCR] Enviando %d paginas para OCR em paralelo (max %d simultaneas)...",
            len(scanned_pages),
            config.ocr_max_concurrent_pages,
        )

        ocr_errors = []
        ocr_success = 0

        with ThreadPoolExecutor(
            max_workers=config.ocr_max_concurrent_pages
        ) as executor:
            future_to_page = {
                executor.submit(
                    copy_context().run,
                    _extract_page_with_ocr,
                    pdf_path,
                    page.page_num,
                    config,
                    ocr_client,
                ): page
                for page in scanned_pages
            }

            for future in as_completed(future_to_page):
                page = future_to_page[future]
                try:
                    page_num, text = future.result()
                    texts_by_page[page_num] = text
                    ocr_success += 1
                except Exception as exc:
                    logger.error("[OCR] Erro na pagina %d: %s", page.page_num, exc)
                    ocr_errors.append((page.page_num, exc))

        if ocr_errors and ocr_success == 0:
            failed_pages = [str(p) for p, _ in ocr_errors]
            msg = (
                f"OCR falhou em todas as {len(scanned_pages)} paginas escaneadas "
                f"(paginas: {', '.join(failed_pages)}). "
                f"Primeiro erro: {ocr_errors[0][1]}"
            )
            logger.error("[OCR] %s", msg)
            raise OCRExtractionError(msg)

        if ocr_errors:
            logger.warning(
                "[OCR] %d de %d paginas falharam no OCR, mas %d foram extraidas com sucesso.",
                len(ocr_errors),
                len(scanned_pages),
                ocr_success,
            )

    final_pages = []
    for page_num in range(start_page + 1, end_page + 1):
        final_pages.append(texts_by_page.get(page_num, ""))

    return "\n\n".join(final_pages)
