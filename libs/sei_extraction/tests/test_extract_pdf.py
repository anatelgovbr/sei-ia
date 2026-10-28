"""Tests for parsers/pdf.py hybrid extraction."""

from __future__ import annotations

import pytest

from sei_extraction.config import ExtractionConfig
from sei_extraction.exceptions import PDFExtractionError
from sei_extraction.ocr.vision import analyze_pdf_pages
from sei_extraction.parsers.pdf import extract_pdf


class MockVisionOCRClient:
    def __init__(self, response: str = "mocked ocr text") -> None:
        self.calls: list = []
        self._response = response

    def extract_page(self, img_base64: str, model: str) -> str:
        self.calls.append((img_base64, model))
        return self._response


@pytest.fixture
def vector_pdf_path(tmp_path):
    import fitz

    path = str(tmp_path / "vector.pdf")
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.draw_rect(
        fitz.Rect(30, 30, 170, 170),
        color=(0, 0, 0),
        fill=(0.8, 0.8, 0.8),
        width=2,
    )
    page.draw_line(fitz.Point(30, 30), fitz.Point(170, 170), width=2)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def blank_pdf_path(tmp_path):
    import fitz

    path = str(tmp_path / "blank.pdf")
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def two_page_vector_pdf_path(tmp_path):
    import fitz

    path = str(tmp_path / "two_page_vector.pdf")
    doc = fitz.open()
    for offset in (0, 20):
        page = doc.new_page(width=200, height=200)
        page.draw_rect(
            fitz.Rect(30 + offset, 30, 150 + offset, 150),
            color=(0, 0, 0),
            fill=(0.7, 0.7, 0.7),
        )
    doc.save(path)
    doc.close()
    return path


def test_native_pdf_no_ocr_client_called(native_pdf_path):
    config = ExtractionConfig(ocr_enabled=False)
    client = MockVisionOCRClient()

    result = extract_pdf(native_pdf_path, config, ocr_client=client)

    assert "Hello" in result
    assert client.calls == [], "OCR client must not be called when ocr_enabled=False"


def test_native_pdf_ocr_enabled_no_scanned_pages(native_pdf_path):
    config = ExtractionConfig(ocr_enabled=True)
    client = MockVisionOCRClient()

    result = extract_pdf(native_pdf_path, config, ocr_client=client)

    assert "Hello" in result
    assert client.calls == [], "OCR client must not be called for a native-text PDF"


def test_ocr_enabled_without_client_raises_on_scanned(tmp_path):
    import fitz

    path = str(tmp_path / "scanned.pdf")
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)

    blank_pix = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 100, 100), False)
    blank_pix.clear_with(200)
    png_bytes = blank_pix.tobytes("png")

    page.insert_image(fitz.Rect(0, 0, 100, 100), stream=png_bytes)

    doc.save(path)
    doc.close()

    config = ExtractionConfig(
        ocr_enabled=True,
        ocr_min_text_threshold=50,
    )

    with pytest.raises(PDFExtractionError, match="ocr_client"):
        extract_pdf(path, config, ocr_client=None)


def test_encrypted_pdf_raises(tmp_path):
    import fitz

    path = str(tmp_path / "enc.pdf")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "secret")
    doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw")
    doc.close()

    config = ExtractionConfig(ocr_enabled=False)
    with pytest.raises(PDFExtractionError, match="criptografado"):
        extract_pdf(path, config)


def test_scanned_pdf_returns_ocr_text(tmp_path):
    import fitz

    path = str(tmp_path / "scanned_ocr.pdf")
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    blank_pix = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 100, 100), False)
    blank_pix.clear_with(200)
    page.insert_image(fitz.Rect(0, 0, 100, 100), stream=blank_pix.tobytes("png"))
    doc.save(path)
    doc.close()

    client = MockVisionOCRClient(response="TEXTO EXTRAIDO VIA OCR 42")
    config = ExtractionConfig(ocr_enabled=True, ocr_min_text_threshold=50)

    result = extract_pdf(path, config, ocr_client=client)

    assert "TEXTO EXTRAIDO VIA OCR 42" in result
    assert len(client.calls) >= 1, "scanned page must be sent to the OCR client"


def test_vector_only_pdf_is_selected_for_ocr(vector_pdf_path):
    client = MockVisionOCRClient(response="TEXTO VETORIAL EXTRAIDO VIA OCR")
    config = ExtractionConfig(ocr_enabled=True, ocr_min_text_threshold=50)

    analysis = analyze_pdf_pages(vector_pdf_path, config)
    result = extract_pdf(vector_pdf_path, config, ocr_client=client)

    assert analysis[0].chars_useful == 0
    assert analysis[0].num_images == 0
    assert analysis[0].num_drawings > 0
    assert analysis[0].is_scanned is True
    assert result == "TEXTO VETORIAL EXTRAIDO VIA OCR"
    assert len(client.calls) == 1


def test_blank_pdf_does_not_trigger_ocr(blank_pdf_path):
    client = MockVisionOCRClient()
    config = ExtractionConfig(ocr_enabled=True, ocr_min_text_threshold=50)

    analysis = analyze_pdf_pages(blank_pdf_path, config)
    result = extract_pdf(blank_pdf_path, config, ocr_client=client)

    assert analysis[0].is_scanned is False
    assert result == ""
    assert client.calls == []


def test_vector_pdf_ocr_respects_page_range(two_page_vector_pdf_path):
    client = MockVisionOCRClient(response="OCR SOMENTE DA PAGINA SOLICITADA")
    config = ExtractionConfig(ocr_enabled=True, ocr_min_text_threshold=50)

    result = extract_pdf(
        two_page_vector_pdf_path,
        config,
        ocr_client=client,
        pag_ini=2,
        pag_fim=2,
    )

    assert result == "OCR SOMENTE DA PAGINA SOLICITADA"
    assert len(client.calls) == 1


def test_vector_page_outside_range_does_not_require_ocr_client(tmp_path):
    import fitz

    path = str(tmp_path / "vector_outside_range.pdf")
    doc = fitz.open()
    vector_page = doc.new_page(width=200, height=200)
    vector_page.draw_rect(
        fitz.Rect(30, 30, 170, 170),
        color=(0, 0, 0),
        fill=(0.8, 0.8, 0.8),
    )
    native_page = doc.new_page(width=400, height=200)
    native_page.insert_text((30, 100), "Native text from the requested second page.")
    doc.save(path)
    doc.close()
    config = ExtractionConfig(ocr_enabled=True, ocr_min_text_threshold=50)

    result = extract_pdf(path, config, ocr_client=None, pag_ini=2, pag_fim=2)

    assert result == "Native text from the requested second page."
