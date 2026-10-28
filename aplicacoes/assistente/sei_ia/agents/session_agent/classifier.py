"""Classificador de complexidade da pergunta (modelo mini).

Roda no router antes do agente principal. O nivel ajusta a INSTRUCAO do agente
(easy/medium/high), nao a topologia. Mesmo padrao do intent_selector_agent.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from sei_ia.configs.settings_config import settings
from sei_ia.services.llm_models.get_model import get_model

logger = logging.getLogger(__name__)

Complexity = Literal["easy", "medium", "high"]
_VALID: tuple[Complexity, ...] = ("easy", "medium", "high")
_FALLBACK: Complexity = "medium"

_PROMPT = """\
Classifique o esforco para responder a pergunta sobre os documentos de um processo
da ANATEL. A sessao tem {n} documentos disponiveis.

Niveis:
- easy: conversa trivial/saudacao que NAO exige ler documentos (ex.: "oi",
  "obrigado", "o que voce faz?").
- medium: pergunta pontual que se resolve lendo poucos documentos especificos.
- high: pergunta ampla que exige cruzar/sintetizar VARIOS documentos. Inclui resumo
  do processo, panorama, analise, andamento, "do que trata", linha do tempo, ou
  qualquer coisa que dependa do conjunto de documentos.

Regra pratica: se a pergunta for sobre "o processo" como um todo e houver varios
documentos, classifique como high. Na duvida entre medium e high, escolha high.

Responda SOMENTE um JSON no formato: {{"nivel": "easy|medium|high"}}.

Pergunta: {pergunta}"""


async def classify_complexity(
    question: str,
    doc_count: int = 0,
    *,
    callbacks: list[Any] | None = None,
) -> Complexity:
    """Devolve o nivel de esforco (easy/medium/high). Em falha, cai para 'medium'.

    `doc_count` entra no prompt: perguntas amplas sobre muitos documentos tendem a high.
    """
    llm = get_model(
        settings.SESSION_CLASSIFIER_MODEL,
        response_format={"type": "json_object"},
    )
    try:
        prompt = _PROMPT.format(pergunta=question, n=doc_count)
        if callbacks:
            resp = await llm.ainvoke(prompt, config={"callbacks": callbacks})
        else:
            resp = await llm.ainvoke(prompt)
        nivel = json.loads(resp.content).get("nivel")
    except Exception:
        logger.warning(
            "Falha ao classificar complexidade; usando '%s'", _FALLBACK, exc_info=True
        )
        return _FALLBACK
    if nivel not in _VALID:
        logger.warning("Nivel invalido '%s'; usando '%s'", nivel, _FALLBACK)
        return _FALLBACK
    return nivel
