"""Utilitários e filtros para processamento de texto."""

import re
from pathlib import Path
from typing import ClassVar

from api_sei.envs import STOPWORDS


class StemmerUtil:
    """Utilitários para processamento de palavras em algoritmos de stemming."""

    # (min_length, suffix, slice_end, append)
    _SUFFIX_RULES: ClassVar[list[tuple]] = [
        (3, "ns", -2, "m"),
        (4, ("eis", "éis"), -3, "el"),
        (4, "ais", -3, "l"),
        (4, "óis", -3, "ol"),
        (4, "is", -2, "l"),
        (3, ("ões", "ães"), -3, "ão"),
        (6, "mente", -5, ""),
    ]

    @staticmethod
    def starts_with(s: str, prefix: str) -> bool:
        """Verifica se a string 's' começa com o prefixo 'prefix'.

        Parâmetros:
        - s (str): A string a ser verificada.
        - prefix (str): O prefixo a ser comparado.

        Retorna:
        - bool: True se 's' começa com 'prefix', caso contrário False.
        """
        return s.startswith(prefix)

    @staticmethod
    def ends_with(s: str, suffix: str | tuple[str, ...]) -> bool:
        """Verifica se a string 's' termina com o sufixo 'suffix'.

        Parâmetros:
        - s (str): A string a ser verificada.
        - suffix (str | tuple[str, ...]): O sufixo (ou tupla de sufixos) a ser comparado.

        Retorna:
        - bool: True se 's' termina com 'suffix', caso contrário False.
        """
        return s.endswith(suffix)

    @staticmethod
    def ends_with_array(s: str, suffix: str) -> bool:
        """Verifica se a string 's' termina com o sufixo 'suffix' usando o método 'ends_with'.

        Parâmetros:
        - s (str): A string a ser verificada.
        - suffix (str): O sufixo a ser comparado.

        Retorna:
        - bool: True se 's' termina com 'suffix', caso contrário False.
        """
        return StemmerUtil.ends_with(s, suffix)

    @staticmethod
    def delete(s: str, pos: int) -> str:
        """Remove o caractere na posição 'pos' da string 's'.

        Parâmetros:
        - s (str): A string de entrada.
        - pos (int): A posição do caractere a ser removido.

        Retorna:
        - str: A string resultante após a remoção.
        """
        return s[:pos] + s[pos + 1 :]

    @staticmethod
    def delete_n(s: str, pos: int, n_chars: int) -> str:
        """Remove 'n_chars' caracteres a partir da posição 'pos' da string 's'.

        Parâmetros:
        - s (str): A string de entrada.
        - pos (int): A posição inicial para remoção.
        - n_chars (int): O número de caracteres a serem removidos.

        Retorna:
        - str: A string resultante após a remoção.
        """
        return s[:pos] + s[pos + n_chars :]


