"""Modelo de dados para log de consumo de API."""

from pydantic import BaseModel


class LogConsumeCreate(BaseModel):
    """Estrutura do log de consumo de API."""

    id_protocol: list[int]
    id_user: int | None
    api_recomend_url: str
    status_code: int
