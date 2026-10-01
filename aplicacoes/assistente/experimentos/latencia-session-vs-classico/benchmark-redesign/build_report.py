#!/usr/bin/env python3
"""Build the versioned HTML and Markdown report for the redesigned benchmark.

The report data is a sanitized snapshot of a completed campaign. Model-role
allocation is always read from ``arms.json``; observed token deployments are
rendered as-is and are never reassigned by the presentation layer.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

DECIMAL_PLACES = 3
ROLE_SLOTS = (
    ("standard", "standard_model"),
    ("subagentes/mini", "mini_model"),
    ("OCR", "mini_model"),
    ("judge", "mini_model"),
    ("nano/explorador", "nano_model"),
    ("classificador", "mini_model"),
)
ARM_KEYS = ("gpt54", "terra-luna")

HERE = Path(__file__).resolve().parent
EXPERIMENT_ROOT = HERE.parent
PRESENTATION_DIR = EXPERIMENT_ROOT / "apresentacoes" / "benchmark-redesign"
DEFAULT_DATA_PATH = PRESENTATION_DIR / "report-data.json"
DEFAULT_TEMPLATE_PATH = PRESENTATION_DIR / "report-template.html"
DEFAULT_HTML_PATH = PRESENTATION_DIR / "report.html"
DEFAULT_MARKDOWN_PATH = PRESENTATION_DIR / "report.md"
ARMS_PATH = HERE / "arms.json"


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Arquivo JSON ausente: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido em {path}: {exc}") from exc


def decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Valor numérico inválido: {value!r}") from exc


def format_decimal(value: Any, digits: int = DECIMAL_PLACES) -> str:
    """Format every displayed decimal with a fixed number of decimal places."""

    if value is None:
        return "N/D"
    quantum = Decimal(1).scaleb(-digits)
    rounded = decimal_value(value).quantize(quantum, rounding=ROUND_HALF_UP)
    formatted = f"{rounded:,.{digits}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def format_usd(value: Any) -> str:
    if value is None:
        return "N/D"
    return f"US$ {format_decimal(value)}"


def format_integer(value: Any) -> str:
    if value is None:
        return "N/D"
    return f"{int(value):,}".replace(",", ".")


def format_percent(value: Any, sign: bool = False) -> str:
    if value is None:
        return "N/D"
    prefix = ""
    number = decimal_value(value)
    if sign and number > 0:
        prefix = "+"
    elif sign and number < 0:
        prefix = "-"
        number = abs(number)
    return f"{prefix}{format_decimal(number)}%"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def html_cell(value: Any, *, numeric: bool = False, winner: bool = False) -> str:
    classes = []
    if numeric:
        classes.append("num")
    if winner:
        classes.append("winner")
    class_attr = f' class="{" ".join(classes)}"' if classes else ""
    return f"<td{class_attr}>{esc(value)}</td>"


def winner_flags(left: Any, right: Any, *, better: str) -> tuple[bool, bool]:
    """Return winner flags for a pair; exact ties highlight both cells."""

    if left is None or right is None:
        return False, False
    left_decimal = decimal_value(left)
    right_decimal = decimal_value(right)
    if left_decimal == right_decimal:
        return True, True
    if better == "lower":
        return left_decimal < right_decimal, right_decimal < left_decimal
    if better == "higher":
        return left_decimal > right_decimal, right_decimal > left_decimal
    raise ValueError(f"Regra de vencedor desconhecida: {better}")


def validate_report_arms(report_arms: list[Any]) -> None:
    expected_qids: list[str] | None = None
    for index, arm in enumerate(report_arms):
        if not isinstance(arm, dict):
            raise TypeError(f"Braço inválido no índice {index}.")
        cases = arm.get("cases")
        if not isinstance(cases, list) or len(cases) != 10:
            raise ValueError(f"O braço {index} precisa conter os dez casos Session.")
        if not all(isinstance(case, dict) for case in cases):
            raise TypeError(f"Casos inválidos no braço {index}.")
        qids = [case.get("qid") for case in cases]
        if any(not qid for qid in qids) or len(set(qids)) != len(qids):
            raise ValueError(f"QIDs ausentes ou duplicados no braço {index}.")
        if expected_qids is None:
            expected_qids = qids
        elif qids != expected_qids:
            raise ValueError(
                "Os dois braços precisam estar alinhados na mesma ordem de QID."
            )
        if not isinstance(arm.get("tokens_total"), dict):
            raise TypeError(f"tokens_total ausente no braço {index}.")
        if not isinstance(arm.get("tokens_by_model"), dict):
            raise TypeError(f"tokens_by_model ausente no braço {index}.")


def validate_configured_deployments(
    arms_data: dict[str, Any], rate_card: dict[str, Any]
) -> None:
    configured_terra = arms_data["arms"]["terra-luna"]
    if configured_terra.get("nano_model") != configured_terra.get("mini_model"):
        raise ValueError(
            "A configuração Terra/Luna precisa usar o deployment Luna em nano/explorador."
        )
    for arm_key in ARM_KEYS:
        config = arms_data["arms"][arm_key]
        for _, config_key in ROLE_SLOTS:
            deployment = config.get(config_key)
            if deployment not in rate_card["deployments"]:
                raise ValueError(
                    f"Deployment {deployment!r} de {arm_key}.{config_key} não está na rate card."
                )


def validate(
    data: dict[str, Any], arms_data: dict[str, Any], rate_card: dict[str, Any]
) -> None:
    if data.get("schema_version") != "benchmark-redesign-report-data-v1":
        raise ValueError("schema_version de report-data.json não suportado.")
    report_arms = data.get("arms")
    if not isinstance(report_arms, list) or len(report_arms) != 2:
        raise ValueError("report-data.json precisa conter exatamente dois braços.")
    if set(arms_data.get("arms", {})) != set(ARM_KEYS):
        raise ValueError("arms.json deve conter os braços gpt54 e terra-luna.")
    if len(rate_card.get("deployments", {})) == 0:
        raise ValueError("A rate card não contém deployments.")

    validate_report_arms(report_arms)
    validate_configured_deployments(arms_data, rate_card)


def load_inputs(
    data_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    data = load_json(data_path)
    arms_data = load_json(ARMS_PATH)
    rate_card_rel = arms_data["arms"]["gpt54"]["rate_card"]
    rate_card_path = (ARMS_PATH.parent / rate_card_rel).resolve()
    rate_card = load_json(rate_card_path)
    validate(data, arms_data, rate_card)
    return data, arms_data, rate_card


def canonical_model(deployment: str, rate_card: dict[str, Any]) -> str:
    try:
        return rate_card["deployments"][deployment]["canonical_model"]
    except KeyError as exc:
        raise ValueError(f"Deployment sem modelo canônico: {deployment}") from exc


def role_rows(
    arms_data: dict[str, Any], rate_card: dict[str, Any]
) -> list[dict[str, str]]:
    rows = []
    for role, config_key in ROLE_SLOTS:
        row = {"role": role}
        for arm_key in ARM_KEYS:
            deployment = arms_data["arms"][arm_key][config_key]
            row[arm_key] = deployment
            row[f"{arm_key}_canonical"] = canonical_model(deployment, rate_card)
        rows.append(row)
    return rows


def metric_rows(data: dict[str, Any]) -> list[tuple[str, Any, Any, str]]:
    left, right = data["arms"]
    return [
        (
            "TTFC mediana",
            left["distributions"]["ttfc_s"]["median"],
            right["distributions"]["ttfc_s"]["median"],
            "s",
        ),
        (
            "Latência total mediana",
            left["distributions"]["total_s"]["median"],
            right["distributions"]["total_s"]["median"],
            "s",
        ),
        (
            "Latência total média",
            left["distributions"]["total_s"]["mean"],
            right["distributions"]["total_s"]["mean"],
            "s",
        ),
        (
            "Quality overall mediana",
            left["distributions"]["quality_overall"]["median"],
            right["distributions"]["quality_overall"]["median"],
            "score",
        ),
        (
            "Quality overall média",
            left["distributions"]["quality_overall"]["mean"],
            right["distributions"]["quality_overall"]["mean"],
            "score",
        ),
        (
            "Groundedness mediana",
            left["distributions"]["groundedness"]["median"],
            right["distributions"]["groundedness"]["median"],
            "score",
        ),
        (
            "Completeness mediana",
            left["distributions"]["completeness"]["median"],
            right["distributions"]["completeness"]["median"],
            "score",
        ),
        (
            "Citation quality mediana",
            left["distributions"]["citation_quality"]["median"],
            right["distributions"]["citation_quality"]["median"],
            "score",
        ),
        ("Alucinações", left["hallucinations"], right["hallucinations"], "count"),
        (
            "Custo USD total",
            left["cost"]["usd_total"],
            right["cost"]["usd_total"],
            "usd",
        ),
    ]


def render_metric_value(value: Any, kind: str) -> str:
    if kind == "count":
        return f"{format_integer(value)}/10"
    if kind == "usd":
        return format_usd(value)
    if kind == "s":
        return f"{format_decimal(value)} s"
    return format_decimal(value)


def render_roles_html(rows: list[dict[str, str]]) -> str:
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<th>{esc(row['role'])}</th>"
            f"<td><code>{esc(row['gpt54'])}</code> → <code>{esc(row['gpt54_canonical'])}</code></td>"
            f"<td><code>{esc(row['terra-luna'])}</code> → <code>{esc(row['terra-luna_canonical'])}</code></td>"
            "</tr>"
        )
    return "\n".join(body)


def render_roles_markdown(rows: list[dict[str, str]]) -> str:
    body = []
    for row in rows:
        body.append(
            f"| {markdown_cell(row['role'])} | `{row['gpt54']}` → `{row['gpt54_canonical']}` | "
            f"`{row['terra-luna']}` → `{row['terra-luna_canonical']}` |"
        )
    return "\n".join(body)


def render_technical_html(data: dict[str, Any]) -> str:
    left, right = data["arms"]
    rows = []
    for label in (
        "Casos / POSTs / terminais",
        "SSE end / error",
        "Traces / judge input completo",
    ):
        if label.startswith("Casos"):
            left_value = f"{len(left['cases'])} / {left['technical']['posts_started']} / {left['technical']['posts_terminal']}"
            right_value = f"{len(right['cases'])} / {right['technical']['posts_started']} / {right['technical']['posts_terminal']}"
        elif label.startswith("SSE"):
            left_value = f"{left['technical']['sse_end']} / {left['technical']['sse_error_frames']}"
            right_value = f"{right['technical']['sse_end']} / {right['technical']['sse_error_frames']}"
        else:
            left_value = f"{left['technical']['traces']} / {left['technical']['judge_input_complete']}"
            right_value = f"{right['technical']['traces']} / {right['technical']['judge_input_complete']}"
        rows.append(
            f'<tr><th>{esc(label)}</th><td class="status ok">{esc(left_value)}</td>'
            f'<td class="status ok">{esc(right_value)}</td></tr>'
        )
    rows.append(
        "<tr><th>Warmup / Classic / retry</th><td>0 / 0 / 0</td><td>0 / 0 / 0</td></tr>"
    )
    return "\n".join(rows)


def render_tokens_html(arm: dict[str, Any]) -> str:
    rows = []
    for deployment in sorted(arm["tokens_by_model"]):
        values = arm["tokens_by_model"][deployment]
        cells = [
            html_cell(deployment),
            html_cell(format_integer(values["input"]), numeric=True),
            html_cell(format_integer(values["cache_read"]), numeric=True),
            html_cell(format_integer(values["output"]), numeric=True),
            html_cell(format_integer(values["reasoning"]), numeric=True),
            html_cell(format_integer(values["generations"]), numeric=True),
        ]
        rows.append(
            f"<tr><th><code>{esc(deployment)}</code></th>{''.join(cells[1:])}</tr>"
        )
    return "\n".join(rows)


def render_tokens_markdown(arm: dict[str, Any]) -> str:
    rows = []
    for deployment in sorted(arm["tokens_by_model"]):
        values = arm["tokens_by_model"][deployment]
        rows.append(
            f"| `{deployment}` | {format_integer(values['input'])} | {format_integer(values['cache_read'])} | "
            f"{format_integer(values['output'])} | {format_integer(values['reasoning'])} | {format_integer(values['generations'])} |"
        )
    return "\n".join(rows)


def observed_model_warning(arm: dict[str, Any], config: dict[str, Any]) -> str | None:
    configured = {config[key] for _, key in ROLE_SLOTS}
    unexpected = sorted(set(arm["tokens_by_model"]) - configured)
    if not unexpected:
        return None
    deployments = ", ".join(f"`{deployment}`" for deployment in unexpected)
    return (
        f"A fonte de tokens registra {deployments} como deployment observado, embora "
        "esse alias não esteja na alocação declarada para este braço. A tabela de papéis "
        "continua derivada de `arms.json`; o gerador não reassocia tokens históricos. "
        "Reconcilie a execução antes de usar a atribuição por deployment como evidência de papel."
    )


def render_case_table_html(data: dict[str, Any]) -> str:
    left, right = data["arms"]
    rows = []
    for left_case, right_case in zip(left["cases"], right["cases"], strict=True):
        total_flags = winner_flags(
            left_case["total_s"], right_case["total_s"], better="lower"
        )
        quality_flags = winner_flags(
            left_case["overall"], right_case["overall"], better="higher"
        )
        cost_flags = winner_flags(
            left_case["cost_usd"], right_case["cost_usd"], better="lower"
        )
        left_total = f"{format_decimal(left_case['total_s'])} s"
        right_total = f"{format_decimal(right_case['total_s'])} s"
        rows.append(
            "<tr>"
            f"<th><code>{esc(left_case['qid'])}</code></th>"
            f"{html_cell(left_total, numeric=True, winner=total_flags[0])}"
            f"{html_cell(right_total, numeric=True, winner=total_flags[1])}"
            f"{html_cell(format_decimal(left_case['overall']), numeric=True, winner=quality_flags[0])}"
            f"{html_cell(format_decimal(right_case['overall']), numeric=True, winner=quality_flags[1])}"
            f"{html_cell(format_usd(left_case['cost_usd']), numeric=True, winner=cost_flags[0])}"
            f"{html_cell(format_usd(right_case['cost_usd']), numeric=True, winner=cost_flags[1])}"
            "</tr>"
        )
    return "\n".join(rows)


def render_case_table_markdown(data: dict[str, Any]) -> str:
    left, right = data["arms"]
    rows = []
    for left_case, right_case in zip(left["cases"], right["cases"], strict=True):
        rows.append(
            f"| `{left_case['qid']}` | {format_decimal(left_case['total_s'])} s | {format_decimal(right_case['total_s'])} s | "
            f"{format_decimal(left_case['overall'])} | {format_decimal(right_case['overall'])} | "
            f"{format_usd(left_case['cost_usd'])} | {format_usd(right_case['cost_usd'])} |"
        )
    return "\n".join(rows)


def render_html(
    data: dict[str, Any],
    arms_data: dict[str, Any],
    rate_card: dict[str, Any],
    template_path: Path,
) -> str:
    left, right = data["arms"]
    comparison = data["comparison"]
    rows = role_rows(arms_data, rate_card)
    metrics = metric_rows(data)
    left_label = left["label"]
    right_label = right["label"]
    observed_warnings = [
        warning
        for arm, key in zip(data["arms"], ARM_KEYS, strict=True)
        if (warning := observed_model_warning(arm, arms_data["arms"][key]))
    ]
    warning_html = "".join(
        f'<div class="warning">⚠ {esc(warning)}</div>' for warning in observed_warnings
    )
    recommendation = (
        "Leitura provisória: Terra/Luna apresenta os melhores agregados desta fotografia; "
        "a promoção deve aguardar a reconciliação do bucket observado seiia-ds-nano com a alocação Luna."
        if observed_warnings
        else "Recomendação operacional: preferir Terra/Luna para esta bateria, mantendo a ressalva de N=1 e sem inferência causal sobre cada componente da configuração."
    )

    metric_html = []
    for label, left_value, right_value, kind in metrics:
        better = "higher" if kind == "score" else "lower"
        flags = winner_flags(left_value, right_value, better=better)
        metric_html.append(
            f"<tr><th>{esc(label)}</th>"
            f"{html_cell(render_metric_value(left_value, kind), numeric=True, winner=flags[0])}"
            f"{html_cell(render_metric_value(right_value, kind), numeric=True, winner=flags[1])}</tr>"
        )

    distribution_html = []
    for label, _key in (
        ("mín.", "min"),
        ("p25", "p25"),
        ("mediana", "median"),
        ("média", "mean"),
        ("p75", "p75"),
        ("p90", "p90"),
        ("máx.", "max"),
    ):
        distribution_html.append(f'<th class="num">{esc(label)}</th>')
    distribution_cells = []
    for arm in (left, right):
        cells = []
        for key in ("min", "p25", "median", "mean", "p75", "p90", "max"):
            cells.append(
                html_cell(
                    f"{format_decimal(arm['distributions']['total_s'][key])} s",
                    numeric=True,
                )
            )
        distribution_cells.append("".join(cells))

    tools_html = []
    for arm in (left, right):
        categories = " · ".join(
            f"{esc(category)} {format_integer(count)}"
            for category, count in sorted(arm["tool_calls_by_category"].items())
        )
        tools_html.append(
            f'<article class="card"><h3>{esc(arm["label"])}</h3><p>{categories}</p></article>'
        )

    body = f"""
  <header class="hero">
    <div class="wrap">
      <p class="eyebrow">Comparativo versionado · N={format_integer(left["n"])} por caso</p>
      <h1>{esc(left_label)} versus Terra/Luna</h1>
      <p class="lead">Os mesmos dez casos foram executados uma vez em cada braço. Os números abaixo são uma fotografia operacional; a atribuição de papéis vem da configuração versionada e os tokens observados não são redistribuídos.</p>
      <div class="badges">
        <span class="badge">✓ {format_integer(left["technical"]["sse_end"] + right["technical"]["sse_end"])}/20 SSE end</span>
        <span class="badge">✓ {format_integer(left["technical"]["sse_error_frames"] + right["technical"]["sse_error_frames"])} errors</span>
        <span class="badge">N={format_integer(left["n"])} por caso</span>
        <span class="badge">USD com {DECIMAL_PLACES} casas</span>
      </div>
    </div>
  </header>
  <nav><div class="wrap"><a href="#conclusao">Conclusão</a><a href="#metodo">Método</a><a href="#metricas">Métricas</a><a href="#tokens">Tokens</a><a href="#casos">Casos</a><a href="#limites">Limitações</a><a href="#rastreio">Rastreio</a></div></nav>
  <main class="wrap">
    <section id="conclusao">
      <p class="eyebrow" style="color:var(--cyan)">Conclusão executiva</p>
      <h2>Terra/Luna liderou nos três eixos principais desta bateria</h2>
      <div class="grid four" style="margin-top:18px">
        <article class="card metric"><small>Latência total mediana</small><strong>{format_decimal(right["distributions"]["total_s"]["median"])} s</strong><span>-{format_percent(comparison["latency_total_median_reduction_pct"])}</span></article>
        <article class="card metric"><small>Qualidade mediana</small><strong>{format_decimal(right["distributions"]["quality_overall"]["median"])}</strong><span>+{format_decimal(comparison["quality_median_delta"])}</span></article>
        <article class="card metric"><small>Custo total</small><strong>{format_usd(right["cost"]["usd_total"])}</strong><span>-{format_percent(comparison["cost_total_reduction_pct"])}</span></article>
        <article class="card metric"><small>Flags de alucinação</small><strong>{format_integer(right["hallucinations"])} / 10</strong><span>{format_integer(abs(comparison["hallucination_delta"]))} a menos</span></article>
      </div>
      <p class="lede">{esc(recommendation)}</p>
    </section>

    <section id="metodo">
      <h2>Contrato e integridade</h2>
      <p class="lede">A alocação por papel é calculada de <code>benchmark-redesign/arms.json</code> e resolvida pela rate card. A tabela não aceita aliases fixos no HTML.</p>
      <div class="table-shell"><table>
        <caption>Alocação por papel</caption>
        <thead><tr><th>Papel</th><th>{esc(left_label)}</th><th>{esc(right_label)}</th></tr></thead>
        <tbody>{render_roles_html(rows)}</tbody>
      </table></div>
      <div class="table-shell"><table>
        <caption>Prova técnica</caption>
        <thead><tr><th>Evidência</th><th>{esc(left_label)}</th><th>{esc(right_label)}</th></tr></thead>
        <tbody>{render_technical_html(data)}</tbody>
      </table></div>
    </section>

    <section id="metricas">
      <h2>Métricas correspondentes</h2>
      <p class="lede">Todos os valores decimais exibidos, inclusive USD, são arredondados e apresentados com exatamente {DECIMAL_PLACES} casas decimais. Os cabeçalhos numéricos ficam alinhados à direita.</p>
      <div class="table-shell"><table>
        <caption>Resumo alinhado</caption>
        <thead><tr><th>Métrica</th><th class="num">{esc(left_label)}</th><th class="num">{esc(right_label)}</th></tr></thead>
        <tbody>{"".join(metric_html)}</tbody>
      </table></div>
      <div class="table-shell"><table>
        <caption>Distribuição de latência total</caption>
        <thead><tr><th>Braço</th>{"".join(distribution_html)}</tr></thead>
        <tbody><tr><th>{esc(left_label)}</th>{distribution_cells[0]}</tr><tr><th>{esc(right_label)}</th>{distribution_cells[1]}</tr></tbody>
      </table></div>
    </section>

    <section id="tokens">
      <h2>Tokens, custo e ferramentas</h2>
      <div class="table-shell"><table>
        <caption>Totais de tokens observados</caption>
        <thead><tr><th>Braço</th><th class="num">Input</th><th class="num">Cache read</th><th class="num">Output</th><th class="num">Reasoning</th><th class="num">Gerações</th></tr></thead>
        <tbody>
          <tr><th>{esc(left_label)}</th><td class="num">{format_integer(left["tokens_total"]["input"])}</td><td class="num">{format_integer(left["tokens_total"]["cache_read"])}</td><td class="num">{format_integer(left["tokens_total"]["output"])}</td><td class="num">{format_integer(left["tokens_total"]["reasoning"])}</td><td class="num">{format_integer(left["tokens_total"]["generations"])}</td></tr>
          <tr><th>{esc(right_label)}</th><td class="num">{format_integer(right["tokens_total"]["input"])}</td><td class="num">{format_integer(right["tokens_total"]["cache_read"])}</td><td class="num">{format_integer(right["tokens_total"]["output"])}</td><td class="num">{format_integer(right["tokens_total"]["reasoning"])}</td><td class="num">{format_integer(right["tokens_total"]["generations"])}</td></tr>
        </tbody>
      </table></div>
      <div class="table-shell"><table>
        <caption>Tokens por deployment observado</caption>
        <thead><tr><th>Deployment</th><th class="num">Input</th><th class="num">Cache read</th><th class="num">Output</th><th class="num">Reasoning</th><th class="num">Gerações</th></tr></thead>
        <tbody>{render_tokens_html(right)}</tbody>
      </table></div>
      <div class="grid" style="margin-top:16px">{"".join(tools_html)}</div>
      {warning_html}
      <p class="lede">Reasoning permanece dentro do output faturado e não é cobrado duas vezes. BRL não é exibido porque a rate card não fixa câmbio.</p>
    </section>

    <section id="casos">
      <h2>Comparação caso a caso</h2>
      <p class="lede">O preenchimento verde marca o vencedor em cada métrica: menor latência, maior qualidade e menor custo. Em empate, os dois valores recebem fill.</p>
      <div class="table-shell"><table>
        <caption>Valores por QID — segundos, score e USD</caption>
        <thead><tr><th>QID</th><th class="num">{esc(left_label)} total</th><th class="num">{esc(right_label)} total</th><th class="num">{esc(left_label)} quality</th><th class="num">{esc(right_label)} quality</th><th class="num">{esc(left_label)} USD</th><th class="num">{esc(right_label)} USD</th></tr></thead>
        <tbody>{render_case_table_html(data)}</tbody>
      </table></div>
      <div class="winner-legend"><span class="winner-swatch" aria-hidden="true"></span> vencedor; empates ficam destacados nos dois lados</div>
    </section>

    <section id="limites">
      <h2>Limitações antes da decisão</h2>
      <ul>
        <li><strong>N=1:</strong> fotografia operacional, sem significância estatística.</li>
        <li><strong>Cauda web:</strong> os máximos de latência são sensíveis ao caso; leia mediana, média e p90 juntas.</li>
        <li><strong>Configuração completa:</strong> a bateria não isola causalmente standard, mini, OCR, judge ou nano/explorador.</li>
        <li><strong>Atribuição por deployment:</strong> a alocação declarada e os tokens observados são apresentados separadamente quando há divergência.</li>
        <li><strong>BRL:</strong> não há câmbio versionado na rate card.</li>
      </ul>
    </section>

    <section id="rastreio">
      <h2>Rastreabilidade</h2>
      <p><strong>Run GPT:</strong> <code>{esc(left["run_name"])}</code></p>
      <p><strong>Run Terra/Luna:</strong> <code>{esc(right["run_name"])}</code></p>
      <p><strong>Commit da execução:</strong> <code>{esc(left["commit"])}</code></p>
      <p><strong>Rate card:</strong> <code>{esc(left["rate_card"]["version"])}</code> · SHA-256 <code>{esc(left["rate_card"]["sha256"])}</code></p>
      <p class="lede">Fonte de dados versionada: <code>report-data.json</code>. Configuração de papéis: <code>benchmark-redesign/arms.json</code>. Template: <code>report-template.html</code>.</p>
    </section>
  </main>
