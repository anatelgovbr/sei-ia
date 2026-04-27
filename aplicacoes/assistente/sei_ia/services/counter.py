"""Modulo de contagem de tokens."""

# import tiktoken

# encoder = tiktoken.get_encoding("o200k_base")


def token_counter(text: str | None) -> int:
    """Funcao de contagem de tokens.

    Args:
        text (str | None): texto

    Returns:
        int: quantidade de tokens
    """
    if text:
        return int(
            len(text) / 3.5
        )  # len(encoder.encode(text)) Foi escolhido utilizar valor apróximado porque o tiktoken em casos com muitos tokens (300k) foi observado panic error . Stackoverflow
    return 0
