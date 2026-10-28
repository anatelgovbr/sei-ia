"""Modulo de contagem de tokens."""

import tiktoken

# Encoding da familia gpt-4o/gpt-5 (o mesmo que o proxy LiteLLM/Azure aplica). Carregado
# uma vez (lazy) e reusado; o vocab fica cacheado em disco (o embedder ja usa este encoding).
_ENCODING_NAME = "o200k_base"
_encoder: tiktoken.Encoding | None = None

# tiktoken dava panic ao encodar um blob unico muito grande (~300k tokens); encodar em
# pedacos e somar evita isso. A perda de tokens de fronteira entre pedacos e desprezivel
# (poucos tokens por pedaco). Mesma estrategia do embedder.
_CHUNK_CHARS = 200_000


def _get_encoder() -> tiktoken.Encoding:
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding(_ENCODING_NAME)
    return _encoder


def token_counter(text: str | None) -> int:
    """Conta tokens com o tokenizer real (tiktoken ``o200k_base``).

    Antes usava a aproximacao ``len/3.5``, que subconta ~1.75x neste conteudo (tabelas,
    numeros, protocolos), deixando os guards de contexto cegos. Agora usa o tokenizer real,
    encodando em pedacos para nao dar panic em textos muito grandes.

    Args:
        text (str | None): texto

    Returns:
        int: quantidade de tokens
    """
    if not text:
        return 0
    enc = _get_encoder()
    if len(text) <= _CHUNK_CHARS:
        return len(enc.encode(text, disallowed_special=()))
    return sum(
        len(enc.encode(text[i : i + _CHUNK_CHARS], disallowed_special=()))
        for i in range(0, len(text), _CHUNK_CHARS)
    )
