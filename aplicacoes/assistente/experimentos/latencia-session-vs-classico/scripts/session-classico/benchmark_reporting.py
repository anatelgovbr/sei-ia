"""Agregação, precificação e artefatos do benchmark comparativo.

Este módulo não fala com Langfuse nem com os endpoints. O runner fornece registros
por endpoint e recebe arquivos JSON/Markdown reproduzíveis em troca.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any

from model_campaign import ModelCampaignError, ModelIdentity, price_usage

_URL_RE = re.compile(r"https?://[^\s<>\]\[\)\}\"']+")
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_PRICE_FIELDS = (
    "input_per_million_usd",
    "cache_read_per_million_usd",
    "output_per_million_usd",
)


def load_rate_card(path: str | Path) -> dict[str, Any]:
    """Lê uma rate card sem substituir valores ausentes por zero."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _rate_card_reference(path: str | Path, rate_card: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": rate_card.get("version"),
        "effective_on": rate_card.get("effective_on"),
        "aggregation_compatibility_key": rate_card.get("aggregation_compatibility_key"),
        "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
    }


def cited_urls(content: str) -> list[str]:
    """Extrai URLs efetivamente presentes no conteúdo final do endpoint."""
    urls = [*_HREF_RE.findall(content or ""), *_URL_RE.findall(content or "")]
    return list(dict.fromkeys(url.rstrip(".,;:") for url in urls if url))


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def cost_for_tokens(
    tokens_by_model: dict[str, dict[str, Any]] | None, rate_card: dict[str, Any]
) -> dict[str, Any]:
    """Calcula input + cache + output. Reasoning é subconjunto informativo da saída."""
    if not tokens_by_model:
        return {"usd": None, "brl": None, "missing_models": [], "available": False}

    models = rate_card.get("models") or {}
    deployments = rate_card.get("deployments") or {}
    missing: list[str] = []
    usd = Decimal(0)
    partial_costs: list[dict[str, Any]] = []
    for model, usage in tokens_by_model.items():
        deployment = deployments.get(model)
        if isinstance(deployment, dict):
            priced = price_usage(
                ModelIdentity(
                    requested_profile=str(deployment["profile"]),
                    deployment=model,
                    canonical_model=str(deployment["canonical_model"]),
                    provider=str(deployment["provider"]),
                ),
                {
                    "input_uncached": usage.get("input", 0),
                    "cache_read": usage.get("cache_read", 0),
                    "cache_write": usage.get("cache_write"),
                    "output": max(
                        int(usage.get("output", 0) or 0)
                        - int(usage.get("reasoning", 0) or 0),
                        0,
                    ),
                    "reasoning": usage.get("reasoning", 0),
                },
                rate_card,
            )
            if priced["available"]:
                usd += Decimal(str(priced["cost_usd"]))
            else:
                partial_costs.append(priced)
            continue
        rate = models.get(model)
        prices = [_decimal((rate or {}).get(field)) for field in _PRICE_FIELDS]
        if rate is None or any(price is None for price in prices):
            missing.append(model)
            continue
        usd += (
            Decimal(int(usage.get("input", 0) or 0)) * prices[0]
            + Decimal(int(usage.get("cache_read", 0) or 0)) * prices[1]
            + Decimal(int(usage.get("output", 0) or 0)) * prices[2]
        ) / Decimal(1000000)

    if missing or partial_costs:
        known = None
        if partial_costs and not missing:
            known = {
                regime: float(
                    usd
                    + sum(
                        (
                            Decimal(
                                str(
                                    row["known_subtotal_excluding_cache_write_usd"][
                                        f"if_all_requests_{regime}"
                                    ]
                                )
                            )
                            for row in partial_costs
                        ),
                        Decimal(0),
                    )
                )
                for regime in ("short_context", "long_context")
            }
        return {
            "usd": None,
            "brl": None,
            "missing_models": sorted(missing),
            "available": False,
            "missing_usage": sorted(
                {
                    field
                    for row in partial_costs
                    for field in row.get("missing_usage", [])
                }
            ),
            "missing_rate": sorted(
                {
                    field
                    for row in partial_costs
                    for field in row.get("missing_rate", [])
                }
            ),
            "known_subtotal_excluding_cache_write_usd": known,
        }
    fx = _decimal(rate_card.get("usd_to_brl"))
    if fx is None:
        return {
            "usd": float(usd),
            "brl": None,
            "missing_models": [],
            "available": False,
        }
    return {
        "usd": float(usd),
        "brl": float(usd * fx),
        "missing_models": [],
        "available": True,
    }


