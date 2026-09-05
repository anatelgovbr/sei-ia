"""Conftest local para tests/services/*.

Os testes em `tests/services/` importam módulos da aplicação (ex.:
`sei_ia.services.cache.redis_client`) que disparam o import de
`sei_ia.configs.settings_config:338` (`settings = Settings()`). Sem env
vars, Pydantic Settings explode na coleta com ValidationError.

`tests/conftest.py` (raiz) não define todas essas variáveis. Logo, rodar
`pytest tests/services/...` isolado quebrava.

Defaults via `os.environ.setdefault` ANTES de qualquer import. Em CI
com env vars reais, são ignorados; em dev, permitem o import seguir.
"""

import os

os.environ.setdefault("DB_SEIIA_HOST", "localhost")
os.environ.setdefault("DB_SEIIA_PORT", "5432")
os.environ.setdefault("DB_SEIIA_USER", "test_user")
os.environ.setdefault("DB_SEIIA_PWD", "test_password")
os.environ.setdefault("ASSISTENTE_EMBEDDING_API_KEY", "test_embedding_key")
os.environ.setdefault("ASSISTENTE_EMBEDDING_ENDPOINT", "https://test.openai.azure.com/")
os.environ.setdefault("ASSISTENTE_API_KEY_STANDARD_MODEL", "test_standard_key")
os.environ.setdefault(
    "ASSISTENTE_ENDPOINT_STANDARD_MODEL", "https://test.openai.azure.com/"
)
os.environ.setdefault("ASSISTENTE_NAME_STANDARD_MODEL", "gpt-4")
os.environ.setdefault("ASSISTENTE_API_KEY_MINI_MODEL", "test_mini_key")
os.environ.setdefault(
    "ASSISTENTE_ENDPOINT_MINI_MODEL", "https://test.openai.azure.com/"
)
os.environ.setdefault("ASSISTENTE_NAME_MINI_MODEL", "gpt-4o-mini")
os.environ.setdefault("SEI_API_DB_ADDRESS", "http://localhost:8000")
os.environ.setdefault("SEI_API_DB_IDENTIFIER_SERVICE", "SeiApiService")
