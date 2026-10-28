"""Testes unitários para sei_extraction/html_to_md/html/editor_sei.py."""

from bs4 import BeautifulSoup

from sei_extraction.html_to_md.html.editor_sei import EditorSei


def make_tag(html: str):
    return BeautifulSoup(html, "html.parser").find()


class TestEditorSeiInit:
    def test_instancia_criada(self):
        e = EditorSei()
        assert e is not None

    def test_logger_name_default(self):
        e = EditorSei()
        assert e._logger_name == "EditorSei"

    def test_logger_name_customizado(self):
        e = EditorSei(logger_name="meu_editor")
        assert e._logger_name == "meu_editor"

    def test_roman_numerals_gerados(self):
        e = EditorSei()
        assert len(e.ROMAN_NUMERALS) == 500

    def test_letters_lower_gerados(self):
        e = EditorSei()
        assert "a" in e.LETTERS_LOWER
        assert "z" in e.LETTERS_LOWER
        assert "aa" in e.LETTERS_LOWER

    def test_p_globals_eh_dict(self):
        e = EditorSei()
        assert isinstance(e.P_GLOBALS, dict)

    def test_p_globals_contem_item_nivel1(self):
        e = EditorSei()
        assert "Item_Nivel1" in e.P_GLOBALS

    def test_li_type_level_contem_defaults(self):
        e = EditorSei()
        assert ("default", 1) in e.LI_TYPE_LEVEL
        assert ("decimal", 0) in e.LI_TYPE_LEVEL


class TestEditorSeiIntToRoman:
    def _make(self):
        return EditorSei()

    def test_1_retorna_I(self):
        e = self._make()
        assert e.int_to_roman(1) == "I"

    def test_4_retorna_IV(self):
        e = self._make()
        assert e.int_to_roman(4) == "IV"

    def test_9_retorna_IX(self):
        e = self._make()
        assert e.int_to_roman(9) == "IX"

    def test_40_retorna_XL(self):
        e = self._make()
        assert e.int_to_roman(40) == "XL"

    def test_90_retorna_XC(self):
        e = self._make()
        assert e.int_to_roman(90) == "XC"

    def test_100_retorna_C(self):
        e = self._make()
        assert e.int_to_roman(100) == "C"

    def test_400_retorna_CD(self):
        e = self._make()
        assert e.int_to_roman(400) == "CD"

    def test_500_retorna_D(self):
        e = self._make()
        assert e.int_to_roman(500) == "D"

    def test_1000_retorna_M(self):
        e = self._make()
        assert e.int_to_roman(1000) == "M"


class TestEditorSeiLatin:
    def _make(self):
        return EditorSei()

    def test_lower_latin_1_retorna_a(self):
        e = self._make()
        assert e.int_to_lower_latin(1) == "a"

    def test_lower_latin_26_retorna_z(self):
        e = self._make()
        assert e.int_to_lower_latin(26) == "z"

    def test_upper_latin_1_retorna_A(self):
        e = self._make()
        assert e.int_to_upper_latin(1) == "A"

    def test_upper_latin_26_retorna_Z(self):
        e = self._make()
        assert e.int_to_upper_latin(26) == "Z"

    def test_lower_roman_1_retorna_i(self):
        e = self._make()
        assert e.int_to_lower_roman(1) == "i"

    def test_upper_roman_1_retorna_I(self):
        e = self._make()
        assert e.int_to_upper_roman(1) == "I"


class TestEditorSeiHasClass:
    def _make(self):
        return EditorSei()

    def test_has_class_retorna_true_quando_encontrada(self):
        e = self._make()
        tag = make_tag('<p class="minha-classe outra">texto</p>')
        assert e.has_class(tag, "minha-classe") is True

    def test_has_class_retorna_false_quando_nao_encontrada(self):
        e = self._make()
        tag = make_tag('<p class="outra">texto</p>')
        assert not e.has_class(tag, "minha-classe")

    def test_has_class_retorna_false_sem_classes(self):
        e = self._make()
        tag = make_tag("<p>texto</p>")
        assert not e.has_class(tag, "qualquer")


