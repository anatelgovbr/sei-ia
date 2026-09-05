"""Vocabulário sanitizado para a disponibilidade de conteúdo externo.

Os estados descrevem o conteúdo, não a identidade da fonte. Cada fronteira
(sessão SEI, upload, cache) carrega sua própria identidade e projeta este
vocabulário para manifesto, prompt, telemetria e cache sem serializar erros crus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ContentState = Literal["available", "empty", "unavailable"]
EmptyContentReason = Literal["content_doc_empty", "no_text_extracted"]
UnavailableContentReason = Literal[
    "binary_not_found",
    "source_not_found",
    "download_failed",
    "extraction_failed",
    "unsupported_format",
    "timeout",
    "visual_not_retained",
    "legacy_state_unknown",
]
ContentReason = EmptyContentReason | UnavailableContentReason


@dataclass(frozen=True)
class ContentStatus:
    """Estado e motivo compatíveis, sem diagnóstico técnico da origem."""

    state: ContentState
    reason: ContentReason | None = None

    def __post_init__(self) -> None:
        if self.state == "available" and self.reason is not None:
            raise ValueError("conteúdo disponível não aceita motivo")
        if self.state != "available" and self.reason is None:
            raise ValueError("conteúdo não disponível exige motivo sanitizado")
        if self.state == "empty" and self.reason not in {
            "content_doc_empty",
            "no_text_extracted",
        }:
            raise ValueError("motivo incompatível com conteúdo vazio")
        if self.state == "unavailable" and self.reason in {
            "content_doc_empty",
            "no_text_extracted",
        }:
            raise ValueError("motivo incompatível com conteúdo indisponível")

    @classmethod
    def available(cls) -> ContentStatus:
        return cls("available")

    @classmethod
    def empty(cls, reason: EmptyContentReason) -> ContentStatus:
        return cls("empty", reason)

    @classmethod
    def unavailable(cls, reason: UnavailableContentReason) -> ContentStatus:
        return cls("unavailable", reason)