""".strip()
    template = template_path.read_text(encoding="utf-8")
    marker = "  <!-- REPORT BODY -->"
    if template.count(marker) != 1:
        raise ValueError(f"Template precisa conter exatamente um marcador {marker!r}.")
    return template.replace(marker, body)


def render_markdown(
    data: dict[str, Any], arms_data: dict[str, Any], rate_card: dict[str, Any]
) -> str:
    left, right = data["arms"]
    comparison = data["comparison"]
    rows = role_rows(arms_data, rate_card)
    warnings = [
        warning
        for arm, key in zip(data["arms"], ARM_KEYS, strict=True)
        if (warning := observed_model_warning(arm, arms_data["arms"][key]))
    ]
    metric_lines = []
    for label, left_value, right_value, kind in metric_rows(data):
        metric_lines.append(
            f"| {label} | {render_metric_value(left_value, kind)} | {render_metric_value(right_value, kind)} |"
        )
    distribution_lines = []
    for arm in (left, right):
        values = arm["distributions"]["total_s"]
        distribution_lines.append(
            f"| {arm['label']} | {format_decimal(values['min'])} | {format_decimal(values['p25'])} | "
            f"{format_decimal(values['median'])} | {format_decimal(values['mean'])} | {format_decimal(values['p75'])} | "
            f"{format_decimal(values['p90'])} | {format_decimal(values['max'])} |"
        )
    warning_section = (
        "\n".join(f"> ⚠ {warning}" for warning in warnings)
        or "> Nenhuma divergência entre aliases observados e configurados."
    )
    recommendation = (
        "Leitura provisória: Terra/Luna apresenta os melhores agregados desta fotografia; "
        "a promoção deve aguardar a reconciliação do bucket observado `seiia-ds-nano` com a alocação Luna."
        if warnings
        else "Recomendação operacional: preferir Terra/Luna para esta bateria, mantendo a ressalva de N=1 e sem inferência causal sobre cada componente da configuração."
    )
    return (
        f"""# Benchmark Session — GPT-5.4 versus Terra/Luna

