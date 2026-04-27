"""Serviços de buscas de citações."""

import re

from api_sei.db_models.get_content_lazy import get_doc_content_lazy
from api_sei.db_models.solr_select import SolrRequests
from api_sei.envs import SOLR_ADDRESS, SOLR_MLT_JURISPRUDENCE_CORE, auth


def get_doc_content(id_document: int) -> str:
    """Busca o conteúdo de um documento no core de jurisprudência do Solr.

    Args:
        id_document (int): O ID do documento a ser buscado.

    Returns:
        str: O conteúdo do documento se encontrado, ou None caso contrário.
    """
    content = SolrRequests.select(
        url=f"{SOLR_ADDRESS}/solr/{SOLR_MLT_JURISPRUDENCE_CORE}/select?q=id_document:{id_document}&fl=content",
        nested_fields=["response", "docs"],
        auth=auth,
    )

    return content[0].get("content", None)


def get_docs_in_doc(content: str) -> list:
    """Busca IDs de documentos em um texto.

    O texto é scanneado procurando por sequências de 7 dígitos que estejam
    rodeadas por caracteres não numéricos. Essas sequências são supostas serem
    IDs de documentos que fazem parte da citação.

    Args:
        content (str): O texto a ser scanneado.

    Returns:
        list: Uma lista de strings com os IDs de documento encontrados.
    """
    return re.findall(r"(?:(?<=[^0-9])|(?<=^))[0-9]{7}(?=[^0-9]|$)", content.lower())


def get_regex_citations(content: str, max_words: int = 15) -> list:
    """Busca sequências de palavras que iniciem com "resolução" ou "acórdão" e tenham no máximo {max_words} palavras.

    Args:
        content (str): O texto a ser scanneado.
        max_words (int, optional): O número máximo de palavras que as sequências devem ter.

    Returns:
        list: Uma lista de tuplas, onde cada tupla contém a sequência de
        palavras encontrada e a posição de início da sequência no texto.
    """
    citations = []
    for match in re.finditer(
        r"(?=((resolu[çc][aã]o|ac[oó]rd[aã]o)\s([^\s]*(?:\s|$)){"
        + re.escape(str(max_words))
        + "}))",
        content,
    ):
        start, _ = match.span(1)
        citations.append((match.group(1), start))

    return citations


def get_regex_citations2(content: str, max_words: int = 15) -> list:
    """Busca sequências de palavras que iniciem com "resolução" ou "acórdão" e tenham no máximo {max_words} palavras.

    Args:
        content (str): O texto a ser scanneado.
        max_words (int, optional): O número máximo de palavras que as sequências devem ter.

    Returns:
        list: Uma lista de tuplas, onde cada tupla contém a sequência de
        palavras encontrada e a posição de início da sequência no texto.
    """
    citations = re.findall(
        r"((resolu[çc][aã]o|ac[oó]rd[aã]o)\s([^\s]*\s){"
        + re.escape(str(max_words))
        + "})",
        content.lower(),
    )

    return [(c[0], 0, 0) for c in citations]


def add_citations(json_doc_list: list) -> list:
    """Adiciona campo "citations" em cada documento de uma lista com ids de documentos que o documento cita.

    O campo "citations" é uma lista de tuplas, onde cada tupla contém a
    sequência de palavras encontrada e a posição de início da sequência no
    texto.

    A ordem de documento é alterada para que os documentos sejam ordenados
    de forma decrescente de acordo com o score.

    Args:
        json_doc_list (list): Uma lista de dicionários com os documentos a
            ter o campo "citations" adicionado.

    Returns:
        list: A lista de dicionários com o campo "citations" adicionado.
    """
    json_doc_list_sorted = sorted(json_doc_list, key=lambda x: str(x["id_document"]))
    id_list = sorted(
        [str(doc_data["id_document"]) for doc_data in json_doc_list_sorted]
    )
    contents = sorted(
        get_doc_content_lazy(list_id_docs=id_list, raw=True),
        key=lambda x: str(x["id_document"]),
    )

    for i, doc_data in enumerate(json_doc_list_sorted):
        content_list = get_regex_citations(contents[i]["content"].lower(), max_words=15)

        doc_data["citations"] = content_list

    return sorted(json_doc_list_sorted, key=lambda x: str(x["score"]), reverse=True)
