#!/usr/bin/env python
"""Validators for pydantic models."""

import pandas as pd


def pandas_dataframe_validator(value: pd.DataFrame) -> pd.DataFrame:
    """Valida se o valor   um objeto pandas.DataFrame.

    Se o valor n o for um objeto pandas.DataFrame, lan a um erro de ValueError com a mensagem.

    Retorna o valor original, sem modifica es.
    """
    if not isinstance(value, pd.DataFrame):
        raise TypeError("O valor deve ser um objeto pandas.DataFrame")
    return value
