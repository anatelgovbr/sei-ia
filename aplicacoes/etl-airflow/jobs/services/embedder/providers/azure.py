"""Azure embedding provider."""

import logging

import httpx
import tiktoken
from openai import AsyncAzureOpenAI

from jobs.envs import EMBEDDING_API_VERSION
from jobs.services.embedder.providers.provider_interface import EmbeddingProvider

try:
    import openai
    from openai import AsyncAzureOpenAI, AzureOpenAI
except ImportError:
    AzureOpenAI = None
    AsyncAzureOpenAI = None


class AzureOpenAIEmbeddingProvider(EmbeddingProvider):
    """Classe para prover embeddings com Azure OpenAI."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        model: str,
        max_context_size: int = 8191,
        timeout_api: int = 900,
    ) -> None:
        """Inicializa a classe."""
        if AzureOpenAI is None:
            msg = "Não foi possível importar o pacote openai. Verifique se está instalado."
            raise ImportError(msg)
        self.model = model
        self.client = AzureOpenAI(
            api_key=api_key, api_version=EMBEDDING_API_VERSION, azure_endpoint=endpoint
        )
        self.model = model
        self.max_context_size = max_context_size * 0.99
        self.test_connection()
        self.tokenizer_type = self._tokenizer_libname()

        # Configura timeout para o cliente assíncrono
        timeout_config = httpx.Timeout(
            connect=30.0,  # Timeout de conexão
            read=timeout_api,  # Timeout de leitura
            write=30.0,  # Timeout de escrita
            pool=10.0,  # Timeout do pool
        )

        self.async_client = AsyncAzureOpenAI(
            api_key=api_key,
            api_version=EMBEDDING_API_VERSION,
            azure_endpoint=endpoint,
            max_retries=0,  # Retry será gerenciado pelo backoff decorator
            timeout=timeout_config,
        )

    def _tokenizer_libname(self) -> str:
        """Retorna o nome da biblioteca do tokenizador."""
        return "tiktoken"

    def get_tokenizer(self) -> tiktoken.core.Encoding:
        """Retorna o tokenizador."""
        try:
            encoding = tiktoken.encoding_for_model(self.model)
        except KeyError as err:
            msg = f"Não foi encontrado o tokenizer para o modelo {self.model}."
            raise KeyError(msg) from err
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
            logging.exception("Erro ao gerar embeddings com Azure OpenAI.")
            raise
        return embeddings

    def test_connection(self) -> bool:
        """Testa a conexão com o Azure OpenAI."""
        try:
            test_text = "Teste de conexão."
            self.generate_embeddings(test_text)
            logging.info("Conexão com Azure OpenAI bem-sucedida.")
            return True
        except Exception:
            logging.exception("Falha na conexão com Azure OpenAI.")
            return False
