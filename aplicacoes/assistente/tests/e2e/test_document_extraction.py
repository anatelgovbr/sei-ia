"""
Testes de extração de documentos para todos os formatos suportados.

Este módulo testa as funções de extração de texto dos diferentes
formatos de documento suportados pelo sistema SEI-IA.

Formatos testados:
- HTM: HTML via Docling
- XML: Texto simples com encoding detection
- RTF: Rich Text Format via Unstructured + Pandoc
- ODT: OpenDocument Text via Unstructured + Pandoc
- ODP: OpenDocument Presentation via OdfPy
- DOC: Microsoft Word 97-2003 via Unstructured + LibreOffice
- PPT: Microsoft PowerPoint 97-2003 via Unstructured + LibreOffice
- PDF escaneado: OCR via LiteLLM proxy (modelo configurado em ASSISTENTE_OCR_MODEL)
"""

from pathlib import Path

# Diretório com arquivos de teste
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "documents"


class TestDocumentExtraction:
    """Testes de extração de texto para cada formato de documento."""

    def test_htm_extraction_with_docling(self):
        """Testa extração de arquivo HTM usando Docling."""
        from sei_ia.data.etl.extract.external import _get_text_from_file_with_docling

        file_path = FIXTURES_DIR / "sample.htm"
        assert file_path.exists(), f"Arquivo de teste não encontrado: {file_path}"

        text = _get_text_from_file_with_docling(str(file_path))

        assert text is not None
        assert len(text) > 0
        assert "Welcome" in text or "Sample" in text

    def test_xml_extraction_as_plain_text(self):
        """Testa extração de arquivo XML como texto simples."""
        from sei_ia.data.etl.extract.external import _get_text_from_plain_text_file

        file_path = FIXTURES_DIR / "sample.xml"
        assert file_path.exists(), f"Arquivo de teste não encontrado: {file_path}"

        text = _get_text_from_plain_text_file(str(file_path))

        assert text is not None
        assert len(text) > 0
        assert "<?xml" in text or "<" in text

    def test_rtf_extraction_with_unstructured(self):
        """Testa extração de arquivo RTF usando Unstructured + Pandoc."""
        from sei_ia.data.etl.extract.external import _get_text_with_unstructured

        file_path = FIXTURES_DIR / "sample.rtf"
        assert file_path.exists(), f"Arquivo de teste não encontrado: {file_path}"

        text = _get_text_with_unstructured(str(file_path))

        assert text is not None
        assert len(text) > 0

    def test_odt_extraction_with_unstructured(self):
        """Testa extração de arquivo ODT usando Unstructured + Pandoc."""
        from sei_ia.data.etl.extract.external import _get_text_with_unstructured

        file_path = FIXTURES_DIR / "sample.odt"
        assert file_path.exists(), f"Arquivo de teste não encontrado: {file_path}"

        text = _get_text_with_unstructured(str(file_path))

        assert text is not None
        assert len(text) > 0

    def test_odp_extraction_with_odfpy(self):
        """Testa extração de arquivo ODP usando OdfPy."""
        from sei_ia.data.etl.extract.external import _get_text_from_odp_file

        file_path = FIXTURES_DIR / "sample.odp"
        assert file_path.exists(), f"Arquivo de teste não encontrado: {file_path}"

        text = _get_text_from_odp_file(str(file_path))

        assert text is not None
        assert len(text) > 0

    def test_doc_extraction_with_unstructured(self):
        """Testa extração de arquivo DOC usando Unstructured + LibreOffice."""
        from sei_ia.data.etl.extract.external import _get_text_with_unstructured

        file_path = FIXTURES_DIR / "sample.doc"
        assert file_path.exists(), f"Arquivo de teste não encontrado: {file_path}"

        text = _get_text_with_unstructured(str(file_path))

        assert text is not None
        assert len(text) > 0

    def test_ppt_extraction_with_unstructured(self):
        """Testa extração de arquivo PPT usando Unstructured + LibreOffice."""
        from sei_ia.data.etl.extract.external import _get_text_with_unstructured

        file_path = FIXTURES_DIR / "sample.ppt"
        assert file_path.exists(), f"Arquivo de teste não encontrado: {file_path}"

        text = _get_text_with_unstructured(str(file_path))

        assert text is not None
        assert len(text) > 0


