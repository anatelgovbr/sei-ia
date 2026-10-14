"""Título curto do tópico (modelo mini).

Roda no router só no primeiro turno do tópico, em paralelo ao agente principal, e
volta no frame ``metadata`` como ``titulo_topico``. O SEI usa a frase como nome do
tópico no histórico, no lugar do nome default com data e hora.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sei_ia.configs.settings_config import settings
from sei_ia.services.llm_models.get_model import get_model

logger = logging.getLogger(__name__)

MAX_CHARS = 80

_PROMPT = """\
Crie um titulo curto para um topico de conversa com um assistente de IA do SEI
(Sistema Eletronico de Informacoes), a partir da primeira mensagem do usuario.

Regras:
- Frase nominal de 3 a 8 palavras, em portugues, que resuma o assunto da mensagem.
- Sem ponto final, aspas, emojis ou prefixos como "Titulo:".
- Preserve numeros de processo, documento ou SEI citados na mensagem.
- Nao responda a mensagem; apenas a nomeie.

Responda SOMENTE um JSON no formato: {{"titulo": "..."}}.

Mensagem: {pergunta}"""

_WRAPPING_CHARS = "\"'`\u201c\u201d\u2018\u2019«»*#"


def _normalize_title(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    title = re.sub(r"\s+", " ", raw)
    previous = None
    while title != previous:
        previous = title
        title = title.strip().strip(_WRAPPING_CHARS).rstrip(".;:")
    if not title:
        return None
    if len(title) > MAX_CHARS:
        cut = title[: MAX_CHARS - 1]
        title = (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip(" ,;:-") + "…"
    return title


async def generate_topic_title(
    question: str,
    *,
    callbacks: list[Any] | None = None,
) -> str | None:
    """Devolve o título do tópico ou ``None`` quando não for possível gerá-lo.

    ``None`` mantém o nome default no SEI; a falha é registrada em log e não
    interrompe a resposta do chat.
    """
    try:
        llm = get_model(
            settings.SESSION_CLASSIFIER_MODEL,
            response_format={"type": "json_object"},
        )
        prompt = _PROMPT.format(pergunta=question)
        if callbacks:
            resp = await llm.ainvoke(prompt, config={"callbacks": callbacks})
        else:
            resp = await llm.ainvoke(prompt)
        raw = json.loads(str(resp.content)).get("titulo")
    except Exception:
        logger.warning("Falha ao gerar título do tópico", exc_info=True)
        return None
    title = _normalize_title(raw)
    if title is None:
        logger.warning("Título do tópico inválido: %r", raw)
    return title