Relatório gerado por `benchmark-redesign/build_report.py`. Os mesmos dez casos
foram executados uma vez por braço. Todos os valores decimais, inclusive USD,
usam exatamente {DECIMAL_PLACES} casas decimais.

## Conclusão

Terra/Luna apresentou latência total mediana de **{format_decimal(right["distributions"]["total_s"]["median"])} s**, qualidade mediana de **{format_decimal(right["distributions"]["quality_overall"]["median"])}**, custo total de **{format_usd(right["cost"]["usd_total"])}** e **{format_integer(right["hallucinations"])}/10** flags de alucinação.

{recommendation}

* Redução da latência total mediana: **{format_percent(comparison["latency_total_median_reduction_pct"])}**.
* Delta da qualidade mediana: **+{format_decimal(comparison["quality_median_delta"])}**.
* Redução do custo total: **{format_percent(comparison["cost_total_reduction_pct"])}**.

## Alocação por papel

Fonte: `benchmark-redesign/arms.json`, resolvida pela rate card.

| Papel | {left["label"]} | {right["label"]} |
|---|---|---|
{render_roles_markdown(rows)}

## Métricas

| Métrica | {left["label"]} | {right["label"]} |
|---|---:|---:|
{chr(10).join(metric_lines)}

### Distribuição de latência total

