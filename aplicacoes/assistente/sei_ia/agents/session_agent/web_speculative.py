"""Planejamento de pontos de busca especulativa (session_stream).

Um mini identifica os poucos fatos externos que precisam ser pesquisados para
responder a pergunta por completo. Ele não reescreve nem responde a pergunta do
usuário: produz até N consultas independentes, que o WebResearchAgent dispara
antes de o agente principal começar.

Espelha o padrão do endpoint clássico (``_extract_doc_search_brief``): com docs, a
query fica ciente do conteúdo (previews); sem docs, sai só da pergunta.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from typing import Any

from sei_ia.services.llm_models.get_model import get_model

logger = logging.getLogger(__name__)

_PROMPT = """\
Você é o planejador de pesquisa web de um assistente. Identifique os pontos
EXTERNOS que precisam ser verificados para responder a pergunta do usuário de
forma completa. Produza consultas independentes para esses pontos.

Não responda à pergunta e NÃO a reescreva/parafraseie como uma única consulta.
Decomponha-a em no máximo {max_queries} perguntas factuais de pesquisa. Cada consulta:
- cobre um fato, entidade ou comparação indispensável;
- preserva entidade, período/data, local, número, limite e métrica relevantes;
- é curta, objetiva e utilizável diretamente no SearXNG;
- não inclui persona, saudação, instruções de formatação nem texto de resposta;
- não inventa uma interpretação se o pedido for genuinamente ambíguo: mantenha o
  termo e seus qualificadores originais.

Evite consultas redundantes. Se bastar pesquisar um único ponto, retorne apenas um.
Data de hoje: {hoje}. Inclua referência temporal coerente: dado anual -> ano;
mensal -> mês e ano; diário -> dia, mês e ano; "atual"/"agora"/"essa semana" ->
dia, mês e ano de hoje; se não houver granularidade, inclua ao menos o ano.
- NÃO use operador `site:`, aspas, nem prefixos ("query:"). Só os termos.
- Responda SOMENTE JSON válido: {{"queries": ["consulta 1", "consulta 2"]}}.{contexto}

Pergunta do usuário:
{pergunta}

JSON:"""


async def plan_speculative_web_queries(
    question: str,
    doc_hint: str = "",
    *,
    model: Any = None,
    today: _dt.date | None = None,
    max_queries: int = 3,
    callbacks: list[Any] | None = None,
) -> list[str]:
    """Planeja até N buscas; em falha, não dispara busca especulativa."""
    today = today or _dt.date.today()
    max_queries = max(1, max_queries)
    llm = model or get_model(agent_tag="busca_web")
    contexto = (
        "\n- Foque a busca no que a pergunta pede sobre este contexto de documentos "
        f"(não repita o texto):\n{doc_hint[:1200]}"
        if doc_hint.strip()
        else ""
    )
    prompt = _PROMPT.format(
        hoje=today.isoformat(),
        contexto=contexto,
        max_queries=max_queries,
        pergunta=question.strip()[:2000],
    )
    try:
        if callbacks:
            resp = await llm.ainvoke(prompt, config={"callbacks": callbacks})
        else:
            resp = await llm.ainvoke(prompt)
        raw = (getattr(resp, "content", "") or "").strip()
        parsed = json.loads(raw)
        raw_queries = parsed.get("queries", []) if isinstance(parsed, dict) else []
        queries: list[str] = []
        seen: set[str] = set()
        for value in raw_queries:
            query = str(value).strip().strip('"').strip()
            if query and query not in seen:
                queries.append(query[:200])
                seen.add(query)
            if len(queries) >= max_queries:
                break
        if queries:
            return queries
    except Exception:
        logger.exception("[web_speculative] falha ao planejar buscas")
    return []


def build_doc_hint(resolved: Any, *, max_docs: int = 3, per_doc: int = 400) -> str:
    """Junta os previews dos primeiros docs do resolve para a query ciente de docs."""
    meta = getattr(resolved, "meta", None)
    docs = getattr(meta, "documentos", None) or {}
    previews = [
        (d.get("preview") or "")[:per_doc]
        for d in list(docs.values())[:max_docs]
        if d.get("preview")
    ]
    return "\n".join(previews)
