"""Testes unitários para sei_extraction/html_to_md/html_to_txtmd.py."""

from sei_extraction.html_to_md.html_to_txtmd import HtmlTxtmd


def convert(html: str) -> str:
    h = HtmlTxtmd()
    h.processa(html)
    return h.output


class TestHtmlTxtmdInit:
    def test_instancia_criada(self):
        h = HtmlTxtmd()
        assert h is not None

    def test_logger_name_default(self):
        h = HtmlTxtmd()
        assert h._logger_name == "HtmlTxtmd"

    def test_logger_name_customizado(self):
        h = HtmlTxtmd(logger_name="meu")
        assert h._logger_name == "meu"


class TestHtmlTxtmdTextSimples:
    def test_paragrafo_simples(self):
        resultado = convert("<p>texto simples</p>")
        assert "texto simples" in resultado

    def test_texto_html_vazio(self):
        resultado = convert("")
        assert isinstance(resultado, str)

    def test_texto_em_div(self):
        resultado = convert("<div><p>texto em div</p></div>")
        assert "texto em div" in resultado

    def test_tab_convertido_para_espaco(self):
        h = HtmlTxtmd()
        resultado = h.tab_to_space("a\tb")
        assert "\t" not in resultado
        assert " " in resultado


class TestHtmlTxtmdHeadings:
    def test_h1_vira_markdown_h1(self):
        resultado = convert("<h1>Título</h1>")
        assert "# Título" in resultado

    def test_h2_vira_markdown_h2(self):
        resultado = convert("<h2>Subtítulo</h2>")
        assert "## Subtítulo" in resultado

    def test_h3_vira_markdown_h3(self):
        resultado = convert("<h3>Seção</h3>")
        assert "### Seção" in resultado


class TestHtmlTxtmdInlineFormatting:
    def test_bold_com_strong(self):
        resultado = convert("<p><strong>negrito</strong></p>")
        assert "**negrito**" in resultado

    def test_bold_com_b(self):
        resultado = convert("<p><b>negrito</b></p>")
        assert "**negrito**" in resultado

    def test_italic_com_em(self):
        resultado = convert("<p><em>itálico</em></p>")
        assert "_itálico_" in resultado

    def test_italic_com_i(self):
        resultado = convert("<p><i>itálico</i></p>")
        assert "_itálico_" in resultado

    def test_strikethrough_com_s(self):
        resultado = convert("<p><s>riscado</s></p>")
        assert "~~riscado~~" in resultado

    def test_strikethrough_com_del(self):
        resultado = convert("<p><del>deletado</del></p>")
        assert "~~deletado~~" in resultado

    def test_code_inline(self):
        resultado = convert("<p><code>codigo</code></p>")
        assert "`codigo`" in resultado

    def test_svg_vira_placeholder(self):
        resultado = convert("<p><svg></svg></p>")
        assert "[svg]" in resultado


class TestHtmlTxtmdLinks:
    def test_link_simples(self):
        resultado = convert('<p><a href="http://exemplo.com">link</a></p>')
        assert "link" in resultado
        assert "http://exemplo.com" in resultado

    def test_link_com_title(self):
        resultado = convert('<p><a href="http://ex.com" title="dica">texto</a></p>')
        assert "dica" in resultado

    def test_link_sem_href_retorna_texto(self):
        resultado = convert("<p><a>texto sem link</a></p>")
        assert "texto sem link" in resultado


class TestHtmlTxtmdImagens:
    def test_imagem_simples(self):
        resultado = convert('<p><img src="img.png" alt="descrição"></p>')
        assert "![descrição](img.png)" in resultado

    def test_imagem_sem_alt(self):
        resultado = convert('<p><img src="img.png"></p>')
        assert "img.png" in resultado

    def test_imagem_data_uri_substituida(self):
        resultado = convert('<p><img src="data:image/png;base64,abc" alt="img"></p>')
        assert "![img](_)" in resultado

    def test_imagem_sem_src_usa_underscore(self):
        resultado = convert('<p><img alt="sem src"></p>')
        assert "![sem src](_)" in resultado


class TestHtmlTxtmdListas:
    def test_lista_nao_ordenada(self):
        resultado = convert("<ul><li>item 1</li><li>item 2</li></ul>")
        assert "- " in resultado
        assert "item 1" in resultado

    def test_lista_ordenada(self):
        resultado = convert("<ol><li>primeiro</li><li>segundo</li></ol>")
        assert "primeiro" in resultado

    def test_lista_ordenada_com_start(self):
        resultado = convert('<ol start="3"><li>três</li></ol>')
        assert "três" in resultado


