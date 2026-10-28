import pytest
from unittest.mock import Mock, patch

from api_sei.services.jurisprudence_search import merge_unweighted_parsed_queries, \
    get_parsedquery_from_string


@pytest.mark.parametrize("weights",[None,[0.2,0.8]])
def test_merge_unweighted_parsed_queries(weights):
    pq_list = ["term1 term2 term3", "term4 term5"]

    result = merge_unweighted_parsed_queries(pq_list, weights=weights)

    assert isinstance(result, str)
    assert result == "term1^0.3333 term2^0.3333 term3^0.3333 term4^0.5000 term5^0.5000" if weights is None else \
        "term1^0.2000 term2^0.2000 term3^0.2000 term4^0.8000 term5^0.8000"


@pytest.mark.parametrize("weights",[0.5,[0.5]])
def test_merge_unweighted_parsed_queries_invalid_weights(weights):
    with pytest.raises(ValueError):
        pq_list = ["term1 term2 term3", "term4 term5"]
        result = merge_unweighted_parsed_queries(pq_list, weights=weights)


def test_merge_unweighted_parsed_queries_invalid_pd_list():
    with pytest.raises(ValueError):
        pq_list = "term1 term2 term3"
        result = merge_unweighted_parsed_queries(pq_list)


def test_get_parsedquery_from_string():

    s = "Da Lei nº 1234 art. 12 temos que qualquer pessoa que faça algo errado será presa"

    expected = {"lei","art","qualquer","pesso","faca","algo","errad","pres"} # "nº" é stopword

    parsedquery = get_parsedquery_from_string(s).replace("content:","").split()

    assert set(parsedquery) == expected
