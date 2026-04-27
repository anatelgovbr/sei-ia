"""
Testes unitários para sei_ia/middleware/__init__.py.

Cobre is_excluded_url: verifica se a URL da requisição deve ser excluída de
logs e métricas com base nos padrões EXCLUDED_URL_PATTERNS.
"""

from unittest.mock import MagicMock

from sei_ia.middleware import is_excluded_url


def _make_request(path: str) -> MagicMock:
    """Cria um mock de Request com o path especificado."""
    mock_request = MagicMock()
    mock_request.url.path = path
    return mock_request


# ---------------------------------------------------------------------------
# URLs excluídas
# ---------------------------------------------------------------------------


def test_health_excluida():
    """'/health' deve ser excluída."""
    assert is_excluded_url(_make_request("/health")) is True


def test_health_com_subpath_excluida():
    """'/health/check' deve ser excluída."""
    assert is_excluded_url(_make_request("/health/check")) is True


def test_docs_excluida():
    """'/docs' deve ser excluída."""
    assert is_excluded_url(_make_request("/docs")) is True


def test_redoc_excluida():
    """'/redoc' deve ser excluída."""
    assert is_excluded_url(_make_request("/redoc")) is True


def test_openapi_json_excluida():
    """'/openapi.json' deve ser excluída."""
    assert is_excluded_url(_make_request("/openapi.json")) is True


def test_tests_excluida():
    """'/tests' deve ser excluída."""
    assert is_excluded_url(_make_request("/tests")) is True


# ---------------------------------------------------------------------------
# URLs não excluídas
# ---------------------------------------------------------------------------


def test_chat_nao_excluida():
    """'/llm_lang/chat_gpt_4o_mini_128k' não deve ser excluída."""
    assert is_excluded_url(_make_request("/llm_lang/chat_gpt_4o_mini_128k")) is False


def test_feedback_nao_excluida():
    """'/feedback/feedback' não deve ser excluída."""
    assert is_excluded_url(_make_request("/feedback/feedback")) is False


def test_raiz_nao_excluida():
    """'/' não deve ser excluída (redoc está em '/' mas padrão é /redoc)."""
    assert is_excluded_url(_make_request("/")) is False


def test_path_arbitrario_nao_excluido():
    """'/api/v1/chat' não deve ser excluída."""
    assert is_excluded_url(_make_request("/api/v1/chat")) is False
