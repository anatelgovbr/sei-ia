"""LDA Resource."""

from gensim import corpora
from gensim.models import LdaModel


def get_words_one_topic(
    documents: list, num_topics: int = 1, n_words: int = 10
) -> list:
    """Obtain the words for a single topic based on the provided list of documents.

    Parameters:
        documents (list): A list of documents.
        num_topics (int): The number of topics to extract (default is 1).
        n_words (int): The number of words to include in the topic (default is 10).

    Returns:
        list: A list of words representing the topic.
    """
    documents = [s for s in documents if s and any(word.strip() for word in s)]

    if not documents:
        return []

    dictionary = corpora.Dictionary(documents)
    corpus = [dictionary.doc2bow(word) for word in documents]
    lda_model = LdaModel(corpus, num_topics=1, id2word=dictionary, random_state=42)

    topic_words = lda_model.print_topics(num_topics=num_topics, num_words=n_words)
    topic_words = topic_words[0][1].split('"')[1::2]

    return list(set(topic_words))
