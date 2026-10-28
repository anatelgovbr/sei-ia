from __future__ import annotations

import importlib.util
from pathlib import Path

_APP = Path(__file__).resolve().parents[2]
_MODULE_PATH = (
    _APP
    / "experimentos/latencia-session-vs-classico/benchmark-redesign/build_report.py"
)
_SPEC = importlib.util.spec_from_file_location("benchmark_report", _MODULE_PATH)
assert _SPEC and _SPEC.loader
report = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(report)


def test_formatacao_fixa_em_tres_casas_inclui_usd():
    assert report.format_decimal("1.53682018") == "1,537"
    assert report.format_decimal("0.05") == "0,050"
    assert report.format_usd("0.0089676") == "US$ 0,009"


def test_vencedor_destaca_menor_maior_e_empate():
    assert report.winner_flags(10, 20, better="lower") == (True, False)
    assert report.winner_flags(0.8, 0.9, better="higher") == (False, True)
    assert report.winner_flags(1, 1, better="lower") == (True, True)


def test_alocacao_terra_luna_usa_luna_no_explorador():
    data, arms_data, rate_card = report.load_inputs(report.DEFAULT_DATA_PATH)
    rows = {row["role"]: row for row in report.role_rows(arms_data, rate_card)}

    assert rows["nano/explorador"]["terra-luna"] == "seiia-ds-gpt-luna"
    assert rows["nano/explorador"]["terra-luna_canonical"] == "gpt-5.6-luna"
    rendered = report.render_html(
        data, arms_data, rate_card, report.DEFAULT_TEMPLATE_PATH
    )
    assert "<tr><th>nano/explorador</th>" in rendered
    assert "<code>seiia-ds-gpt-luna</code> → <code>gpt-5.6-luna</code>" in rendered
    assert "tokens históricos" in rendered


def test_tabela_caso_a_caso_tem_fill_e_cabecalhos_numericos():
    data, arms_data, rate_card = report.load_inputs(report.DEFAULT_DATA_PATH)
    rendered = report.render_html(
        data, arms_data, rate_card, report.DEFAULT_TEMPLATE_PATH
    )

    assert "td.winner { background:var(--good-bg)" in rendered
    assert rendered.count('class="num winner"') >= 20
    assert '<th class="num">' in rendered
    assert (
        'Casos / POSTs / terminais</th><td class="status ok">10 / 10 / 10' in rendered
    )
