"""Tests for jobs/services/embedder/providers/litellm.py."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from jobs.services.embedder.providers.litellm import LiteLLMEmbeddingProvider


@pytest.fixture(autouse=True)
def _clear_deployment_cache():
    LiteLLMEmbeddingProvider._DEPLOYMENT_CACHE.clear()
    yield
    LiteLLMEmbeddingProvider._DEPLOYMENT_CACHE.clear()


def _make_provider(**overrides):
    kwargs = {
        "base_url": "http://litellm.local",
        "model": "embedding",
        "base_model": "text-embedding-3-small",
        "api_key": "dummy",
    }
    kwargs.update(overrides)
    return LiteLLMEmbeddingProvider(**kwargs)


class TestInit:
    def test_builds_sync_and_async_clients(self):
        provider = _make_provider()
        assert provider.base_url == "http://litellm.local"
        assert provider.model == "embedding"
        assert provider.tokenizer_type == "tiktoken"
        assert provider.client is not None
        assert provider.async_client is not None

    def test_defaults_base_model_when_not_given(self):
        provider = _make_provider(base_model=None)
        assert provider.base_model == "text-embedding-3-small"

    def test_raises_when_openai_unavailable(self):
        with (
            patch("jobs.services.embedder.providers.litellm.OpenAI", None),
            pytest.raises(ImportError),
        ):
            _make_provider()


class TestTiktokenModelName:
    def test_uses_base_model_when_recognized_by_tiktoken(self):
        provider = _make_provider(base_model="text-embedding-3-small")
        assert provider.tiktoken_model_name == "text-embedding-3-small"

    def test_caches_result_across_calls(self):
        provider = _make_provider(base_model="text-embedding-3-small")
        first = provider.tiktoken_model_name
        cache_key = f"{provider.base_url}|{provider.model}"
        assert LiteLLMEmbeddingProvider._DEPLOYMENT_CACHE[cache_key] == first

    def test_falls_back_to_http_header_when_unrecognized(self):
        provider = _make_provider(base_model="unknown/some-custom-model")

        fake_response = MagicMock()
        fake_response.headers = {
            "llm_provider-x-ms-deployment-name": "resolved-deployment"
        }
        fake_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=fake_response):
            assert provider.tiktoken_model_name == "resolved-deployment"

    def test_falls_back_to_default_when_header_missing(self):
        """Upstream não-Azure (ex: proxy Vertex) nunca manda o header — não
        deve levantar, deve cair no fallback 'text-embedding-3-small'."""
        provider = _make_provider(base_model="unknown/some-custom-model")

        fake_response = MagicMock()
        fake_response.headers = {}
        fake_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=fake_response):
            assert provider.tiktoken_model_name == "text-embedding-3-small"

    def test_falls_back_to_default_on_http_error(self):
        provider = _make_provider(base_model="unknown/some-custom-model")

        with patch("httpx.post", side_effect=httpx.ConnectError("boom")):
            assert provider.tiktoken_model_name == "text-embedding-3-small"

    def test_falls_back_to_default_when_response_status_error(self):
        provider = _make_provider(base_model="unknown/some-custom-model")

        fake_response = MagicMock()
        fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=MagicMock()
        )

        with patch("httpx.post", return_value=fake_response):
            assert provider.tiktoken_model_name == "text-embedding-3-small"


class TestApplyTokenizer:
    def test_accepts_single_string(self):
        provider = _make_provider()
        tokens = provider.apply_tokenizer("hello world")
        assert len(tokens) == 1
        assert isinstance(tokens[0], list)

    def test_accepts_list_of_strings(self):
        provider = _make_provider()
        tokens = provider.apply_tokenizer(["hello", "world"])
        assert len(tokens) == 2


class TestGenerateEmbeddings:
    def test_returns_empty_list_for_empty_input(self):
        provider = _make_provider()
        assert provider.generate_embeddings([]) == []

    def test_accepts_single_string_input(self):
        provider = _make_provider()
        fake_item = MagicMock(embedding=[0.1, 0.2])
        fake_response = MagicMock(data=[fake_item])

        with patch.object(
            provider.client.embeddings, "create", return_value=fake_response
        ):
            result = provider.generate_embeddings("hello")

        assert result == [[0.1, 0.2]]

    def test_returns_embeddings_for_list_input(self):
        provider = _make_provider()
        fake_items = [MagicMock(embedding=[0.1]), MagicMock(embedding=[0.2])]
        fake_response = MagicMock(data=fake_items)

        with patch.object(
            provider.client.embeddings, "create", return_value=fake_response
        ):
            result = provider.generate_embeddings(["a", "b"])

        assert result == [[0.1], [0.2]]

    def test_reraises_http_status_error(self):
        provider = _make_provider()
        request = httpx.Request("POST", "http://litellm.local/v1/embeddings")
        response = httpx.Response(500, request=request)
        error = httpx.HTTPStatusError("boom", request=request, response=response)

        with (
            patch.object(provider.client.embeddings, "create", side_effect=error),
            pytest.raises(httpx.HTTPStatusError),
        ):
            provider.generate_embeddings(["a"])

    def test_reraises_unexpected_error(self):
        provider = _make_provider()
        with (
            patch.object(
                provider.client.embeddings, "create", side_effect=ValueError("boom")
            ),
            pytest.raises(ValueError),
        ):
            provider.generate_embeddings(["a"])


class TestConnection:
    def test_test_connection_true_on_success(self):
        provider = _make_provider()
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=fake_response) as request:
            assert provider.test_connection() is True
        request.assert_called_once_with(
            "http://litellm.local/health/liveliness",
            headers={"Authorization": "Bearer dummy"},
            timeout=5.0,
        )

    def test_test_connection_false_on_failure(self):
        provider = _make_provider()
        with patch("httpx.get", side_effect=httpx.ConnectError("boom")):
            assert provider.test_connection() is False
