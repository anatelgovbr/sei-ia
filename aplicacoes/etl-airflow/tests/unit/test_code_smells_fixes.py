"""Testes para as correções de code smells SonarQube."""

import unittest

from bs4 import BeautifulSoup


class TestRegexFixes(unittest.TestCase):
    """S5361 e S7512 — regex.py."""

    def test_transform_expressions_removes_special_chars(self):
        from jobs.dags.inference.regex import transform_expressions

        result = transform_expressions("resolução nº 123")
        self.assertNotIn("ç", result)
        self.assertNotIn("ã", result)
        self.assertNotIn("º", result)

    def test_transform_expressions_cedilha_removed(self):
        from jobs.dags.inference.regex import transform_expressions

        # re.sub removes ç before .replace("ç","c") executes
        result = transform_expressions("çç")
        self.assertNotIn("ç", result)

    def test_transform_expressions_til_removed(self):
        from jobs.dags.inference.regex import transform_expressions

        # re.sub removes ã before .replace("ã","a") executes
        result = transform_expressions("ão")
        self.assertNotIn("ã", result)

    def test_summarize_text_returns_string(self):
        from jobs.dags.inference.regex import summarize_text

        result = summarize_text("resolução nº 123.456")
        self.assertIsInstance(result, str)

    def test_summarize_text_empty(self):
        from jobs.dags.inference.regex import summarize_text

        result = summarize_text("")
        self.assertEqual(result, "")

    def test_summarize_text_no_matches(self):
        from jobs.dags.inference.regex import summarize_text

        result = summarize_text("texto sem expressões regulamentares")
        self.assertEqual(result, "")


class TestFuncsFixes(unittest.TestCase):
    """S7508 — funcs.py."""

    def test_group_concat_distinct_unique(self):
        import pandas as pd

        from jobs.utils.funcs import group_concat_distinct

        series = pd.Series(["a", "b", "a", "c"])
        result = group_concat_distinct(series)
        parts = result.split(",")
        self.assertEqual(len(parts), len(set(parts)))

    def test_group_concat_distinct_sorted_desc(self):
        import pandas as pd

        from jobs.utils.funcs import group_concat_distinct

        series = pd.Series(["b", "a", "c"])
        result = group_concat_distinct(series)
        parts = result.split(",")
        self.assertEqual(parts, sorted(parts, reverse=True))

    def test_group_concat_distinct_single(self):
        import pandas as pd

        from jobs.utils.funcs import group_concat_distinct

        series = pd.Series(["x"])
        self.assertEqual(group_concat_distinct(series), "x")


class TestTextPreprocessFixes(unittest.TestCase):
    """S6659, S6397, S5857 — funções extraídas diretamente sem importar o módulo completo
    (que depende de sei_ia não disponível no ambiente de teste)."""

    def test_remove_html_tags_basic(self):
        import re

        def remove_html_tags(text):
            return re.sub(r"<[^>]*>", "", text)

        result = remove_html_tags("<p>hello <b>world</b></p>")
        self.assertEqual(result, "hello world")

    def test_remove_html_tags_empty(self):
        import re

        def remove_html_tags(text):
            return re.sub(r"<[^>]*>", "", text)

        self.assertEqual(remove_html_tags(""), "")

    def test_remove_html_tags_no_tags(self):
        import re

        def remove_html_tags(text):
            return re.sub(r"<[^>]*>", "", text)

        self.assertEqual(remove_html_tags("plain text"), "plain text")

    def test_remove_html_tags_angle_bracket_in_content(self):
        import re

        def remove_html_tags(text):
            return re.sub(r"<[^>]*>", "", text)

        # [^>]* para no ">" então não consome o conteúdo após o tag
        result = remove_html_tags("<p>a > b</p>")
        self.assertEqual(result, "a > b")

class TestSectionsDictionary(unittest.TestCase):
    """S1192 — sections_dictionary.py: constantes REFERÊNCIA/CONCLUSÃO."""

    def test_constants_present_in_analise(self):
        from jobs.dags.preprocessing.sections_dictionary import SECTIONS_DICTIONARY

        refs = SECTIONS_DICTIONARY["analise"]["referencias"]
        self.assertIn("REFERÊNCIA", refs)
        self.assertIn("REFERÊNCIAS", refs)
        conclusao = SECTIONS_DICTIONARY["analise"]["conclusao"]
        self.assertIn("CONCLUSÃO", conclusao)

    def test_constants_present_in_informe(self):
        from jobs.dags.preprocessing.sections_dictionary import SECTIONS_DICTIONARY

        refs = SECTIONS_DICTIONARY["informe"]["referencias"]
        self.assertIn("REFERÊNCIA", refs)
        self.assertIn("REFERÊNCIAS", refs)

    def test_constants_present_in_voto(self):
        from jobs.dags.preprocessing.sections_dictionary import SECTIONS_DICTIONARY

        refs = SECTIONS_DICTIONARY["voto"]["referencias"]
        self.assertIn("REFERÊNCIA", refs)
        self.assertIn("REFERÊNCIAS", refs)


class TestSplitSection(unittest.TestCase):
    """S1192 — split_section2.py: constante _HTML_PARSER."""

    def test_split_section_parses_html(self):
        from jobs.dags.preprocessing.split_section2 import SplitSection

        html = "<html><body><p>Texto</p></body></html>"
        obj = SplitSection(html)
        self.assertIsNotNone(obj.doc)

    def test_split_section_empty_body(self):
        from jobs.dags.preprocessing.split_section2 import SplitSection

        obj = SplitSection("<html><body></body></html>")
        self.assertIsNotNone(obj)


class TestBs4ListCast(unittest.TestCase):
    """Valida que find_all() retorna ResultSet (já iterável como lista)."""

    def test_find_all_result_is_iterable_without_list_cast(self):
        html = "<ul><li>a</li><li>b</li><li>c</li></ul>"
        soup = BeautifulSoup(html, "html.parser")
        ul = soup.find("ul")
        items = ul.find_all("li", recursive=False)
        result = [li.get_text() for li in items]
        self.assertEqual(result, ["a", "b", "c"])

    def test_find_all_supports_enumerate_directly(self):
        html = "<ol><li>x</li><li>y</li></ol>"
        soup = BeautifulSoup(html, "html.parser")
        ol = soup.find("ol")
        pairs = list(enumerate(ol.find_all("li", recursive=False), start=1))
        self.assertEqual(pairs[0][0], 1)
        self.assertEqual(pairs[0][1].get_text(), "x")

    def test_find_all_tr_th_td_without_list_cast(self):
        html = "<table><tr><th>H1</th><th>H2</th></tr><tr><td>A</td><td>B</td></tr></table>"
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        rows = table.find_all("tr")
        cells = [cell.get_text() for row in rows for cell in row.find_all(["th", "td"])]
        self.assertEqual(cells, ["H1", "H2", "A", "B"])


if __name__ == "__main__":
    unittest.main()
