"""Testes unitários para sei_extraction/html_to_md/html/tag_types.py."""

from sei_extraction.html_to_md.html.tag_types import HtmlTagTypes


class TestHtmlTagTypesStructure:
    def test_document_eh_set(self):
        assert isinstance(HtmlTagTypes.DOCUMENT, set)

    def test_document_contem_html(self):
        assert "html" in HtmlTagTypes.DOCUMENT

    def test_document_contem_body(self):
        assert "body" in HtmlTagTypes.DOCUMENT

    def test_sectioning_contem_section(self):
        assert "section" in HtmlTagTypes.SECTIONING

    def test_sectioning_contem_article(self):
        assert "article" in HtmlTagTypes.SECTIONING

    def test_div_like_contem_div(self):
        assert "div" in HtmlTagTypes.DIV_LIKE

    def test_div_like_inclui_sectioning(self):
        for tag in HtmlTagTypes.SECTIONING:
            assert tag in HtmlTagTypes.DIV_LIKE

    def test_table_contem_tags_basicas(self):
        for tag in ["table", "tr", "td", "th"]:
            assert tag in HtmlTagTypes.TABLE

    def test_lists_contem_ul_ol_li(self):
        for tag in ["ul", "ol", "li"]:
            assert tag in HtmlTagTypes.LISTS

    def test_phrasing_tags_contem_span(self):
        assert "span" in HtmlTagTypes.PHRASING_TAGS

    def test_phrasing_tags_contem_strong(self):
        assert "strong" in HtmlTagTypes.PHRASING_TAGS

    def test_phrasing_tags_contem_a(self):
        assert "a" in HtmlTagTypes.PHRASING_TAGS

    def test_phrasing_tags_contem_b(self):
        assert "b" in HtmlTagTypes.PHRASING_TAGS

    def test_phrasing_tags_contem_em(self):
        assert "em" in HtmlTagTypes.PHRASING_TAGS

    def test_phrasing_tags_contem_code(self):
        assert "code" in HtmlTagTypes.PHRASING_TAGS

    def test_phrasing_tags_contem_br(self):
        assert "br" in HtmlTagTypes.PHRASING_TAGS

    def test_flow_containers_eh_set(self):
        assert isinstance(HtmlTagTypes.FLOW_CONTAINERS, set)

    def test_flow_containers_inclui_table(self):
        for tag in HtmlTagTypes.TABLE:
            assert tag in HtmlTagTypes.FLOW_CONTAINERS

    def test_flow_containers_inclui_lists(self):
        for tag in HtmlTagTypes.LISTS:
            assert tag in HtmlTagTypes.FLOW_CONTAINERS

    def test_ignore_contem_script(self):
        assert "script" in HtmlTagTypes.IGNORE

    def test_ignore_contem_style(self):
        assert "style" in HtmlTagTypes.IGNORE

    def test_document_ignore_contem_head(self):
        assert "head" in HtmlTagTypes.DOCUMENT_IGNORE

    def test_quotes_contem_blockquote(self):
        assert "blockquote" in HtmlTagTypes.QUOTES

    def test_quotes_contem_pre(self):
        assert "pre" in HtmlTagTypes.QUOTES

    def test_separators_contem_hr(self):
        assert "hr" in HtmlTagTypes.SEPARATORS

    def test_obsolete_contem_center(self):
        assert "center" in HtmlTagTypes.OBSOLETE
