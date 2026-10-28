"""Contrato do gate nano que avalia evidência web já coletada."""

from sei_ia.agents.session_agent.web_evidence_gate import (
    EvidenceGateVerdict,
    compact_evidence_input,
    parse_evidence_gate_verdict,
)


def test_parse_verdict_preserva_matriz_e_consulta_dirigida():
    verdict = parse_evidence_gate_verdict(
        """{
          "ledger": [{"entity": "ALZR11", "criterion": "DY 12M", "value": "10,1%", "url": "https://fonte/a", "evidence": "DY 12M 10,1%"}],
          "gaps": [{"entity": "TRXF11", "criterion": "contratos atípicos", "reason": "não localizado"}],
          "next_query": "TRXF11 contratos atípicos relatório gerencial 2026"
        }"""
    )

    assert verdict == EvidenceGateVerdict(
        ledger=(
            {
                "entity": "ALZR11",
                "criterion": "DY 12M",
                "value": "10,1%",
                "url": "https://fonte/a",
                "evidence": "DY 12M 10,1%",
            },
        ),
        gaps=(
            {
                "entity": "TRXF11",
                "criterion": "contratos atípicos",
                "reason": "não localizado",
            },
        ),
        next_query="TRXF11 contratos atípicos relatório gerencial 2026",
    )


def test_parse_verdict_rejeita_consulta_sem_lacuna():
    verdict = parse_evidence_gate_verdict(
        '{"ledger": [], "gaps": [], "next_query": "busca desnecessária"}'
    )

    assert verdict.next_query is None


def test_compact_evidence_input_reparte_orcamento_entre_lotes():
    compact = compact_evidence_input(["A" * 100, "B" * 100, "C" * 100], max_chars=90)

    assert len(compact) <= 90
    assert "A" in compact and "B" in compact and "C" in compact
