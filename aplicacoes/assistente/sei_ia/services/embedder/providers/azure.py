"""Azure embedding provider."""

import logging

import httpx
import tiktoken
from openai import AsyncAzureOpenAI

from sei_ia.configs.settings_config import settings
from sei_ia.services.embedder.providers.provider_interface import EmbeddingProvider
from sei_ia.services.exceptions.http_exceptions import HTTPException413

try:
    import openai
    from openai import AsyncAzureOpenAI, AzureOpenAI
except ImportError:
    AzureOpenAI = None
    AsyncAzureOpenAI = None


class AzureOpenAIEmbeddingProvider(EmbeddingProvider):
    """Classe para prover embeddings com Azure OpenAI ou via LiteLLM Proxy.

    Esta classe suporta dois modos de operação:
    1. Azure direto: Conecta diretamente ao Azure OpenAI
    2. LiteLLM Proxy: Conecta via proxy LiteLLM

    O modo é determinado automaticamente pelo parâmetro endpoint:
    - Se endpoint contém "openai.azure.com" → Azure direto
    - Caso contrário → LiteLLM Proxy
    """

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        model: str,
        max_context_size: int = 8191,
        api_version: str | None = None,
        encoding_name: str | None = None,
    ) -> None:
        """Inicializa a classe.

        Args:
            api_key: API key (para Azure) ou dummy key (para proxy)
            endpoint: Azure endpoint ou URL do proxy LiteLLM
            model: Nome do modelo
            max_context_size: Tamanho máximo do contexto
            api_version: Versão da API Azure (opcional, usa settings se não fornecido)
            encoding_name: Nome do encoding tiktoken (ex: "o200k_base", "cl100k_base")
        """
        if AzureOpenAI is None:
            msg = "Não foi possível importar o pacote openai. Verifique se está instalado."
            raise ImportError(msg)

        self.model = model
        self.max_context_size = max_context_size * 0.99
        self.encoding_name = encoding_name  # Encoding configurável

        # Detecta se está usando Azure direto ou proxy
        self.is_proxy = "openai.azure.com" not in endpoint

        # Resolve o nome real do modelo para uso com tiktoken
        self.tokenizer_model = self._resolve_base_model(model, endpoint)

        if self.is_proxy:
            # Modo proxy: usa OpenAI genérico
            from openai import AsyncOpenAI, OpenAI

            self.client = OpenAI(
                base_url=endpoint,
                api_key=api_key or "dummy-key",
            )

            logging.info(f"Embedding provider inicializado em modo PROXY: {endpoint}")
        else:
            # Modo Azure direto
            self.client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version or settings.OPENAI_API_VERSION,
                azure_endpoint=endpoint,
            )

            logging.info(f"Embedding provider inicializado em modo AZURE: {endpoint}")

        self.test_connection()
        self.tokenizer_type = self._tokenizer_libname()

        # Configura timeout para o cliente assíncrono
        timeout_config = httpx.Timeout(
            connect=30.0,
            read=settings.TIMEOUT_API,
            write=30.0,
            pool=10.0,
        )

        if self.is_proxy:
            # Cliente assíncrono para proxy
            from openai import AsyncOpenAI

            self.async_client = AsyncOpenAI(
                base_url=endpoint,
                api_key=api_key or "dummy-key",
                max_retries=0,
                timeout=timeout_config,
            )
        else:
            # Cliente assíncrono para Azure
            self.async_client = AsyncAzureOpenAI(
                api_key=api_key,
                api_version=api_version or settings.OPENAI_API_VERSION,
                azure_endpoint=endpoint,
                max_retries=0,
                timeout=timeout_config,
            )

    @staticmethod
    def _resolve_base_model(model: str, endpoint: str) -> str:
        """Consulta o LiteLLM proxy para resolver o base_model real a partir de um alias.

        Args:
            model: Nome do modelo (pode ser alias do LiteLLM, ex: "embedding").
            endpoint: URL do LiteLLM proxy.

        Returns:
            Nome real do modelo para uso com tiktoken. Retorna o próprio model se não
            conseguir resolver.
        """
        try:
            tiktoken.encoding_for_model(model)
            return model
        except KeyError:
            pass

        try:
            resp = httpx.get(f"{endpoint}/model/info", timeout=10.0)
            resp.raise_for_status()
            for m in resp.json().get("data", []):
                if m.get("model_name") == model:
                    base_model = m.get("model_info", {}).get("base_model", "")
                    if base_model:
                        logging.info(
                            f"Modelo '{model}' resolvido para base_model '{base_model}' via LiteLLM"
                        )
                        return base_model
        except Exception:
            logging.warning(
                f"Não foi possível resolver base_model para '{model}' via LiteLLM em {endpoint}"
            )

        return model

    def _tokenizer_libname(self) -> str:
        """Retorna o nome da biblioteca do tokenizador."""
        return "tiktoken"

    def get_tokenizer(self) -> tiktoken.core.Encoding:
        """Retorna o tokenizador.

        Se encoding_name foi configurado, usa ele diretamente.
        Caso contrário, tenta detectar automaticamente pelo nome do modelo.
        """
        # Se encoding foi explicitamente configurado, usa ele
        if self.encoding_name:
            logging.info(
                f"Usando tokenizer configurado: {self.encoding_name} para modelo {self.model}"
            )
            return tiktoken.get_encoding(self.encoding_name)

        # Caso contrário, usa o modelo resolvido via LiteLLM
        try:
            encoding = tiktoken.encoding_for_model(self.tokenizer_model)
        except KeyError:
            msg = (
                f"Não foi encontrado o tokenizer para o modelo {self.tokenizer_model}."
            )
            raise KeyError(msg) from None
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
            raise HTTPException413 from err

        except Exception:
            logging.exception("Erro ao gerar embeddings com Azure OpenAI.")
        return embeddings

    def test_connection(self) -> bool:
        """Testa a conexão com o Azure OpenAI."""
        try:
            test_text = "Teste de conexão."
            self.generate_embeddings(test_text)
            logging.info("Conexão com Azure OpenAI bem-sucedida.")
        except Exception:
            logging.exception("Falha na conexão com Azure OpenAI.")
