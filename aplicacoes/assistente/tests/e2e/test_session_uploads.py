"""E2E herméticos de uploads no ``/llm_lang/session_stream``."""

from __future__ import annotations

import base64
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
from langchain_core.messages import BaseMessage

from tests.e2e.session_support import (
    DeterministicSessionModel,
    SessionStreamHarness,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "documents"

SUPPORTED_EXTENSIONS = (
    "pdf",
    "html",
    "htm",
    "docx",
    "pptx",
    "md",
    "asciidoc",
    "txt",
    "json",
    "csv",
    "xml",
    "rtf",
    "odt",
    "doc",
    "ppt",
    "odp",
    "ods",
    "xls",
    "xlsb",
    "xlsm",
    "xlsx",
    "mp3",
    "mp4",
    "wav",
    "ogg",
    "m4a",
    "webm",
    "flac",
    "aac",
    "opus",
    "wma",
    "png",
    "jpg",
    "jpeg",
    "webp",
)
AUDIO_EXTENSIONS = {
    "mp3",
    "mp4",
    "wav",
    "ogg",
    "m4a",
    "webm",
    "flac",
    "aac",
    "opus",
    "wma",
}
IMAGE_MIMES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
# Texto UTF-8/HTML e planilhas OOXML mínimas têm parsers estáveis no runner.
# Binários dependentes de Docling, LibreOffice/Pandoc ou engines opcionais usam
# doubles de extração; o download, a classificação e a agregação continuam reais.
REAL_EXTRACTION = {"html", "htm", "txt", "json", "csv", "xml", "xlsm", "xlsx"}


@dataclass(frozen=True)
class UploadCase:
    extension: str
    kind: str
    image_mime: str | None = None


UPLOAD_CASES = tuple(
    UploadCase(
        extension=extension,
        kind=(
            "audio"
            if extension in AUDIO_EXTENSIONS
            else "image"
            if extension in IMAGE_MIMES
            else "text"
        ),
        image_mime=IMAGE_MIMES.get(extension),
    )
    for extension in SUPPORTED_EXTENSIONS
)

assert len(SUPPORTED_EXTENSIONS) == len(set(SUPPORTED_EXTENSIONS)) == 35
assert tuple(case.extension for case in UPLOAD_CASES) == SUPPORTED_EXTENSIONS


def test_matriz_corresponde_aos_formatos_suportados_em_producao():
    from sei_extraction import AUDIO_EXTENSIONS as RUNTIME_AUDIO_EXTENSIONS

    from sei_ia.data.etl.extract.external import (
        EXT_DOCLING_SUPPORTED,
        EXT_HTML,
        EXT_ODP,
        EXT_PLAIN_TEXT,
        EXT_UNSTRUCTURED,
    )
    from sei_ia.data.etl.extract.uploads import EXT_IMAGE, EXT_SPREADSHEETS

    runtime_extensions = (
        {"pdf"}
        | set(EXT_DOCLING_SUPPORTED)
        | set(EXT_HTML)
        | set(EXT_ODP)
        | set(EXT_PLAIN_TEXT)
        | set(EXT_UNSTRUCTURED)
        | set(EXT_SPREADSHEETS)
        | set(RUNTIME_AUDIO_EXTENSIONS)
        | set(EXT_IMAGE)
    )

    assert set(SUPPORTED_EXTENSIONS) == runtime_extensions


def _fixture_path(extension: str) -> Path:
    filename = "sample_upload.pdf" if extension == "pdf" else f"sample.{extension}"
    return FIXTURES_DIR / filename


def _strings(value):  # noqa: ANN001
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list | tuple):
        for child in value:
            yield from _strings(child)