class TestHtmlTxtmdTabelas:
    def test_tabela_simples_vira_markdown(self):
        html = """<table>
            <tr><th>Col A</th><th>Col B</th></tr>
            <tr><td>1</td><td>2</td></tr>
        </table>"""
        resultado = convert(html)
        assert "|" in resultado
        assert "Col A" in resultado

    def test_tabela_com_caption(self):
        html = """<table>
            <caption>Minha Tabela</caption>
            <tr><td>dados</td></tr>
        </table>"""
        resultado = convert(html)
        assert "Minha Tabela" in resultado

    def test_tabela_aninhada_vira_divs(self):
        html = """<table>
            <tr><td><table><tr><td>interna</td></tr></table></td></tr>
        </table>"""
        resultado = convert(html)
        assert "interna" in resultado


class TestHtmlTxtmdSpecial:
    def test_hr_vira_separador(self):
        resultado = convert("<div><hr></div>")
        assert "---" in resultado

    def test_pre_vira_code_block(self):
        resultado = convert("<pre>codigo\npré-formatado</pre>")
        assert "```" in resultado
        assert "codigo" in resultado

    def test_remove_tags_ignoradas(self):
        resultado = convert("<script>alert('xss')</script><p>texto</p>")
        assert "alert" not in resultado
        assert "texto" in resultado

    def test_remove_display_none(self):
        resultado = convert('<p style="display:none">escondido</p><p>visível</p>')
        assert "escondido" not in resultado
        assert "visível" in resultado

    def test_embed_com_src(self):
        resultado = convert('<p><embed src="arquivo.pdf"></p>')
        assert "embed src" in resultado

    def test_br_em_paragrafo(self):
        resultado = convert("<p>linha 1<br>linha 2</p>")
        assert "linha 1" in resultado
        assert "linha 2" in resultado

    def test_br_em_heading_vira_dash(self):
        resultado = convert("<h1>parte 1<br>parte 2</h1>")
        assert "—" in resultado


class TestHtmlTxtmdUtilities:
    def test_suffix_if_not_adiciona_sufixo(self):
        h = HtmlTxtmd()
        assert h.suffix_if_not("texto", "\n") == "texto\n"

    def test_suffix_if_not_nao_duplica_sufixo(self):
        h = HtmlTxtmd()
        assert h.suffix_if_not("texto\n", "\n") == "texto\n"

    def test_has_nested_table_true(self):
        from bs4 import BeautifulSoup

        h = HtmlTxtmd()
        soup = BeautifulSoup(
            "<table><tr><td><table></table></td></tr></table>", "html.parser"
        )
        outer = soup.find("table")
        assert h.has_nested_table(outer) is True

    def test_has_nested_table_false(self):
        from bs4 import BeautifulSoup

        h = HtmlTxtmd()
        soup = BeautifulSoup("<table><tr><td>dados</td></tr></table>", "html.parser")
        outer = soup.find("table")
        assert not h.has_nested_table(outer)

    def test_outputs_append_conteudo_nao_vazio(self):
        h = HtmlTxtmd()
        outputs = []
        h.outputs_append(outputs, "texto")
        assert outputs == ["texto"]

    def test_outputs_append_string_vazia_nao_adicionada(self):
        h = HtmlTxtmd()
        outputs = []
        h.outputs_append(outputs, "")
        assert outputs == []

    def test_new_levels_incrementa_log_level(self):
        h = HtmlTxtmd()
        levels = {"ol_level": 1, "log_level": 0}
        result = h.new_levels(levels)
        assert result["log_level"] == 1
        assert levels["log_level"] == 0  # original não modificado

    def test_lista_titulo_interior_separa(self):
        h = HtmlTxtmd()
        titulo, interior = h.lista_titulo_interior(["título", "linha 1", "linha 2"])
        assert titulo == "título"
        assert interior == ["linha 1", "linha 2"]

    def test_lista_titulo_interior_vazia(self):
        h = HtmlTxtmd()
        titulo, interior = h.lista_titulo_interior([])
        assert titulo == "\n\n"
        assert interior == []


class TestHtmlTxtmdSupSub:
    def test_sup_com_texto(self):
        resultado = convert("<p>m<sup>2</sup></p>")
        assert "^{2}" in resultado

    def test_sub_com_texto(self):
        resultado = convert("<p>H<sub>2</sub>O</p>")
        assert "_{2}" in resultado

    def test_sup_anexado_ao_texto_anterior(self):
        resultado = convert("<p>m<sup>2</sup></p>")
        assert "^{2}" in resultado


class TestHtmlTxtmdOutput:
    def test_output_limpa_outputs_internos(self):
        h = HtmlTxtmd()
        h.processa("<p>texto</p>")
        _ = h.output
        h.processa("<p>novo</p>")
        resultado = h.output
        assert "novo" in resultado

    def test_new_outputs_reseta_lista(self):
        h = HtmlTxtmd()
        h.new_outputs()
        assert h._outputs == []


class TestRegressaoLinkSemTitle:
    def test_link_sem_title_nao_corrompe_url(self):
        resultado = convert('<p><a href="http://ex.com">texto</a></p>')
        assert "[texto](http://ex.com)" in resultado
        assert "None" not in resultado
