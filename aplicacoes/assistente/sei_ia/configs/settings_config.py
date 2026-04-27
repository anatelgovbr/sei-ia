"""Modulo responsavel por carregar as variaveis de ambiente."""

import os
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import quote

import urllib3
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from requests.auth import HTTPBasicAuth

# Desabilita os warnings de verificação de certificados SSL, pois estamos utilizando certificados auto-assinados
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Settings(BaseSettings):
    """Configurações da aplicação usando pydantic-settings."""

    # Path configurações
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )
    BASE_DIR: ClassVar[str] = str(Path(__file__).parent.parent.resolve())

    # Informações da aplicação
    APP_NAME: str = "SEI-IA Assistant"
    VERSION: str = "1.0"
    ENVIRONMENT: str = "prod"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Assistente"
    PORT: int = Field(8088, alias="ASSISTENTE_PORT")
    WORKERS: int = 2
    MAX_REQUESTS: int = Field(200, alias="ASSISTENTE_MAX_REQUESTS")
    MAX_REQUESTS_JITTER: int = Field(50, alias="ASSISTENTE_MAX_REQUESTS_JITTER")
    KEEPALIVE: int = 5
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # Configurações de testes
    TESTS_ID_DOC_EXT: str | None = Field(None, alias="ASSISTENTE_TESTS_ID_DOC_EXT")
    TESTS_ID_DOC_INT: str | None = Field(None, alias="ASSISTENTE_TESTS_ID_DOC_INT")
    TESTS_DATA_FILENAME: str = Field(
        "/app/sei_ia/routers/tests/tests_input_data.json",
        alias="ASSISTENTE_TESTS_DATA_FILENAME",
    )

    # Configurações de timeout
    TIMEOUT_GET_DOC: int = Field(120, alias="ASSISTENTE_TIMEOUT_GET_DOC")
    TIMEOUT_API: int = Field(900, alias="ASSISTENTE_TIMEOUT_API")
    REQUEST_TIMEOUT: int = 30
    STREAMING_HEARTBEAT_INTERVAL: int = Field(
        30, alias="ASSISTENTE_STREAMING_HEARTBEAT_INTERVAL"
    )

    # Configurações de valores fator que regulam limites o tamanho limite de contexto
    FACTOR_MAX_INPUT: float = Field(0.95, alias="ASSISTENTE_FACTOR_MAX_INPUT")
    FACTOR_LIMIT_RAG: float = Field(4.0, alias="ASSISTENTE_FATOR_LIMITAR_RAG")

    # Configurações de RAG
    TOP_K_DOCUMENTS: int = 5
    MIN_SIMILARITY: float = 0.3
    N_QUESTIONS: int = Field(
        5, alias="ASSISTENTE_N_QUESTIONS"
    )  # Número de perguntas adicionais a gerar no rag enhanced

    # Configurações de parse de planilhas (Excel/ODS)
    MAX_ROWS_PER_SHEET: int = Field(
        1000, alias="ASSISTENTE_MAX_ROWS_PER_SHEET"
    )  # Limite de linhas por aba (ajustável via variável de ambiente)
    MAX_SHEETS_TO_PROCESS: int = Field(
        10, alias="ASSISTENTE_MAX_SHEETS_TO_PROCESS"
    )  # Limite de abas a processar (ajustável via variável de ambiente)

    # Configurações de sumarização
    SUMMARIZE_TOKENS_LIMIT_MULTIPLIER: float = Field(
        5.0, alias="ASSISTENTE_SUMMARIZE_TOKENS_LIMIT_MULTIPLIER"
    )
    SUMMARIZE_MODEL: str = Field("mini", alias="ASSISTENTE_SUMMARIZE_MODEL")
    SUMMARIZE_TEMPERATURE: float = 0.1
    SUMMARIZE_ENCODING_NAME: str = Field(
        "o200k_base", alias="ASSISTENTE_SUMMARIZE_ENCODING_NAME"
    )
    SUMMARIZE_CHUNK_SIZE: int = Field(16000, alias="ASSISTENTE_SUMMARIZE_CHUNK_SIZE")
    SUMMARIZE_CHUNK_MAX_OUTPUT: int = Field(
        4000, alias="ASSISTENTE_SUMMARIZE_CHUNK_MAX_OUTPUT"
    )

    # Configurações do Solr da aplicação
    SOLR_ADDRESS: str
    SOLR_USER: str
    SOLR_PASSWORD: str

    # Configurações de banco de dados da aplicação SEI-IA
    DB_SEIIA_HOST: str
    DB_SEIIA_PORT: str
    DB_SEIIA_USER: str
    DB_SEIIA_PWD: str
    DB_SEIIA_ASSISTENTE: str = "SEI_LLM"
    DB_SEIIA_ASSISTENTE_SCHEMA: str = "sei_llm"
    DB_SEIIA_POOL_MIN_SIZE: int = 1
    DB_SEIIA_POOL_MAX_SIZE: int = 10

    # Configurações de monitoramento
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_URL: str | None = None
    USE_LANGFUSE: bool = Field(default=False, alias="ASSISTENTE_USE_LANGFUSE")

    # Configurações de logging
    LOG_LEVEL: str = "ERROR"
    RLM_REPORTER: bool = Field(default=False, alias="ASSISTENTE_RLM_REPORTER")
    # ENABLE_SOLR_LOGGING: bool = Field(default=True, alias="ASSISTENTE_ENABLE_SOLR_LOGGING")  # REMOVIDO - não usado mais

    # Configurações do Redis Cache
    REDIS_URI: str = Field("redis://redis_cache:6379/0", alias="ASSISTENTE_REDIS_URI")

    # Configurações de cache
    CACHE_ENABLED: bool = Field(True, alias="ASSISTENTE_CACHE_ENABLED")
    CACHE_TTL_SECONDS: int = Field(259200, alias="ASSISTENTE_CACHE_TTL_SECONDS")  # 72h
    CACHE_MAX_CONNECTIONS: int = Field(100, alias="ASSISTENTE_CACHE_MAX_CONNECTIONS")
    CACHE_RETRY_ON_TIMEOUT: bool = Field(
        True, alias="ASSISTENTE_CACHE_RETRY_ON_TIMEOUT"
    )
    CACHE_SOCKET_TIMEOUT: float = Field(5.0, alias="ASSISTENTE_CACHE_SOCKET_TIMEOUT")
    CACHE_CONNECTION_TIMEOUT: float = Field(
        5.0, alias="ASSISTENTE_CACHE_CONNECTION_TIMEOUT"
    )

    # Configurações de serialização do cache
    CACHE_COMPRESS: bool = Field(
        True, alias="ASSISTENTE_CACHE_COMPRESS"
    )  # Usar compressão gzip
    CACHE_KEY_PREFIX: str = Field("seiia:doc:", alias="ASSISTENTE_CACHE_KEY_PREFIX")
    CACHE_VERSION: str = Field(
        "v1", alias="ASSISTENTE_CACHE_VERSION"
    )  # Versão do formato de cache

    # Configurações do modelo de embeddings
    EMBEDDING_MODEL: str = Field(
        "text-embedding-3-small", alias="ASSISTENTE_EMBEDDING_MODEL"
    )
    EMBEDDING_ENCODING_NAME: str = Field(
        "o200k_base", alias="ASSISTENTE_EMBEDDING_ENCODING_NAME"
    )
    EMBEDDING_DIMENSION: int = Field(1536, alias="ASSISTENTE_EMBEDDING_DIMENSION")
    MAX_LENGTH_CHUNK_SIZE: int = Field(1512, alias="ASSISTENTE_MAX_LENGTH_CHUNK_SIZE")
    CHUNK_OVERLAP: int = Field(50, alias="ASSISTENTE_CHUNK_OVERLAP")
    EMBEDDINGS_MAX_CONCURRENCY: int = Field(
        20, alias="ASSISTENTE_EMBEDDINGS_MAX_CONCURRENCY"
    )

    # Deprecated - embeddings agora sempre usam o proxy
    # EMBEDDING_PROVIDER: str = Field("azure", alias="ASSISTENTE_EMBEDDING_PROVIDER")
    # EMBEDDING_API_KEY: str = Field(..., alias="ASSISTENTE_EMBEDDING_API_KEY")
    # EMBEDDING_ENDPOINT: str = Field(..., alias="ASSISTENTE_EMBEDDING_ENDPOINT")

    # Configurações do LiteLLM Proxy
    LITELLM_PROXY_URL: str = Field(
        "http://localhost:4000", alias="ASSISTENTE_LITELLM_PROXY_URL"
    )
    LITELLM_PROXY_API_KEY: str | None = Field(
        None, alias="ASSISTENTE_LITELLM_PROXY_API_KEY"
    )

    # Aliases dos modelos no LiteLLM Proxy (devem coincidir com model_name no litellm_config)
    LITELLM_STANDARD_MODEL_NAME: str = Field(
        "standard", alias="ASSISTENTE_LITELLM_STANDARD_MODEL_NAME"
    )
    LITELLM_MINI_MODEL_NAME: str = Field(
        "mini", alias="ASSISTENTE_LITELLM_MINI_MODEL_NAME"
    )
    LITELLM_NANO_MODEL_NAME: str = Field(
        "nano", alias="ASSISTENTE_LITELLM_NANO_MODEL_NAME"
    )
    LITELLM_THINK_MODEL_NAME: str = Field(
        "think", alias="ASSISTENTE_LITELLM_THINK_MODEL_NAME"
    )
    LITELLM_EMBEDDING_MODEL_NAME: str = Field(
        "embedding", alias="ASSISTENTE_LITELLM_EMBEDDING_MODEL_NAME"
    )
    LITELLM_STT_MODEL_NAME: str = Field(
        "speech-to-text", alias="ASSISTENTE_LITELLM_STT_MODEL_NAME"
    )

    # Nomes reais dos modelos (base_model no litellm_config, preenchidos pelo CI/CD)
    LITELLM_STANDARD_MODEL: str = Field("", alias="LITELLM_STANDARD_MODEL")
    LITELLM_MINI_MODEL: str = Field("", alias="LITELLM_MINI_MODEL")
    LITELLM_NANO_MODEL: str = Field("", alias="LITELLM_NANO_MODEL")

    # Configurações OpenAI/Azure
    OPENAI_API_VERSION: str = "2024-10-21"
    DEFAULT_RESPONSE_MODEL: str = Field(
        "standard", alias="ASSISTENTE_DEFAULT_RESPONSE_MODEL"
    )
    MAX_RETRIES: int = Field(
        5, alias="ASSISTENTE_MAX_RETRIES"
    )  # Aumentado de 3 para 5 para melhor recuperação de falhas de rede

    # ===================================================================
    # DEPRECATED: Variáveis abaixo não são mais utilizadas após migração
    # para LiteLLM Proxy. Comentadas para não serem mais carregadas.
    # Use LITELLM_PROXY_URL ao invés.
    # ===================================================================

    # API Keys e Endpoints (não mais utilizados - proxy gerencia)
    # API_KEY_STANDARD_MODEL: str = Field(..., alias="ASSISTENTE_API_KEY_STANDARD_MODEL")
    # ENDPOINT_STANDARD_MODEL: str = Field(
    #     ..., alias="ASSISTENTE_ENDPOINT_STANDARD_MODEL"
    # )
    # NAME_STANDARD_MODEL: str = Field(..., alias="ASSISTENTE_NAME_STANDARD_MODEL")

    # API_KEY_MINI_MODEL: str = Field(..., alias="ASSISTENTE_API_KEY_MINI_MODEL")
    # ENDPOINT_MINI_MODEL: str = Field(..., alias="ASSISTENTE_ENDPOINT_MINI_MODEL")
    # NAME_MINI_MODEL: str = Field(..., alias="ASSISTENTE_NAME_MINI_MODEL")

    # API_KEY_NANO_MODEL: str = Field("", alias="ASSISTENTE_API_KEY_NANO_MODEL")
    # ENDPOINT_NANO_MODEL: str = Field("", alias="ASSISTENTE_ENDPOINT_NANO_MODEL")
    # NAME_NANO_MODEL: str = Field("", alias="ASSISTENTE_NAME_NANO_MODEL")

    # API_KEY_THINK_MODEL: str = Field("", alias="ASSISTENTE_API_KEY_THINK_MODEL")
    # ENDPOINT_THINK_MODEL: str = Field("", alias="ASSISTENTE_ENDPOINT_THINK_MODEL")
    # NAME_THINK_MODEL: str = Field("", alias="ASSISTENTE_NAME_THINK_MODEL")

    # Context Length (ainda usados para cálculo interno de limites de memória)
    CTX_LEN_STANDARD_MODEL: int = Field(
        250_000, alias="ASSISTENTE_CTX_LEN_STANDARD_MODEL"
    )
    CTX_LEN_MINI_MODEL: int = Field(250_000, alias="ASSISTENTE_CTX_LEN_MINI_MODEL")
    CTX_LEN_NANO_MODEL: int = Field(128_000, alias="ASSISTENTE_CTX_LEN_NANO_MODEL")
    CTX_LEN_THINK_MODEL: int = Field(128_000, alias="ASSISTENTE_CTX_LEN_THINK_MODEL")

    # ===================================================================
    # Output Tokens - AINDA UTILIZADOS (mantidos)
    # ===================================================================
    OUTPUT_TOKENS_STANDARD_MODEL: int = Field(
        32_768, alias="ASSISTENTE_OUTPUT_TOKENS_STANDARD_MODEL"
    )
    OUTPUT_TOKENS_MINI_MODEL: int = Field(
        32_000, alias="ASSISTENTE_OUTPUT_TOKENS_MINI_MODEL"
    )
    OUTPUT_TOKENS_NANO_MODEL: int = Field(
        30000, alias="ASSISTENTE_OUTPUT_TOKENS_NANO_MODEL"
    )
    OUTPUT_TOKENS_THINK_MODEL: int = Field(
        65_000, alias="ASSISTENTE_OUTPUT_TOKENS_THINK_MODEL"
    )

    # Configurações de memória
    MEMORY_ITERATION_LIMIT: int = 100
    MEMORY_ITERATION_TOKENS_LIMIT: int = 0
    MAX_LENGTH_CONTENT_WEBSEARCH: int = 256000
    WEBSEARCH_AGENT_MODEL: str = Field("mini", alias="ASSISTENTE_WEBSEARCH_AGENT_MODEL")
    # Configurações de rate limiting
    REQUESTS_PER_SECOND: float = Field(30.0, alias="ASSISTENTE_REQUESTS_PER_SECOND")

    # Configurações de backoff
    BACKOFF_MAX_TRIES: int = Field(99, alias="ASSISTENTE_BACKOFF_MAX_TRIES")
    BACKOFF_MAX_TIME: int = Field(240, alias="ASSISTENTE_BACKOFF_MAX_TIME")
    BACKOFF_INITIAL_WAIT: float = Field(1.0, alias="ASSISTENTE_BACKOFF_INITIAL_WAIT")
    RETRY_BACKOFF_FACTOR: float = 1

    # SSL e outros
    VERIFY_SSL: bool = Field(
        default=False,
        alias="ASSISTENTE_VERIFY_SSL",
    )

    # Configurações da API Banco de dados do SEI
    SEI_API_DB_ADDRESS: str = Field(alias="SEI_API_DB_ADDRESS")
    SEI_API_DB_IDENTIFIER_SERVICE: str = Field(
        alias="SEI_API_DB_IDENTIFIER_SERVICE",
    )
    SEI_API_DB_TIMEOUT: int = Field(
        default=120,
        alias="SEI_API_DB_TIMEOUT",
    )
    SEI_API_DB_USER: str = Field(
        default="Usuario_IA",
        alias="SEI_API_DB_USER",
    )
    SEI_API_SEMAPHORE: int = Field(
        default=30,
        alias="SEI_API_SEMAPHORE",
    )
    SEI_API_DB_CHUNK_SIZE: int = Field(
        default=100,
        alias="SEI_API_DB_CHUNK_SIZE",
    )

    ENABLE_OTEL_METRICS: bool = False

    # Configurações derivadas
    APP_SOLR_ADDRESS: str = Field(..., alias="SOLR_ADDRESS")
    # APP_SOLR_CORE: dict[str, str] = {"log_api": "assistente_log_api"}  # REMOVIDO - não usado mais
    APP_SOLR_USER: str = Field(..., alias="SOLR_USER")
    APP_SOLR_PASSWORD: str = Field(..., alias="SOLR_PASSWORD")
    EMBEDDINGS_TABLE_NAME: str = ""
    DB_SEIIA_PWD_QUOTED: str = ""
    DB_SEIIA_CONNECTION_STRING: str = ""
    PGVECTOR_CONNECTION_STRING: str = ""
    auth: Any = None
    # EMBEDDING_MODEL_CONFIG removido - o provider gerencia encoding automaticamente

    # Configurações de OCR para PDFs escaneados
    OCR_ENABLED: bool = Field(True, alias="ASSISTENTE_OCR_ENABLED")
    OCR_MIN_TEXT_THRESHOLD: int = Field(50, alias="ASSISTENTE_OCR_MIN_TEXT_THRESHOLD")
    OCR_DPI: int = Field(150, alias="ASSISTENTE_OCR_DPI")
    OCR_MAX_CONCURRENT_PAGES: int = Field(
        10, alias="ASSISTENTE_OCR_MAX_CONCURRENT_PAGES"
    )
    OCR_MODEL: str = Field("nano", alias="ASSISTENTE_OCR_MODEL")

    # web search azure
    PROJECT_ENDPOINT: str = Field(default="", alias="PROJECT_ENDPOINT")
    AZURE_WEB_AGENT_ID: str | None = Field(default="", alias="AZURE_WEB_AGENT_ID")
    BING_CONNECTION_NAME: str = Field(default="", alias="BING_CONNECTION_NAME")
    MODEL_DEPLOYMENT_NAME: str = Field(default="", alias="MODEL_DEPLOYMENT_NAME")

    def model_post_init(self, __context: dict[str, Any]) -> None:  # noqa: PYI063
        """Inicialização de valores que dependem de cálculos ou combinações de outros valores."""
        self.auth = HTTPBasicAuth(self.APP_SOLR_USER, self.APP_SOLR_PASSWORD)
        model_chunk_settings = (
            f"{self.EMBEDDING_MODEL}-{self.MAX_LENGTH_CHUNK_SIZE}-{self.CHUNK_OVERLAP}"
        )
        self.EMBEDDINGS_TABLE_NAME = model_chunk_settings.replace("-", "_")
        self.DB_SEIIA_PWD_QUOTED = quote(self.DB_SEIIA_PWD)
        self.DB_SEIIA_CONNECTION_STRING = f"postgresql://{self.DB_SEIIA_USER}:{self.DB_SEIIA_PWD_QUOTED}@{self.DB_SEIIA_HOST}:{self.DB_SEIIA_PORT}/{self.DB_SEIIA_ASSISTENTE}"
        self.PGVECTOR_CONNECTION_STRING = self.DB_SEIIA_CONNECTION_STRING

        # Define MEMORY_ITERATION_TOKENS_LIMIT como 10% do contexto do modelo default
        if "mini" in self.DEFAULT_RESPONSE_MODEL.lower():
            ctx_len = self.CTX_LEN_MINI_MODEL
        else:
            ctx_len = self.CTX_LEN_STANDARD_MODEL
        self.MEMORY_ITERATION_TOKENS_LIMIT = int(ctx_len * 0.1)


settings = Settings()
os.environ["PROJECT_ENDPOINT"] = settings.PROJECT_ENDPOINT
os.environ["BING_CONNECTION_NAME"] = settings.BING_CONNECTION_NAME
os.environ["MODEL_DEPLOYMENT_NAME"] = settings.MODEL_DEPLOYMENT_NAME
os.environ["AZURE_WEB_AGENT_ID"] = settings.AZURE_WEB_AGENT_ID
