"""Testes unitários para sei_extraction/html_to_md/html/bs4.py."""

from bs4 import BeautifulSoup

from sei_extraction.html_to_md.html.bs4 import BS


class TestBSInit:
    def test_instancia_criada_com_defaults(self):
        bs = BS()
        assert bs is not None

    def test_parser_default(self):
        bs = BS()
        assert bs._parser == "lxml"

    def test_fallback_parser_default(self):
        bs = BS()
        assert bs._fallback_parser == "html5lib"

    def test_logger_name_default(self):
        bs = BS()
        assert bs._logger_name == "BS"

    def test_logger_name_customizado(self):
        bs = BS(logger_name="meu_bs")
        assert bs._logger_name == "meu_bs"

    def test_parser_customizado(self):
        bs = BS(parser="html.parser")
        assert bs._parser == "html.parser"


class TestBSInicialize:
    def test_retorna_beautiful_soup(self):
        bs = BS(parser="html.parser")
        resultado = bs.inicialize("<p>texto</p>")
        assert isinstance(resultado, BeautifulSoup)

    def test_html_simples_parseado(self):
        bs = BS(parser="html.parser")
        soup = bs.inicialize("<div><p>Olá</p></div>")
        assert soup.find("p").text == "Olá"

    def test_html_com_cabecalho(self):
        bs = BS(parser="html.parser")
        soup = bs.inicialize("<html><body><h1>Título</h1></body></html>")
        assert soup.find("h1").text == "Título"

    def test_usa_fallback_quando_parser_invalido(self):
        bs = BS(parser="parser_invalido_xyz", fallback_parser="html.parser")
        soup = bs.inicialize("<p>teste</p>")
        assert isinstance(soup, BeautifulSoup)

    def test_html_vazio(self):
        bs = BS(parser="html.parser")
        soup = bs.inicialize("")
        assert isinstance(soup, BeautifulSoup)


class TestBSStaticMethods:
    def _make_soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    def test_get_root_el_retorna_raiz(self):
        soup = self._make_soup("<div><p>texto</p></div>")
        p = soup.find("p")
        raiz = BS.get_root_el(p)
        assert raiz.name == "[document]"

    def test_has_tag_children_com_filhos_tag(self):
        soup = self._make_soup("<div><p>texto</p></div>")
        div = soup.find("div")
        assert BS.has_tag_children(div) is True

    def test_has_tag_children_sem_filhos_tag(self):
        soup = self._make_soup("<p>apenas texto</p>")
        p = soup.find("p")
        assert BS.has_tag_children(p) is False

    def test_is_first_child_not_p_quando_primeiro_filho_nao_p(self):
        soup = self._make_soup("<div><span>texto</span></div>")
        div = soup.find("div")
        assert BS.is_first_child_not_p(div) is True

    def test_is_first_child_not_p_quando_primeiro_filho_p(self):
        soup = self._make_soup("<div><p>texto</p></div>")
        div = soup.find("div")
        assert BS.is_first_child_not_p(div) is False

    def test_is_first_child_not_name_quando_match(self):
        soup = self._make_soup("<div><span>x</span></div>")
        div = soup.find("div")
        assert BS.is_first_child_not_name(div, "span") is False

    def test_is_first_child_not_name_quando_diferente(self):
        soup = self._make_soup("<div><span>x</span></div>")
        div = soup.find("div")
        assert BS.is_first_child_not_name(div, "p") is True

    def test_name_first_parent_in_list_encontra_pai(self):
        soup = self._make_soup("<table><tr><td><span>x</span></td></tr></table>")
        span = soup.find("span")
        resultado = BS.name_first_parent_in_list(span, ["td", "tr"])
        assert resultado == "td"

    def test_name_first_parent_in_list_retorna_vazio_sem_match(self):
        soup = self._make_soup("<div><p><span>x</span></p></div>")
        span = soup.find("span")
        resultado = BS.name_first_parent_in_list(span, ["table", "ul"])
        assert resultado == ""

    def test_has_single_child_com_filho_unico(self):
        soup = self._make_soup("<div><p>único</p></div>")
        div = soup.find("div")
        assert BS.has_single_child(div, "p") is True

    def test_has_single_child_com_multiplos_filhos(self):
        soup = self._make_soup("<div><p>um</p><p>dois</p></div>")
        div = soup.find("div")
        assert BS.has_single_child(div, "p") is False

    def test_has_single_child_tipo_diferente(self):
        soup = self._make_soup("<div><span>texto</span></div>")
        div = soup.find("div")
        assert BS.has_single_child(div, "p") is False