class TestExtensionConstants:
    """Testes para validar as constantes de extensão."""

    def test_ext_constants_are_defined(self):
        """Verifica que todas as constantes de extensão estão definidas."""
        from sei_ia.data.etl.extract.external import (
            EXT_DOCLING_SUPPORTED,
            EXT_ODP,
            EXT_PAGINADOS,
            EXT_PLAIN_TEXT,
            EXT_UNSTRUCTURED,
        )

        assert isinstance(EXT_PAGINADOS, list)
        assert isinstance(EXT_DOCLING_SUPPORTED, list)
        assert isinstance(EXT_PLAIN_TEXT, list)
        assert isinstance(EXT_UNSTRUCTURED, list)
        assert isinstance(EXT_ODP, list)

    def test_htm_in_docling_supported(self):
        """Verifica que HTM está na lista de formatos suportados pelo Docling."""
        from sei_ia.data.etl.extract.external import EXT_DOCLING_SUPPORTED

        assert "htm" in EXT_DOCLING_SUPPORTED

    def test_xml_in_plain_text(self):
        """Verifica que XML está na lista de texto simples."""
        from sei_ia.data.etl.extract.external import EXT_PLAIN_TEXT

        assert "xml" in EXT_PLAIN_TEXT

    def test_legacy_formats_in_unstructured(self):
        """Verifica que formatos legados estão na lista do Unstructured."""
        from sei_ia.data.etl.extract.external import EXT_UNSTRUCTURED

        assert "rtf" in EXT_UNSTRUCTURED
        assert "odt" in EXT_UNSTRUCTURED
        assert "doc" in EXT_UNSTRUCTURED
        assert "ppt" in EXT_UNSTRUCTURED

    def test_odp_has_dedicated_handler(self):
        """Verifica que ODP tem handler dedicado (não está no Unstructured)."""
        from sei_ia.data.etl.extract.external import EXT_ODP, EXT_UNSTRUCTURED

        assert "odp" in EXT_ODP
        assert "odp" not in EXT_UNSTRUCTURED


class TestAllSupportedFormats:
    """Teste integrado que valida todos os 18 formatos suportados."""

    def test_all_formats_are_covered(self):
        """Verifica que todos os 18 formatos documentados estão cobertos."""
        from sei_ia.data.etl.extract.external import (
            EXT_DOCLING_SUPPORTED,
            EXT_ODP,
            EXT_PAGINADOS,
            EXT_PLAIN_TEXT,
            EXT_UNSTRUCTURED,
        )

        # Formatos esperados conforme documentação
        expected_formats = {
            "pdf",
            "html",
            "htm",
            "txt",
            "ods",
            "xlsx",
            "csv",
            "xml",
            "odt",
            "odp",
            "doc",
            "docx",
            "json",
            "ppt",
            "pptx",
            "rtf",
            "xls",
            "xlsm",
        }

        # Formatos cobertos pelas constantes
        covered_formats = set()
        covered_formats.update(EXT_PAGINADOS)  # pdf, ods, xls, xlsb, xlsm, xlsx
        covered_formats.update(
            EXT_DOCLING_SUPPORTED
        )  # html, htm, docx, pptx, md, asciidoc
        covered_formats.update(EXT_PLAIN_TEXT)  # txt, json, csv, xml
        covered_formats.update(EXT_UNSTRUCTURED)  # rtf, odt, doc, ppt
        covered_formats.update(EXT_ODP)  # odp

        # Verifica que todos os formatos esperados estão cobertos
        missing = expected_formats - covered_formats
        assert not missing, f"Formatos não cobertos: {missing}"
