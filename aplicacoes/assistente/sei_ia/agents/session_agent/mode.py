"""Decisão de modo do fluxo session: injetado vs filesystem.

Um dado calculado UMA vez a partir do tamanho total do conteúdo dos documentos
(`total_content_tokens`, acumulado pelo `SessionManager.resolve` via `token_counter`)
e do threshold (knob `SESSION_INJECT_TOKENS_THRESHOLD`, com override por request).
O router computa a `ModeDecision` e passa `mode` adiante como valor — nenhuma camada
recontabiliza tokens nem re-decide (foundational-thinking). Um override explícito no
payload (`mode`) é reservado para testes.

Na fase 5 a decisão é só CALCULADA e OBSERVADA (trace/Langfuse); o comportamento do
modo injetado é a fase 6. `mode="injected"` ainda cai no fluxo filesystem atual.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SessionMode = Literal["injected", "filesystem"]


@dataclass(frozen=True)
class ModeDecision:
    """Modo do request + os insumos que o embasaram (para observabilidade)."""

    mode: SessionMode
    total_content_tokens: int
    threshold: int


def decide_mode(
    total_content_tokens: int,
    threshold: int,
    mode_override: SessionMode | None = None,
) -> ModeDecision:
    """Injeta quando o conteúdo cabe no corte; senão explora via filesystem.

    Escape hatches do knob: ``threshold <= 0`` DESLIGA o modo injetado (sempre
    filesystem); um ``threshold`` gigante FORÇA injetado (todo conteúdo real cabe).
    O corte é inclusivo (``<=``): conteúdo exatamente no threshold vai para injetado.
    Quando ``mode_override`` é informado, ele prevalece sobre o threshold.
    """
    if mode_override is not None:
        return ModeDecision(
            mode=mode_override,
            total_content_tokens=total_content_tokens,
            threshold=threshold,
        )

    inject = threshold > 0 and total_content_tokens <= threshold
    return ModeDecision(
        mode="injected" if inject else "filesystem",
        total_content_tokens=total_content_tokens,
        threshold=threshold,
    )
