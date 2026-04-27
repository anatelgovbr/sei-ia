"""Definições gerais para o JOBS."""

import os
from datetime import timedelta

import pendulum
from requests.auth import HTTPBasicAuth

dags_default_args = {
    "retries": 4,
    "retry_delay": timedelta(seconds=10),
    "retry_exponential_backoff": True,
    "start_date": pendulum.now("America/Sao_Paulo").subtract(days=1),
    "depends_on_past": False,
}


LIST_RETRY_DELAYS_4t = [
    timedelta(minutes=1),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=5),
]


CONFIGS_PAR_DIR = os.path.dirname(os.path.abspath(__file__))  # noqa: PTH120, PTH100
ENVIRONMENT = os.getenv("ENVIRONMENT", "test")
DEFAULT_ALLOWED_DOCUMENT_FORMATS = [
    "pdf",
    "docx",
    "odt",
    "pptx",
    "xlsx",
    "xls",
    "ods",
    "csv",
]

if ENVIRONMENT not in ["dev", "homol", "prod", "test"]:
    raise Exception("Paramentro ENVIRONMENT nao definido")  # noqa: TRY002

########################### Banco de Dado ##########################

## Solr

SOLR_ADDRESS = os.getenv("SOLR_ADDRESS")
SOLR_MLT_PROCESS_CORE = os.getenv("SOLR_MLT_PROCESS_CORE")
MLT_PROCESS_CONFIGSET = os.getenv(
    "MLT_PROCESS_CONFIGSET",
    os.path.join(  # noqa: PTH118
        CONFIGS_PAR_DIR, "configs/solr_core_configs/process"
    ),
)
SOLR_MLT_DOCUMENTS_CORE = os.getenv("SOLR_MLT_JURISPRUDENCE_CORE", "documentos_bm25")
SOLR_N_ROWS = int(os.getenv("SOLR_N_ROWS", "700"))

MLT_DOCUMENTS_CONFIGSET = os.getenv(
    "MLT_JURISPRUDENCE_CONFIGSET",
    os.path.join(CONFIGS_PAR_DIR, "configs/solr_core_configs/jurisprudence"),
)

BASE_URL_DOCUMENTS = f"{SOLR_ADDRESS}/solr/{SOLR_MLT_DOCUMENTS_CORE}"
BASE_URL_DOCUMENTS_SELECT = f"{BASE_URL_DOCUMENTS}/select"
BASE_URL_DOCUMENTS_MLT = f"{BASE_URL_DOCUMENTS}/mlt"

## Relacional
CONN_STRING_APP_DB = os.getenv("CONN_STRING_APP_DB")


formats_file = os.getenv(
    "FORMATS",
    os.path.join(  # noqa: PTH118
        CONFIGS_PAR_DIR, "configs/formats.csv"
    ),
)
try:
    with open(formats_file) as file:  # noqa: PTH123
        # Formatos liberados de documentos considerados no processo externo
        FORMATS = [line.strip() for line in file.read().splitlines() if line.strip()]
except FileNotFoundError:
    FORMATS = DEFAULT_ALLOWED_DOCUMENT_FORMATS.copy()

#### airflow
AIRFLOW__CORE__DEFAULT_TIMEZONE = os.getenv(
    "AIRFLOW__CORE__DEFAULT_TIMEZONE", "America/Sao_Paulo"
)
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN = os.getenv(
    "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN",
    "postgresql+psycopg2://seiia:seiia@localhost:5433/airflow",
)
AIRFLOW_WWW_USER_USERNAME = os.getenv("_AIRFLOW_WWW_USER_USERNAME", "seiia")
AIRFLOW_WWW_USER_PASSWORD = os.getenv("_AIRFLOW_WWW_USER_PASSWORD", "seiia")
AIRFLOW_API_BASE_URL = os.getenv(
    "AIRFLOW_API_BASE_URL", "http://etl-airflow-webserver:8080/api/v1"
)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

SOLR_USER = os.getenv("SOLR_USER")
SOLR_PASSWORD = os.getenv("SOLR_PASSWORD")

# Default timeout (in seconds) for outgoing HTTP requests done by modules
# that interact with external services (Solr, SEI etc.).
# Can be overwritten by setting SEI_API_DB_TIMEOUT environment variable.
# If absent, defaults to 120 seconds.
DEFAULT_REQUEST_TIMEOUT = int(os.getenv("SEI_API_DB_TIMEOUT", "120"))

auth = HTTPBasicAuth(SOLR_USER, SOLR_PASSWORD)

VERIFY_SSL = os.getenv("VERIFY_SSL", "False").lower() == "true"

# Configurações da API Banco de dados do SEI
SEI_API_DB_ADDRESS = os.getenv("SEI_API_DB_ADDRESS") or os.getenv("SEI_ADDRESS")
SEI_API_DB_IDENTIFIER_SERVICE = os.getenv("SEI_API_DB_IDENTIFIER_SERVICE")
SEI_API_DB_TIMEOUT = int(os.getenv("SEI_API_DB_TIMEOUT", "120"))
SEI_API_DB_USER = os.getenv("SEI_API_DB_USER", "Usuario_IA")
SEI_API_DB_CHUNK_SIZE = int(os.getenv("SEI_API_DB_CHUNK_SIZE", "100"))


# Configurações de indexação
INDEX_BATCH_SIZE = int(os.getenv("INDEX_PROCESS_BATCH_SIZE", "5"))
LIMIT_QUEUE = int(os.getenv("LIMIT_QUEUE", "100"))

