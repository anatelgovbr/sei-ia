"""Modulo que define a interface para os provedores de embeddings."""

from abc import ABC, abstractmethod

import tiktoken


class EmbeddingProvider(ABC):
    """Classe para interface provedores de embeddings."""

    @abstractmethod
    def generate_embeddings(self, texts: str | list[str]) -> list[list[float]]:
        """Gera embeddings para um dado texto."""

    @abstractmethod
    def _tokenizer_libname(self) -> str:
        """Obtém o nome da biblioteca do tokenizador."""

    @abstractmethod
    def test_connection(self) -> bool:
        """Testa a conexão com o serviço de embeddings."""

    @abstractmethod
    def get_tokenizer(self, model_name: str) -> tiktoken.core.Encoding:
        """Obtém o tokenizador para o modelo especificado."""

    @abstractmethod
    def apply_tokenizer(self, texts: str | list[str]) -> list[list[int]]:
        """Aplica o tokenizador aos textos e retorna os tokens."""
