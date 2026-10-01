"""Azure embedding provider."""

import logging
from typing import ClassVar

import httpx
import tiktoken
from openai import AsyncAzureOpenAI

from sei_ia.configs.settings_config import settings
from sei_ia.services.embedder.input_validation import ensure_embedding_input
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

    _DEPLOYMENT_CACHE: ClassVar[dict[str, str]] = {}

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

        self.endpoint = endpoint
        self.api_key = api_key or "dummy-key"

        # Detecta se está usando Azure direto ou proxy
        self.is_proxy = "openai.azure.com" not in endpoint

        # tokenizer_model é resolvido lazy via property — não dispara rede no __init__
        # (importante pra contextos sem proxy disponível, como CI de testes unitários)

        if self.is_proxy:
            # Modo proxy: usa OpenAI genérico
            from openai import OpenAI

            self.client = OpenAI(
                base_url=endpoint,
                api_key=self.api_key,
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
                api_key=self.api_key,
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

    @property
    def tokenizer_model(self) -> str:
        """Nome do modelo para uso com tiktoken, resolvido lazy via _resolve_base_model.

        Não dispara rede até a primeira leitura. O resultado é cacheado em nível
        de classe pela própria _resolve_base_model.
        """
        return self._resolve_base_model(self.model, self.endpoint, self.api_key)

    @classmethod
    def _resolve_base_model(
        cls, model: str, endpoint: str, api_key: str | None = None
    ) -> str:
        """Resolve o nome real do modelo para uso com tiktoken.

        Resolução em ordem:
        1. ``model`` direto, se tiktoken já reconhecer.
        2. Header ``llm_provider-x-ms-deployment-name`` de uma chamada minimal
           a ``/v1/embeddings``. O LiteLLM upstream propaga esse header com o
           nome real do deployment Azure (ex: 'text-embedding-3-small').

        O resultado é cacheado em nível de classe (chave: endpoint|model), de
        forma que múltiplas instâncias com a mesma configuração compartilham
        a descoberta — só o primeiro acesso no processo paga a chamada HTTP.

        Args:
            model: Nome do modelo (pode ser alias do LiteLLM, ex: "embedding").
            endpoint: URL do LiteLLM proxy.
            api_key: Chave de autenticação do proxy.

        Returns:
            Nome real do modelo para uso com tiktoken.
        """
        cache_key = f"{endpoint}|{model}"
        cached = cls._DEPLOYMENT_CACHE.get(cache_key)
        if cached is not None:
            return cached

        try:
            tiktoken.encoding_for_model(model)
            cls._DEPLOYMENT_CACHE[cache_key] = model
            return model  # noqa: TRY300
        except KeyError:
            pass

        # Fallback tiktoken quando o alias do proxy (ex.: 'seiia-ds-embedding') nao e
        # conhecido pelo tiktoken: um modelo OpenAI-compativel cujo encoding e o mesmo
        # da familia de embeddings. O tokenizer_model so alimenta a CONTAGEM de tokens
        # (chunking), nunca os vetores — logo assumir aqui e seguro se a resolucao via
        # header nao for possivel.
        fallback_model = "text-embedding-3-small"

        # Tenta descobrir o deployment real via header que o LiteLLM propaga. Se o
        # proxy nao expuser esse header (nao configurado) OU a chamada falhar (auth,
        # rede), NAO bloqueia a indexacao: cai no fallback tiktoken acima, com aviso.
        try:
            resp = httpx.post(
                f"{endpoint}/v1/embeddings",
                json={"model": model, "input": "a"},
                headers={"Authorization": f"Bearer {api_key or 'dummy-key'}"},
                timeout=15.0,
            )
            resp.raise_for_status()
            deployment = resp.headers.get("llm_provider-x-ms-deployment-name")
            if deployment:
                logging.info(
                    f"Modelo '{model}' resolvido para deployment '{deployment}' via header"
                )
            else:
                logging.warning(
                    f"LiteLLM nao retornou 'llm_provider-x-ms-deployment-name' para "
                    f"'{model}'; assumindo tiktoken de '{fallback_model}'."
                )
        except Exception as e:  # noqa: BLE001 — resolucao e best-effort; ver fallback
            logging.warning(
                f"Nao foi possivel resolver o deployment de '{model}' via LiteLLM "
                f"({type(e).__name__}: {e}); assumindo tiktoken de '{fallback_model}'."
            )
            deployment = None

        resolved = deployment or fallback_model
        cls._DEPLOYMENT_CACHE[cache_key] = resolved
        return resolved

    def _tokenizer_libname(self) -> str:
        """Retorna o nome da biblioteca do tokenizador."""
        return "tiktoken"

    def get_tokenizer(self, model_name: str | None = None) -> tiktoken.core.Encoding:  # noqa: ARG002  # NOSONAR
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
        ensure_embedding_input(texts)
        try:
            embeddings = []
            if isinstance(texts, str):
                texts = [texts]
            response = self.client.embeddings.create(
                input=texts, model=self.model, extra_body={"tags": ["agents:embedding"]}
            )
            embeddings = [item.embedding for item in response.data]

        except (httpx.HTTPStatusError, openai.RateLimitError) as err:
            raise HTTPException413 from err

        except Exception:
            logging.exception("Erro ao gerar embeddings com Azure OpenAI.")
        return embeddings

    def test_connection(self) -> bool:
        """Verifica que o LiteLLM Proxy está alcançável.

        Modo proxy: HTTP GET /health/liveliness (sem custo, sem upstream).
        Modo Azure direto: skip — não há endpoint barato equivalente.
        """
        if not self.is_proxy:
            return True
        try:
            resp = httpx.get(
                f"{self.endpoint}/health/liveliness",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5.0,
            )
            resp.raise_for_status()
            logging.info("LiteLLM Proxy alcançável em %s", self.endpoint)
            return True  # noqa: TRY300
        except Exception:
            logging.exception("Falha ao alcançar LiteLLM Proxy em %s", self.endpoint)
            return False
