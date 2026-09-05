"""Middleware modules."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request

# URLs que devem ser excluídas de logs e métricas
EXCLUDED_URL_PATTERNS = [
    r"^/health($|/.*)",
    r"^/docs($|/.*)",
    r"^/redoc($|/.*)",
    r"^/openapi\.json($|/.*)",
    r"^/tests($|/.*)",
]

# Compila os padrões regex para melhor performance
_compiled_patterns = [re.compile(pattern) for pattern in EXCLUDED_URL_PATTERNS]


def is_excluded_url(request: "Request") -> bool:
    """Verifica se a URL da requisição deve ser excluída de logs e métricas.

    Args:
        request: Objeto Request do FastAPI/Starlette

    Returns:
        bool: True se a URL deve ser excluída
    """
    path = request.url.path
    return any(pattern.match(path) for pattern in _compiled_patterns)
