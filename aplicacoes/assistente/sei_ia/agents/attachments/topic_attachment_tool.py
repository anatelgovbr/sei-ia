"""Tool LangChain para consulta de anexos avulsos do tópico atual.

O `id_topico` é capturado por closure a partir do `user_state` no backend,
para que o LLM nunca precise (e nunca consiga) informar esse parâmetro —
schema da tool só expõe `nome_arquivo` e `id_arquivo_avulso`.

A tool retorna o conteúdo completo do anexo — sem paginação via slicing.

Quando `make_consultar_anexos_topico_tool` é chamada com `id_topico=None`
(ou com o cache desabilitado), devolve `None` — caller deve omitir a tool
do agente.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.services.cache.topic_attachments import (
    find_topic_attachments_by_name,
    get_topic_attachment,
    list_topic_attachments,
)
from sei_ia.services.counter import token_counter

setup_logging()
logger = logging.getLogger(__name__)


TOOL_NAME = "consultar_anexos_do_topico"

TOPIC_ATTACHMENTS_TOOL_SYSTEM_INSTRUCTION = """

Você tem acesso à ferramenta `consultar_anexos_do_topico`, que consulta anexos avulsos enviados recentemente neste mesmo tópico.

Use essa ferramenta APENAS quando todas as condições abaixo forem verdadeiras:
1. A pergunta do usuário menciona ou depende de um arquivo/anexo/documento/PDF específico;
2. O conteúdo desse anexo **não** está disponível na conversa atual (não foi enviado inline no prompt, não está entre tags `<arquivos_avulsos>`...`</arquivos_avulsos>`).

NÃO use a ferramenta quando:
- O usuário não mencionou nenhum arquivo ou anexo;
- O conteúdo do arquivo mencionado já está presente na conversa (inline ou via `<arquivos_avulsos>`).

Regras:
- A ferramenta retorna o conteúdo completo do anexo quando ele couber no contexto restante. Não há necessidade de paginar ou limitar caracteres.
- Se a ferramenta retornar `status="content_too_large"`, explique que o anexo excede o contexto restante e não invente conteúdo.
- Se retornar `status="empty"`, o arquivo existe, mas não tinha conteúdo textual extraído.
- Se retornar `status="unavailable"`, o arquivo existe, mas o conteúdo não está disponível nesta solicitação; não infira fatos.
- Nunca invente nome ou conteúdo de anexo.
- Não peça nem informe `id_topico`; o sistema já limita a ferramenta ao tópico atual.
- Se não souber qual anexo consultar, chame a ferramenta sem nome/id para listar os anexos do tópico.
- Se a ferramenta indicar que o anexo expirou ou não existe, informe isso claramente ao usuário sem inventar conteúdo.