class UploadTurnObserverModel(DeterministicSessionModel):
    """Modelo que só confirma estados realmente presentes no turno recebido."""

    required_fragments: tuple[str, ...] = ()
    forbidden_fragments: tuple[str, ...] = ()
    expected_image_mime: str | None = None
    expected_image_payload_b64: str | None = None

    def _answer(self, messages: list[BaseMessage]) -> str:
        visible_strings = [
            text for message in messages for text in _strings(message.content)
        ]
        combined = "\n".join(visible_strings)
        observed = all(
            fragment in combined for fragment in self.required_fragments
        ) and all(fragment not in combined for fragment in self.forbidden_fragments)

        if self.expected_image_mime is not None:
            prefix = f"data:{self.expected_image_mime};base64,"
            urls = [text for text in visible_strings if text.startswith(prefix)]
            expected = base64.b64decode(
                self.expected_image_payload_b64 or "", validate=True
            )
            observed = observed and any(
                base64.b64decode(url.removeprefix(prefix), validate=True) == expected
                for url in urls
            )

        marker = "UPLOAD_TURN_OBSERVED" if observed else "UPLOAD_TURN_MISSING"
        return f"{marker};{super()._answer(messages)}"


class FailingSessionModel(DeterministicSessionModel):
    """Falha depois de receber o turno para provar que o SEI não é liberado."""

    def _answer(self, messages: list[BaseMessage]) -> str:
        _ = messages
        raise RuntimeError("falha determinística do agente")


class CompletionAwareModel(DeterministicSessionModel):
    """Marca a conclusão do modelo antes da borda de remoção do SEI."""

    completion_hook: Callable[[], None]

    def _answer(self, messages: list[BaseMessage]) -> str:
        answer = super()._answer(messages)
        self.completion_hook()
        return answer


@dataclass
class UploadHarnessProbe:
    harness: SessionStreamHarness
    downloaded_paths: list[Path]
    removed_ids: list[int]
    event_order: list[str]


@pytest.fixture
def upload_harness_factory(monkeypatch, tmp_path):
    from sei_ia.data.etl.extract import uploads as uploads_module
    from sei_ia.routers.session import uploads as session_uploads_module

    harnesses: list[SessionStreamHarness] = []
    real_extract = uploads_module.extract_text_from_file

    def create(
        *,
        extraction_results: Mapping[str, str | Exception] | None = None,
        transcription_results: Mapping[str, str | Exception] | None = None,
        download_errors: Mapping[str, Exception] | None = None,
        model_factory: Callable[[], DeterministicSessionModel] = (
            DeterministicSessionModel
        ),
        event_order: list[str] | None = None,
    ) -> UploadHarnessProbe:
        extraction_results = dict(extraction_results or {})
        transcription_results = dict(transcription_results or {})
        download_errors = dict(download_errors or {})
        order = event_order if event_order is not None else []
        downloaded_paths: list[Path] = []
        removed_ids: list[int] = []
        downloads_dir = tmp_path / f"downloads-{len(harnesses)}"

        def download_upload(id_upload: int, extension: str) -> str:
            ext = extension.lower().strip(".")
            if error := download_errors.get(ext):
                raise error
            source = _fixture_path(ext)
            downloads_dir.mkdir(parents=True, exist_ok=True)
            destination = downloads_dir / f"{id_upload}-{len(downloaded_paths)}.{ext}"
            shutil.copyfile(source, destination)
            downloaded_paths.append(destination)
            return str(destination)

        def extract_text(file_path: str, extension: str) -> str:
            ext = extension.lower().strip(".")
            if ext not in extraction_results:
                return real_extract(file_path, extension)
            result = extraction_results[ext]
            if isinstance(result, Exception):
                raise result
            return result

        async def transcribe_audio(_file_path: str, extension: str) -> str:
            ext = extension.lower().strip(".")
            result = transcription_results[ext]
            if isinstance(result, Exception):
                raise result
            return result

        async def persist_attachments(**_kwargs) -> None:
            return None

        def remove_uploads(ids: list[int]) -> None:
            order.append("remove")
            removed_ids.extend(ids)

        monkeypatch.setattr(
            uploads_module.sei_client,
            "md_ia_download_arquivo_avulso",
            download_upload,
        )
        monkeypatch.setattr(uploads_module, "extract_text_from_file", extract_text)
        monkeypatch.setattr(uploads_module, "transcribe_audio_file", transcribe_audio)
        monkeypatch.setattr(
            session_uploads_module, "persist_topic_attachments", persist_attachments
        )
        monkeypatch.setattr(
            session_uploads_module.sei_client,
            "md_ia_remove_arquivos_avulsos",
            remove_uploads,
        )

        harness = SessionStreamHarness(
            monkeypatch,
            tmp_path,
            documents={},
            model_factory=model_factory,
            id_usuario=93000 + len(harnesses),
            id_topico=94000 + len(harnesses),
        )
        harnesses.append(harness)
        return UploadHarnessProbe(
            harness=harness,
            downloaded_paths=downloaded_paths,
            removed_ids=removed_ids,
            event_order=order,
        )

    yield create

    for harness in harnesses:
        harness.close()