# Configurações de vetorização (embeddings)
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "10"))
EMBEDDING_MAX_ACTIVE_RUNS = int(os.getenv("EMBEDDING_MAX_ACTIVE_RUNS", "2"))

# Limites e comportamento do cliente da API do SEI (controle de carga)
# Máximo de requisições concorrentes para conteúdo de documentos
SEI_API_MAX_CONCURRENCY = int(os.getenv("SEI_API_MAX_CONCURRENCY", "15"))
# Número máximo de tentativas em falhas transitórias (429/5xx/timeouts)
SEI_API_MAX_RETRIES = int(os.getenv("SEI_API_MAX_RETRIES", "5"))
# Backoff base em segundos para tentativas (exponencial com jitter)
SEI_API_BACKOFF_BASE = float(os.getenv("SEI_API_BACKOFF_BASE", "1.0"))
# Backoff máximo em segundos
SEI_API_BACKOFF_MAX = float(os.getenv("SEI_API_BACKOFF_MAX", "32.0"))

########################### Configurações de Embeddings ##########################

# Configurações do PostgreSQL compartilhado com Assistente
DB_SEIIA_HOST = os.getenv("DB_SEIIA_HOST")
DB_SEIIA_PORT = os.getenv("DB_SEIIA_PORT", "5432")
DB_SEIIA_USER = os.getenv("DB_SEIIA_USER")
DB_SEIIA_PWD = os.getenv("DB_SEIIA_PWD")
DB_SEIIA_ASSISTENTE = os.getenv("DB_SEIIA_ASSISTENTE", "SEI_LLM")
DB_SEIIA_ASSISTENTE_SCHEMA = os.getenv("DB_SEIIA_ASSISTENTE_SCHEMA", "sei_llm")


# Função para buscar informações do modelo no LiteLLM proxy
def _get_litellm_model_info(proxy_url: str, model_name: str) -> dict:
    """Busca informações do modelo no LiteLLM proxy.

    Args:
        proxy_url: URL do LiteLLM proxy (ex: http://localhost:4000)
        model_name: Nome do modelo configurado no proxy (ex: "embedding")

    Returns:
        dict com 'model', 'base_model' e 'api_version' extraídos do litellm_params e model_info
    """
    import requests

    try:
        response = requests.get(f"{proxy_url}/model/info", timeout=5)
        response.raise_for_status()
        data = response.json()

        # Filtra o modelo pelo model_name
        for model_info in data.get("data", []):
            if model_info.get("model_name") == model_name:
                litellm_params = model_info.get("litellm_params", {})
                inner_model_info = model_info.get("model_info", {})
                return {
                    "model": litellm_params.get("model", ""),
                    "base_model": inner_model_info.get("base_model", ""),
                    "api_version": litellm_params.get("api_version", ""),
                }

        # Se não encontrar o modelo, retorna valores vazios
        return {"model": "", "base_model": "", "api_version": ""}

    except Exception:
        # Em caso de erro (proxy não disponível, etc), retorna valores vazios
        return {"model": "", "base_model": "", "api_version": ""}


# Configurações do LiteLLM Proxy
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "http://localhost:4000")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "embedding")
LITELLM_MODEL_NAME = os.getenv("LITELLM_MODEL_NAME", EMBEDDING_MODEL)

# Busca informações do modelo no LiteLLM proxy
_model_info = _get_litellm_model_info(LITELLM_PROXY_URL, LITELLM_MODEL_NAME)

# Configurações do modelo de embeddings
EMBEDDING_API_VERSION = os.getenv(
    "EMBEDDING_API_VERSION", _model_info.get("api_version", "2024-10-21")
)
_resolved_base_model = _model_info.get("base_model", "").strip()
if not _resolved_base_model:
    if EMBEDDING_MODEL and EMBEDDING_MODEL.lower() not in {"embedding"}:
        _resolved_base_model = EMBEDDING_MODEL
    else:
        msg = (
            "Nao foi possivel resolver o base_model de embeddings via LiteLLM "
            f"para o alias '{EMBEDDING_MODEL}'."
        )
        raise RuntimeError(msg)

# Modelo base para uso com tiktoken e derivação do nome da tabela.
EMBEDDING_BASE_MODEL = os.getenv("EMBEDDING_BASE_MODEL", _resolved_base_model)

# Configurações de chunking
MAX_LENGTH_CHUNK_SIZE = int(os.getenv("MAX_LENGTH_CHUNK_SIZE", "1512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
EMBEDDINGS_MAX_CONCURRENCY = int(os.getenv("EMBEDDINGS_MAX_CONCURRENCY", "20"))

# Nome da tabela de embeddings (seguindo padrão do Assistente: modelo_chunksize_overlap)
EMBEDDINGS_TABLE_NAME = (
    f"{EMBEDDING_BASE_MODEL}-{MAX_LENGTH_CHUNK_SIZE}-{CHUNK_OVERLAP}".replace(
        "-", "_"
    ).replace("/", "_")
)

########################### Configurações de Redis (Cache) ##########################

# Configurações do Redis para cache (compartilhado com Assistente)
REDIS_URI = os.getenv("JOBS_REDIS_URI", "redis://redis_cache:6379/0")
CACHE_ENABLED = os.getenv("JOBS_CACHE_ENABLED", "true").lower() == "true"
CACHE_KEY_PREFIX = os.getenv(
    "JOBS_CACHE_KEY_PREFIX", "seiia:doc:"
)  # Mesmo padrão do Assistente
