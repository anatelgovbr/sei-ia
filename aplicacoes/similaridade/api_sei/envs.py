#!/usr/bin/env python3
"""Arquivo contendo variáveis de ambiente globais do projeto."""

import os
from pathlib import Path

import urllib3
from requests.auth import HTTPBasicAuth

DATABASE_TYPE = "mysql"  # temporario
# Desabilita os warnings de verificação de certificados SSL, pois estamos utilizando certificados auto-assinados
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONFIGS_PAR_DIR = Path(__file__).resolve().parent


SOLR_ADDRESS = os.getenv("SOLR_ADDRESS", "").rstrip("/")


DB_SEIIA_USER = os.getenv("DB_SEIIA_USER")
DB_SEIIA_PWD = os.getenv("DB_SEIIA_PWD")
DB_SEIIA_HOST = os.getenv("DB_SEIIA_HOST", "localhost")
DB_SEIIA_SIMILARIDADE = os.getenv("DB_SEIIA_SIMILARIDADE", "sei_similaridade")

CONN_STRING_APP_DB = os.getenv(
    "CONN_STRING_APP_DB",
    f"postgresql+psycopg2://{DB_SEIIA_USER}:{DB_SEIIA_PWD}@{DB_SEIIA_HOST}/{DB_SEIIA_SIMILARIDADE}",
)  # String de conexão com o banco da aplicação

DB_SEI_ORACLE_SID = os.getenv("DB_SEI_ORACLE_SID")

STORAGE_PROJ_DIR = os.getenv("STORAGE_PROJ_DIR", "/opt/sei_similaridade/")

SOLR_MLT_PROCESS_CORE = os.getenv("SOLR_MLT_PROCESS_CORE")


CONFIG_AUTO_TESTS_PATH = os.getenv(
    "CONFIG_AUTO_TESTS_PATH",
    (CONFIGS_PAR_DIR / "configs/autotests_endpoints.json").as_posix(),
)

STOPWORDS = (Path(CONFIGS_PAR_DIR) / "configs/stopwords_pt.txt").as_posix()

SOLR_MLT_JURISPRUDENCE_CORE = os.getenv(
    "SOLR_MLT_JURISPRUDENCE_CORE", "documentos_bm25"
)

BASE_URL_JURISPRUDENCE = f"{SOLR_ADDRESS}/solr/{SOLR_MLT_JURISPRUDENCE_CORE}"
BASE_URL_JURISPRUDENCE_SELECT = f"{BASE_URL_JURISPRUDENCE}/select"
BASE_URL_JURISPRUDENCE_MLT = f"{BASE_URL_JURISPRUDENCE}/mlt"

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "6dec24a32c2df9cbc81fb978b307e652d64df6b12766a0cffcc52fa3cd5d4b30",
)

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "5"))
USE_AUTHENTICATION = os.getenv("USE_AUTHENTICATION", "False").lower() == "true"

JOBS_API_ADDRESS = os.getenv("JOBS_API_ADDRESS", "https://jobs_api:8642")

LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()

SOLR_USER = os.getenv("SOLR_USER")
SOLR_PASSWORD = os.getenv("SOLR_PASSWORD")

auth = HTTPBasicAuth(SOLR_USER, SOLR_PASSWORD)

VERIFY_SSL = os.getenv("VERIFY_SSL", "False").lower() == "true"

ENABLE_OTEL_METRICS = os.getenv("ENABLE_OTEL_METRICS", "true").lower() == "true"

SEI_API_DB_TIMEOUT = int(os.getenv("SEI_API_DB_TIMEOUT", "120"))  # Timeout em segundos

# Configurações da API Banco de dados do SEI
SEI_API_DB_ADDRESS = os.getenv("SEI_API_DB_ADDRESS")
SEI_API_DB_IDENTIFIER_SERVICE = os.getenv("SEI_API_DB_IDENTIFIER_SERVICE")
SEI_API_DB_USER = os.getenv("SEI_API_DB_USER", "Usuario_IA")
SEI_API_DB_CHUNK_SIZE = int(os.getenv("SEI_API_DB_CHUNK_SIZE", "100"))
