"""Modelo de dados para log de recomendação."""

import re
from datetime import datetime

from pydantic import BaseModel, validator


class LogRecommendationBase(BaseModel):
    """Modelo de dados para log de recomendação."""

    id_protocolo_search: int
    id_protocolo_interest: int
    email_user: str
    created_at: str | None = None


class LogRecommendation(LogRecommendationBase):
    """Modelo de dados para log de recomendação."""

    @validator("email_user")
    def validate_email_format(cls, email: str) -> str:
        """Valida o formato do email."""
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            raise ValueError("Invalid email format")
        return email

    @validator("created_at")
    def validate_created_at(cls, created_at: str | None) -> str | None:
        """Valida o formato da data de criação."""
        if created_at:
            try:
                parsed_datetime = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
                return parsed_datetime.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError as e:
                raise ValueError(
                    "Invalid timestamp format. It should be in the format 'YYYY-MM-DD HH:MM:SS'"
                ) from e

        return created_at
