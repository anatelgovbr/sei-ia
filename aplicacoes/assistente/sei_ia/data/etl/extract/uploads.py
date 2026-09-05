"""Módulo para download e extração de texto de uploads do Assistente IA."""

import asyncio
import html
import logging
import os
from dataclasses import dataclass, field
from typing import Literal

from sei_extraction import AUDIO_EXTENSIONS
from sei_extraction.extract import extract_document
from sei_extraction.text import html_to_markdown

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.content_status import ContentReason, ContentState, ContentStatus
from sei_ia.data.database.sei_client import extraction_config, ocr_client, sei_client
from sei_ia.data.etl.extract.external import (
    EXT_DOCLING_SUPPORTED,
    EXT_HTML,
    EXT_ODP,
    EXT_PLAIN_TEXT,
    EXT_UNSTRUCTURED,
)
from sei_ia.data.pydantic_models import UploadItem
from sei_ia.services.llm_models.speech_to_text import transcribe_audio_file

setup_logging()
logger = logging.getLogger(__name__)

EXT_SPREADSHEETS = ["ods", "xls", "xlsb", "xlsm", "xlsx"]
EXT_IMAGE = ["png", "jpg", "jpeg", "webp"]

# Mapeamento extensão → MIME type para anexos de imagem multimodais.
_IMAGE_MIME_BY_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION = (
    "\n\nAtenção: um ou mais arquivos de áudio foram enviados pelo usuário e transcritos "
    "automaticamente. O conteúdo transcrito está disponível na seção <arquivos_avulsos> da mensagem. "
    "Considere o texto transcrito como parte da comunicação do usuário ao formular sua resposta."
)

IMAGE_ATTACHMENT_SYSTEM_INSTRUCTION = (
    "\n\nAtenção: uma ou mais imagens foram enviadas pelo usuário e estão "
    "anexadas como mídia multimodal nesta mensagem. Os nomes dos arquivos "
    "estão listados na seção <arquivos_avulsos> e o conteúdo visual de cada imagem está "
    "acessível diretamente na sua entrada multimodal. Use ambos ao formular "
    "sua resposta — quando o usuário se referir a um arquivo pelo nome, cruze "
    "com a imagem correspondente."
)

# Cada arquivo dentro de <arquivos_avulsos> é encapsulado por um <arquivo>...</arquivo>
# com atributos. Discriminador `tipo` (text/audio/imagem) ajuda o LLM a
# distinguir natureza da fonte. Atributos extras só para imagem (`mime` e
# `tamanho`). Fechamento explícito blinda contra colisão com `---` ou
# `# Arquivo:` presentes no conteúdo (markdown, código, etc).
UPLOAD_TEXT_BLOCK_TEMPLATE = """<arquivo id_arquivo_avulso="{id_arquivo_avulso}" nome="{nome_original}" extensao="{extensao}" tipo="{tipo}" estado="{estado}" motivo="{motivo}">
{conteudo}
</arquivo>"""

UPLOAD_IMAGE_BLOCK_TEMPLATE = (
    '<arquivo id_arquivo_avulso="{id_arquivo_avulso}" nome="{nome_original}" '
    'extensao="{extensao}" tipo="imagem" estado="available" motivo="" '
    'mime="{mime}" tamanho="{size_human}">\n{conteudo}\n</arquivo>'
)

# Compat: alguns testes ainda referenciam `UPLOAD_BLOCK_TEMPLATE`. Mantemos
# como alias do template de texto.
UPLOAD_BLOCK_TEMPLATE = UPLOAD_TEXT_BLOCK_TEMPLATE

UPLOADS_WRAPPER_TEMPLATE = """<arquivos_avulsos>
{blocos}
</arquivos_avulsos>"""

# Conteúdo do bloco de imagem: só metadado, sem bytes nem transcrição. Os
# bytes da imagem chegam ao LLM via `image_url` multimodal na própria
# HumanMessage (ver chat_workflow._build_multimodal_human_message).
IMAGE_BLOCK_PLACEHOLDER = (
    "[Imagem anexada como mídia multimodal — conteúdo visual disponível "
    "diretamente na mensagem.]"
)


