"""Excecptions for PDF related errors."""


class PDFExtractionError(Exception):
    """Exceção levantada quando ocorre um erro na extração do conteúdo do PDF."""


class OCRExtractionError(Exception):
    """Exceção levantada quando ocorre um erro no OCR de paginas escaneadas."""