class TestEditorSeiGetClasses:
    def _make(self):
        return EditorSei()

    def test_get_classes_by_prefix_sem_prefix_retorna_todas(self):
        e = self._make()
        tag = make_tag('<p class="foo bar baz">texto</p>')
        resultado = e.get_classes_by_prefix(tag)
        assert "foo" in resultado

    def test_get_classes_by_prefix_com_prefix(self):
        e = self._make()
        tag = make_tag('<ol class="list-style-type-decimal foo">texto</ol>')
        resultado = e.get_classes_by_prefix(tag, "list-style-type-")
        assert "decimal" in resultado

    def test_get_classes_sem_elemento_retorna_default(self):
        e = self._make()
        tag = make_tag("<p>texto</p>")
        resultado = e.get_classes_by_prefix(tag, "prefixo-", "meu_default")
        assert resultado == ["meu_default"]

    def test_get_1st_class_by_prefix_retorna_primeira(self):
        e = self._make()
        tag = make_tag('<p class="list-style-type-upper-roman">texto</p>')
        resultado = e.get_1st_class_by_prefix(tag, "list-style-type-")
        assert resultado == "upper-roman"


class TestEditorSeiSetLogIdent:
    def test_set_log_ident(self):
        e = EditorSei()
        e.set_log_ident("  ")
        assert e._log_ident == "  "


class TestEditorSeiGetPGlobals:
    def test_get_p_globals_retorna_dict(self):
        e = EditorSei()
        resultado = e.get_p_globals()
        assert isinstance(resultado, dict)

    def test_get_p_globals_tem_item_nivel1(self):
        e = EditorSei()
        resultado = e.get_p_globals()
        assert "Item_Nivel1" in resultado

    def test_get_p_globals_valores_sao_zero(self):
        e = EditorSei()
        resultado = e.get_p_globals()
        for v in resultado.values():
            assert v == 0


class TestEditorSeiPSeriesInc:
    def test_incrementa_nivel(self):
        e = EditorSei()
        counters = dict.fromkeys(e.P_GLOBALS, 0)
        e.p_series_inc("Item_Nivel1", counters)
        assert counters["Item_Nivel1"] == 1

    def test_zera_niveis_subsequentes(self):
        e = EditorSei()
        counters = dict.fromkeys(e.P_GLOBALS, 5)
        e.p_series_inc("Item_Nivel1", counters)
        assert counters["Item_Nivel2"] == 0


class TestEditorSeiOlNumberLambda:
    def test_ol_padrao_retorna_callable(self):
        e = EditorSei()
        tag = make_tag(
            '<ol class="infra-editor__lista list-style-type-decimal">items</ol>'
        )
        resultado = e.ol_number_lambda(tag, level=0)
        assert callable(resultado)

    def test_ol_nao_sei_usa_tipo_html(self):
        e = EditorSei()
        tag = make_tag('<ol type="1">items</ol>')
        resultado = e.ol_number_lambda(tag, level=0)
        assert callable(resultado)
        assert "1." in resultado(1)


class TestEditorSeiPClassLambda:
    def test_item_nivel1_formata_como_titulo(self):
        e = EditorSei()
        counters = dict.fromkeys(e.P_GLOBALS, 0)
        tag = make_tag('<p class="Item_Nivel1">texto</p>')
        fn = e.p_class_lambda(tag, counters)
        resultado = fn("meu título")
        assert "**" in resultado

    def test_classe_sem_match_retorna_linha(self):
        e = EditorSei()
        counters = dict.fromkeys(e.P_GLOBALS, 0)
        tag = make_tag('<p class="Outra_Classe">texto</p>')
        fn = e.p_class_lambda(tag, counters)
        assert fn("linha") == "linha"

    def test_p_upper_retorna_maiusculo(self):
        e = EditorSei()
        counters = dict.fromkeys(e.P_GLOBALS, 0)
        tag = make_tag('<p class="Texto_Centralizado_Maiusculas">texto</p>')
        fn = e.p_class_lambda(tag, counters)
        assert fn("texto") == "TEXTO"

    def test_p_bold_retorna_negrito(self):
        e = EditorSei()
        counters = dict.fromkeys(e.P_GLOBALS, 0)
        tag = make_tag('<p class="Texto_Fundo_Cinza_Negrito">texto</p>')
        fn = e.p_class_lambda(tag, counters)
        assert fn("texto") == "**texto**"

    def test_p_quote_retorna_code_block(self):
        e = EditorSei()
        counters = dict.fromkeys(e.P_GLOBALS, 0)
        tag = make_tag('<p class="Citacao">texto</p>')
        fn = e.p_class_lambda(tag, counters)
        resultado = fn("texto")
        assert "```" in resultado