def _format_size(size_bytes: int) -> str:
    """Formato humano simples (B / KB / MB) para o atributo `tamanho`."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _xml_attr(value: str) -> str:
    """Escapa valor para atributo XML/HTML — evita que aspas no nome do
    arquivo quebrem o `<arquivo nome="...">`."""
    return html.escape(str(value), quote=True)


# ---------------------------------------------------------------------------
# Resultado estruturado do processamento de uploads
# ---------------------------------------------------------------------------


class UploadProcessingError(Exception):
    """Erro identificável durante o processamento de um upload.

    Levantada por `download_and_extract_upload` quando o download ou a
    extração de um arquivo falha. O handler do endpoint converte em
    `HTTPException(422, {filename, extensao, message})` para que o usuário
    saiba qual arquivo falhou — em vez de receber 200 OK com placeholder
    silencioso.
    """

    def __init__(self, filename: str, extensao: str, message: str = ""):
        self.filename = filename
        self.extensao = extensao
        self.message = message
        super().__init__(
            f"Falha ao processar upload '{filename}' (.{extensao}): {message}"
        )


@dataclass
class ImageAttachment:
    """Anexo de imagem para envio multimodal ao agente.

    Apenas metadado é armazenado no `user_state`. Os bytes são lidos do
    `fs_path` no último momento — durante a construção da `HumanMessage` —
    para evitar inflar o estado do grafo (checkpoints LangGraph, trace
    Langfuse) com base64 grande.
    """

    filename: str  # nome original do arquivo (ex.: "captura.png")
    mime: str  # MIME type (ex.: "image/png")
    fs_path: str  # caminho absoluto em /tmp/ (efêmero, deletado no finally)
    size_bytes: int  # tamanho validado no momento do upload


@dataclass
class _UploadResult:
    """Resultado interno de `download_and_extract_upload`.

    `kind` discrimina a origem para o LLM saber se um bloco de texto vem de
    extração textual (text), de transcrição de áudio (audio), ou se é um
    placeholder de mídia visual anexada (imagem).
    """

    filename: str
    fs_path: str | None
    kind: Literal["text", "audio", "imagem"]
    id_arquivo_avulso: int
    extensao: str
    text: str | None = None
    image: ImageAttachment | None = None
    size_bytes: int | None = None
    mime: str | None = None
    status: ContentStatus = field(default_factory=ContentStatus.available)


@dataclass
class ProcessedAttachment:
    """Anexo processado para persistência consultável posteriormente no tópico.

    Estrutura serializável que carrega o conteúdo textual completo extraído
    (PDF/DOCX/XLSX/TXT/áudio transcrito). Para imagens, `conteudo` é None e
    apenas metadado é guardado, pois os bytes são efêmeros (/tmp).
    """

    id_arquivo_avulso: int
    nome_arquivo: str
    extensao: str
    tipo: Literal["text", "audio", "imagem"]
    conteudo: str | None
    size_bytes: int | None = None
    mime: str | None = None
    content_state: ContentState = "available"
    content_reason: ContentReason | None = None


@dataclass
class UploadOutcome:
    """Resultado agregado de `process_uploads`.

    Carrega o bloco `<arquivos_avulsos>` formatado (para concatenar ao `user_request`),
    a lista de anexos de imagem multimodais (para o `user_state`), a lista
    estruturada de anexos processados (para persistência no Redis), e o conjunto
    de caminhos em /tmp/ que o handler do endpoint deve deletar no `finally`.
    """

    text_block: str = ""
    image_attachments: list[ImageAttachment] = field(default_factory=list)
    attachments: list[ProcessedAttachment] = field(default_factory=list)
    temp_files: set[str] = field(default_factory=set)
    removal_ids: set[int] = field(default_factory=set)


def extract_text_from_file(file_path: str, extensao: str) -> str:
    """Extrai texto de um arquivo local baseado na sua extensão.

    Args:
        file_path: Caminho completo para o arquivo em /tmp/.
        extensao: Extensão do arquivo (sem ponto), ex: "pdf", "docx", "png".

    Returns:
        Texto extraído, ou mensagem indicando formato não suportado.
    """
    ext = extensao.lower().strip(".")

    if ext in EXT_HTML:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            return html_to_markdown(f.read())

    supported = (
        {"pdf"}
        | set(EXT_DOCLING_SUPPORTED)
        | set(EXT_PLAIN_TEXT)
        | set(EXT_UNSTRUCTURED)
        | set(EXT_ODP)
        | set(EXT_SPREADSHEETS)
    )
    if ext not in supported:
        logger.warning(
            f"Extensão '{ext}' não suportada para extração de texto em uploads."
        )
        return f"[Formato .{ext} não suportado para extração de texto]"

    return extract_document(file_path, ext, extraction_config, ocr_client)


def _build_image_attachment(upload: UploadItem, file_path: str) -> ImageAttachment:
    """Constrói o metadado do anexo de imagem (sem ler bytes).

    Faz um `stat()` no upload para validar que o arquivo é legível e capturar
    o tamanho. Bytes só são lidos depois, na construção da `HumanMessage`.
    """
    ext = upload.extensao.lower().strip(".")
    size_bytes = os.path.getsize(file_path)
    return ImageAttachment(
        filename=upload.nome_original,
        mime=_IMAGE_MIME_BY_EXT[ext],
        fs_path=file_path,
        size_bytes=size_bytes,
    )


def _upload_kind(extensao: str) -> Literal["text", "audio", "imagem"]:
    if extensao in EXT_IMAGE:
        return "imagem"
    if extensao in AUDIO_EXTENSIONS:
        return "audio"
    return "text"


def _is_supported_text_extension(extensao: str) -> bool:
    return extensao in (
        {"pdf"}
        | set(EXT_DOCLING_SUPPORTED)
        | set(EXT_PLAIN_TEXT)
        | set(EXT_UNSTRUCTURED)
        | set(EXT_ODP)
        | set(EXT_SPREADSHEETS)
        | set(EXT_HTML)
    )


async def download_and_extract_upload(
    upload: UploadItem, *, tolerant: bool = False
) -> _UploadResult:
    """Faz download de um upload e retorna texto extraído ou anexo de imagem.

    Pipeline:
      1. Baixa o arquivo via sei_client para /tmp/.
      2. Se extensão for de imagem (EXT_IMAGE): retorna `_UploadResult` com
         `image` populado — os bytes ficam no FS para leitura sob demanda na
         construção da HumanMessage multimodal.
      3. Se extensão for de áudio (AUDIO_EXTENSIONS): transcreve via Whisper/LiteLLM.
      4. Caso contrário: extrai texto via `extract_text_from_file`.

    Raises:
        UploadProcessingError: quando download ou extração falham. A exception
            carrega `filename` e `extensao` para o handler do endpoint montar
            o erro 422 com o nome do arquivo.
    """
    loop = asyncio.get_running_loop()
    ext = upload.extensao.lower().strip(".")
    file_path: str | None = None
    try:
        file_path = await loop.run_in_executor(
            None,
            sei_client.md_ia_download_arquivo_avulso,
            upload.id_upload,
            upload.extensao,
        )
        logger.debug(
            f"Upload {upload.id_upload} ({upload.nome_original}) salvo em '{file_path}'"
        )

        if ext in EXT_IMAGE:
            logger.info(
                f"Upload {upload.id_upload} ({upload.nome_original}) identificado como "
                f"imagem (.{ext}). Anexando como mídia multimodal."
            )
            attachment = _build_image_attachment(upload, file_path)
            return _UploadResult(
                filename=upload.nome_original,
                fs_path=file_path,
                kind="imagem",
                id_arquivo_avulso=upload.id_arquivo_avulso,
                extensao=ext,
                image=attachment,
                size_bytes=attachment.size_bytes,
                mime=attachment.mime,
                status=ContentStatus.available(),
            )

        if ext in AUDIO_EXTENSIONS:
            logger.info(
                f"Upload {upload.id_upload} ({upload.nome_original}) identificado como "
                f"arquivo de áudio (.{ext}). Iniciando transcrição."
            )
            conteudo = await transcribe_audio_file(file_path, upload.extensao)
            return _UploadResult(
                filename=upload.nome_original,
                fs_path=file_path,
                kind="audio",
                id_arquivo_avulso=upload.id_arquivo_avulso,
                extensao=ext,
                text=conteudo,
                status=(
                    ContentStatus.empty("no_text_extracted")
                    if conteudo == ""
                    else ContentStatus.available()
                ),
            )

        if tolerant and not _is_supported_text_extension(ext):
            return _UploadResult(
                filename=upload.nome_original,
                fs_path=file_path,
                kind="text",
                id_arquivo_avulso=upload.id_arquivo_avulso,
                extensao=ext,
                status=ContentStatus.unavailable("unsupported_format"),
            )
        conteudo = await loop.run_in_executor(
            None,
            extract_text_from_file,
            file_path,
            upload.extensao,
        )
        return _UploadResult(
            filename=upload.nome_original,
            fs_path=file_path,
            kind="text",
            id_arquivo_avulso=upload.id_arquivo_avulso,
            extensao=ext,
            text=conteudo,
            status=(
                ContentStatus.empty("no_text_extracted")
                if conteudo == ""
                else ContentStatus.available()
            ),
        )

    except UploadProcessingError:
        raise
    except Exception as exc:
        logger.exception(
            f"Erro ao processar upload {upload.id_upload} ({upload.nome_original})"
        )
        if tolerant:
            return _UploadResult(
                filename=upload.nome_original,
                fs_path=file_path,
                kind=_upload_kind(ext),
                id_arquivo_avulso=upload.id_arquivo_avulso,
                extensao=ext,
                status=ContentStatus.unavailable(
                    "timeout"
                    if isinstance(exc, TimeoutError)
                    else ("extraction_failed" if file_path else "download_failed")
                ),
            )
        raise UploadProcessingError(
            filename=upload.nome_original,
            extensao=upload.extensao,
            message=str(exc),
        ) from exc


def _raise_first_upload_error(results: list, cleanup_paths: set[str]) -> None:
    """Propaga o primeiro erro encontrado nos resultados, anotando os paths de limpeza."""
    for r in results:
        if isinstance(r, UploadProcessingError):
            r.cleanup_paths = cleanup_paths
            raise r
        if isinstance(r, BaseException):
            raise UploadProcessingError(
                filename="desconhecido",
                extensao="?",
                message=f"Erro inesperado: {r}",
            ) from r


async def _process_uploads(
    uploads: list[UploadItem] | None, *, tolerant: bool
) -> UploadOutcome:
    """Processa todos os uploads em paralelo e retorna o resultado agregado.

    Retorna `UploadOutcome` com:
      - `text_block`: bloco `<arquivos_avulsos>...</arquivos_avulsos>` formatado para concatenar
        ao `user_request` (vazio se nenhum upload gerou texto).
      - `image_attachments`: lista de anexos de imagem para o `user_state`,
        materializados como `image_url` multimodal no momento de montar a
        HumanMessage final.
      - `temp_files`: conjunto de caminhos em /tmp/ que o handler do endpoint
        deve apagar no `finally`, depois que a resposta for enviada.

    Raises:
        UploadProcessingError: se qualquer upload falhar. A exception preserva
            o nome do primeiro arquivo que falhou; outros uploads que tenham
            chegado ao FS são incluídos em `temp_files` da exception via
            atributo `cleanup_paths`.
    """
    if not uploads:
        return UploadOutcome()

    tasks = [
        download_and_extract_upload(upload, tolerant=tolerant) for upload in uploads
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    cleanup_paths: set[str] = {
        r.fs_path
        for r in results
        if isinstance(r, _UploadResult) and r.fs_path is not None
    }
    if not tolerant:
        _raise_first_upload_error(results, cleanup_paths)

    # Preserva a ordem dos uploads no payload original — texto, áudio e
    # imagem convivem no mesmo bloco <arquivos_avulsos>; cada bloco é encapsulado
    # por <arquivo nome="..." tipo="..."> ... </arquivo> com fechamento
    # explícito para blindar segmentação contra conteúdo que tenha
    # `---` ou `# Arquivo:` dentro.
    blocos: list[str] = []
    attachments: list[ProcessedAttachment] = []
    removal_ids: set[int] = set()
    for r in results:
        if not isinstance(r, _UploadResult):
            continue
        nome_attr = _xml_attr(r.filename)
        common = {
            "id_arquivo_avulso": r.id_arquivo_avulso,
            "nome_original": nome_attr,
            "extensao": _xml_attr(r.extensao),
            "tipo": r.kind,
            "estado": r.status.state,
            "motivo": _xml_attr(r.status.reason or ""),
        }
        if r.status.state == "unavailable":
            blocos.append(
                UPLOAD_TEXT_BLOCK_TEMPLATE.format(
                    **common,
                    conteudo=(
                        "[Conteúdo do upload indisponível nesta solicitação. "
                        "Não infira fatos.]"
                    ),
                )
            )
        elif r.kind == "imagem" and r.image is not None:
            blocos.append(
                UPLOAD_IMAGE_BLOCK_TEMPLATE.format(
                    **common,
                    mime=_xml_attr(r.image.mime),
                    size_human=_xml_attr(_format_size(r.image.size_bytes)),
                    conteudo=IMAGE_BLOCK_PLACEHOLDER,
                )
            )
        elif r.text is not None:
            blocos.append(
                UPLOAD_TEXT_BLOCK_TEMPLATE.format(
                    **common,
                    conteudo=(
                        "[Arquivo existente, mas sem conteúdo textual extraído.]"
                        if r.status.state == "empty"
                        else r.text
                    ),
                )
            )

        attachments.append(
            ProcessedAttachment(
                id_arquivo_avulso=r.id_arquivo_avulso,
                nome_arquivo=r.filename,
                extensao=r.extensao,
                tipo=r.kind,
                # Imagem não persiste conteúdo visual aqui — apenas metadados.
                # Os bytes são efêmeros em /tmp/ e a consulta posterior não
                # tem acesso à imagem original sem OCR/persistência binária.
                conteudo=r.text if r.kind != "imagem" else None,
                size_bytes=r.size_bytes,
                mime=r.mime,
                content_state=r.status.state,
                content_reason=r.status.reason,
            )
        )
        if r.status.state != "unavailable":
            removal_ids.add(r.id_arquivo_avulso)

    text_block = (
        UPLOADS_WRAPPER_TEMPLATE.format(blocos="\n".join(blocos)) if blocos else ""
    )

    image_attachments = [
        r.image for r in results if isinstance(r, _UploadResult) and r.image is not None
    ]

    return UploadOutcome(
        text_block=text_block,
        image_attachments=image_attachments,
        attachments=attachments,
        temp_files=cleanup_paths,
        removal_ids=removal_ids,
    )


async def process_uploads(uploads: list[UploadItem] | None) -> UploadOutcome:
    """Contrato legado: propaga a primeira falha de upload como erro 422."""
    return await _process_uploads(uploads, tolerant=False)


async def process_uploads_tolerant(uploads: list[UploadItem] | None) -> UploadOutcome:
    """Processa cada upload da sessão e descreve falhas no prompt, sem abortar o lote."""
    return await _process_uploads(uploads, tolerant=True)


def cleanup_upload_temp_files(paths: set[str] | list[str] | None) -> None:
    """Deleta arquivos de uploads em /tmp/. Best-effort, nunca propaga erro.

    Chamada no `finally` do handler do endpoint, depois que a resposta foi
    enviada (com sucesso ou erro). Cada path falha silenciosamente — limpeza
    é auxiliar e não pode impedir resposta ao usuário.
    """
    if not paths:
        return
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning(f"Falha ao remover arquivo de upload '{path}': {e}")


# Compatibilidade temporária com nomes da frente anterior de arquivos avulsos.
# Mantém callers ainda não migrados sem duplicar fluxo de produção.
ArquivoAvulsoProcessingError = UploadProcessingError
ArquivosAvulsosOutcome = UploadOutcome
download_and_extract_arquivo_avulso = download_and_extract_upload
process_arquivos_avulsos = process_uploads
cleanup_arquivos_avulsos_temp_files = cleanup_upload_temp_files
