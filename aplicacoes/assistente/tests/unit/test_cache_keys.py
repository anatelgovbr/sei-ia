"""Testes unitários para o módulo cache_keys.

Módulo testado: sei_ia/services/cache/cache_keys.py
"""

from sei_ia.services.cache.cache_keys import CacheKeyGenerator, generate_cache_key


class TestCreateHash:
    """Testes para CacheKeyGenerator._create_hash."""

    def test_mesmos_argumentos_geram_mesmo_hash(self):
        h1 = CacheKeyGenerator._create_hash("doc1", 1, 5, True)
        h2 = CacheKeyGenerator._create_hash("doc1", 1, 5, True)
        assert h1 == h2

    def test_argumentos_diferentes_geram_hashes_diferentes(self):
        h1 = CacheKeyGenerator._create_hash("doc1", 1, 5, True)
        h2 = CacheKeyGenerator._create_hash("doc2", 1, 5, True)
        assert h1 != h2

    def test_hash_tem_16_caracteres(self):
        h = CacheKeyGenerator._create_hash("doc1")
        assert len(h) == 16

    def test_ordem_dos_argumentos_importa(self):
        h1 = CacheKeyGenerator._create_hash("a", "b")
        h2 = CacheKeyGenerator._create_hash("b", "a")
        assert h1 != h2

    def test_none_como_argumento_e_aceito(self):
        h = CacheKeyGenerator._create_hash("doc1", None, None)
        assert len(h) == 16


class TestGenerateDocumentKey:
    """Testes para CacheKeyGenerator.generate_document_key."""

    def test_chave_contem_id_documento(self):
        key = CacheKeyGenerator.generate_document_key("12345")
        assert "12345" in key

    def test_mesmos_parametros_geram_mesma_chave(self):
        k1 = CacheKeyGenerator.generate_document_key("doc1", 1, 10, True, ["a", "b"])
        k2 = CacheKeyGenerator.generate_document_key("doc1", 1, 10, True, ["a", "b"])
        assert k1 == k2

    def test_parametros_diferentes_geram_chaves_diferentes(self):
        k1 = CacheKeyGenerator.generate_document_key("doc1", pag_ini=1)
        k2 = CacheKeyGenerator.generate_document_key("doc1", pag_ini=2)
        assert k1 != k2

    def test_anexos_em_ordem_diferente_geram_mesma_chave(self):
        k1 = CacheKeyGenerator.generate_document_key("doc1", id_anexos=["b", "a"])
        k2 = CacheKeyGenerator.generate_document_key("doc1", id_anexos=["a", "b"])
        assert k1 == k2

    def test_chave_sem_parametros_opcionais(self):
        key = CacheKeyGenerator.generate_document_key("doc1")
        assert "doc:doc1:" in key

    def test_chave_com_todos_os_parametros(self):
        key = CacheKeyGenerator.generate_document_key("doc1", 1, 5, False, ["x"])
        assert "doc:doc1:" in key

    def test_chave_contem_prefixo_e_versao(self):
        from sei_ia.configs.settings_config import settings

        key = CacheKeyGenerator.generate_document_key("doc1")
        assert key.startswith(settings.CACHE_KEY_PREFIX)
        assert settings.CACHE_VERSION in key

    def test_id_documento_diferente_gera_chave_diferente(self):
        k1 = CacheKeyGenerator.generate_document_key("doc1")
        k2 = CacheKeyGenerator.generate_document_key("doc2")
        assert k1 != k2


class TestGenerateStatsKey:
    """Testes para CacheKeyGenerator.generate_stats_key."""

    def test_chave_stats_contem_stats(self):
        key = CacheKeyGenerator.generate_stats_key()
        assert "stats" in key

    def test_chave_stats_e_consistente(self):
        assert (
            CacheKeyGenerator.generate_stats_key()
            == CacheKeyGenerator.generate_stats_key()
        )

    def test_chave_stats_contem_prefixo(self):
        from sei_ia.configs.settings_config import settings

        key = CacheKeyGenerator.generate_stats_key()
        assert key.startswith(settings.CACHE_KEY_PREFIX)


class TestGetKeyPattern:
    """Testes para CacheKeyGenerator.get_key_pattern."""

    def test_padrao_contem_wildcard(self):
        pattern = CacheKeyGenerator.get_key_pattern()
        assert "*" in pattern

    def test_padrao_contem_doc(self):
        pattern = CacheKeyGenerator.get_key_pattern()
        assert "doc:" in pattern

    def test_padrao_e_consistente(self):
        assert (
            CacheKeyGenerator.get_key_pattern() == CacheKeyGenerator.get_key_pattern()
        )


class TestGenerateCacheKey:
    """Testes para a função de conveniência generate_cache_key."""

    def test_equivalente_ao_metodo_da_classe(self):
        k1 = generate_cache_key("doc1", 1, 5, True, ["a"])
        k2 = CacheKeyGenerator.generate_document_key("doc1", 1, 5, True, ["a"])
        assert k1 == k2

    def test_retorna_string(self):
        key = generate_cache_key("doc1")
        assert isinstance(key, str)

    def test_aceita_apenas_id_documento(self):
        key = generate_cache_key("doc99")
        assert "doc99" in key
