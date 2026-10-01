import pytest
from api_sei.resources.lda import get_words_one_topic

def test_get_words_one_topic_basic():
    documents = [["human", "interface", "computer"], ["survey", "user", "computer", "system", "response", "time"]]
    result = get_words_one_topic(documents)
    assert isinstance(result, list)
    assert len(result) > 0

def test_get_words_one_topic_empty_document():
    documents = []
    result = get_words_one_topic(documents)
    assert result == []

def test_get_words_one_topic_empty_strings():
    documents = [[""], [""]]
    result = get_words_one_topic(documents)
    assert result == []

def test_get_words_one_topic_single_document():
    documents = [["test", "document"]]
    result = get_words_one_topic(documents)
    assert isinstance(result, list)
    assert len(result) > 0

def test_get_words_one_topic_multiple_topics():
    documents = [["human", "interface", "computer"], ["survey", "user", "computer", "system", "response", "time"]]
    result = get_words_one_topic(documents, num_topics=2)
    assert isinstance(result, list)
    assert len(result) > 0

def test_get_words_one_topic_n_words():
    documents = [["human", "interface", "computer"], ["survey", "user", "computer", "system", "response", "time"]]
    result = get_words_one_topic(documents, n_words=5)
    assert isinstance(result, list)
    assert len(result) > 0
    assert len(result) <= 5

if __name__ == "__main__":
    pytest.main()
