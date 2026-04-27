"""Modelo de dados para recomendação por embedding."""

from pydantic import BaseModel, Field, validator


class NEmbeddingRecomenderRequest(BaseModel):
    """Requisição para recomendação por embedding."""

    id_protocolo: int
    fq: list[int] = Field(default_factory=list)
    rows: int = 10

    @validator("id_protocolo")
    def valida_id_protocolo(cls, valor: int) -> int:
        """Valida o campo 'id_protocolo'."""
        if valor <= 0:
            raise ValueError("O campo 'id_protocolo' deve ser um inteiro positivo.")
        return valor

    @validator("fq")
    def valida_fq(cls, valor: list[int]) -> list[int]:
        """Valida o campo 'fq'."""
        if not valor or not all(
            isinstance(element, int) and element > 0 for element in valor
        ):
            raise ValueError("O campo 'fq' deve ser uma lista de inteiros positivos.")
        return valor

    @validator("rows")
    def valida_rows(cls, valor: int) -> int:
        """Valida o campo 'rows'."""
        if valor <= 0:
            raise ValueError("O campo 'rows' deve ser um número inteiro positivo.")
        return valor
