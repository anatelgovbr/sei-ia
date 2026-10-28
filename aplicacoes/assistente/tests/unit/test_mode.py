"""Unit test puro da decisão de modo do session (fase 5), sem rede nem env.

Cobre os dois lados do threshold, a fronteira (igual), e os escape hatches do knob
(0 desliga o injetado, valor gigante força). Também exercita a semântica do override
por request (mesmo conteúdo, threshold diferente -> modo diferente).
"""

from __future__ import annotations

from sei_ia.agents.session_agent.mode import ModeDecision, decide_mode


def test_abaixo_do_threshold_injeta():
    d = decide_mode(10_000, 50_000)
    assert isinstance(d, ModeDecision)
    assert d.mode == "injected"
    assert d.total_content_tokens == 10_000
    assert d.threshold == 50_000


def test_acima_do_threshold_filesystem():
    assert decide_mode(120_000, 50_000).mode == "filesystem"


def test_igual_ao_threshold_injeta():
    # corte inclusivo (<=): conteúdo exatamente no threshold vai para injetado
    assert decide_mode(50_000, 50_000).mode == "injected"


def test_threshold_zero_desliga_injetado():
    # 0 desliga o modo injetado -> sempre filesystem, mesmo conteúdo minúsculo
    assert decide_mode(1, 0).mode == "filesystem"
    assert decide_mode(0, 0).mode == "filesystem"


def test_threshold_gigante_forca_injetado():
    assert decide_mode(549_000, 10_000_000).mode == "injected"


def test_override_por_request_troca_o_modo():
    # mesmo conteúdo (60k): com o knob 50k cai em filesystem; um override de 100k injeta
    tokens = 60_000
    assert decide_mode(tokens, 50_000).mode == "filesystem"
    assert decide_mode(tokens, 100_000).mode == "injected"


def test_override_explicito_forca_modo_independente_do_threshold():
    assert decide_mode(1, 0, mode_override="injected").mode == "injected"
    assert decide_mode(1, 1_000_000, mode_override="filesystem").mode == "filesystem"