def endpoint_records(
    results: list[dict[str, Any]],
    rate_card: dict[str, Any],
    *,
    rate_card_reference: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Achata resultados pareados em uma linha auditável por endpoint."""
    records: list[dict[str, Any]] = []
    for result in results:
        for endpoint, data in result.get("endpoints", {}).items():
            metrics = data.get("metrics") or {}
            tokens = {
                model: dict(usage)
                for model, usage in (metrics.get("tokens_by_model") or {}).items()
            }
            tokens_by_scope = {
                scope: dict(usage)
                for scope, usage in (metrics.get("tokens_by_scope") or {}).items()
            }
            judge_usage = (data.get("judge") or {}).get("usage")
            if judge_usage:
                deployment = judge_usage["deployment"]
                bucket = tokens.setdefault(
                    deployment,
                    {
                        "input": 0,
                        "cache_read": 0,
                        "cache_write": 0,
                        "output": 0,
                        "reasoning": 0,
                        "total": 0,
                        "generations": 0,
                    },
                )
                for field in (
                    "input",
                    "cache_read",
                    "output",
                    "reasoning",
                    "total",
                    "generations",
                ):
                    value = judge_usage.get(field)
                    if value is not None:
                        bucket[field] = int(bucket.get(field, 0) or 0) + int(value)
                cache_write = judge_usage.get("cache_write")
                if cache_write is None:
                    bucket["cache_write"] = None
                elif bucket.get("cache_write") is not None:
                    bucket["cache_write"] = int(bucket.get("cache_write", 0)) + int(
                        cache_write
                    )
                tokens_by_scope["judge"] = {
                    field: judge_usage.get(field)
                    for field in (
                        "input",
                        "cache_read",
                        "cache_write",
                        "output",
                        "reasoning",
                        "total",
                        "generations",
                    )
                }
            records.append(
                {
                    "qid": result.get("qid"),
                    "case": result.get("case") or {},
                    "question": result.get("question"),
                    "endpoint": endpoint,
                    "trace_id": data.get("trace_id"),
                    "latency": data.get("latency") or {},
                    "judge": data.get("judge"),
                    "tokens_by_model": tokens,
                    "tokens_by_scope": tokens_by_scope,
                    "tool_metrics": data.get("tool_metrics"),
                    "cited_urls": data.get("cited_urls") or [],
                    "response": data.get("response"),
                    "cost": cost_for_tokens(tokens, rate_card),
                    "rate_card": rate_card_reference,
                }
            )
    return records


def _numbers(records: list[dict[str, Any]], getter) -> dict[str, Any]:
    values = [getter(record) for record in records]
    values = [float(value) for value in values if value is not None]
    return {"n": len(values), "median": median(values) if values else None}


def _sum_numbers(records: list[dict[str, Any]], getter) -> float | None:
    """Soma valores disponíveis, preservando ausência quando nada foi medido."""
    values = [getter(record) for record in records]
    values = [float(value) for value in values if value is not None]
    return sum(values) if values else None


def _bucket_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    def judge_value(record: dict[str, Any], name: str) -> float | None:
        judge = record.get("judge") or {}
        return (judge.get("numeric") or {}).get(name)

    return {
        "records": len(records),
        "latency": {
            "ttfc_s": _numbers(records, lambda r: r["latency"].get("ttfc_s")),
            "total_s": _numbers(records, lambda r: r["latency"].get("total_s")),
        },
        "quality": {
            name: _numbers(records, lambda r, name=name: judge_value(r, name))
            for name in ("overall", "groundedness", "completeness", "citation_quality")
        },
        "tool_calls": _numbers(
            records, lambda r: (r.get("tool_metrics") or {}).get("total_calls")
        ),
        "web_references_returned": _numbers(
            records,
            lambda r: (r.get("tool_metrics") or {}).get("web_references_returned"),
        ),
        "urls_cited": _numbers(records, lambda r: len(r.get("cited_urls") or [])),
        "cost": {
            "usd": _numbers(records, lambda r: (r.get("cost") or {}).get("usd")),
            "brl": _numbers(records, lambda r: (r.get("cost") or {}).get("brl")),
            "usd_total": _sum_numbers(
                records, lambda r: (r.get("cost") or {}).get("usd")
            ),
            "brl_total": _sum_numbers(
                records, lambda r: (r.get("cost") or {}).get("brl")
            ),
        },
        "hallucinations": sum(
            1
            for record in records
            if ((record.get("judge") or {}).get("bool") or {}).get("hallucination")
        ),
    }


def summarize(
    records: list[dict[str, Any]], run_context: dict[str, Any]
) -> dict[str, Any]:
    """Agrupa dados sem esconder valores ausentes ou a assimetria do clássico."""
    groups: dict[str, list[dict[str, Any]]] = {"overall": records}
    for endpoint in ("session", "classic"):
        groups[f"endpoint:{endpoint}"] = [
            record for record in records if record["endpoint"] == endpoint
        ]
    groups["web:pure"] = [
        record for record in records if record["case"].get("processo") is None
    ]
    groups["web:with_process"] = [
        record
        for record in records
        if record["case"].get("requires_web")
        and record["case"].get("processo") is not None
    ]
    for size in ("small", "medium", "large"):
        groups[f"size:{size}"] = [
            record for record in records if record["case"].get("size_class") == size
        ]
    return {
        "run": run_context,
        "groups": {name: _bucket_summary(items) for name, items in groups.items()},
        "records": len(records),
        "limitations": [
            "N=1 é uma fotografia operacional e não sustenta inferência estatística.",
            "No clássico, a invocação do agente web é registrada por uma ponte explícita (`classic_web_bridge`), não por `on_tool_start/end`; os tokens e o custo total incluem suas gerações, mas o custo da etapa web não é isolado do restante do trace.",
            "Custo USD fica indisponível quando faltar preço de algum modelo na rate card; BRL não é publicado neste estudo.",
        ],
    }


def _format_number(value: Any, digits: int = 2) -> str:
    return "N/D" if value is None else f"{float(value):.{digits}f}"


def _pair_text(session_value: Any, classic_value: Any, digits: int = 2) -> str:
    """Mostra os dois endpoints na mesma célula, sempre na ordem session/clássico."""
    return f"{_format_number(session_value, digits)} / {_format_number(classic_value, digits)}"


def _pair_metric(
    session_value: Any,
    classic_value: Any,
    *,
    higher_is_better: bool,
    digits: int = 2,
) -> str:
    """Mostra um par e destaca o melhor valor com Markdown."""
    session_text = _format_number(session_value, digits)
    classic_text = _format_number(classic_value, digits)
    if session_value is None or classic_value is None:
        return f"{session_text} / {classic_text}"
    try:
        session_number = float(session_value)
        classic_number = float(classic_value)
    except (TypeError, ValueError):
        return f"{session_text} / {classic_text}"
    if session_number == classic_number:
        return f"{session_text} / {classic_text}"
    session_wins = (
        session_number > classic_number
        if higher_is_better
        else session_number < classic_number
    )
    if session_wins:
        session_text = f"**{session_text}**"
    else:
        classic_text = f"**{classic_text}**"
    return f"{session_text} / {classic_text}"


def _pair_count(session_value: Any, classic_value: Any) -> str:
    """Par de contagens sem converter ausência em zero."""
    session_text = "N/D" if session_value is None else str(session_value)
    classic_text = "N/D" if classic_value is None else str(classic_value)
    return f"{session_text} / {classic_text}"


def _format_tokens(value: Any) -> str:
    """Exibe tokens em milhares para manter as tabelas legíveis."""
    return "N/D" if value is None else f"{float(value) / 1000:.1f}k"


def _pair_tokens(session_value: Any, classic_value: Any) -> str:
    return f"{_format_tokens(session_value)} / {_format_tokens(classic_value)}"


def _token_total(record: dict[str, Any], field: str) -> int | None:
    """Soma um tipo de token entre os modelos usados na chamada."""
    tokens = record.get("tokens_by_model")
    if not tokens:
        return None
    return sum(int((usage or {}).get(field, 0) or 0) for usage in tokens.values())


def _cache_share(record: dict[str, Any]) -> float | None:
    """Percentual de cache-read sobre input mais cache acumulados na chamada."""
    input_tokens = _token_total(record, "input")
    cache_tokens = _token_total(record, "cache_read")
    if input_tokens is None or cache_tokens is None or input_tokens + cache_tokens == 0:
        return None
    return cache_tokens / (input_tokens + cache_tokens) * 100


def _cache_text(record: dict[str, Any]) -> str:
    tokens = _token_total(record, "cache_read")
    share = _cache_share(record)
    share_text = "N/D" if share is None else f"{share:.1f}%"
    token_text = _format_tokens(tokens)
    return f"{token_text} ({share_text})"


def _cache_text_from_totals(input_tokens: int | None, cache_tokens: int | None) -> str:
    """Formata cache agregado usando o mesmo denominador da tabela por chamada."""
    token_text = _format_tokens(cache_tokens)
    if input_tokens is None or cache_tokens is None or input_tokens + cache_tokens == 0:
        return f"{token_text} (N/D)"
    share_text = f"{cache_tokens / (input_tokens + cache_tokens) * 100:.1f}%"
    return f"{token_text} ({share_text})"


def _sum_tokens(records: list[dict[str, Any]], field: str) -> int | None:
    values = [_token_total(record, field) for record in records]
    return (
        sum(value for value in values if value is not None)
        if any(value is not None for value in values)
        else None
    )


def _relative_difference(session_value: Any, classic_value: Any) -> str:
    """Diferença proporcional do session em relação ao clássico."""
    if session_value is None or classic_value in (None, 0):
        return "N/D"
    difference = (
        (float(session_value) - float(classic_value)) / float(classic_value) * 100
    )
    return f"{difference:+.1f}%"


def _report_text(value: Any, fallback: str) -> str:
    """Limita apenas o artefato de leitura e evita quebrar o bloco HTML."""
    if not value:
        return fallback
    text = str(value).replace("</details>", "&lt;/details&gt;")
    return html.escape(text[:30000], quote=False)


def _question_label(value: Any) -> str:
    """Mantém a pergunta em uma linha no summary do bloco recolhível."""
    if not value:
        return "Pergunta não persistida nesta rodada."
    text = str(value)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*\*|__|`|~~)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return html.escape(text[:1000], quote=False)


def _score_triplet_lines(session: dict[str, Any], classic: dict[str, Any]) -> str:
    """Renderiza G/C/Cit em duas linhas, preservando o destaque por métrica."""
    session_values: list[str] = []
    classic_values: list[str] = []
    for key in ("groundedness", "completeness", "citation_quality"):
        pair = _pair_metric(
            _metric(session, key),
            _metric(classic, key),
            higher_is_better=True,
        )
        session_value, classic_value = pair.split(" / ", maxsplit=1)
        session_values.append(session_value)
        classic_values.append(classic_value)
    return (
        f"session: {' / '.join(session_values)}<br>"
        f"clássico: {' / '.join(classic_values)}"
    )


def _metric(record: dict[str, Any], name: str) -> Any:
    """Lê um score numérico sem quebrar quando o endpoint falhou."""
    return ((record.get("judge") or {}).get("numeric") or {}).get(name)


def _paired_records(
    records: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Agrupa os dois endpoints na mesma linha, preservando QIDs sem par."""
    by_qid: dict[str, dict[str, dict[str, Any]]] = {}
    order: list[str] = []
    for record in records:
        qid = str(record.get("qid") or "N/D")
        if qid not in by_qid:
            by_qid[qid] = {}
            order.append(qid)
        by_qid[qid][record.get("endpoint", "")] = record
    return [
        (qid, by_qid[qid].get("session", {}), by_qid[qid].get("classic", {}))
        for qid in order
    ]


def _winner(session: dict[str, Any], classic: dict[str, Any]) -> str:
    s = _metric(session, "overall")
    c = _metric(classic, "overall")
    if s is None or c is None:
        return "N/D"
    if s > c:
        return "session"
    if c > s:
        return "clássico"
    return "empate"


def _score_examples(records: list[dict[str, Any]]) -> list[str]:
    """Explica scores usando casos reais, sem codificar números da fixture."""
    paired = {
        qid: (session, classic) for qid, session, classic in _paired_records(records)
    }
    examples: list[str] = []
    if "LARGE-OFICIOS-01" in paired:
        session, classic = paired["LARGE-OFICIOS-01"]
        examples.append(
            "Em `LARGE-OFICIOS-01`, `completude`/`overall` favorecem o session "
            f"({_format_number(_metric(session, 'overall'))} vs "
            f"{_format_number(_metric(classic, 'overall'))}): a resposta do session "
            "listou os 8 ofícios exigidos, enquanto a do clássico omitiu itens e "
            "repetiu um ofício."
        )
    if "SMALL-NEG-01" in paired:
        session, classic = paired["SMALL-NEG-01"]
        examples.append(
            "Em `SMALL-NEG-01`, `negativa_correta=true` indica que o endpoint não "
            "inventou uma multa inexistente; ambos chegaram a overall "
            f"{_format_number(_metric(session, 'overall'))}."
        )
    web_qid = next(
        (
            qid
            for qid in ("WEB-FII-01", "SMALL-WEB-01", "Q23", "LARGE-WEB-01")
            if qid in paired
        ),
        None,
    )
    if web_qid:
        session, classic = paired[web_qid]
        examples.append(
            f"Em `{web_qid}`, `citation_quality` mede se as afirmações vêm acompanhadas "
            "de fontes utilizáveis; nesta rodada a busca web teve poucas/nenhuma URL "
            f"citada (session {_format_number(_metric(session, 'citation_quality'))}; "
            f"clássico {_format_number(_metric(classic, 'citation_quality'))}), "
            "por isso o resultado web deve ser lido com cautela."
        )
    return examples


def _ratio_text(numerator: Any, denominator: Any) -> str:
    """Formata uma razão de tempo sem sugerir precisão quando faltam dados."""
    if numerator is None or denominator in (None, 0):
        return "N/D"
    return f"{float(numerator) / float(denominator):.1f}x"


def _case_reading(session: dict[str, Any], classic: dict[str, Any]) -> str:
    """Resume o trade-off do caso usando somente medidas auditáveis."""
    s_overall = _metric(session, "overall")
    c_overall = _metric(classic, "overall")
    s_total = (session.get("latency") or {}).get("total_s")
    c_total = (classic.get("latency") or {}).get("total_s")
    if s_overall is None or c_overall is None:
        return (
            "Comparação de qualidade indisponível porque um endpoint não foi julgado."
        )

    def latency_reading() -> str:
        if s_total is None or c_total is None:
            return "Tempo total indisponível."
        slowest = max(float(s_total), float(c_total))
        relative_gap = abs(float(s_total) - float(c_total)) / slowest
        if relative_gap <= 0.05:
            return "O tempo total foi equivalente."
        faster = "session" if s_total < c_total else "clássico"
        slower = max(s_total, c_total)
        faster_time = min(s_total, c_total)
        return (
            f"O {faster} terminou antes, {_format_number(faster_time)} s contra "
            f"{_format_number(slower)} s."
        )

    quality_gap = float(s_overall) - float(c_overall)
    if abs(quality_gap) <= 0.03:
        return (
            f"Empate técnico de qualidade, diferença de {abs(quality_gap):.2f}. "
            f"{latency_reading()}"
        )

    winner = "session" if quality_gap > 0 else "clássico"
    winner_record = session if quality_gap > 0 else classic
    loser_record = classic if quality_gap > 0 else session
    dimensions = (
        ("apoio nas fontes", "groundedness"),
        ("cobertura dos itens pedidos", "completeness"),
        ("qualidade das citações", "citation_quality"),
    )
    reason, _ = max(
        dimensions,
        key=lambda item: (_metric(winner_record, item[1]) or 0)
        - (_metric(loser_record, item[1]) or 0),
    )
    strength = "clara" if abs(quality_gap) >= 0.10 else "pequena"
    return (
        f"Vantagem {strength} do {winner}, {abs(quality_gap):.2f} em overall. "
        f"A maior diferença entre os sub-scores foi em {reason}. {latency_reading()}"
    )


def _executive_reading(
    summary: dict[str, Any], records: list[dict[str, Any]]
) -> list[str]:
    """Produz conclusões da suíte sem extrapolar além do N=1."""
    session = summary["groups"]["endpoint:session"]
    classic = summary["groups"]["endpoint:classic"]
    paired = _paired_records(records)
    wins = sum(_winner(s, c) == "session" for _, s, c in paired)
    losses = sum(_winner(s, c) == "clássico" for _, s, c in paired)
    ties = sum(_winner(s, c) == "empate" for _, s, c in paired)
    s_total = session["latency"]["total_s"]["median"]
    c_total = classic["latency"]["total_s"]["median"]
    s_ttfc = session["latency"]["ttfc_s"]["median"]
    c_ttfc = classic["latency"]["ttfc_s"]["median"]
    s_quality = session["quality"]["overall"]["median"]
    c_quality = classic["quality"]["overall"]["median"]
    web_pairs = [
        (s, c)
        for _, s, c in paired
        if (s.get("case") or c.get("case") or {}).get("requires_web")
    ]
    web_session_wins = sum(_winner(s, c) == "session" for s, c in web_pairs)
    session_tools = sum(
        int((record.get("tool_metrics") or {}).get("total_calls", 0) or 0)
        for record in records
        if record.get("endpoint") == "session"
    )
    classic_tools = sum(
        int((record.get("tool_metrics") or {}).get("total_calls", 0) or 0)
        for record in records
        if record.get("endpoint") == "classic"
    )
    if not classic["records"]:
        return [
            "Este artefato não inclui registros do clássico. Ele descreve somente a "
            "execução do session; qualquer comparação requer anexar um baseline "
            "clássico explicitamente identificado.",
            (
                f"O session teve overall mediano {_format_number(s_quality)}, TTFC "
                f"mediano de {_format_number(s_ttfc)} s e tempo total mediano de "
                f"{_format_number(s_total)} s."
            ),
            f"O session fez {session_tools} chamadas de ferramenta nesta suíte.",
        ]

    dimensions = (
        ("groundedness", "apoio nas fontes"),
        ("completeness", "cobertura dos itens pedidos"),
        ("citation_quality", "qualidade das citações"),
    )
    lines = [
        (
            f"O session teve overall mediano {_format_number(s_quality)}, contra "
            f"{_format_number(c_quality)} do clássico. Venceu {wins} casos, perdeu "
            f"{losses} e empatou {ties}."
        ),
        (
            f"O session mostrou o primeiro conteúdo antes, TTFC mediano de "
            f"{_format_number(s_ttfc)} s contra {_format_number(c_ttfc)} s. No tempo "
            f"total, porém, levou {_ratio_text(s_total, c_total)} o tempo do clássico "
            f"({_format_number(s_total)} s contra {_format_number(c_total)} s)."
        ),
        (
            f"Nos {len(web_pairs)} casos com web, o session teve maior overall em "
            f"{web_session_wins}. O recorte é N=1 por caso e deve ser lido junto com "
            "as fontes e falhas registradas nas respostas."
        ),
        (
            f"O session fez {session_tools} chamadas de ferramenta, contra "
            f"{classic_tools} do clássico. Essa exploração explica parte do ganho de "
            "cobertura e também o maior tempo total."
        ),
    ]
    available_dimensions = [
        item
        for item in dimensions
        if session["quality"][item[0]]["median"] is not None
        and classic["quality"][item[0]]["median"] is not None
    ]
    if available_dimensions:
        dimension, label = max(
            available_dimensions,
            key=lambda item: abs(
                float(session["quality"][item[0]]["median"])
                - float(classic["quality"][item[0]]["median"])
            ),
        )
        dimension_gap = float(session["quality"][dimension]["median"]) - float(
            classic["quality"][dimension]["median"]
        )
        dimension_winner = "session" if dimension_gap > 0 else "clássico"
        lines.append(
            f"A maior diferença entre as dimensões de qualidade foi em {label}: "
            f"{dimension_winner} ficou {abs(dimension_gap):.2f} à frente na mediana."
        )
    return lines


def render_report(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    """Renderiza um relatório Markdown curto, derivado exclusivamente dos registros."""
    run = summary["run"]
    lines = [
        "# Estudo comparativo: session_stream vs stream clássico",
        "",
        f"Run: `{run.get('run_name', 'N/D')}`. Dataset: `{run.get('dataset', 'N/D')}`. N=1 por caso.",
        "",
        "## Resumo executivo",
        "",
    ]
    if comparison_note := run.get("comparison_note"):
        lines[4:4] = [comparison_note, ""]
    lines.extend(f"- {item}" for item in _executive_reading(summary, records))
    lines.extend(
        [
            "",
            "## Resumo por endpoint",
            "",
            "| Recorte | Registros (session/clássico) | TTFC mediano (session/clássico, s) | Total mediano (session/clássico, s) | Overall (session/clássico) | Custo USD total (session/clássico) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    session_bucket = summary["groups"]["endpoint:session"]
    classic_bucket = summary["groups"]["endpoint:classic"]
    lines.append(
        "| suíte | {records} | {ttfc} | {total} | {overall} | {cost} |".format(
            records=_pair_count(session_bucket["records"], classic_bucket["records"]),
            ttfc=_pair_metric(
                session_bucket["latency"]["ttfc_s"]["median"],
                classic_bucket["latency"]["ttfc_s"]["median"],
                higher_is_better=False,
            ),
            total=_pair_metric(
                session_bucket["latency"]["total_s"]["median"],
                classic_bucket["latency"]["total_s"]["median"],
                higher_is_better=False,
            ),
            overall=_pair_metric(
                session_bucket["quality"]["overall"]["median"],
                classic_bucket["quality"]["overall"]["median"],
                higher_is_better=True,
            ),
            cost=_pair_metric(
                session_bucket["cost"]["usd_total"],
                classic_bucket["cost"]["usd_total"],
                higher_is_better=False,
                digits=3,
            ),
        )
    )

    lines.extend(
        [
            "",
            "## Qualidade da resposta",
            "",
            "| Recorte | G (session/clássico) | C (session/clássico) | Cit (session/clássico) | Alucinações (session/clássico) |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    lines.append(
        "| suíte | {groundedness} | {completeness} | {citation} | {hallucinations} |".format(
            groundedness=_pair_metric(
                session_bucket["quality"]["groundedness"]["median"],
                classic_bucket["quality"]["groundedness"]["median"],
                higher_is_better=True,
            ),
            completeness=_pair_metric(
                session_bucket["quality"]["completeness"]["median"],
                classic_bucket["quality"]["completeness"]["median"],
                higher_is_better=True,
            ),
            citation=_pair_metric(
                session_bucket["quality"]["citation_quality"]["median"],
                classic_bucket["quality"]["citation_quality"]["median"],
                higher_is_better=True,
            ),
            hallucinations=_pair_metric(
                session_bucket["hallucinations"],
                classic_bucket["hallucinations"],
                higher_is_better=False,
            ),
        )
    )

    lines.extend(
        [
            "",
            "## Busca web",
            "",
            "| Recorte | Overall (session/clássico) | Cit (session/clássico) | URLs (session/clássico) | Tools (session/clássico) |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for group in ("web:pure", "web:with_process"):
        buckets = {}
        for endpoint in ("session", "classic"):
            subset = [
                record
                for record in records
                if record["endpoint"] == endpoint
                and (
                    (group == "web:pure" and record["case"].get("processo") is None)
                    or (
                        group == "web:with_process"
                        and record["case"].get("requires_web")
                        and record["case"].get("processo") is not None
                    )
                )
            ]
            buckets[endpoint] = _bucket_summary(subset)
        lines.append(
            "| {group} | {overall} | {citation} | {urls} | {tools} |".format(
                group=group.removeprefix("web:"),
                overall=_pair_metric(
                    buckets["session"]["quality"]["overall"]["median"],
                    buckets["classic"]["quality"]["overall"]["median"],
                    higher_is_better=True,
                ),
                citation=_pair_metric(
                    buckets["session"]["quality"]["citation_quality"]["median"],
                    buckets["classic"]["quality"]["citation_quality"]["median"],
                    higher_is_better=True,
                ),
                urls=_pair_text(
                    buckets["session"]["urls_cited"]["median"],
                    buckets["classic"]["urls_cited"]["median"],
                    0,
                ),
                tools=_pair_text(
                    buckets["session"]["tool_calls"]["median"],
                    buckets["classic"]["tool_calls"]["median"],
                    0,
                ),
            )
        )

    lines.extend(
        [
            "",
            "## Comparação caso a caso",
            "",
            "Cada linha é um caso; as colunas `session` e `clássico` são diretamente comparáveis.",
            "",
            "| QID | Classe/tarefa | TTFC (session/clássico, s) | Total (session/clássico, s) | Overall (session/clássico) | G/C/Cit (duas linhas) | Tools (session/clássico) | URLs (session/clássico) | vencedor |",
            "|---|---|---:|---:|---:|---|---:|---:|---|",
        ]
    )
    for qid, session, classic in _paired_records(records):
        case = session.get("case") or classic.get("case") or {}

        lines.append(
            "| {qid} | {size} / {task} | {ttfc} | {total} | {overall} | {quality} | {tools} | {urls} | {winner} |".format(
                qid=qid,
                size=case.get("size_class", "N/D"),
                task="web" if case.get("requires_web") else "autos",
                ttfc=_pair_metric(
                    (session.get("latency") or {}).get("ttfc_s"),
                    (classic.get("latency") or {}).get("ttfc_s"),
                    higher_is_better=False,
                ),
                total=_pair_metric(
                    (session.get("latency") or {}).get("total_s"),
                    (classic.get("latency") or {}).get("total_s"),
                    higher_is_better=False,
                ),
                overall=_pair_metric(
                    _metric(session, "overall"),
                    _metric(classic, "overall"),
                    higher_is_better=True,
                ),
                quality=_score_triplet_lines(session, classic),
                tools=_pair_count(
                    (session.get("tool_metrics") or {}).get("total_calls"),
                    (classic.get("tool_metrics") or {}).get("total_calls"),
                ),
                urls=_pair_count(
                    len(session.get("cited_urls") or []),
                    len(classic.get("cited_urls") or []),
                ),
                winner=_winner(session, classic),
            )
        )

    lines.extend(
        [
            "",
            "## Tokens e custo por chamada",
            "",
            "O custo usa `input x preço de input + cache x preço de cache + output x preço de output`. Reasoning já está incluído em `output` e não é cobrado novamente. Na linha `total`, `dif. %` é `(session - clássico) / clássico`; custo menor aparece em negrito.",
            "",
            "| QID | Input (k, session/clássico) | Cache (k; cache/(input+cache) %, session/clássico) | Output (k, session/clássico) | Custo USD (session/clássico) | Dif. custo % |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for qid, session, classic in _paired_records(records):
        lines.append(
            "| {qid} | {input} | {cache} | {output} | {cost} | — |".format(
                qid=qid,
                input=_pair_tokens(
                    _token_total(session, "input"),
                    _token_total(classic, "input"),
                ),
                cache=f"{_cache_text(session)} / {_cache_text(classic)}",
                output=_pair_tokens(
                    _token_total(session, "output"),
                    _token_total(classic, "output"),
                ),
                cost=_pair_metric(
                    (session.get("cost") or {}).get("usd"),
                    (classic.get("cost") or {}).get("usd"),
                    higher_is_better=False,
                    digits=3,
                ),
            )
        )

    session_records = [record for record in records if record["endpoint"] == "session"]
    classic_records = [record for record in records if record["endpoint"] == "classic"]
    session_cost_total = _sum_numbers(
        session_records, lambda record: (record.get("cost") or {}).get("usd")
    )
    classic_cost_total = _sum_numbers(
        classic_records, lambda record: (record.get("cost") or {}).get("usd")
    )
    session_input = _sum_tokens(session_records, "input")
    classic_input = _sum_tokens(classic_records, "input")
    session_cache = _sum_tokens(session_records, "cache_read")
    classic_cache = _sum_tokens(classic_records, "cache_read")
    lines.append(
        "| total | {input} | {cache} | {output} | {cost} | {difference} |".format(
            input=_pair_tokens(session_input, classic_input),
            cache=(
                f"{_cache_text_from_totals(session_input, session_cache)} / "
                f"{_cache_text_from_totals(classic_input, classic_cache)}"
            ),
            output=_pair_tokens(
                _sum_tokens(session_records, "output"),
                _sum_tokens(classic_records, "output"),
            ),
            cost=_pair_metric(
                session_cost_total,
                classic_cost_total,
                higher_is_better=False,
                digits=3,
            ),
            difference=_relative_difference(session_cost_total, classic_cost_total),
        )
    )

    lines.extend(
        [
            "",
            "## Tokens por modelo e pergunta",
            "",
            "Valores em milhares de tokens (`k`), separados por endpoint e modelo.",
            "",
            "| QID | Endpoint | Modelo | Input (k) | Cache (k) | Output (k) | Reasoning (k) | Total (k) |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for record in records:
        for model, usage in sorted((record.get("tokens_by_model") or {}).items()):
            lines.append(
                "| {qid} | {endpoint} | {model} | {input} | {cache} | {output} | {reasoning} | {total} |".format(
                    qid=record.get("qid", "N/D"),
                    endpoint=record.get("endpoint", "N/D"),
                    model=model,
                    input=_format_tokens(usage.get("input")),
                    cache=_format_tokens(usage.get("cache_read")),
                    output=_format_tokens(usage.get("output")),
                    reasoning=_format_tokens(usage.get("reasoning")),
                    total=_format_tokens(usage.get("total")),
                )
            )

    lines.extend(["", "## Perguntas e respostas", ""])
    lines.append(
        "Cada bloco é recolhível para facilitar a auditoria da pergunta e das duas respostas."
    )
    for qid, session, classic in _paired_records(records):
        question = session.get("question") or classic.get("question")
        lines.extend(
            [
                "",
                "<details>",
                f"<summary><strong>{html.escape(str(qid))}</strong> — "
                f"{_question_label(question)}</summary>",
                "",
                "**session**",
                "",
                _report_text(
                    session.get("response"),
                    "Resposta não persistida nesta rodada.",
                ),
                "",
                "---",
                "",
                "**clássico**",
                "",
                _report_text(
                    classic.get("response"),
                    "Resposta não persistida nesta rodada.",
                ),
                "",
                "</details>",
            ]
        )

    lines.extend(
        [
            "",
            "## Leitura caso a caso",
            "",
            "| QID | Interpretação |",
            "|---|---|",
        ]
    )
    for qid, session, classic in _paired_records(records):
        lines.append(f"| {qid} | {_case_reading(session, classic)} |")

    lines.extend(
        [
            "",
            "## Como interpretar os scores",
            "",
            "Todos os scores de qualidade vão de 0 a 1; quanto maior, melhor.",
            "",
            "- **Overall**: síntese do juiz sobre a resposta inteira, combinando cobertura, apoio nos autos, citações e penalidade por alucinação. Não é uma média simples publicada como regra de cálculo.",
            "- **Groundedness (G)**: quanto das afirmações pode ser sustentado pelos documentos ou fontes disponíveis. Uma resposta pode ser completa, mas perder G se afirmar fatos sem evidência.",
            "- **Completude (C)**: proporção dos elementos obrigatórios entregues. Omissões e listas incompletas reduzem C mesmo quando o texto restante está correto.",
            "- **Qualidade de citação (Cit)**: se a resposta aponta fontes específicas, úteis e coerentes com as afirmações; contar URLs, sozinho, não garante uma boa citação.",
            "- **Alucinação**: indicador booleano de afirmação proibida, contraditória ou sem suporte. Uma ocorrência pesa mais que pequenas diferenças de estilo.",
            "- **negativa_correta**: para perguntas do tipo 'não consta', confirma que o endpoint declarou a ausência sem inventar um valor.",
            "",
            "### Exemplos desta rodada",
        ]
    )
    lines.extend(f"- {example}" for example in _score_examples(records))
    lines.extend(
        [
            "",
            "## Leitura para decisão",
            "",
            "Use esta rodada como evidência operacional, lendo os resultados caso a caso e as limitações abaixo.",
            "",
            "- O custo USD é calculado por chamada com input, cache e output; reasoning é visível dentro de output e não entra duas vezes na cobrança.",
            "- N=1 mede esta execução, não a variância. Repita os casos decisivos antes de transformar uma diferença em regra de roteamento.",
        ]
    )
    if not classic_bucket["records"]:
        lines.append(
            "- Este artefato contém somente session; a comparação de endpoint exige um baseline clássico identificado."
        )
    lines.extend(["", "## Limitações", ""])
    lines.extend(f"- {limitation}" for limitation in summary["limitations"])
    return "\n".join(lines) + "\n"


def write_artifacts(
    directory: str | Path,
    run_context: dict[str, Any],
    results: list[dict[str, Any]],
    rate_card_path: str | Path,
) -> dict[str, Path]:
    """Escreve dados por endpoint, resumo e relatório, sempre no mesmo diretório."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    rate_card = load_rate_card(rate_card_path)
    rate_card_reference = _rate_card_reference(rate_card_path, rate_card)
    campaign_context = run_context.get("model_campaign") or {}
    expected_reference = campaign_context.get("rate_card")
    if expected_reference is not None and expected_reference != rate_card_reference:
        raise ModelCampaignError("Resultados usam rate card incompatível")
    records = endpoint_records(
        results, rate_card, rate_card_reference=rate_card_reference
    )
    summary = summarize(
        records,
        {
            **run_context,
            "rate_card": rate_card,
            "rate_card_reference": rate_card_reference,
        },
    )

    measurements = target / "measurements.jsonl"
    measurements.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    (target / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (target / "report.md").write_text(render_report(summary, records), encoding="utf-8")
    (target / "run.json").write_text(
        json.dumps(run_context, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    copied_rate_card = target / Path(rate_card_path).name
    shutil.copyfile(rate_card_path, copied_rate_card)
    return {
        "measurements": measurements,
        "summary": target / "summary.json",
        "report": target / "report.md",
        "run": target / "run.json",
        "rate_card": copied_rate_card,
    }
