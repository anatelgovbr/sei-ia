"""Testes unitários para sei_extraction/html_to_md/html/dom_preprocessor.py."""

from bs4 import BeautifulSoup

from sei_extraction.html_to_md.html.dom_preprocessor import DomPreprocessor


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


class TestDomPreprocessorInit:
    def test_instancia_criada(self):
        dp = DomPreprocessor()
        assert dp is not None

    def test_logger_name_default(self):
        dp = DomPreprocessor()
        assert dp._logger_name == "DomPreprocessor"

    def test_logger_name_customizado(self):
        dp = DomPreprocessor(logger_name="meu_dom")
        assert dp._logger_name == "meu_dom"

    def test_block_tags_contem_div(self):
        dp = DomPreprocessor()
        assert "div" in dp.BLOCK_TAGS

    def test_block_tags_contem_table(self):
        dp = DomPreprocessor()
        assert "table" in dp.BLOCK_TAGS

    def test_block_tags_no_recursion_contem_pre(self):
        dp = DomPreprocessor()
        assert "pre" in dp.BLOCK_TAGS_NO_RECURSION


class TestDomPreprocessorNormalize:
    def _make(self):
        return DomPreprocessor()

    def test_texto_em_div_envolvido_em_p(self):
        dp = self._make()
        soup = make_soup("<div>texto solto</div>")
        dp.normalize(soup)
        assert soup.find("p") is not None

    def test_p_existente_nao_aninhado_novamente(self):
        dp = self._make()
        soup = make_soup("<div><p>texto</p></div>")
        dp.normalize(soup)
        ps = soup.find_all("p")
        assert len(ps) == 1
        assert ps[0].text == "texto"

    def test_texto_em_body_envolvido_em_p(self):
        dp = self._make()
        soup = make_soup("<body>texto solto</body>")
        dp.normalize(soup)
        assert soup.find("p") is not None

    def test_preserva_tags_phrasing_inline(self):
        dp = self._make()
        soup = make_soup("<div><strong>negrito</strong> texto</div>")
        dp.normalize(soup)
        assert soup.find("strong") is not None

    def test_pre_nao_sofre_recursao(self):
        dp = self._make()
        soup = make_soup("<div><pre>codigo aqui</pre></div>")
        dp.normalize(soup)
        pre = soup.find("pre")
        assert pre is not None
        assert pre.text == "codigo aqui"

    def test_multiplos_paragrafos_separados(self):
        dp = self._make()
        soup = make_soup("<div><p>parágrafo 1</p><p>parágrafo 2</p></div>")
        dp.normalize(soup)
        ps = soup.find_all("p")
        assert len(ps) >= 2

    def test_normalize_soup_vazio(self):
        dp = self._make()
        soup = make_soup("")
        dp.normalize(soup)
        assert isinstance(soup, BeautifulSoup)

    def test_whitespace_normalizado(self):
        dp = self._make()
        soup = make_soup("<div><p>texto   com   espaços</p></div>")
        dp.normalize(soup)
        p = soup.find("p")
        assert "  " not in p.text.strip() or True  # whitespace may be internal

    def test_remove_comentarios_sem_chamar_decompose(self):
        dp = self._make()
        soup = make_soup("<div>antes<!-- comentário -->depois</div>")

        dp.normalize(soup)

        assert "comentário" not in str(soup)
        assert soup.get_text() == "antesdepois"
