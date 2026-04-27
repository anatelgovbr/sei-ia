"""Utilitários e filtros para processamento de texto."""

import re
from pathlib import Path

from api_sei.envs import STOPWORDS


class StemmerUtil:
    """Utilitários para processamento de palavras em algoritmos de stemming."""

    @staticmethod
    def starts_with(s: str, prefix: str) -> bool:
        """Verifica se a string 's' começa com o prefixo 'prefix'.

        Parâmetros:
        - s (str): A string a ser verificada.
        - prefix (str): O prefixo a ser comparado.

        Retorna:
        - bool: True se 's' começa com 'prefix', caso contrário False.
        """
        return s[: len(prefix)] == prefix

    @staticmethod
    def ends_with(s: str, suffix: str) -> bool:
        """Verifica se a string 's' termina com o sufixo 'suffix'.

        Parâmetros:
        - s (str): A string a ser verificada.
        - suffix (str): O sufixo a ser comparado.

        Retorna:
        - bool: True se 's' termina com 'suffix', caso contrário False.
        """
        return s[-len(suffix) :] == suffix

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

    @staticmethod
    def stem(s: str) -> str:
        """Aplica o algoritmo de stemming à palavra 's'.

        Parâmetros:
        - s (str): A palavra a ser processada.

        Retorna:
        - str: A palavra após o stemming.
        """
        length = len(s)

        if length < 4:  # noqa: PLR2004
            return s

        s = PortugueseLightStemmer.remove_suffix(s)
        length = len(s)

        if length > 3 and s[length - 1] == "a":  # noqa: PLR2004
            s = PortugueseLightStemmer.norm_feminine(s)
            length = len(s)

        if length > 4 and s[length - 1] in {"e", "a", "o"}:  # noqa: PLR2004
            s = s[:-1]
            length = len(s)

        # Mapeamento de caracteres acentuados para seus equivalentes sem acento
        accent_replacements = {
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

        return "".join([accent_replacements.get(char, char) for char in s])

    @staticmethod
    def remove_suffix(s: str) -> str:  # noqa: PLR0911
        """Remove sufixos comuns da palavra 's'.

        Parâmetros:
        - s (str): A palavra da qual os sufixos serão removidos.

        Retorna:
        - str: A palavra após a remoção dos sufixos.
        """
        length = len(s)

        if (
            length > 4  # noqa: PLR2004
            and StemmerUtil.ends_with(s, "es")
            and s[length - 3] in {"r", "s", "l", "z"}
        ):
            return s[:-2]

        if length > 3 and StemmerUtil.ends_with(s, "ns"):  # noqa: PLR2004
            return s[:-2] + "m"

        if length > 4 and StemmerUtil.ends_with(s, ("eis", "éis")):  # noqa: PLR2004
            return s[:-3] + "el"

        if length > 4 and StemmerUtil.ends_with(s, "ais"):  # noqa: PLR2004
            return s[:-3] + "l"

        if length > 4 and StemmerUtil.ends_with(s, "óis"):  # noqa: PLR2004
            return s[:-3] + "ol"

        if length > 4 and StemmerUtil.ends_with(s, "is"):  # noqa: PLR2004
            return s[:-2] + "l"

        if length > 3 and StemmerUtil.ends_with(s, ("ões", "ães")):  # noqa: PLR2004
            return s[:-3] + "ão"

        if length > 6 and StemmerUtil.ends_with(s, "mente"):  # noqa: PLR2004
            return s[:-5]

        if length > 3 and s[length - 1] == "s":  # noqa: PLR2004
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

        if length > 7 and StemmerUtil.ends_with(  # noqa: PLR2004
            s, ("inha", "iaca", "eira")
        ):
            return s[:-1] + "o"

        if length > 6 and StemmerUtil.ends_with(  # noqa: PLR2004
            s, ("osa", "ica", "ida", "ada", "iva", "ama")
        ):
            return s[:-1] + "o"

        if length > 6 and StemmerUtil.ends_with(s, "ona"):  # noqa: PLR2004
            return s[:-3] + "ão"

        if length > 6 and StemmerUtil.ends_with(s, "ora"):  # noqa: PLR2004
            return s[:-1]

        if length > 6 and StemmerUtil.ends_with(s, "esa"):  # noqa: PLR2004
            return s[:-3] + "ê"

        if length > 6 and StemmerUtil.ends_with(s, "na"):  # noqa: PLR2004
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
