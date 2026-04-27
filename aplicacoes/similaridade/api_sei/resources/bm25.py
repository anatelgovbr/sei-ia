"""Módulo de calculo do bm25 da API."""

import logging
import math
import re
from collections import Counter
from typing import Any

from api_sei.db_models.solr_select import SolrRequests
from api_sei.envs import auth

logger = logging.getLogger(__name__)


def find_terms(expression: str) -> list:
    """Encontra termos em uma expressão dada.

    Parameters
    ----------
    expression : str
        A expressão a ser pesquisada por termos


    Returns:
    -------
    list
        Uma lista de termos encontrados na expressão.
    """
    return re.findall(r"\s([^\s]+)\^", " {} ".format(expression))  # noqa: UP032


def find_weights(expression: str) -> list:
    """Encontra pesos em uma expressão dada.

    Parameters
    ----------
    expression : str
        A expressão a ser pesquisada por pesos


    Returns:
    -------
    list
        Uma lista de pesos encontrados na expressão.
    """
    return list(map(float, re.findall(r"\^([^\s]+)\s", " {} ".format(expression))))  # noqa: UP032


def find_field(term: str) -> str:
    """Finds field in a given term.

    Parameters
    ----------
    term : str
        The term to be searched for field

    Returns:
    -------
    str
        The field found in the term.
    """
    return term.split(":")[0]


def find_term(term: str) -> str:
    """Encontra termo em um termo dado.

    Parameters
    ----------
    term : str
        O termo procurado no term

    Returns:
    -------
    str
        O termo encontrado no termo..
    """
    return ":".join(term.split(":")[1:])


def simplified_bm25_tfidf(n: int, n2: int) -> float:
    """Versão simplificada da fórmula BM25, considerando apenas o caso em que há um termo.

    com uma frequência de 1 no documento.


    Parameters
    ----------
    n : int
        Número de documentos em que o termo ocorre.
    n2 : int
        Número total de documentos no índice.


    Returns:
    -------
    float
        O score BM25 do termo no documento.
    """
    freq = 1
    k1 = 1.2
    b = 0.75  # does not really matter (dl == avgdl)
    dl = 1  # does not really matter (dl == avgdl)
    avgdl = 1  # does not really matter (dl == avgdl)

    return (
        freq
        / (freq + k1 * (1 - b + b * dl / avgdl))
        * math.log(1 + (n2 - n + 0.5) / (n + 0.5))
    )


def bm25_tfidf(
    n: int,
    nupper: int,
    freq: int,
    dl: int,
    avgdl: int,
    k1: float = 1.2,
    b: float = 0.75,
) -> tuple[float, str]:
    """Calcula o score BM25 de um termo em um documento.

    A fórmula utilizada é a seguinte:

    score = (freq / (freq + k1 * (1 - b + b * dl / avgdl))) * log(1 + (N - n + 0.5) / (n + 0.5))

    Parameters:
    ----------

    - freq é a frequência do termo no documento.
    - k1 é o parâmetro de saturação do termo (padrão=1.2).
    - b é o parâmetro de normalização de comprimento (padrão=0.75).
    - dl é o comprimento do campo no documento.
    - avgdl é o comprimento médio do campo em todos os documentos.
    - nupper é o número total de documentos com o campo.
    - n é o número de documentos que contém o termo.

    Retorna o score BM25 do termo no documento e uma string de depuração com os valores utilizados na fórmula.
    """
    tf = freq / (freq + k1 * (1 - b + b * dl / avgdl))
    idf = math.log(1 + (nupper - n + 0.5) / (n + 0.5))
    score = tf * idf

    debug_str = (
        f"{score} = weight({{}}), result of:"
        + f"\n    {score} = score(freq=1.0), computed as boost * idf * tf from:"
        + f"\n      {idf} = idf, computed as log(1 + (N - n + 0.5) / (n + 0.5)) from:"
        + f"\n        {n} = n, number of documents containing term"
        + f"\n        {nupper} = nupper, total number of documents with field"
        + f"\n      {tf} = tf, computed as freq / (freq + k1 * (1 - b + b * dl / avgdl)) from:"
        + f"\n        {freq} = freq, occurrences of term within document"
        + f"\n        {k1} = k1, term saturation parameter"
        + f"\n        {b} = b, length normalization parameter"
        + f"\n        {dl} = dl, length of field"
        + f"\n        {avgdl} = avgdl, average length of field"
    )  # noqa: ISC003

    return score, debug_str


