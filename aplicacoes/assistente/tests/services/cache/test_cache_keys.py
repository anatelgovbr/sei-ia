"""Testes para geração de chaves de cache."""

from sei_ia.services.cache.cache_keys import CacheKeyGenerator, generate_cache_key


class TestCacheKeyGenerator:
    """Testes para o gerador de chaves de cache."""

    def test_generate_document_key_basic(self):
        """Testa geração básica de chave."""
        key = CacheKeyGenerator.generate_document_key("123456")
        assert key.startswith("seiia:doc:v1:doc:123456:")
        assert len(key.split(":")) == 6

    def test_generate_document_key_with_pages(self):
        """Testa geração de chave com paginação."""
        key1 = CacheKeyGenerator.generate_document_key("123456", pag_ini=1, pag_fim=5)
        key2 = CacheKeyGenerator.generate_document_key("123456", pag_ini=1, pag_fim=10)

        # Chaves devem ser diferentes para páginas diferentes
        assert key1 != key2, "As chaves não deveriam ser iguais para páginas diferentes"

        # Ambas as chaves devem conter o ID do documento
        assert "123456" in key1, "key1 deveria conter o ID do documento"
        assert "123456" in key2, "key2 deveria conter o ID do documento"

    def test_generate_document_key_with_download_ext(self):
        """Testa geração de chave com flag download_ext."""
        key1 = CacheKeyGenerator.generate_document_key("123456", download_ext=True)
        key2 = CacheKeyGenerator.generate_document_key("123456", download_ext=False)
        key3 = CacheKeyGenerator.generate_document_key("123456", download_ext=None)

        # Todas devem ser diferentes
        assert key1 != key2 != key3

    def test_generate_document_key_with_anexos(self):
        """Testa geração de chave com anexos."""
        key1 = CacheKeyGenerator.generate_document_key(
            "123456", id_anexos=["111", "222"]
        )
        key2 = CacheKeyGenerator.generate_document_key(
            "123456", id_anexos=["222", "111"]
        )  # ordem diferente
        key3 = CacheKeyGenerator.generate_document_key(
            "123456", id_anexos=["111", "333"]
        )

        # key1 e key2 devem ser iguais (anexos são normalizados)
        assert key1 == key2
        # key3 deve ser diferente
        assert key1 != key3

    def test_generate_document_key_consistency(self):
        """Testa consistência das chaves."""
        key1 = CacheKeyGenerator.generate_document_key(
            "123456", pag_ini=1, pag_fim=5, download_ext=True, id_anexos=["111", "222"]
        )
        key2 = CacheKeyGenerator.generate_document_key(
            "123456", pag_ini=1, pag_fim=5, download_ext=True, id_anexos=["111", "222"]
        )

        # Mesmos parâmetros devem gerar mesma chave
        assert key1 == key2

    def test_generate_stats_key(self):
        """Testa geração da chave de estatísticas."""
        key = CacheKeyGenerator.generate_stats_key()
        assert key == "seiia:doc:v1:stats"

    def test_get_key_pattern(self):
        """Testa geração do padrão de busca."""
        pattern = CacheKeyGenerator.get_key_pattern()
        assert pattern == "seiia:doc:v1:doc:*"


class TestGenerateCacheKey:
    """Testes para a função conveniente de geração de chaves."""

    def test_generate_cache_key_function(self):
        """Testa função conveniente de geração de chaves."""
        key = generate_cache_key("123456", pag_ini=1, pag_fim=5)
        expected_key = CacheKeyGenerator.generate_document_key(
            "123456", pag_ini=1, pag_fim=5
        )
        assert key == expected_key
