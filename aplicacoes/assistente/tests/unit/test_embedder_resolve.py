"""Unit test do fallback de resolucao de deployment do embedder (sem rede).

`_resolve_base_model` alimenta so a CONTAGEM de tokens (tiktoken), nunca os vetores.
Quando o alias do proxy nao e conhecido pelo tiktoken E a resolucao via header do
LiteLLM nao e possivel (proxy nao expoe o header, ou auth/rede falham), o metodo NAO
pode bloquear a indexacao: cai num tiktoken conhecido (`text-embedding-3-small`).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import tiktoken

from sei_ia.services.embedder.providers.azure import AzureOpenAIEmbeddingProvider


def test_modelo_conhecido_nao_dispara_rede():
    AzureOpenAIEmbeddingProvider._DEPLOYMENT_CACHE.clear()
    # endpoint morto: se tocasse a rede, estouraria; modelo conhecido curto-circuita
    r = AzureOpenAIEmbeddingProvider._resolve_base_model(
        "text-embedding-3-small", "http://127.0.0.1:1"
    )
    assert r == "text-embedding-3-small"


def test_alias_desconhecido_com_resolucao_indisponivel_cai_no_fallback():
    AzureOpenAIEmbeddingProvider._DEPLOYMENT_CACHE.clear()
    # alias do proxy que o tiktoken nao conhece + endpoint inalcancavel (porta morta):
    # a resolucao via header falha -> fallback tiktoken-conhecido, sem levantar excecao
    r = AzureOpenAIEmbeddingProvider._resolve_base_model(
        "seiia-ds-embedding", "http://127.0.0.1:1"
    )
    assert r == "text-embedding-3-small"
    tiktoken.encoding_for_model(r)  # o resolvido tem que ser conhecido pelo tiktoken


def test_resultado_e_cacheado_por_endpoint_e_modelo():
    AzureOpenAIEmbeddingProvider._DEPLOYMENT_CACHE.clear()
    AzureOpenAIEmbeddingProvider._resolve_base_model(
        "seiia-ds-embedding", "http://127.0.0.1:1"
    )
    assert (
        AzureOpenAIEmbeddingProvider._DEPLOYMENT_CACHE[
            "http://127.0.0.1:1|seiia-ds-embedding"
        ]
        == "text-embedding-3-small"
    )


def test_resolucao_via_proxy_envia_autenticacao():
    AzureOpenAIEmbeddingProvider._DEPLOYMENT_CACHE.clear()
    response = MagicMock()
    response.headers = {"llm_provider-x-ms-deployment-name": "text-embedding-3-small"}

    with patch(
        "sei_ia.services.embedder.providers.azure.httpx.post",
        return_value=response,
    ) as request:
        resolved = AzureOpenAIEmbeddingProvider._resolve_base_model(
            "embedding", "http://litellm.local", "proxy-secret"
        )

    assert resolved == "text-embedding-3-small"
    request.assert_called_once_with(
        "http://litellm.local/v1/embeddings",
        json={"model": "embedding", "input": "a"},
        headers={"Authorization": "Bearer proxy-secret"},
        timeout=15.0,
    )


def test_healthcheck_do_proxy_envia_autenticacao():
    provider = AzureOpenAIEmbeddingProvider.__new__(AzureOpenAIEmbeddingProvider)
    provider.is_proxy = True
    provider.endpoint = "http://litellm.local"
    provider.api_key = "proxy-secret"
    response = MagicMock()

    with patch(
        "sei_ia.services.embedder.providers.azure.httpx.get",
        return_value=response,
    ) as request:
        assert provider.test_connection() is True

    request.assert_called_once_with(
        "http://litellm.local/health/liveliness",
        headers={"Authorization": "Bearer proxy-secret"},
        timeout=5.0,
    )
