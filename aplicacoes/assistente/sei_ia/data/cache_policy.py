"""Política de armazenamento informada pelo SEI."""

from typing import Literal

CachePolicy = Literal["S", "N"]


def parse_cache_policy(value: object) -> CachePolicy:
    """Valida a política sem assumir que ausência significa cacheável."""
    if value == "S":
        return "S"
    if value == "N":
        return "N"
    raise ValueError("sin_armazena_cache deve ser 'S' ou 'N'")
