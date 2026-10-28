"""Anexos Office no ETL passam pela docling via sei_extraction."""

import zipfile

from sei_extraction.config import ExtractionConfig
from sei_extraction.extract import extract_document

_CT = (
    '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
)
_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
)
_DOC = (
    '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body><w:p><w:r><w:t>Parecer sobre o processo SEI</w:t></w:r></w:p></w:body></w:document>"
)


def test_docx_extrai_texto(tmp_path):
    arquivo = tmp_path / "anexo.docx"
    with zipfile.ZipFile(arquivo, "w") as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", _DOC)

    texto = extract_document(
        str(arquivo), "docx", ExtractionConfig(ocr_enabled=False), None
    )

    assert "Parecer sobre o processo SEI" in texto