def get_field_terms_statistics(
    solr_core_base_url: str, field: str, terms: list, batch_size: int = 1000
) -> tuple[int, dict, int]:
    """Retorna estatísticas de termos em um campo de um índice Solr.

    Retorna um dicionário com as seguintes chaves:
    - N: O número total de documentos no índice.
    - tokens_n: Um dicionário com a frequência de cada termo no índice.
    - avgdl: O comprimento médio do campo em todos os documentos.

    Parameters:
    ----------

    - solr_core_base_url: A URL base do índice Solr.
    - field: O nome do campo que contém os termos.
    - terms: Uma lista de termos para os quais devem ser calculadas as estatísticas.
    - batch_size: O tamanho do lote de termos a serem processados por vez (padrão=1000).
    """
    nupper = SolrRequests.get(
        f"{solr_core_base_url}/select?q={field}:*",
        ["response", "numFound"],
        rows=0,
        auth=auth,
    )
    nupper = 1 if nupper == 0 else nupper
    avgdl = (
        SolrRequests.get(
            f"{solr_core_base_url}/select?q=*:*&fl=sumtotaltermfreq({field})",
            ["response", "docs", 0, f"sumtotaltermfreq({field})"],
            rows=1,
            auth=auth,
        )
        / nupper
    )

    tokens_n = {}
    for i in range(0, len(terms), batch_size):
        batch_terms = [
            term for term in terms[i : (i + batch_size)] if term and term.strip()
        ]
        if not batch_terms:
            continue
        terms_docfreq_k = [f"docfreq({field},'{term}')" for term in batch_terms]
        jsn = {"params": {"fl": ",".join(terms_docfreq_k), "rows": 1, "q": "*:*"}}
        docfreqs = SolrRequests.post(
            url=f"{solr_core_base_url}/select",
            payload=jsn,
            nested_fields=["response", "docs", 0],
            auth=auth,
        )
        for term, docfreq_k in zip(batch_terms, terms_docfreq_k, strict=False):
            tokens_n[term] = docfreqs[docfreq_k]

    # Precisamos de uma forma melhor de estimar o N.
    # O N está em desacordo com as outras estatísticas.
    # Todas as outras estatísticas estão contando também documentos
    # "that are marked as deleted but have not yet been purged" e o N não.
    # Enquanto não achamos uma forma melhor de estimar o N,
    # as linhas a seguir previnem n > N.
    new_nupper = max([*list(tokens_n.values()), nupper])
    avgdl = (avgdl * nupper) / new_nupper
    nupper = new_nupper

    return nupper, tokens_n, avgdl


def extract(
    solr_core_base_url: str,
    field: str,
    tokens: list,
    max_tokens: int | None = None,
    mintf: int = 0,
) -> list:
    """Extrai os termos mais importantes de uma lista de tokens.

    Parameters:
    ----------
    - solr_core_base_url: A URL base do índice Solr.
    - field: O nome do campo que contém os termos.
    - tokens: A lista de tokens a serem extraídos.
    - max_tokens: O número máximo de termos a serem extraídos (padrão=None).
    - mintf: A frequência mínima de um termo para ele ser considerado (padrão=0).

    Retorna uma lista de pares (termo, score) ordenada pela pontuação BM25 em ordem decrescente.
    """
    tokens_freq = Counter(tokens)
    dl = len(tokens)
    tokens = [
        t
        for t, c in tokens_freq.items()
        if t and t.strip() and not t.isspace() and len(t.strip()) > 0 and (c > mintf)
    ]

    if not tokens:
        return []

    nupper, tokens_n, avgdl = get_field_terms_statistics(
        solr_core_base_url, field, tokens
    )
    tokens_scores = []
    for token in tokens:
        if not token or not token.strip():
            continue
        freq = tokens_freq[token]
        n = tokens_n.get(token, 0)
        if n == 0:
            score = 0
        else:
            score, debug_str = bm25_tfidf(n, nupper, freq, dl, avgdl)
        tokens_scores.append((token, score))
    tokens_scores = sorted(tokens_scores, key=lambda x: x[1], reverse=True)
    return tokens_scores[:max_tokens]


def extract_parsedquery(
    solr_core_base_url: str, field: str, tokens: list, **kwargs: dict[str, Any]
) -> str:
    """Extracts the parsed query from the given Solr core base URL, field, and tokens.

    Args:
        solr_core_base_url (str): The base URL of the Solr core.
        field (str): The field to extract the parsed query from.
        tokens (list): The list of tokens to extract the parsed query from.
        **kwargs: Additional keyword arguments to pass to the `extract` function.

    Returns:
        str: The extracted parsed query, formatted as a space-separated string of field:token pairs.
    """
    tokens_scores = extract(solr_core_base_url, field, tokens, **kwargs)
    valid_queries = []
    for t in tokens_scores:
        token = t[0]
        if token and token.strip() and not token.isspace():
            valid_queries.append(f"{field}:{token}")
    return " ".join(valid_queries)


def get_doc_score(solr_core_base_url: str, parsedquery: str, doc: dict) -> float:
    """Calculates the score of a document based on a parsed query.

    Args:
        solr_core_base_url (str): The base URL of the Solr core.
        parsedquery (str): The parsed query string.
        doc (dict): The document to calculate the score for.

    Returns:
        float: The calculated score of the document.

    Raises:
        None

    Examples:
        >>> get_doc_score("http://localhost:8983/solr/core", "field:value", {"field": ["token1", "token2", "token3"]})
        0.78
    """
    if "^" in parsedquery:
        term_field_value_pairs = find_terms(parsedquery)
        term_weights = find_weights(parsedquery)
    else:
        term_field_value_pairs = parsedquery.split()
        term_weights = [1 for _ in range(len(term_field_value_pairs))]
    term_fields = []
    term_values = []
    for tfvp, _ in zip(term_field_value_pairs, term_weights, strict=False):
        f = find_field(tfvp)
        term_fields.append(f)
        t = find_term(tfvp)
        term_values.append(t)

    tokens_scores = []
    for field in set(term_fields):
        parsedquery_tokens = [
            t for f, t in zip(term_fields, term_values, strict=False) if f == field
        ]
        parsedquery_weights = [
            w for f, w in zip(term_fields, term_weights, strict=False) if f == field
        ]
        text_tokens = doc[field]
        text_dl = len(text_tokens)
        n, parsedquery_tokens_n, avgdl = get_field_terms_statistics(
            solr_core_base_url, field, parsedquery_tokens
        )
        for parsedquery_token, pw in zip(
            parsedquery_tokens, parsedquery_weights, strict=False
        ):
            parsedquery_token_freq = text_tokens.count(parsedquery_token)
            parsedquery_token_n = parsedquery_tokens_n[parsedquery_token]
            score, _ = bm25_tfidf(
                parsedquery_token_n, n, parsedquery_token_freq, text_dl, avgdl
            )
            tokens_scores.append(score * pw)
    return sum(tokens_scores)
