import re
from api_sei.resources.tokenizers_and_filters import PortugueseLightStemmer, remove_stopwords, solr_preprocessing, lowercase_tokenizer


def test_solr_preprocessing():

    s = "Da Lei nº 1234 art. 12 temos que qualquer pessoa que faça algo errado será presa"

    expected = {"lei","art","qualquer","pesso","faca","algo","errad","pres"} # "nº" é stopword

    s_list = solr_preprocessing(s)

    assert set(s_list) == expected


def test_solr_preprocessing_empty():

    s = ""

    expected = []

    s_list = solr_preprocessing(s)

    assert s_list == expected


def test_lowercase_tokenizer_empty():

    s = ""

    expected = []

    s_list = lowercase_tokenizer(s)

    assert s_list == expected


class TestPortugueseLightStemmer:

    def test_stem(self):
        assert PortugueseLightStemmer.stem("amigos") == "amig"
        assert PortugueseLightStemmer.stem("corações") == "coraca"

    def test_remove_suffix(self):
        assert PortugueseLightStemmer.remove_suffix("carros") == "carro"
        assert PortugueseLightStemmer.remove_suffix("andares") == "andar"

    def test_norm_feminine(self):
        assert PortugueseLightStemmer.norm_feminine("menina") == "menina"
        assert PortugueseLightStemmer.norm_feminine("rosa") == "rosa"

class TestRemoveStopwords:

    def test_remove_stopwords(self):
        input_words = ["eu", "não", "gosto", "de", "stopwords"]
        output_words = remove_stopwords(input_words)
        assert output_words == ["gosto", "stopwords"]

class TestLowercaseTokenizer:

    def test_lowercase_tokenizer(self):
        input_string = "Palavras na Língua Portuguesa!"
        output_words = lowercase_tokenizer(input_string)
        assert output_words == ["palavras", "na", "língua", "portuguesa"]

class TestSolrPreprocessing:

    def test_solr_preprocessing(self):
        input_string = "Esta é uma frase de teste com stopwords."
        output_words = solr_preprocessing(input_string)
        assert output_words == ['é', 'fras', 'test', 'stopword']
