"""Modulo responsavel por carregar as variaveis de ambiente."""

from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import quote

import urllib3
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Nomes públicos estáveis expostos pelo LiteLLM Proxy. Os valores físicos
# configurados em LITELLM_*_MODEL continuam sendo usados pelo proxy como
# model/base_model, mas nunca substituem estes aliases nas requisições da app.
LITELLM_STANDARD_ALIAS = "standard"
LITELLM_MINI_ALIAS = "mini"
LITELLM_NANO_ALIAS = "nano"
LITELLM_EMBEDDING_ALIAS = "embedding"
LITELLM_STT_ALIAS = "speech-to-text"

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
    SUMMARIZE_MODEL: str = Field("classificador", alias="ASSISTENTE_SUMMARIZE_MODEL")
    SUMMARIZE_ENCODING_NAME: str = Field(
        "o200k_base", alias="ASSISTENTE_SUMMARIZE_ENCODING_NAME"
    )
    SUMMARIZE_CHUNK_SIZE: int = Field(16000, alias="ASSISTENTE_SUMMARIZE_CHUNK_SIZE")
    SUMMARIZE_CHUNK_MAX_OUTPUT: int = Field(
        4000, alias="ASSISTENTE_SUMMARIZE_CHUNK_MAX_OUTPUT"
    )

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
    # O default de produção limita payloads textuais no trace. Benchmarks isolados
    # podem desligar apenas esse truncamento; redaction de mídia continua ativa.
    LANGFUSE_TRUNCATE_PAYLOADS: bool = Field(
        default=True, alias="ASSISTENTE_LANGFUSE_TRUNCATE_PAYLOADS"
    )

    # Configurações de logging
    LOG_LEVEL: str = "ERROR"

    # Configurações do Redis Cache
    REDIS_URI: str = Field("redis://infra-redis:6379/0", alias="REDIS_URI")

    # Configurações de cache
    CACHE_ENABLED: bool = Field(True, alias="ASSISTENTE_CACHE_ENABLED")
    CACHE_TTL_SECONDS: int = Field(3600, alias="ASSISTENTE_CACHE_TTL_SECONDS")  # 1h
    CACHE_MAX_CONNECTIONS: int = Field(100, alias="ASSISTENTE_CACHE_MAX_CONNECTIONS")
    CACHE_POOL_WAIT_TIMEOUT: float = Field(
        5.0, alias="ASSISTENTE_CACHE_POOL_WAIT_TIMEOUT"
    )  # segundos que coroutines esperam por conexão livre antes de falhar
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

    # Cache de anexos avulsos por tópico (consulta posterior pelo agente)
    ARQUIVOS_AVULSOS_CACHE_ENABLED: bool = Field(
        True, alias="ASSISTENTE_ARQUIVOS_AVULSOS_CACHE_ENABLED"
    )
    ARQUIVOS_AVULSOS_CACHE_TTL_SECONDS: int = Field(
        3600, alias="ASSISTENTE_ARQUIVOS_AVULSOS_CACHE_TTL_SECONDS"
    )  # Cache Redis pós-processamento: 1h. Não altera o TTL do upload-fonte no SEI.
    ARQUIVOS_AVULSOS_CACHE_KEY_PREFIX: str = Field(
        "seiia:topic_attachments:",
        alias="ASSISTENTE_ARQUIVOS_AVULSOS_CACHE_KEY_PREFIX",
    )

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
    # EMBEDDING_PROVIDER: str = Field("azure", alias="ASSISTENTE_EMBEDDING_PROVIDER")  # noqa: ERA001  # NOSONAR
    # EMBEDDING_API_KEY: str = Field(..., alias="ASSISTENTE_EMBEDDING_API_KEY")  # noqa: ERA001  # NOSONAR
    # EMBEDDING_ENDPOINT: str = Field(..., alias="ASSISTENTE_EMBEDDING_ENDPOINT")  # noqa: ERA001  # NOSONAR

    # Configurações do LiteLLM Proxy
    LITELLM_PROXY_URL: str = Field(
        "http://localhost:4000", alias="ASSISTENTE_LITELLM_PROXY_URL"
    )
    LITELLM_PROXY_API_KEY: str | None = Field(
        None, alias="ASSISTENTE_LITELLM_PROXY_API_KEY"
    )

    # Nomes físicos configurados como model/base_model no LiteLLM Proxy.
    # As requisições usam os aliases públicos fixos definidos acima.
    LITELLM_STANDARD_MODEL: str = Field("", alias="LITELLM_STANDARD_MODEL")
    LITELLM_MINI_MODEL: str = Field("", alias="LITELLM_MINI_MODEL")
    LITELLM_NANO_MODEL: str = Field("", alias="LITELLM_NANO_MODEL")
    # base_model canônico do embedding (mesma var que configura o litellm_config e o ETL).
    # É a fonte do nome da tabela de embeddings — NÃO usar o alias EMBEDDING_MODEL.
    LITELLM_EMBEDDING_MODEL: str = Field("", alias="LITELLM_EMBEDDING_MODEL")
    LITELLM_STT_MODEL: str = Field("", alias="LITELLM_STT_MODEL")

    # Configurações OpenAI/Azure
    OPENAI_API_VERSION: str = "2024-10-21"
    DEFAULT_RESPONSE_MODEL: str = Field(
        "principal", alias="ASSISTENTE_DEFAULT_RESPONSE_MODEL"
    )
    MAX_RETRIES: int = Field(
        5, alias="ASSISTENTE_MAX_RETRIES"
    )  # Aumentado de 3 para 5 para melhor recuperação de falhas de rede

    # ===================================================================
    # DEPRECATED: Variáveis abaixo não são mais utilizadas após migração
    # para LiteLLM Proxy. Comentadas para não serem mais carregadas.
    # Use LITELLM_PROXY_URL ao invés.
    # ===================================================================

    # Context Length (limites de memória + fallback do ModelProfile da sessão).
    # Default 1M alinhado ao default.env; declare o valor real da janela quando
    # o modelo por trás do alias mudar.
    CTX_LEN_STANDARD_MODEL: int = Field(
        1_000_000, alias="ASSISTENTE_CTX_LEN_STANDARD_MODEL"
    )
    CTX_LEN_MINI_MODEL: int = Field(500_000, alias="ASSISTENTE_CTX_LEN_MINI_MODEL")
    CTX_LEN_NANO_MODEL: int = Field(500_000, alias="ASSISTENTE_CTX_LEN_NANO_MODEL")

    # ===================================================================
    # Output Tokens - reserva local exclusiva do endpoint /stream legado.
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

    # Configurações de reasoning (Responses API)
    REASONING_EFFORT: str = Field("medium", alias="ASSISTENTE_REASONING_EFFORT")
    REASONING_SUMMARY: str = Field("detailed", alias="ASSISTENTE_REASONING_SUMMARY")

    # --- Endpoint Deep Agents (session_stream) ---
    # Endpoint Deep Agents (/llm_lang/session_stream): sessão escopada por
    # {id_usuario}_{id_topico} com filesystem do deepagents + TTL deslizante.
    SESSIONS_ROOT: str = Field("/var/seiia/sessions", alias="ASSISTENTE_SESSIONS_ROOT")
    SESSION_TTL_SECONDS: int = Field(
        3600, alias="ASSISTENTE_SESSION_TTL_SECONDS"
    )  # janela deslizante (sliding): reinicia a cada interação
    SESSION_MAX_FILE_SIZE_MB: int = Field(
        50, alias="ASSISTENTE_SESSION_MAX_FILE_SIZE_MB"
    )
    SESSION_SWEEPER_INTERVAL_SECONDS: int = Field(
        300, alias="ASSISTENTE_SESSION_SWEEPER_INTERVAL_SECONDS"
    )
    SESSION_MAIN_MODEL: str = Field("principal", alias="ASSISTENTE_SESSION_MAIN_MODEL")
    SESSION_EXPLORER_MODEL: str = Field(
        "explorador", alias="ASSISTENTE_SESSION_EXPLORER_MODEL"
    )
    SESSION_CLASSIFIER_MODEL: str = Field(
        "classificador", alias="ASSISTENTE_SESSION_CLASSIFIER_MODEL"
    )
    SESSION_CHECKPOINTER_SCHEMA: str = Field(
        "seiia_session", alias="ASSISTENTE_SESSION_CHECKPOINTER_SCHEMA"
    )
    # Teto (soft, via prompt) de exploradores paralelos no nível high. Quem decide
    # a quantidade é o agente principal; isto só limita o que ele pode pedir.
    SESSION_MAX_EXPLORERS: int = Field(12, alias="ASSISTENTE_SESSION_MAX_EXPLORERS")
    # Liga o trace de tool calls (nome/args/duração) no log do terminal para debug.
    SESSION_TRACE: bool = Field(False, alias="ASSISTENTE_SESSION_TRACE")
    # Mantém o SSE vivo enquanto documentos/histórico são preparados, antes do agente.
    SESSION_PREPARATION_HEARTBEAT_INTERVAL_SECONDS: float = Field(
        30.0,
        gt=0,
        le=300,
        alias="ASSISTENTE_SESSION_PREPARATION_HEARTBEAT_INTERVAL_SECONDS",
    )
    # Mantém o SSE vivo enquanto o agente aguarda o upstream do modelo.
    SESSION_AGENT_HEARTBEAT_INTERVAL_SECONDS: float = Field(
        30.0,
        ge=15,
        le=30,
        alias="ASSISTENTE_SESSION_AGENT_HEARTBEAT_INTERVAL_SECONDS",
    )
    # Fonte de bytes congelados, opt-in e exclusiva do harness isolado. O header do
    # benchmark não ativa pinning quando este caminho está ausente.
    SESSION_BENCHMARK_EVIDENCE_INDEX: str | None = Field(
        None, alias="ASSISTENTE_SESSION_BENCHMARK_EVIDENCE_INDEX"
    )
    # N governa seed do histórico na thread nova, trim da janela a cada turno e o limiar de long_topic.
    SESSION_SEED_HISTORY: bool = Field(True, alias="ASSISTENTE_SESSION_SEED_HISTORY")
    SESSION_MAX_TURNS: int = Field(12, alias="ASSISTENTE_SESSION_MAX_TURNS")
    # Threshold (tokens de conteúdo) da decisão de modo do session (fase 5): conteúdo
    # <= corte -> modo injetado; acima -> filesystem. Escape hatches: 0 desliga o
    # injetado (sempre filesystem); valor gigante força injetado. Corte = 200k (decisão
    # nº1, revisada 2026-07-07). Evidência: injeção ganha claro até ~55k (medium 2-5x +
    # rápido, qualidade igual/melhor, juiz saneado); no teto 459k a extração empata mas a
    # SÍNTESE degrada (0.80 vs filesystem 0.90); o caching multi-turno amortiza o custo da
    # injeção (turno 2+ ~99% do input vem do cache). 200k = ponto entre o medium (bom) e o
    # 459k (síntese degrada); a fronteira ~200k não tem ponto de qualidade medido direto —
    # aposta calibrada, revisar se surgir sinal. Override por request via
    # `inject_tokens_threshold` no payload. Ver session_agent/mode.py e o README do experimento.
    SESSION_INJECT_TOKENS_THRESHOLD: int = Field(
        200000, alias="ASSISTENTE_SESSION_INJECT_TOKENS_THRESHOLD"
    )
    # Tamanho do preview (chars do início do doc) gravado no manifesto session.json.
    SESSION_PREVIEW_CHARS: int = Field(1500, alias="ASSISTENTE_SESSION_PREVIEW_CHARS")
    # Websearch no session_stream: teto de páginas por chamada. O modo raso
    # WebResearchAgent usa este valor como teto para perguntas high; 8 limita a largura
    # do crawl sem reduzir seu orçamento de chamadas.
    SESSION_WEBSEARCH_MAX_ROUNDS: int = Field(
        6, alias="ASSISTENTE_SESSION_WEBSEARCH_MAX_ROUNDS"
    )
    SESSION_WEBSEARCH_MAX_PAGES: int = Field(
        8, alias="ASSISTENTE_SESSION_WEBSEARCH_MAX_PAGES"
    )
    # Qual tool web o session usa (fase 8): "web_research" = WebResearchAgent raso
    # (truncar-e-armazenar, zero LLM interno, profundidade dirigida pelo principal);
    # "deep_research" = DeepResearchAgent (o mesmo do clássico, ~290 gens/pesquisa).
    # O clássico NÃO é afetado por este knob (decisão: DeepResearchAgent intocado).
    SESSION_WEB_TOOL: str = Field("web_research", alias="ASSISTENTE_SESSION_WEB_TOOL")
    # Orçamento (chars) da janela devolvida por página crawleada pelo WebResearchAgent
    # (o conteúdo completo fica em web/ na sessão; a janela é orientação).
    SESSION_WEBRESEARCH_WINDOW_CHARS: int = Field(
        4000, alias="ASSISTENTE_SESSION_WEBRESEARCH_WINDOW_CHARS"
    )
    # Orçamento DURO de chamadas do WebResearchAgent por request. Diretiva de prompt
    # não segura agente perfeccionista (medido: 63 chamadas/28min); após o teto a tool
    # devolve "orçamento esgotado, sintetize com o que há em web/".
    SESSION_WEBRESEARCH_MAX_CALLS: int = Field(
        6, alias="ASSISTENTE_SESSION_WEBRESEARCH_MAX_CALLS"
    )
    # Crawl paralelo somente entre domínios. WebResearchAgent conserva uma vaga por
    # host, evitando rajada contra uma única fonte; este teto limita a soma dos hosts.
    SESSION_WEBRESEARCH_CRAWL_CONCURRENCY: int = Field(
        4, ge=1, le=8, alias="ASSISTENTE_SESSION_WEBRESEARCH_CRAWL_CONCURRENCY"
    )
    # Gate opt-in: nano confere o lote inicial e libera no máximo uma busca dirigida.
    # Desligado por padrão para ativação gradual por experimento/configuração.
    SESSION_WEBRESEARCH_EVIDENCE_GATE_ENABLED: bool = Field(
        False, alias="ASSISTENTE_SESSION_WEBRESEARCH_EVIDENCE_GATE_ENABLED"
    )
    SESSION_WEBRESEARCH_EVIDENCE_GATE_INPUT_CHARS: int = Field(
        24000,
        ge=1000,
        le=100000,
        alias="ASSISTENTE_SESSION_WEBRESEARCH_EVIDENCE_GATE_INPUT_CHARS",
    )
    # Pontos independentes são disparados antes do agente principal. O teto efetivo
    # também respeita MAX_CALLS da ferramenta.
    SESSION_WEBRESEARCH_SPECULATIVE_MAX_QUERIES: int = Field(
        3, ge=1, alias="ASSISTENTE_SESSION_WEBRESEARCH_SPECULATIVE_MAX_QUERIES"
    )
    # Reasoning do agente de sessão, independente do REASONING_EFFORT global (que
    # serve ao endpoint clássico). Default tunado p/ velocidade: low + auto.
    SESSION_REASONING_EFFORT: str = Field(
        "low", alias="ASSISTENTE_SESSION_REASONING_EFFORT"
    )
    SESSION_REASONING_SUMMARY: str = Field(
        "auto", alias="ASSISTENTE_SESSION_REASONING_SUMMARY"
    )
    # Effort quando use_thinking=True (sobe de low para medium). Reasoning é sempre
    # ligado; este só muda o nível quando o usuário pede aprofundamento.
    SESSION_REASONING_EFFORT_THINKING: str = Field(
        "medium", alias="ASSISTENTE_SESSION_REASONING_EFFORT_THINKING"
    )

    # Configurações de memória
    MEMORY_ITERATION_LIMIT: int = 100
    MEMORY_ITERATION_TOKENS_LIMIT: int = 0
    MAX_LENGTH_CONTENT_WEBSEARCH: int = 256000
    WEBSEARCH_AGENT_MODEL: str = Field(
        "busca_web", alias="ASSISTENTE_WEBSEARCH_AGENT_MODEL"
    )
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
    SEI_ADDRESS: str | None = Field(default=None, alias="SEI_ADDRESS")
    SEI_API_DB_ADDRESS: str = Field(alias="SEI_API_DB_ADDRESS")
    SEI_API_DB_IDENTIFIER_SERVICE: str = Field(
        alias="SEI_API_DB_IDENTIFIER_SERVICE",
    )
    SEI_API_DB_TIMEOUT: int = Field(
        default=120,
        alias="SEI_API_DB_TIMEOUT",
    )
    SEI_API_MAX_RETRIES: int = Field(
        default=5,
        alias="ASSISTENTE_SEI_API_MAX_RETRIES",
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
    OCR_MODEL: str = Field("", alias="ASSISTENTE_OCR_MODEL")

    # Configurações SearXNG + web-search stack
    SEARX_BASE_URL: str = Field(
        default="http://infra-searxng:8081",  # NOSONAR — URL interna de rede Docker, HTTPS não se aplica
        alias="SEARX_BASE_URL",
    )
    SEARX_SEARCH_PATH: str = Field(default="/search", alias="SEARX_SEARCH_PATH")
    FASTCRW_BASE_URL: str = Field(
        default="http://infra-fastcrw:3000",  # NOSONAR — URL interna de rede Docker, HTTPS não se aplica
        alias="FASTCRW_BASE_URL",
    )
    BYPARR_BASE_URL: str = Field(
        default="http://infra-byparr:8191",  # NOSONAR — URL interna de rede Docker, HTTPS não se aplica
        alias="BYPARR_BASE_URL",
    )
    MARKER_BASE_URL: str = Field(
        default="http://infra-marker:8082",  # NOSONAR — URL interna de rede Docker, HTTPS não se aplica
        alias="MARKER_BASE_URL",
    )

    def model_post_init(self, __context: dict[str, Any]) -> None:  # noqa: PYI063, RUF100
        """Inicialização de valores que dependem de cálculos ou combinações de outros valores."""
        # O OCR reutiliza o modelo nano por padrão. Um valor explícito em
        # ASSISTENTE_OCR_MODEL continua sendo o override específico do OCR.
        self.OCR_MODEL = self.OCR_MODEL.strip() or LITELLM_NANO_ALIAS

        # Nome da tabela derivado do BASE_MODEL canônico (não do alias EMBEDDING_MODEL),
        # com a MESMA fórmula do ETL (jobs/envs.py): {base_model}-{chunk}-{overlap} com
        # replace de "-" e "/". Fallback para o alias só se o base_model não vier do CI/CD.
        embedding_base_model = self.LITELLM_EMBEDDING_MODEL or self.EMBEDDING_MODEL
        model_chunk_settings = (
            f"{embedding_base_model}-{self.MAX_LENGTH_CHUNK_SIZE}-{self.CHUNK_OVERLAP}"
        )
        self.EMBEDDINGS_TABLE_NAME = model_chunk_settings.replace("-", "_").replace(
            "/", "_"
        )
        self.DB_SEIIA_PWD_QUOTED = quote(self.DB_SEIIA_PWD)
        self.DB_SEIIA_CONNECTION_STRING = f"postgresql://{self.DB_SEIIA_USER}:{self.DB_SEIIA_PWD_QUOTED}@{self.DB_SEIIA_HOST}:{self.DB_SEIIA_PORT}/{self.DB_SEIIA_ASSISTENTE}"
        self.PGVECTOR_CONNECTION_STRING = self.DB_SEIIA_CONNECTION_STRING

        # Define MEMORY_ITERATION_TOKENS_LIMIT como 10% do contexto do modelo default
        if self.DEFAULT_RESPONSE_MODEL.lower() in {"classificador", "busca_web"}:
            ctx_len = self.CTX_LEN_MINI_MODEL
        else:
            ctx_len = self.CTX_LEN_STANDARD_MODEL
        self.MEMORY_ITERATION_TOKENS_LIMIT = int(ctx_len * 0.1)


settings = Settings()
