"""Office document parsers: docling, unstructured, odfpy (ODP), plain text, HTML."""

from __future__ import annotations

import logging
import posixpath
import tempfile
import xml.etree.ElementTree as ET
from contextlib import suppress
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sei_extraction.exceptions import OfficeExtractionError
from sei_extraction.text import clean_text

logger = logging.getLogger(__name__)

_PPTX_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_RELATIONSHIP_NS = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
_PPTX_PICTURE_TAG = f"{{{_PPTX_NS}}}pic"
_DRAWING_BLIP_TAG = f"{{{_DRAWING_NS}}}blip"
_RELATIONSHIP_EMBED = f"{{{_RELATIONSHIP_NS}}}embed"
_RELATIONSHIP_ID = "Id"
_RELATIONSHIP_TARGET = "Target"
_RELATIONSHIP_TARGET_MODE = "TargetMode"


def _pptx_relationship_targets(
    slide_name: str, files: set[str], files_by_name: dict[str, bytes]
) -> dict[str, str | None]:
    rels_name = posixpath.join(
        posixpath.dirname(slide_name),
        "_rels",
        posixpath.basename(slide_name) + ".rels",
    )
    if rels_name not in files:
        return {}

    root = ET.fromstring(files_by_name[rels_name])
    targets: dict[str, str | None] = {}
    for relationship in root.findall(f"{{{_PACKAGE_RELATIONSHIP_NS}}}Relationship"):
        relation_id = relationship.get(_RELATIONSHIP_ID)
        target = relationship.get(_RELATIONSHIP_TARGET)
        if relation_id is None:
            continue
        if relationship.get(_RELATIONSHIP_TARGET_MODE) == "External":
            targets[relation_id] = None
            continue
        slide_dir = posixpath.dirname(slide_name)
        targets[relation_id] = posixpath.normpath(
            posixpath.join(slide_dir, target or "")
        )
    return targets


def _remove_unembedded_picture_shapes(
    slide_name: str, slide_xml: bytes, files: set[str], files_by_name: dict[str, bytes]
) -> tuple[bytes, int]:
    root = ET.fromstring(slide_xml)
    relation_targets = _pptx_relationship_targets(slide_name, files, files_by_name)
    removed = 0

    for parent in root.iter():
        for picture in list(parent):
            if picture.tag != _PPTX_PICTURE_TAG:
                continue

            blips = [
                element
                for element in picture.iter()
                if element.tag == _DRAWING_BLIP_TAG
            ]
            embedded_ids = [blip.get(_RELATIONSHIP_EMBED) for blip in blips]
            has_valid_image = bool(embedded_ids) and all(
                relation_id in relation_targets
                and relation_targets[relation_id] in files
                for relation_id in embedded_ids
            )
            if not has_valid_image:
                parent.remove(picture)
                removed += 1

    if not removed:
        return slide_xml, 0
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), removed


def _sanitize_pptx_for_docling(file_path: Path) -> tuple[Path, Path | None]:
    """Remove PPTX picture shapes that have no usable embedded image.

    Docling currently probes ``shape.image`` for every picture shape. The
    python-pptx property raises ``ValueError`` when ``r:embed`` is absent,
    even though the rest of the slide can still be read. A temporary copy
    keeps the uploaded file unchanged and lets Docling process its text.
    """
    if file_path.suffix.lower() != ".pptx":
        return file_path, None

    with ZipFile(file_path) as source:
        files_by_name = {name: source.read(name) for name in source.namelist()}

    files = set(files_by_name)
    removed_total = 0
    for slide_name in sorted(
        name
        for name in files
        if name.startswith("ppt/slides/slide") and name.endswith(".xml")
    ):
        sanitized_xml, removed = _remove_unembedded_picture_shapes(
            slide_name, files_by_name[slide_name], files, files_by_name
        )
        if removed:
            files_by_name[slide_name] = sanitized_xml
            removed_total += removed

    if not removed_total:
        return file_path, None

    temporary_file = tempfile.NamedTemporaryFile(
        prefix="sei-docling-", suffix=".pptx", delete=False
    )
    temporary_path = Path(temporary_file.name)
    try:
        with (
            temporary_file,
            ZipFile(temporary_file, "w", compression=ZIP_DEFLATED) as target,
        ):
            for name, content in files_by_name.items():
                target.writestr(name, content)
    except Exception:
        with suppress(OSError):
            temporary_path.unlink()
        raise

    logger.warning(
        "PPTX %s contém %d shape(s) de imagem sem conteúdo incorporado; "
        "esses shapes foram removidos apenas da cópia enviada ao Docling",
        file_path,
        removed_total,
    )
    return temporary_path, temporary_path


