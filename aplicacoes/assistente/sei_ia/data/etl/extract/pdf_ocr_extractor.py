"""Modulo para extracao de texto de PDFs escaneados usando OCR via LLM com visao (LiteLLM proxy).

Usa chamadas sincronas ao litellm para evitar problemas de event loop
quando executado dentro de ThreadPoolExecutor (via run_in_executor do asyncio).
"""

import base64
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import fitz
from litellm import completion

from sei_ia.configs.settings_config import settings
from sei_ia.services.exceptions.pdf_exceptions import OCRExtractionError

logger = logging.getLogger(__name__)


@dataclass
class PageAnalysis:
    page_num: int
    is_scanned: bool
    chars_useful: int
    num_images: int
    native_text: str


def analyze_pdf_pages(pdf_path: str) -> list[PageAnalysis]:
    """Analisa cada pagina do PDF e classifica como escaneada ou com texto nativo."""
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

        is_scanned = (
            len(useful_text) < settings.OCR_MIN_TEXT_THRESHOLD and len(img_list) > 0
        )

        results.append(
            PageAnalysis(
                page_num=page_num + 1,
                is_scanned=is_scanned,
                chars_useful=len(useful_text),
                num_images=len(img_list),
                native_text=text,
            )
        )

    doc.close()
    return results


def render_page_to_base64(pdf_path: str, page_num: int, dpi: int | None = None) -> str:
    """Renderiza uma pagina do PDF como imagem PNG em base64."""
    if dpi is None:
        dpi = settings.OCR_DPI

    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode("utf-8")


def extract_text_with_ocr(pdf_path: str, page_num: int) -> tuple[int, str]:
    """Envia uma pagina escaneada para o LLM com visao via LiteLLM proxy (sync) e retorna o texto extraido."""
    logger.info(f"[OCR] Iniciando OCR da pagina {page_num}...")

    try:
        img_base64 = render_page_to_base64(pdf_path, page_num)

        response = completion(
            model=settings.OCR_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extraia todo o texto desta imagem de documento escaneado. "
                                "Mantenha a formatacao de tabelas em markdown. "
                                "Preserve numeros e dados exatamente como aparecem."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            api_base=settings.LITELLM_PROXY_URL,
            api_key="not-needed",
        )

        text = response.choices[0].message.content
        usage = response.usage
        logger.info(
            f"[OCR] Pagina {page_num} concluida - Tokens: {usage.prompt_tokens} input, {usage.completion_tokens} output"
        )
        return page_num, text

    except Exception as e:
        logger.exception(f"[OCR] Erro ao processar pagina {page_num}: {e}")
        raise OCRExtractionError(f"Falha no OCR da pagina {page_num}: {e}") from e


def extract_text_hybrid_sync(
    pdf_path: str,
    pag_ini: int | None = None,
    pag_fim: int | None = None,
) -> str:
    """Extrai texto do PDF usando estrategia hibrida: texto nativo + OCR para escaneadas.

    Usa ThreadPoolExecutor para paralelizar chamadas OCR de forma segura,
    sem depender de asyncio (evitando problemas de event loop).
    """
    logger.info(f"[OCR] Analisando PDF: {pdf_path}")

    analysis = analyze_pdf_pages(pdf_path)
    total_pages = len(analysis)

    start_page = (pag_ini - 1) if pag_ini else 0
    end_page = pag_fim if pag_fim and pag_fim <= total_pages else total_pages

    pages_to_process = analysis[start_page:end_page]
    scanned_pages = [p for p in pages_to_process if p.is_scanned]
    native_pages = [p for p in pages_to_process if not p.is_scanned]

    logger.info(
        f"[OCR] Paginas {start_page + 1}-{end_page}: "
        f"{len(scanned_pages)} escaneadas, {len(native_pages)} com texto nativo"
    )

    texts_by_page: dict[int, str] = {}

    for page in native_pages:
        texts_by_page[page.page_num] = page.native_text

    if scanned_pages:
        logger.info(
            f"[OCR] Enviando {len(scanned_pages)} paginas para OCR em paralelo "
            f"(max {settings.OCR_MAX_CONCURRENT_PAGES} simultaneas)..."
        )

        ocr_errors = []
        ocr_success = 0

        with ThreadPoolExecutor(
            max_workers=settings.OCR_MAX_CONCURRENT_PAGES
        ) as executor:
            future_to_page = {
                executor.submit(extract_text_with_ocr, pdf_path, page.page_num): page
                for page in scanned_pages
            }

            for future in as_completed(future_to_page):
                page = future_to_page[future]
                try:
                    page_num, text = future.result()
                    texts_by_page[page_num] = text
                    ocr_success += 1
                except Exception as e:
                    logger.error(f"[OCR] Erro na pagina {page.page_num}: {e}")
                    ocr_errors.append((page.page_num, e))

        # Se TODAS as paginas escaneadas falharam, levantar erro
        if ocr_errors and ocr_success == 0:
            failed_pages = [str(p) for p, _ in ocr_errors]
            msg = (
                f"OCR falhou em todas as {len(scanned_pages)} paginas escaneadas "
                f"(paginas: {', '.join(failed_pages)}). "
                f"Primeiro erro: {ocr_errors[0][1]}"
            )
            logger.error(f"[OCR] {msg}")
            raise OCRExtractionError(msg)

        if ocr_errors:
            logger.warning(
                f"[OCR] {len(ocr_errors)} de {len(scanned_pages)} paginas falharam no OCR, "
                f"mas {ocr_success} foram extraidas com sucesso."
            )

    final_pages = []
    for page_num in range(start_page + 1, end_page + 1):
        text = texts_by_page.get(page_num, "")
        final_pages.append(text)

    return "\n\n".join(final_pages)


def has_scanned_pages(pdf_path: str) -> bool:
    """Verifica rapidamente se o PDF tem paginas escaneadas."""
    analysis = analyze_pdf_pages(pdf_path)
    return any(p.is_scanned for p in analysis)