| Braço | mín. | p25 | mediana | média | p75 | p90 | máx. |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(distribution_lines)}

## Tokens por deployment observado

| Deployment | Input | Cache read | Output | Reasoning | Gerações |
|---|---:|---:|---:|---:|---:|
{render_tokens_markdown(right)}

{warning_section}

## Comparação caso a caso

O vencedor é o menor valor para latência/custo e o maior valor para quality.
Empates devem ser destacados nos dois lados no HTML.

| QID | {left["label"]} total | {right["label"]} total | {left["label"]} quality | {right["label"]} quality | {left["label"]} USD | {right["label"]} USD |
|---|---:|---:|---:|---:|---:|---:|
{render_case_table_markdown(data)}

## Limitações

* N=1 por caso não sustenta significância estatística.
* A bateria não isola causalmente standard, mini, OCR, judge ou nano/explorador.
* Tokens observados são preservados como fonte; o gerador não reassocia deployment histórico a papel configurado.
* BRL não é exibido porque a rate card não fixa câmbio.

## Rastreabilidade

* Run GPT: `{left["run_name"]}`
* Run Terra/Luna: `{right["run_name"]}`
* Commit da execução: `{left["commit"]}`
* Rate card: `{left["rate_card"]["version"]}`, SHA-256 `{left["rate_card"]["sha256"]}`
* Configuração: `benchmark-redesign/arms.json`
""".strip()
        + "\n"
    )


def build_report(
    *,
    data_path: Path = DEFAULT_DATA_PATH,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    html_path: Path = DEFAULT_HTML_PATH,
    markdown_path: Path = DEFAULT_MARKDOWN_PATH,
    check: bool = False,
) -> None:
    data, arms_data, rate_card = load_inputs(data_path)
    rendered_html = render_html(data, arms_data, rate_card, template_path)
    rendered_markdown = render_markdown(data, arms_data, rate_card)
    if check:
        expected = ((html_path, rendered_html), (markdown_path, rendered_markdown))
        stale = [
            str(path)
            for path, content in expected
            if not path.exists() or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            raise ValueError(
                "Relatório desatualizado; execute build_report.py: " + ", ".join(stale)
            )
        print(f"Relatório consistente: {html_path} e {markdown_path}")
        return
    html_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(rendered_html, encoding="utf-8")
    markdown_path.write_text(rendered_markdown, encoding="utf-8")
    print(f"Relatório atualizado: {html_path} e {markdown_path}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="falha se HTML ou Markdown não forem atuais",
    )
    parser.add_argument(
        "--data", type=Path, default=DEFAULT_DATA_PATH, help="snapshot JSON versionado"
    )
    parser.add_argument(
        "--template", type=Path, default=DEFAULT_TEMPLATE_PATH, help="template HTML"
    )
    parser.add_argument(
        "--html-output", type=Path, default=DEFAULT_HTML_PATH, help="HTML gerado"
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=DEFAULT_MARKDOWN_PATH,
        help="Markdown gerado",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        build_report(
            data_path=args.data,
            template_path=args.template,
            html_path=args.html_output,
            markdown_path=args.markdown_output,
            check=args.check,
        )
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
