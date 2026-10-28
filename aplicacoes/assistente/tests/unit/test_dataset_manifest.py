"""Testes da materializacao versionada do dataset decisorio."""

from __future__ import annotations

import json
import os
import sys

_EXP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "experimentos",
    "latencia-session-vs-classico",
)
sys.path.insert(0, os.path.join(_EXP_DIR, "scripts", "shared"))
sys.path.insert(0, os.path.join(_EXP_DIR, "scripts", "session-classico"))

from dataset_manifest import DATASET_DIR, load_suite  # noqa: E402


def test_v2_materializa_dez_casos_em_ordem_com_metadados_de_versao():
    manifest, cases = load_suite("benchmark-decision-v2")

    assert manifest["dataset_name"] == "benchmark-decision-v2"
    assert [case["qid"] for case in cases] == manifest["qids"]
    assert len(cases) == 10
    assert all(case["metadata"]["benchmark_version"] == "v2" for case in cases)


def test_v2_corrige_gabaritos_web_sem_alterar_caso_base():
    base_cases = json.loads((DATASET_DIR / "cases.json").read_text(encoding="utf-8"))[
        "cases"
    ]
    _, v2_cases = load_suite("benchmark-decision-v2")
    base = {case["qid"]: case for case in base_cases}
    v2 = {case["qid"]: case for case in v2_cases}

    assert (
        "falencia decretada em 10 de novembro de 2025"
        in base["LARGE-WEB-01"]["expected_output"]["gold_answer_exemplo"]
    )
    assert (
        "suspendeu os efeitos"
        in v2["LARGE-WEB-01"]["expected_output"]["gold_answer_exemplo"]
    )
    assert "Nao faca recomendacao" in v2["WEB-FII-01"]["input"]["text"]
    assert (
        "pode retornar menos de 10"
        in v2["WEB-FII-01"]["expected_output"]["gold_answer"].lower()
    )


def test_v2_nao_trata_falta_de_url_como_indicador_de_alucinacao():
    _, cases = load_suite("benchmark-decision-v2")
    web_cases = [case for case in cases if case["metadata"]["requires_web"]]

    for case in web_cases:
        indicators = " ".join(case["expected_output"]["indicadores_alucinacao"])
        assert "Nao citar nenhuma fonte" not in indicators
        assert "sem citar fonte" not in indicators
