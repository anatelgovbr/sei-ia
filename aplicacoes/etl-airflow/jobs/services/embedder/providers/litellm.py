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

    _DEPLOYMENT_CACHE: dict[str, str] = {}

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

        self.base_url = base_url
        self.model = model
        self.base_model = base_model or "text-embedding-3-small"
        self.api_key = api_key or "dummy-key"
        self.max_context_size = max_context_size * 0.99

        # Cliente síncrono para o LiteLLM proxy
        self.client = OpenAI(
            base_url=f"{base_url}/v1",
            api_key=self.api_key,
        )

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
            api_key=self.api_key,
            max_retries=0,  # Retry será gerenciado pelo backoff decorator
            timeout=timeout_config,
        )

    def _tokenizer_libname(self) -> str:
        """Retorna o nome da biblioteca do tokenizador."""
        return "tiktoken"

    @property
    def tiktoken_model_name(self) -> str:
        """Nome do modelo para uso com tiktoken.

        Resolução em ordem:
        1. ``base_model`` sem prefixo de provider, se tiktoken já reconhecer.
        2. Header ``llm_provider-x-ms-deployment-name`` de uma chamada minimal
           a ``/v1/embeddings``. Esse header só existe quando o upstream do
           LiteLLM é Azure OpenAI — quando o upstream é outro provider (ex:
           proxy Vertex), o header não vem, e isso NÃO é uma falha: cai no
           fallback tiktoken abaixo, com aviso. Mesmo padrão (e mesma robustez
           contra falha de rede/auth na sondagem) do provider equivalente em
           ``aplicacoes/assistente/sei_ia/services/embedder/providers/azure.py``
           (``_resolve_base_model``).

        O resultado é cacheado em nível de classe (chave: base_url|model), de
        forma que múltiplas instâncias com a mesma configuração compartilham
        a descoberta — só o primeiro acesso no processo paga a chamada HTTP.
        """
        cache_key = f"{self.base_url}|{self.model}"
        cached = self._DEPLOYMENT_CACHE.get(cache_key)
        if cached is not None:
            return cached

        candidate = self.base_model.split("/", 1)[-1]
        try:
            tiktoken.encoding_for_model(candidate)
            self._DEPLOYMENT_CACHE[cache_key] = candidate
            return candidate
        except KeyError:
            pass

        # Fallback tiktoken quando nem base_model nem o header do upstream Azure
        # resolvem um nome que o tiktoken reconheça. tiktoken_model_name só
        # alimenta a CONTAGEM de tokens (chunking local antes do embedding),
        # nunca os vetores em si — logo assumir aqui é seguro se a resolução via
        # header não for possível (upstream Vertex, por exemplo, nunca manda
        # esse header).
        fallback = "text-embedding-3-small"

        # Tenta descobrir o deployment real via header que o LiteLLM propaga. Se
        # o proxy não expuser esse header (upstream não é Azure) OU a chamada
        # falhar (auth, rede), NÃO bloqueia a task: cai no fallback tiktoken
        # acima, com aviso.
        try:
            resp = httpx.post(
                f"{self.base_url}/v1/embeddings",
                json={"model": self.model, "input": "a"},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=15.0,
            )
            resp.raise_for_status()
            deployment = resp.headers.get("llm_provider-x-ms-deployment-name")
            if deployment:
                logging.info(
                    f"Modelo '{self.model}' resolvido para deployment '{deployment}' via header"
                )
            else:
                logging.warning(
                    f"LiteLLM upstream não retornou header "
                    f"'llm_provider-x-ms-deployment-name' para o modelo "
                    f"'{self.model}' (provider provavelmente não é Azure); "
                    f"usando tokenizador aproximado de '{fallback}'."
                )
        except Exception as e:  # noqa: BLE001 — resolução é best-effort; ver fallback
            logging.warning(
                f"Não foi possível resolver o deployment de '{self.model}' via "
                f"LiteLLM ({type(e).__name__}: {e}); usando tokenizador "
                f"aproximado de '{fallback}'."
            )
            deployment = None

        resolved = deployment or fallback
        self._DEPLOYMENT_CACHE[cache_key] = resolved
        return resolved

    def get_tokenizer(self, model_name: str | None = None) -> tiktoken.core.Encoding:
        """Retorna o tokenizador."""
        return tiktoken.encoding_for_model(model_name or self.tiktoken_model_name)

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
            if not texts:
                logging.warning(
                    "generate_embeddings chamado com input vazio — retornando []"
                )
                return []
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
        """Verifica que o LiteLLM Proxy está alcançável."""
        try:
            resp = httpx.get(
                f"{self.base_url}/health/liveliness",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5.0,
            )
            resp.raise_for_status()
            logging.info("LiteLLM Proxy alcançável em %s", self.base_url)
            return True
        except Exception:
            logging.exception("Falha ao alcançar LiteLLM Proxy em %s", self.base_url)
            return False
