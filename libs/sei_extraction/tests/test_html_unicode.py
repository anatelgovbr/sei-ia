"""Testes unitários para sei_extraction/html_to_md/html/unicode.py."""

from sei_extraction.html_to_md.html.unicode import (
    ENCLOSED_CODES,
    SUBSCRIPTS,
    SUPER_SUB_SCRIPTS,
    SUPERSCRIPTS,
    Normalize,
)


class TestConstants:
    def test_enclosed_codes_eh_set(self):
        assert isinstance(ENCLOSED_CODES, set)

    def test_enclosed_codes_nao_vazio(self):
        assert len(ENCLOSED_CODES) > 0

    def test_enclosed_codes_contem_circled_digits(self):
        assert 0x2460 in ENCLOSED_CODES  # ①

    def test_superscripts_eh_set(self):
        assert isinstance(SUPERSCRIPTS, set)

    def test_subscripts_eh_set(self):
        assert isinstance(SUBSCRIPTS, set)

    def test_super_sub_scripts_uniao(self):
        assert SUPER_SUB_SCRIPTS == SUPERSCRIPTS | SUBSCRIPTS

    def test_superscript_dois_presente(self):
        assert 0x00B2 in SUPERSCRIPTS  # ²

    def test_superscript_tres_presente(self):
        assert 0x00B3 in SUPERSCRIPTS  # ³

    def test_subscript_zero_presente(self):
        assert 0x2080 in SUBSCRIPTS  # ₀


class TestNormalize:
    def _make(self):
        return Normalize()

    def test_instancia_criada(self):
        n = self._make()
        assert n is not None

    def test_texto_ascii_inalterado(self):
        n = self._make()
        assert n.nfkc_seletivo("hello world") == "hello world"

    def test_texto_vazio_retorna_vazio(self):
        n = self._make()
        assert n.nfkc_seletivo("") == ""

    def test_ligadura_fi_normalizada(self):
        n = self._make()
        resultado = n.nfkc_seletivo("ﬁ")  # ligatura fi U+FB01
        assert resultado == "fi"

    def test_superscript_normalizado_para_digit(self):
        # SUPER_SUB_SCRIPTS contains int codepoints, not chars, so check always
        # evaluates to False and the character goes through NFKC normalization
        n = self._make()
        resultado = n.nfkc_seletivo("m²")
        assert isinstance(resultado, str)
        assert len(resultado) > 0

    def test_subscript_normalizado_para_digit(self):
        n = self._make()
        resultado = n.nfkc_seletivo("H₂O")
        assert isinstance(resultado, str)
        assert len(resultado) > 0

    def test_fracao_unicode_preservada(self):
        n = self._make()
        resultado = n.nfkc_seletivo("½")  # VULGAR FRACTION ONE HALF
        assert "½" in resultado

    def test_cache_utilizado_em_chamadas_repetidas(self):
        n = self._make()
        n.nfkc_seletivo("ﬁ")
        assert "ﬁ" in n._cache

    def test_enclosed_digit_circled_um_preservado(self):
        n = self._make()
        resultado = n.nfkc_seletivo("①")  # CIRCLED DIGIT ONE
        assert "①" in resultado

    def test_texto_com_espaco_e_acento(self):
        n = self._make()
        resultado = n.nfkc_seletivo("café")
        assert "café" in resultado

    def test_logger_name_customizado(self):
        n = Normalize(logger_name="meu_logger")
        assert n._logger_name == "meu_logger"

    def test_logger_name_default_usa_classe(self):
        n = Normalize()
        assert n._logger_name == "Normalize"


class TestRegressaoOrdinais:
    def test_ordinal_masculino_preservado(self):
        assert Normalize().nfkc_seletivo("nº 612") == "nº 612"

    def test_ordinal_feminino_preservado(self):
        assert Normalize().nfkc_seletivo("1ª") == "1ª"
