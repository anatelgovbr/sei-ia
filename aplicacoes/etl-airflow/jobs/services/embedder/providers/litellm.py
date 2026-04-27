"""LiteLLM proxy embedding provider."""

import logging

import httpx
import tiktoken

from jobs.services.embedder.providers.provider_interface import EmbeddingProvider

try:
    import openai
    from openai import AsyncOpenAI, OpenAI
except ImportError:
    OpenAI = None
    AsyncOpenAI = None


class LiteLLMEmbeddingProvider(EmbeddingProvider):
    """Classe para prover embeddings via LiteLLM proxy."""

    def __init__(
        self,
        base_url: str,
        model: str,
        base_model: str | None = None,
        api_key: str | None = None,
        max_context_size: int = 8191,
        timeout_api: int = 900,
    ) -> None:
        """Inicializa a classe.

        Args:
            base_url: URL base do LiteLLM proxy (ex: http://localhost:4000)
            model: Nome do modelo configurado no LiteLLM proxy (ex: "embedding")
            base_model: Nome do modelo base para tiktoken (ex: "text-embedding-3-small")
            api_key: Chave de API para autenticação no proxy (opcional)
            max_context_size: Tamanho máximo do contexto
            timeout_api: Timeout para requisições assíncronas
        """
        if OpenAI is None:
            msg = "Não foi possível importar o pacote openai. Verifique se está instalado."
            raise ImportError(msg)

        self.model = model
        self.base_model = base_model or "text-embedding-3-small"
        self.max_context_size = max_context_size * 0.99

        # Cliente síncrono para o LiteLLM proxy
        self.client = OpenAI(
            base_url=f"{base_url}/v1",
            api_key=api_key or "dummy-key",  # LiteLLM pode não requerer API key
        )

        self.test_connection()
        self.tokenizer_type = self._tokenizer_libname()

        # Configura timeout para o cliente assíncrono
        timeout_config = httpx.Timeout(
            connect=30.0,  # Timeout de conexão
            read=timeout_api,  # Timeout de leitura
            write=30.0,  # Timeout de escrita
            pool=10.0,  # Timeout do pool
        )

        # Cliente assíncrono para o LiteLLM proxy
        self.async_client = AsyncOpenAI(
            base_url=f"{base_url}/v1",
            api_key=api_key or "dummy-key",
            max_retries=0,  # Retry será gerenciado pelo backoff decorator
            timeout=timeout_config,
        )

    def _tokenizer_libname(self) -> str:
        """Retorna o nome da biblioteca do tokenizador."""
        return "tiktoken"

    def get_tokenizer(self) -> tiktoken.core.Encoding:
        """Retorna o tokenizador."""
        try:
            encoding = tiktoken.encoding_for_model(self.base_model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        return encoding

    def apply_tokenizer(self, texts: str | list[str]) -> list[list[int]]:
        """Aplica o tokenizador para uma lista de textos.

        Args:
            texts (str | list[str]): Texto ou lista de textos para aplicar o tokenizador.

        Return:
            list[list[int]]: Lista de tokens gerados.
        """
        tokenizer = self.get_tokenizer()
        if isinstance(texts, str):
            texts = [texts]
        return [tokenizer.encode(text) for text in texts]

    def generate_embeddings(self, texts: str | list[str]) -> list[list[float]]:
        """Gera embeddings para uma lista de textos.

        Args:
            texts (str | list[str]): Texto ou lista de textos para gerar embeddings.

        Returns:
            list[list[float]]: Lista de embeddings gerados.
        """
        try:
            embeddings = []
            if isinstance(texts, str):
                texts = [texts]
            response = self.client.embeddings.create(input=texts, model=self.model)
            embeddings = [item.embedding for item in response.data]

        except (httpx.HTTPStatusError, openai.RateLimitError) as err:
            logging.exception(f"Erro de rate limit ou HTTP ao gerar embeddings: {err}")
            raise

        except Exception:
            logging.exception("Erro ao gerar embeddings com LiteLLM proxy.")
            raise
        return embeddings

    def test_connection(self) -> bool:
        """Testa a conexão com o LiteLLM proxy."""
        try:
            test_text = "Teste de conexão."
            self.generate_embeddings(test_text)
            logging.info("Conexão com LiteLLM proxy bem-sucedida.")
            return True
        except Exception:
            logging.exception("Falha na conexão com LiteLLM proxy.")
            return False