def _upload(upload_id: int, extension: str, *, name: str | None = None) -> dict:
    return {
        "id_arquivo_avulso": upload_id,
        "nome_arquivo_avulso": name or f"sample.{extension}",
        "extensao_arquivo_avulso": extension,
    }


def _post_uploads(probe: UploadHarnessProbe, *uploads: dict):
    return probe.harness.post(
        "Analise os arquivos anexados sem repetir a pergunta.",
        request_overrides={"arquivos_avulsos": list(uploads)},
    )


@pytest.mark.parametrize("case", UPLOAD_CASES, ids=lambda case: case.extension)
def test_matriz_de_formatos_entrega_upload_ao_turno_do_agente(
    case: UploadCase, upload_harness_factory
):
    fixture = _fixture_path(case.extension)
    fixture_bytes = fixture.read_bytes()
    assert fixture_bytes, f"fixture vazia para .{case.extension}"

    canary = f"CANARY_UPLOAD_{case.extension.upper()}"
    extraction_results = {}
    transcription_results = {}
    model_factory: Callable[[], DeterministicSessionModel] = DeterministicSessionModel

    if case.kind == "text" and case.extension not in REAL_EXTRACTION:
        extraction_results[case.extension] = canary
    elif case.kind == "audio":
        transcription_results[case.extension] = canary
    elif case.kind == "image":
        payload_b64 = base64.b64encode(fixture_bytes).decode("ascii")

        def image_model_factory() -> UploadTurnObserverModel:
            return UploadTurnObserverModel(
                required_fragments=(
                    f'nome="sample.{case.extension}"',
                    'tipo="imagem" estado="available"',
                ),
                expected_image_mime=case.image_mime,
                expected_image_payload_b64=payload_b64,
            )

        model_factory = image_model_factory

    probe = upload_harness_factory(
        extraction_results=extraction_results,
        transcription_results=transcription_results,
        model_factory=model_factory,
    )
    result = _post_uploads(probe, _upload(1001, case.extension))

    result.assert_completed()
    if case.kind == "image":
        assert "UPLOAD_TURN_OBSERVED" in result.content
    else:
        assert canary in result.content
    assert len(probe.downloaded_paths) == 1
    assert not probe.downloaded_paths[0].exists()
    assert probe.removed_ids == [1001]


def _media_system_instructions() -> tuple[str, str]:
    from sei_ia.data.etl.extract.uploads import (
        AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION,
        IMAGE_ATTACHMENT_SYSTEM_INSTRUCTION,
    )

    return (
        AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION,
        IMAGE_ATTACHMENT_SYSTEM_INSTRUCTION,
    )


def test_audio_expoe_instrucao_de_transcricao_ao_modelo(
    upload_harness_factory,
):
    audio_instruction, image_instruction = _media_system_instructions()
    probe = upload_harness_factory(
        transcription_results={"wav": "CANARY_UPLOAD_WAV"},
        model_factory=lambda: UploadTurnObserverModel(
            required_fragments=(audio_instruction,),
            forbidden_fragments=(image_instruction,),
        ),
    )

    result = _post_uploads(probe, _upload(1051, "wav"))

    result.assert_completed()
    assert "UPLOAD_TURN_OBSERVED" in result.content
    assert "CANARY_UPLOAD_WAV" in result.content


