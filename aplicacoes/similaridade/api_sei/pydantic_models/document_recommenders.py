#!/usr/bin/env python
"""document recommenders."""

from pydantic import BaseModel, Field


class RecommendationItemDocument(BaseModel):
    """recommendation item."""

    id: str = Field(...)  # , alias='id_documento')
    score: float

    class Config:  # noqa: D106
        populate_by_name = True


class RecommendationResponseDocument(BaseModel):
    """recommendation response."""

    recommendation: list[RecommendationItemDocument]
    debug: dict = {}


class DocumentRecommendation(BaseModel):
    """document recommendation."""

    id_user: int
    id_documento: int
    id_documento_consumed: int
    id_recomendacao_documento: int | None = None


class DocumentRecommendationResponse(BaseModel):
    """document recommendation response."""

    id_user: int
    id_documento: int
    id_documento_consumed: int
    id_recomendacao_documento: int | None = None
    created_at: str | None = None


class DocumentMLTRecommendationRequest(BaseModel):
    """document mlt recommendation request."""

    text: str
    list_id_doc: list[int]
    list_type_id_doc: list[int]
    rows: int
    include_citations: bool
    text_weight: float
    normalized: bool
    fq: list[str]
