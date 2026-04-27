import re

from api_sei.resources.tokenizers_and_filters import solr_preprocessing


def get_parsedquery_from_string(s):
    s_list = solr_preprocessing(s)

    # Remove duplicados
    s_list = list(set(s_list))

    # Remove tokens vazios
    s_list = [token for token in s_list if token and token.strip()]

    # Se não houver tokens válidos, retorna string vazia
    if not s_list:
        return ""

    # Formata
    parsedquery = "content:" + re.sub(r"[ ]", " content:", " ".join(s_list).strip())

    return parsedquery


def merge_unweighted_parsed_queries(pq_list, weights=None):
    if not isinstance(pq_list, list):
        raise ValueError("pq_list must be a list")
    if (weights is not None) and (not isinstance(weights, list)):
        raise ValueError("weights must be None or a list")
    if (weights is not None) and (len(weights) != len(pq_list)):
        raise ValueError("weights must be the same length as pq_list")

    merged_pq_list = []

    for i, pq in enumerate(pq_list):
        # Pula queries vazias
        if not pq or not pq.strip():
            continue

        word_list = pq.split()
        # Filtra palavras vazias
        word_list = [
            word
            for word in word_list
            if word and word.strip() and not word.endswith(":")
        ]

        total = len(word_list)
        if total == 0:
            continue

        weight = 1 / total if weights is None else weights[i]

        for word in word_list:
            weighted = word + "^" + f"{weight:.4f}"
            merged_pq_list.append(weighted)

    merged_pq = " ".join(merged_pq_list)

    return merged_pq