def test_imagem_expoe_instrucao_multimodal_ao_modelo(
    upload_harness_factory,
):
    audio_instruction, image_instruction = _media_system_instructions()
    image_bytes = _fixture_path("png").read_bytes()
    probe = upload_harness_factory(
        model_factory=lambda: UploadTurnObserverModel(
            required_fragments=(image_instruction,),
            forbidden_fragments=(audio_instruction,),
            expected_image_mime="image/png",
            expected_image_payload_b64=base64.b64encode(image_bytes).decode("ascii"),
        )
    )

    result = _post_uploads(probe, _upload(1052, "png"))

    result.assert_completed()
    assert "UPLOAD_TURN_OBSERVED" in result.content


def test_texto_simples_nao_recebe_instrucoes_de_midia(
    upload_harness_factory,
):
    audio_instruction, image_instruction = _media_system_instructions()
    probe = upload_harness_factory(
        model_factory=lambda: UploadTurnObserverModel(
            required_fragments=("CANARY_UPLOAD_TXT",),
            forbidden_fragments=(audio_instruction, image_instruction),
        )
    )

    result = _post_uploads(probe, _upload(1053, "txt"))

    result.assert_completed()
    assert "UPLOAD_TURN_OBSERVED" in result.content
    assert "CANARY_UPLOAD_TXT" in result.content


def test_upload_sem_texto_chega_com_estado_empty(upload_harness_factory):
    probe = upload_harness_factory(
        extraction_results={"txt": ""},
        model_factory=lambda: UploadTurnObserverModel(
            required_fragments=(
                'nome="vazio.txt" extensao="txt" tipo="text" '
                'estado="empty" motivo="no_text_extracted"',
                "[Arquivo existente, mas sem conteúdo textual extraído.]",
            )
        ),
    )

    result = _post_uploads(probe, _upload(1101, "txt", name="vazio.txt"))

    result.assert_completed()
    assert "UPLOAD_TURN_OBSERVED" in result.content
    assert probe.removed_ids == [1101]


@pytest.mark.parametrize(
    ("download_errors", "extraction_results", "expected_reason"),
    [
        ({"txt": OSError("SEI offline")}, {}, "download_failed"),
        ({}, {"txt": RuntimeError("extrator offline")}, "extraction_failed"),
    ],
    ids=("download", "extraction"),
)
def test_upload_indisponivel_nao_aborta_a_sessao_nem_e_removido(
    upload_harness_factory,
    download_errors,
    extraction_results,
    expected_reason,
):
    probe = upload_harness_factory(
        download_errors=download_errors,
        extraction_results=extraction_results,
        model_factory=lambda: UploadTurnObserverModel(
            required_fragments=(
                'nome="indisponivel.txt" extensao="txt" tipo="text" '
                f'estado="unavailable" motivo="{expected_reason}"',
                "[Conteúdo do upload indisponível nesta solicitação. Não infira fatos.]",
            )
        ),
    )

    result = _post_uploads(probe, _upload(1201, "txt", name="indisponivel.txt"))

    result.assert_completed()
    assert "UPLOAD_TURN_OBSERVED" in result.content
    assert probe.removed_ids == []
    assert all(not path.exists() for path in probe.downloaded_paths)


def test_falha_de_transcricao_e_exposta_sem_abortar_sessao(
    upload_harness_factory,
):
    audio_instruction, _ = _media_system_instructions()
    provider_error = "falha sigilosa do provider"
    probe = upload_harness_factory(
        transcription_results={"wav": RuntimeError(provider_error)},
        model_factory=lambda: UploadTurnObserverModel(
            required_fragments=(
                'nome="reuniao.wav" extensao="wav" tipo="audio" '
                'estado="unavailable" motivo="transcription_failed"',
                "[Conteúdo do upload indisponível nesta solicitação. Não infira fatos.]",
            ),
            forbidden_fragments=(audio_instruction, provider_error),
        ),
    )

    result = _post_uploads(probe, _upload(1202, "wav", name="reuniao.wav"))

    result.assert_completed()
    assert "UPLOAD_TURN_OBSERVED" in result.content
    assert result.metadata["uploads"] == [
        {
            "id": 1202,
            "name": "reuniao.wav",
            "type": "audio",
            "state": "unavailable",
            "reason": "transcription_failed",
        }
    ]
    assert probe.removed_ids == []
    assert len(probe.downloaded_paths) == 1
    assert not probe.downloaded_paths[0].exists()


