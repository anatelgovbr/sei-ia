"""Gate nano para transformar páginas web já coletadas em evidência auditável.

O gate não pesquisa, não decide recomendação e não declara fatos sem trecho e URL.
Ele reduz o material entregue ao modelo principal e aponta, no máximo, uma lacuna
que justifique mais uma busca dirigida.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

_MAX_QUERY_CHARS = 200
_MAX_FIELD_CHARS = 500
_MAX_LEDGER_ROWS = 24
_MAX_GAP_ROWS = 12

_PROMPT = """\
Você confere evidências para uma pesquisa web. Não pesquise e não responda ao
usuário. Trabalhe SOMENTE com os trechos e URLs recebidos.

Pergunta original:
{question}

Trechos de páginas já coletadas:
{evidence}

Monte uma matriz de evidências factual. Cada item de `ledger` precisa ter:
`entity`, `criterion`, `value`, `url` e `evidence`. Só inclua um item quando o
trecho e a URL sustentarem explicitamente o valor. Não converta unidade implícita,
não presuma que ausência de dado comprova um critério e não invente entidades.

Em `gaps`, registre os critérios necessários que continuam sem prova explícita:
`entity`, `criterion`, `reason`.

Limites: no máximo 24 itens em `ledger`, 12 em `gaps` e 500 caracteres por campo.

Use `next_query` apenas se houver lacuna e UMA busca dirigida puder resolvê-la.
Caso contrário, use null. A consulta deve ter no máximo 200 caracteres, sem `site:`,
aspas, URL ou texto de resposta.

Responda SOMENTE JSON válido:
{{"ledger":[{{"entity":"...","criterion":"...","value":"...","url":"https://...","evidence":"..."}}],"gaps":[{{"entity":"...","criterion":"...","reason":"..."}}],"next_query":null}}
"""


@dataclass(frozen=True)
class EvidenceGateVerdict:
    """Resultado validado do nano, pronto para restringir a busca do principal."""

    ledger: tuple[dict[str, str], ...]
    gaps: tuple[dict[str, str], ...]
    next_query: str | None

    def render_for_agent(self) -> str:
        """Resumo curto para o principal, sem reenviar as páginas brutas."""
        payload = {
            "ledger": list(self.ledger),
            "gaps": list(self.gaps),
            "next_query": self.next_query,
        }
        return (
            "MATRIZ DE EVIDÊNCIAS DA BUSCA INICIAL (gerada a partir das páginas "
            "salvas):\n"
            f"{json.dumps(payload, ensure_ascii=False)}\n\n"
            "Use esta matriz como ponto de partida. Só inclua uma entidade quando "
            "todos os critérios necessários tiverem URL e trecho explícitos. As "
            "páginas completas continuam em web/. "
            + (
                "Há UMA busca dirigida permitida para a lacuna indicada em "
                f"next_query: {self.next_query!r}. Depois, sintetize."
                if self.next_query
                else "Não há busca adicional permitida. Sintetize e declare lacunas."
            )
        )


def _clean_text(value: Any, *, max_chars: int = _MAX_FIELD_CHARS) -> str:
    return " ".join(str(value or "").split())[:max_chars]


def _clean_rows(
    value: Any, fields: tuple[str, ...], *, max_rows: int
) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list):
        return ()
    rows: list[dict[str, str]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        row = {field: _clean_text(raw.get(field)) for field in fields}
        if all(row.values()):
            rows.append(row)
        if len(rows) >= max_rows:
            break
    return tuple(rows)


def parse_evidence_gate_verdict(raw: str) -> EvidenceGateVerdict:
    """Valida o JSON do nano e remove sugestão de busca que não tem lacuna."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise TypeError("gate de evidência não retornou objeto JSON")
    ledger = _clean_rows(
        parsed.get("ledger"),
        ("entity", "criterion", "value", "url", "evidence"),
        max_rows=_MAX_LEDGER_ROWS,
    )
    gaps = _clean_rows(
        parsed.get("gaps"),
        ("entity", "criterion", "reason"),
        max_rows=_MAX_GAP_ROWS,
    )
    next_query = _clean_text(parsed.get("next_query"), max_chars=_MAX_QUERY_CHARS)
    if not gaps or not next_query or "http" in next_query.lower():
        next_query = None
    return EvidenceGateVerdict(ledger=ledger, gaps=gaps, next_query=next_query)


def _head_tail(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    marker = "\n[...trecho reduzido...]\n"
    if budget <= len(marker) + 2:
        return text[:budget]
    content_budget = budget - len(marker)
    head = int(content_budget * 0.75)
    tail = content_budget - head
    return f"{text[:head]}{marker}{text[-tail:]}"


def compact_evidence_input(batches: list[str], *, max_chars: int) -> str:
    """Distribui o orçamento entre lotes para o trace não carregar páginas inteiras."""
    nonempty = [batch for batch in batches if batch]
    if not nonempty or max_chars < 1:
        return ""
    separators = 2 * (len(nonempty) - 1)
    per_batch = max(1, (max_chars - separators) // len(nonempty))
    return "\n\n".join(_head_tail(batch, per_batch) for batch in nonempty)


async def assess_web_evidence(
    question: str,
    batches: list[str],
    *,
    model: Any,
    callbacks: Any = None,
    max_input_chars: int = 24000,
) -> EvidenceGateVerdict:
    """Chama o nano uma vez, com entrada limitada e callbacks do request pai."""
    evidence = compact_evidence_input(batches, max_chars=max_input_chars)
    if not evidence:
        raise ValueError("gate de evidência recebeu páginas vazias")
    prompt = _PROMPT.format(question=question.strip()[:2000], evidence=evidence)
    config: dict[str, Any] = {
        "run_name": "session_web_evidence_gate",
        "metadata": {"stage": "web_evidence_gate", "input_chars": len(evidence)},
    }
    if callbacks is not None:
        config["callbacks"] = callbacks
    response = await model.ainvoke(prompt, config=config)
    return parse_evidence_gate_verdict((getattr(response, "content", "") or "").strip())
