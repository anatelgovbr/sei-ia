"""Pydantic models for feedback endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def current_timestamp() -> str:
    """Return an UTC timestamp formatted like the legacy feedback API."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class FeedbackItem(BaseModel):
    """One rated recommendation item."""

    id_recommended: int = Field(..., description="ID recomendado")
    like_flag: int = Field(..., description="Avaliacao do usuario")
    sugesty: str = Field(..., description="Sugestao do usuario")
    racional: str = Field(..., description="Justificativa do usuario")
    ranking_user: int = Field(..., description="Posicao dada pelo usuario")


class Feedback(BaseModel):
    """Feedback payload compatible with the legacy app-api."""

    id_recommendation: int = Field(..., description="ID da recomendacao originaria")
    result: list[FeedbackItem] = Field(
        ...,
        description="Lista de itens avaliados pelo usuario.",
    )


class FeedbackResponse(BaseModel):
    """Response returned after persisting feedback rows."""

    message: str
    timestamp: str = Field(default_factory=current_timestamp)
    ids: list[int]