def extract_with_docling(file_path: str) -> str:
    temporary_file: Path | None = None
    try:
        docling_file, temporary_file = _sanitize_pptx_for_docling(Path(file_path))
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(docling_file)
        text_content = result.document.export_to_markdown()
        logger.debug("Docling extracted %d chars from %s", len(text_content), file_path)
        return clean_text(text_content)
    except Exception as exc:
        logger.exception("Docling falhou para %s", file_path)
        raise OfficeExtractionError(
            f"Erro ao extrair conteúdo do arquivo {file_path} com Docling: {exc}"
        ) from exc
    finally:
        if temporary_file is not None:
            with suppress(OSError):
                temporary_file.unlink()


def extract_with_unstructured(file_path: str) -> str:
    try:
        from unstructured.partition.auto import partition

        elements = partition(filename=file_path)
        text_content = "\n\n".join([str(el) for el in elements])
        logger.debug(
            "Unstructured extracted %d chars from %s", len(text_content), file_path
        )
        return clean_text(text_content)
    except Exception as exc:
        logger.exception("Unstructured falhou para %s", file_path)
        raise OfficeExtractionError(
            f"Erro ao extrair conteúdo do arquivo {file_path} com Unstructured: {exc}"
        ) from exc


def extract_odp(file_path: str) -> str:
    try:
        from odf import draw, text
        from odf.opendocument import load

        doc = load(file_path)
        content = []

        for frame in doc.getElementsByType(draw.Frame):
            for textbox in frame.getElementsByType(draw.TextBox):
                for paragraph in textbox.getElementsByType(text.P):

                    def _get_text_recursive(node: object) -> str:
                        result = ""
                        for child in node.childNodes:
                            if child.nodeType == child.TEXT_NODE:
                                result += str(child)
                            else:
                                result += _get_text_recursive(child)
                        return result

                    txt = _get_text_recursive(paragraph).strip()
                    if txt:
                        content.append(txt)

        text_content = "\n\n".join(content)
        logger.debug(
            "odfpy extracted %d chars from ODP %s", len(text_content), file_path
        )
        return clean_text(text_content)
    except Exception as exc:
        logger.exception("odfpy falhou para %s", file_path)
        raise OfficeExtractionError(
            f"Erro ao extrair conteúdo do arquivo ODP {file_path}: {exc}"
        ) from exc


def extract_plain_text(file_path: str) -> str:
    encodings = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]
    try:
        for encoding in encodings:
            try:
                with open(file_path, encoding=encoding) as fh:
                    text_content = fh.read()
                logger.debug(
                    "Read %d chars from %s with encoding %s",
                    len(text_content),
                    file_path,
                    encoding,
                )
                return clean_text(text_content)
            except UnicodeDecodeError:
                if encoding == encodings[-1]:
                    logger.warning(
                        "Failed to decode %s with common encodings, using fallback",
                        file_path,
                    )
                    with open(file_path, encoding="utf-8", errors="ignore") as fh:
                        text_content = fh.read()
                    return clean_text(text_content)
                continue
    except Exception as exc:
        logger.exception("Erro ao ler arquivo de texto %s", file_path)
        raise OfficeExtractionError(
            f"Erro ao ler conteúdo do arquivo de texto {file_path}: {exc}"
        ) from exc


def extract_html(file_path: str) -> str:
    from sei_extraction.html_to_md import HtmlTxtmd

    try:
        with Path(file_path).open(encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        html_txtmd = HtmlTxtmd()
        html_txtmd.processa(raw)
        return html_txtmd.output
    except Exception as exc:
        logger.exception("Erro ao converter HTML %s", file_path)
        raise OfficeExtractionError(
            f"Erro ao converter HTML {file_path}: {exc}"
        ) from exc