def test_tsv_e_observado_como_formato_nao_suportado(upload_harness_factory):
    probe = upload_harness_factory(
        model_factory=lambda: UploadTurnObserverModel(
            required_fragments=(
                'nome="tabela.tsv" extensao="tsv" tipo="text" '
                'estado="unavailable" motivo="unsupported_format"',
                "[Conteúdo do upload indisponível nesta solicitação. Não infira fatos.]",
            )
        )
    )

    result = _post_uploads(probe, _upload(1301, "tsv", name="tabela.tsv"))

    result.assert_completed()
    assert "UPLOAD_TURN_OBSERVED" in result.content
    assert probe.removed_ids == []


def test_mistura_tipos_preserva_disponiveis_e_isola_o_nao_suportado(
    upload_harness_factory,
):
    image_bytes = (FIXTURES_DIR / "sample.png").read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    probe = upload_harness_factory(
        transcription_results={"wav": "CANARY_UPLOAD_WAV"},
        model_factory=lambda: UploadTurnObserverModel(
            required_fragments=(
                'nome="sample.txt" extensao="txt" tipo="text" estado="available"',
                'nome="sample.wav" extensao="wav" tipo="audio" estado="available"',
                'nome="sample.png" extensao="png" tipo="imagem" estado="available"',
                'nome="sample.tsv" extensao="tsv" tipo="text" '
                'estado="unavailable" motivo="unsupported_format"',
            ),
            expected_image_mime="image/png",
            expected_image_payload_b64=image_b64,
        ),
    )

    result = _post_uploads(
        probe,
        _upload(2001, "txt"),
        _upload(2002, "wav"),
        _upload(2003, "png"),
        _upload(2004, "tsv"),
    )

    result.assert_completed()
    assert "UPLOAD_TURN_OBSERVED" in result.content
    assert "CANARY_UPLOAD_TXT" in result.content
    assert "CANARY_UPLOAD_WAV" in result.content
    assert probe.removed_ids == [2001, 2002, 2003]
    assert len(probe.downloaded_paths) == 4
    assert all(not path.exists() for path in probe.downloaded_paths)


def test_upload_permanece_no_checkpoint_para_o_turno_seguinte(
    upload_harness_factory,
):
    probe = upload_harness_factory()

    first = _post_uploads(probe, _upload(2901, "txt"))
    downloads_after_first = list(probe.downloaded_paths)
    removals_after_first = list(probe.removed_ids)
    second = probe.harness.post(
        "Retome o conteúdo relevante anexado no turno anterior."
    )

    first.assert_completed()
    assert "CANARY_UPLOAD_TXT" in first.content
    second.assert_completed()
    assert second.metadata["is_new_session"] is False
    assert "CANARY_UPLOAD_TXT" in second.content
    assert probe.downloaded_paths == downloads_after_first
    assert probe.removed_ids == removals_after_first == [2901]


def test_remocao_no_sei_acontece_somente_depois_da_resposta_do_agente(
    upload_harness_factory,
):
    order: list[str] = []
    probe = upload_harness_factory(
        model_factory=lambda: CompletionAwareModel(
            completion_hook=lambda: order.append("model_completed")
        ),
        event_order=order,
    )

    result = _post_uploads(probe, _upload(3001, "txt"))

    result.assert_completed()
    assert "CANARY_UPLOAD_TXT" in result.content
    assert probe.removed_ids == [3001]
    assert order[-1] == "remove"
    assert "model_completed" in order[:-1]


def test_falha_do_agente_mantem_upload_no_sei_para_retry(upload_harness_factory):
    probe = upload_harness_factory(model_factory=FailingSessionModel)

    result = _post_uploads(probe, _upload(3101, "txt"))

    assert result.status_code == 200
    assert result.content_type.startswith("text/event-stream")
    assert result.errors
    assert result.event_types.count("metadata") == 0
    assert result.event_types.count("end") == 0
    assert probe.removed_ids == []
    assert len(probe.downloaded_paths) == 1
    assert not probe.downloaded_paths[0].exists()
