"""Docling real (sem mock) extrai o DOCX de fixture.

Os demais testes de extração patcham `extract_document`; sem este, uma
combinação docling/pydantic incompatível (a resolução passa em `uv pip check`
mas `import docling.document_converter` quebra) só aparece em runtime.
"""

from pathlib import Path

from sei_extraction.config import ExtractionConfig
from sei_extraction.extract import extract_document

FIXTURES = Path(__file__).parent.parent / "fixtures" / "documents"


def test_docx_fixture_extraido_pelo_docling_real():
    texto = extract_document(
        str(FIXTURES / "sample.docx"), "docx", ExtractionConfig(ocr_enabled=False)
    )

    assert "Hello world from DOCX fixture" in texto
