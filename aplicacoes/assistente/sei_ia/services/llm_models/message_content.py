"""Helpers de conteúdo multimodal e extração de reasoning para o endpoint Session."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage


def _build_multimodal_human_message(
    text_content: str, image_attachments: list
) -> HumanMessage:
    """Monta a HumanMessage final para envio ao LLM.

    Quando há `image_attachments` no `user_state`, constrói o content como
    lista multimodal `[{"type":"text","text":...}, {"type":"image_url",...}]`
    com cada imagem em base64 inline (`data:<mime>;base64,...`). Bytes só são
    lidos do FS aqui — última etapa antes do LLM — para evitar inflar o
    `user_state` (e os checkpoints LangGraph / traces Langfuse) com base64.

    Caso não haja imagens, devolve `HumanMessage(content=str)` como antes,
    preservando o caminho hot.

    Falhas de leitura do FS (arquivo apagado, permissão) viram
    `ArquivoAvulsoProcessingError` para o handler do endpoint converter em 4xx com
    o nome do arquivo — sem silent error.
    """
    if not image_attachments:
        return HumanMessage(content=text_content)

    # Importação tardia para evitar ciclo (uploads → ... → message_content).
    from sei_ia.data.etl.extract.uploads import ArquivoAvulsoProcessingError

    parts: list[dict[str, Any]] = [{"type": "text", "text": text_content}]
    for att in image_attachments:
        try:
            raw = Path(att.fs_path).read_bytes()
        except OSError as exc:
            ext = Path(att.filename).suffix.lstrip(".") or "?"
            raise ArquivoAvulsoProcessingError(
                filename=att.filename,
                extensao=ext,
                message=f"falha ao ler imagem do FS para anexar à mensagem: {exc}",
            ) from exc
        b64 = base64.b64encode(raw).decode()
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{att.mime};base64,{b64}"},
            }
        )
    return HumanMessage(content=parts)


def _collect_summary_texts(block: dict) -> list[str]:
    texts = []
    for summary in block.get("summary") or []:
        if isinstance(summary, dict):
            text = summary.get("text")
            if text:
                texts.append(text)
    return texts


def extract_reasoning_delta_from_content(content: Any) -> str:
    """Delta de reasoning a partir do `content` de um chunk já desembrulhado.

    Na Responses API (`use_responses_api=True`) o `content` vira `list[dict]`
    com blocos `{"type": "reasoning", "summary": [{"type": "summary_text",
    "text": "..."}, ...]}`; concatena os `summary_text`. Para `content` string
    (Chat Completions), retorna "".

    Núcleo compartilhado: o session/stream.py chama esta forma direto (tem o
    `content` na mão), sem embrulhar num objeto só para reexpor `.content`.
    """
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "reasoning":
            continue
        parts.extend(_collect_summary_texts(block))
    return "".join(parts)
