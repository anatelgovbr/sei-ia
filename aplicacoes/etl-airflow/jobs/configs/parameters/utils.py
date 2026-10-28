"""utils module."""

import unicodedata


def remover_acento(texto):
    return "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def clean_txt(txt: str) -> str:
    return remover_acento(txt.lower().strip().replace(" ", "_"))