class PortugueseLightStemmer:
    """Implementação de um stemmer leve para a língua portuguesa."""

    _MIN_WORD_LENGTH: int = 4
    _MIN_PLURAL_LENGTH: int = 3
    _MIN_FEMININE_LENGTH: int = 6
    _MIN_FEMININE_LONG_LENGTH: int = 7

    _ACCENT_MAP: ClassVar[dict[str, str]] = {
        "à": "a",
        "á": "a",
        "â": "a",
        "ä": "a",
        "ã": "a",
        "ò": "o",
        "ó": "o",
        "ô": "o",
        "ö": "o",
        "õ": "o",
        "è": "e",
        "é": "e",
        "ê": "e",
        "ë": "e",
        "ù": "u",
        "ú": "u",
        "û": "u",
        "ü": "u",
        "ì": "i",
        "í": "i",
        "î": "i",
        "ï": "i",
        "ç": "c",
    }

    @staticmethod
    def stem(s: str) -> str:
        """Aplica o algoritmo de stemming à palavra 's'.

        Parâmetros:
        - s (str): A palavra a ser processada.

        Retorna:
        - str: A palavra após o stemming.
        """
        if len(s) < PortugueseLightStemmer._MIN_WORD_LENGTH:
            return s

        s = PortugueseLightStemmer.remove_suffix(s)

        if len(s) > PortugueseLightStemmer._MIN_PLURAL_LENGTH and s[-1] == "a":
            s = PortugueseLightStemmer.norm_feminine(s)

        if len(s) > PortugueseLightStemmer._MIN_WORD_LENGTH and s[-1] in {
            "e",
            "a",
            "o",
        }:
            s = s[:-1]

        return "".join(PortugueseLightStemmer._ACCENT_MAP.get(c, c) for c in s)

    @staticmethod
    def remove_suffix(s: str) -> str:
        """Remove sufixos comuns da palavra 's'.

        Parâmetros:
        - s (str): A palavra da qual os sufixos serão removidos.

        Retorna:
        - str: A palavra após a remoção dos sufixos.
        """
        length = len(s)

        if (
            length > PortugueseLightStemmer._MIN_WORD_LENGTH
            and StemmerUtil.ends_with(s, "es")
            and s[length - 3] in {"r", "s", "l", "z"}
        ):
            return s[:-2]

        for min_len, suffix, cut, append in StemmerUtil._SUFFIX_RULES:
            if length > min_len and StemmerUtil.ends_with(s, suffix):
                return s[:cut] + append

        if length > PortugueseLightStemmer._MIN_PLURAL_LENGTH and s[length - 1] == "s":
            return s[:-1]

        return s

    @staticmethod
    def norm_feminine(s: str) -> str:  # noqa: PLR0911
        """Normaliza formas femininas da palavra 's'.

        Parâmetros:
        - s (str): A palavra a ser normalizada.

        Retorna:
        - str: A palavra após a normalização.
        """
        length = len(s)

        if (
            length > PortugueseLightStemmer._MIN_FEMININE_LONG_LENGTH
            and StemmerUtil.ends_with(s, ("inha", "iaca", "eira"))
        ):
            return s[:-1] + "o"

        if (
            length > PortugueseLightStemmer._MIN_FEMININE_LENGTH
            and StemmerUtil.ends_with(s, ("osa", "ica", "ida", "ada", "iva", "ama"))
        ):
            return s[:-1] + "o"

        if (
            length > PortugueseLightStemmer._MIN_FEMININE_LENGTH
            and StemmerUtil.ends_with(s, "ona")
        ):
            return s[:-3] + "ão"

        if (
            length > PortugueseLightStemmer._MIN_FEMININE_LENGTH
            and StemmerUtil.ends_with(s, "ora")
        ):
            return s[:-1]

        if (
            length > PortugueseLightStemmer._MIN_FEMININE_LENGTH
            and StemmerUtil.ends_with(s, "esa")
        ):
            return s[:-3] + "ê"

        if (
            length > PortugueseLightStemmer._MIN_FEMININE_LENGTH
            and StemmerUtil.ends_with(s, "na")
        ):
            return s[:-1] + "o"

        return s


def remove_stopwords(s_list: list[str]) -> list[str]:
    """Remove stopwords de uma lista de strings fornecida.

    Parâmetros:
    - s_list (List[str]): Uma lista de strings da qual as stopwords serão removidas.

    Retorna:
    - List[str]: Uma lista de strings sem as stopwords.
    """
    # Obtém as stopwords
    stopwords = []
    with Path(STOPWORDS).open(encoding="utf8") as f:
        for line in f:
            word = line.split("|")[0].strip()
            if word:
                stopwords.append(word)

    # Remove as stopwords
    return [word for word in s_list if word not in stopwords]


def lowercase_tokenizer(s: str) -> list[str]:
    """Tokeniza a string 's' em letras minúsculas, removendo caracteres não alfabéticos.

    Baseado em: https://solr.apache.org/guide/solr/latest/indexing-guide/tokenizers.html#lower-case-tokenizer

    Parâmetros:
    - s (str): A string de entrada.

    Retorna:
    - List[str]: Uma lista de tokens resultantes.
    """
    # Remove caracteres que não são letras
    s = s.lower()
    s = re.sub(r"[^a-zªµºàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþßÿ\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.split()


def solr_preprocessing(s: str) -> list[str]:
    """Processamento de texto similar ao utilizado pelo Solr.

    Aplica tokenização em minúsculas, remove stopwords e aplica stemming.

    Parâmetros:
    - s (str): A string de entrada.

    Retorna:
    - List[str]: Uma lista de tokens processados.
    """
    s_list = lowercase_tokenizer(s)

    # Remove as stopwords
    s_list = remove_stopwords(s_list)

    # Aplica o stemmer
    return [PortugueseLightStemmer.stem(word) for word in s_list]