"""


def _attachment_summary(entry: dict[str, Any]) -> dict[str, Any]:
    """Resumo padrão de um anexo para listagens/respostas da tool."""
    return {
        "id_arquivo_avulso": entry.get("id_arquivo_avulso"),
        "nome_arquivo": entry.get("nome_arquivo"),
        "extensao": entry.get("extensao"),
        "tipo": entry.get("tipo"),
        "content_chars": entry.get("content_chars"),
        "content_tokens": entry.get("content_tokens"),
        "size_bytes": entry.get("size_bytes"),
        "cached_at": entry.get("cached_at"),
        "content_state": entry.get("content_state"),
        "content_reason": entry.get("content_reason"),
    }


def _dump(payload: dict[str, Any]) -> str:
    """Serializa o resultado da tool em JSON UTF-8 sem escapes."""
    return json.dumps(payload, ensure_ascii=False, default=str)


def make_consultar_anexos_topico_tool(  # noqa: C901  # NOSONAR
    id_topico: int | None, remaining_context_tokens: int | None = None
):
    """Factory que devolve a tool com `id_topico` fixo via closure.

    Retorna None quando não há tópico ou quando o cache está desabilitado —
    nesse caso a tool não deve ser plugada ao agente.
    """
    if id_topico is None:
        return None
    if not settings.ARQUIVOS_AVULSOS_CACHE_ENABLED:
        return None

    # Captura uma vez para garantir invariante de closure.
    bound_id_topico = int(id_topico)
    bound_remaining_context_tokens = remaining_context_tokens

    async def _handle_catalog(remaining: int | None) -> str:
        entries = await list_topic_attachments(bound_id_topico)
        if not entries:
            return _dump(
                {
                    "status": "empty",
                    "message": "Nenhum anexo recente disponível neste tópico (pode ter expirado ou nunca ter sido enviado).",
                    "attachments": [],
                    "remaining_context_tokens": remaining,
                }
            )
        return _dump(
            {
                "status": "ok",
                "attachments": [_attachment_summary(e) for e in entries],
                "remaining_context_tokens": remaining,
            }
        )

    async def _handle_name_search(nome: str, remaining: int | None) -> str | None:
        candidates = await find_topic_attachments_by_name(bound_id_topico, nome)
        if not candidates:
            return _dump(
                {
                    "status": "not_found",
                    "message": f"Nenhum anexo encontrado pelo nome '{nome}'. Liste os anexos do tópico para conferir os nomes.",
                    "remaining_context_tokens": remaining,
                }
            )
        if len(candidates) > 1:
            return _dump(
                {
                    "status": "ambiguous",
                    "message": "Vários anexos compatíveis com o nome informado. Refine pelo id_arquivo_avulso.",
                    "matches": [_attachment_summary(c) for c in candidates],
                    "remaining_context_tokens": remaining,
                }
            )
        return None

    async def _handle_fetch(
        nome: str | None, id_arq: int | None, remaining: int | None
    ) -> str:
        payload = await get_topic_attachment(
            id_topico=bound_id_topico,
            id_arquivo_avulso=id_arq,
            nome_arquivo=nome if id_arq is None else None,
        )
        if payload is None:
            return _dump(
                {
                    "status": "not_found",
                    "message": "Anexo não disponível: pode ter expirado do cache ou não existir. Liste os anexos do tópico.",
                    "remaining_context_tokens": remaining,
                }
            )
        content_state = payload.get("content_state", "unavailable")
        content_reason = payload.get("content_reason")
        conteudo = payload.get("conteudo") or ""
        content_chars = payload.get("content_chars") or len(conteudo)
        content_tokens = int(payload.get("content_tokens") or token_counter(conteudo))
        selected = {
            "id_arquivo_avulso": payload.get("id_arquivo_avulso"),
            "nome_arquivo": payload.get("nome_arquivo"),
            "extensao": payload.get("extensao"),
            "tipo": payload.get("tipo"),
            "content_chars": content_chars,
            "content_tokens": content_tokens,
            "size_bytes": payload.get("size_bytes"),
            "cached_at": payload.get("cached_at"),
            "content_state": content_state,
            "content_reason": content_reason,
        }
        if content_state == "unavailable":
            return _dump(
                {
                    "status": "unavailable",
                    "message": "O anexo existe, mas o conteúdo não está disponível nesta solicitação. Não infira fatos a partir dele.",
                    "selected": selected,
                    "remaining_context_tokens": remaining,
                }
            )
        if content_state == "empty":
            return _dump(
                {
                    "status": "empty",
                    "message": "O anexo existe, mas não tinha conteúdo textual extraído.",
                    "selected": selected,
                    "remaining_context_tokens": remaining,
                }
            )
        if remaining is not None and content_tokens > remaining:
            return _dump(
                {
                    "status": "content_too_large",
                    "message": f"O anexo '{payload.get('nome_arquivo')}' tem {content_tokens} tokens, mas restam apenas {remaining} tokens na janela de contexto.",
                    "selected": selected,
                    "file_tokens": content_tokens,
                    "remaining_context_tokens": remaining,
                }
            )
        return _dump(
            {
                "status": "ok",
                "selected": selected,
                "conteudo": conteudo,
                "remaining_context_tokens": remaining,
            }
        )

    @tool(TOOL_NAME)
    async def consultar_anexos_do_topico(
        nome_arquivo: str | None = None,
        id_arquivo_avulso: int | None = None,
    ) -> str:
        """Lista ou consulta anexos avulsos enviados recentemente neste tópico.

        Use sempre que o usuário perguntar sobre arquivo/anexo/PDF/documento
        que ele enviou antes neste mesmo tópico, desde que o conteúdo desse
        anexo não esteja disponível na conversa atual.

        A ferramenta retorna o conteúdo completo apenas quando estiver
        disponível. Para anexos vazios ou indisponíveis, retorna o estado e um
        motivo sanitizado, sem inventar conteúdo.

        Se chamada sem `nome_arquivo` e sem `id_arquivo_avulso` (ambos
        vazios/None), lista todos os anexos disponíveis no tópico com
        metadados (nome, extensão, tamanho) — sem o conteúdo.

        Não informe id_topico: o servidor já limita a ferramenta ao tópico
        atual.

        Args:
            nome_arquivo: Nome (ou parte do nome) do anexo a consultar.
                Match case-insensitive contra os nomes cacheados.
            id_arquivo_avulso: Id numérico do anexo, quando conhecido.

        Returns:
            JSON string com status e dados. Quando nenhum seletor é
            informado, retorna o catálogo. Quando o anexo expirou ou não
            existe, retorna `status="not_found"`.
        """
        try:
            remaining = bound_remaining_context_tokens
            if id_arquivo_avulso is None and not nome_arquivo:
                return await _handle_catalog(remaining)
            if id_arquivo_avulso is None and nome_arquivo:
                early = await _handle_name_search(nome_arquivo, remaining)
                if early is not None:
                    return early
            return await _handle_fetch(nome_arquivo, id_arquivo_avulso, remaining)
        except Exception as exc:
            logger.warning(
                "Falha inesperada na tool consultar_anexos_do_topico: %s", exc
            )
            return _dump(
                {
                    "status": "error",
                    "message": "Falha ao consultar anexos do tópico. Tente novamente em instantes.",
                }
            )

    return consultar_anexos_do_topico
