"""Testes unitários para o módulo pdf_exceptions.

Módulo testado: sei_ia/services/exceptions/pdf_exceptions.py
"""

import pytest

from sei_ia.services.exceptions.pdf_exceptions import (
    OCRExtractionError,
    PDFExtractionError,
)


class TestPDFExtractionError:
    """Testes para PDFExtractionError."""

    def test_herda_de_exception(self):
        assert issubclass(PDFExtractionError, Exception)

    def test_pode_ser_levantada_sem_mensagem(self):
        with pytest.raises(PDFExtractionError):
            raise PDFExtractionError()

    def test_pode_ser_levantada_com_mensagem(self):
        with pytest.raises(PDFExtractionError) as exc_info:
            raise PDFExtractionError("erro ao extrair PDF")
        assert "erro ao extrair PDF" in str(exc_info.value)

    def test_instancia_criada_corretamente(self):
        exc = PDFExtractionError("falha na extração")
        assert isinstance(exc, PDFExtractionError)
        assert isinstance(exc, Exception)

    def test_mensagem_preservada(self):
        exc = PDFExtractionError("detalhe do erro")
        assert str(exc) == "detalhe do erro"


class TestOCRExtractionError:
    """Testes para OCRExtractionError."""

    def test_herda_de_exception(self):
        assert issubclass(OCRExtractionError, Exception)

    def test_pode_ser_levantada_sem_mensagem(self):
        with pytest.raises(OCRExtractionError):
            raise OCRExtractionError()

    def test_pode_ser_levantada_com_mensagem(self):
        with pytest.raises(OCRExtractionError) as exc_info:
            raise OCRExtractionError("falha no OCR")
        assert "falha no OCR" in str(exc_info.value)

    def test_nao_herda_de_pdf_extraction_error(self):
        assert not issubclass(OCRExtractionError, PDFExtractionError)

    def test_instancia_e_exception(self):
        exc = OCRExtractionError("página escaneada ilegível")
        assert isinstance(exc, Exception)
