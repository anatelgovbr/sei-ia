#!/usr/bin/env python
"""process recommenders."""

from enum import Enum

from pydantic import BaseModel, Field


class RecommendationItem(BaseModel):
    """recommendation item."""

    id: str = Field(..., alias="nr_processo")
    score: float

    class Config:  # noqa: D106
        populate_by_name = True


class RecommendationResponse(BaseModel):
    """recommendation response."""

    recommendation: list[RecommendationItem]
    debug: dict = {}


class RecommendationByIdProtocoloItem(BaseModel):
    """recommendation by id protocolo item."""

    id: str = Field(..., alias="id_protocolo")
    score: float

    class Config:  # noqa: D106
        populate_by_name = True


class RecommendationByIdProtocoloResponse(BaseModel):
    """recommendation by id protocolo response."""

    recommendation: list[RecommendationByIdProtocoloItem]
    debug: dict = {}


class RecommnedationByIdProtocoloResponseWithRegisterRecommendation(
    RecommendationByIdProtocoloResponse
):
    """recomendação por id protocolo resposta com registro recomendação."""

    id: int


class IdField(str, Enum):
    """Campos ids de processos."""

    id_process = "id_process"
    id_protocolo = "id_protocolo"
    id_protocolo_processo = "id_protocolo_processo"


class RecommendationByEmbd(BaseModel):
    """Estrutura de recomendação por embedding."""

    id: str = Field(..., alias="id_protocolo")


class ProcessRecommendation(BaseModel):
    """Estrutura de recomendação de processo."""

    id_user: int
    id_protocolo: int
    id_protocolo_consumed: int
    id_recomendacao_processo: int | None = None


class ProcessRecommnedationResponse(BaseModel):
    """Estrutura de resposta de recomendação de processo."""

    id_user: int
    id_protocolo: int
    id_protocolo_consumed: int
    id_recomendacao_processo: int | None = None
    created_at: str | None = None
