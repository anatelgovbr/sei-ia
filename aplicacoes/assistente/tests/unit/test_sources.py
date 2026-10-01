"""Testes unitários para o módulo sources.

Módulo testado: sei_ia/services/llm_models/citation_sources.py
"""

from sei_ia.services.llm_models.citation_sources import (
    _clean_web_excerpt,
    _escape_tooltip_title,
    build_web_references_section,
    clean_chunk_text_for_display,
    create_chunk_tooltip,
    create_doc_tooltip,
    create_web_search_tooltip,
    find_web_search_metadata,
    get_document_count,
)


class TestCleanChunkTextForDisplay:
    """Testes para clean_chunk_text_for_display."""

    def test_texto_sem_cabecalho_nao_muda(self):
        texto = "conteúdo simples sem cabeçalho"
        assert clean_chunk_text_for_display(texto) == texto

    def test_retorna_string(self):
        assert isinstance(clean_chunk_text_for_display("qualquer texto"), str)

    def test_texto_vazio_retorna_vazio_ou_original(self):
        resultado = clean_chunk_text_for_display("")
        assert isinstance(resultado, str)

    def test_texto_com_conteudo_real_preservado(self):
        texto = "Este é o conteúdo real do documento."
        resultado = clean_chunk_text_for_display(texto)
        assert "conteúdo real" in resultado


class TestGetDocumentCount:
    """Testes para get_document_count."""

    def test_retorna_zero_para_none(self):
        assert get_document_count(None) == 0

    def test_retorna_zero_para_state_sem_procedimentos(self):
        assert get_document_count({}) == 0

    def test_usa_rag_documents_count_se_disponivel(self):
        state = {"rag_documents_count": 5}
        assert get_document_count(state) == 5


class TestCreateWebSearchTooltip:
    """Testes para create_web_search_tooltip."""

    def test_retorna_string(self):
        metadata = {"url": "https://example.com", "title": "Exemplo"}
        assert isinstance(create_web_search_tooltip(metadata, 1), str)

    def test_contem_url(self):
        metadata = {"url": "https://gov.br", "title": "Gov"}
        resultado = create_web_search_tooltip(metadata, 1)
        assert "https://gov.br" in resultado

    def test_contem_numero_sequencial(self):
        metadata = {"url": "https://example.com", "title": "X"}
        resultado = create_web_search_tooltip(metadata, 7)
        assert "[7]" in resultado

    def test_contem_classe_css(self):
        metadata = {"url": "https://example.com", "title": "X"}
        resultado = create_web_search_tooltip(metadata, 1)
        assert "AssistenteSEIIAfonteWebSearch" in resultado

    def test_hover_mostra_trecho_nao_url(self):
        """O title (hover) deve exibir o trecho, não a URL, quando há preview."""
        metadata = {
            "url": "https://gov.br",
            "title": "Gov",
            "preview": "trecho de conteudo usado na resposta",
        }
        resultado = create_web_search_tooltip(metadata, 1)
        assert 'title="trecho de conteudo usado na resposta"' in resultado
        # a URL continua clicável no href, mas não é o conteúdo do hover
        assert 'href="https://gov.br"' in resultado
        assert 'title="https://gov.br"' not in resultado

    def test_hover_cai_para_url_sem_preview(self):
        """Sem preview, o hover cai para a URL (comportamento anterior)."""
        metadata = {"url": "https://gov.br", "title": "Gov"}
        resultado = create_web_search_tooltip(metadata, 1)
        assert 'title="https://gov.br"' in resultado


class TestCleanWebExcerpt:
    """Testes para _clean_web_excerpt."""

    def test_colapsa_espacos_e_trunca(self):
        texto = "linha um\n\n   linha    dois " + "x" * 500
        out = _clean_web_excerpt(texto, max_len=30)
        assert "\n" not in out
        assert "  " not in out
        assert out.endswith("...")
        assert len(out) <= 33  # 30 + reticências

    def test_nao_escapa_aqui_escape_e_no_builder(self):
        # _clean_web_excerpt só limpa/trunca; o escape do title é responsabilidade do
        # builder do tooltip (_escape_tooltip_title), num único ponto de saída.
        out = _clean_web_excerpt('aspas " e <tag> & cia | pipe')
        assert out == 'aspas " e <tag> & cia | pipe'

    def test_vazio_retorna_vazio(self):
        assert _clean_web_excerpt("") == ""


class TestFindWebSearchMetadata:
    """Testes para find_web_search_metadata (inclui preview)."""

    def test_preview_do_content_modo_simples(self):
        state = {
            "tool_web_search": [
                {
                    "idx": 1,
                    "content": "texto da pagina usado",
                    "references": [{"url": "https://a.com", "title": "A"}],
                }
            ]
        }
        md = find_web_search_metadata("1", state)
        assert md["url"] == "https://a.com"
        assert md["preview"] == "texto da pagina usado"

    def test_preview_do_snippet_modo_deep(self):
        """No deep o content do item é vazio; o trecho vem do snippet da referência."""
        state = {
            "tool_web_search": [
                {
                    "idx": 2,
                    "content": "",
                    "references": [
                        {"url": "https://b.com", "title": "B", "snippet": "trecho deep"}
                    ],
                }
            ]
        }
        md = find_web_search_metadata("2", state)
        assert md["preview"] == "trecho deep"

    def test_preview_prefere_snippet_sobre_content_no_classic(self):
        """Classic path: com snippet do SearXNG disponível, o tooltip usa o snippet
        (trecho relevante à query), não o topo da página crua (nav/cookies)."""
        state = {
            "tool_web_search": [
                {
                    "idx": 3,
                    "content": "menu mobile Notícias Artigos Cookies Nós utilizamos",
                    "references": [
                        {
                            "url": "https://fiis.com.br/knri11/",
                            "title": "KNRI11",
                            "snippet": "KNRI11 distribui rendimentos mensais; DY 12M de 8,2%.",
                        }
                    ],
                }
            ]
        }
        md = find_web_search_metadata("3", state)
        assert md["preview"] == "KNRI11 distribui rendimentos mensais; DY 12M de 8,2%."
        assert "Cookies" not in md["preview"]


class TestBuildWebReferencesSection:
    """Testes para build_web_references_section."""

    def test_vazio_retorna_vazio(self):
        assert build_web_references_section([]) == ""

    def test_lista_ordenada_e_clicavel(self):
        section = build_web_references_section(
            [(2, "https://dois.com"), (1, "https://um.com")]
        )
        assert "Referências:" in section
        assert section.index("[1]") < section.index("[2]")  # ordenado por número
        assert 'href="https://um.com"' in section
        assert "[1]:" in section and "[2]:" in section

    def test_deduplica_por_numero(self):
        section = build_web_references_section(
            [(1, "https://um.com"), (1, "https://um.com")]
        )
        assert section.count("[1]:") == 1


class TestEscapeTooltipTitle:
    """Testes para _escape_tooltip_title."""

    def test_escapa_pipe_como_entidade(self):
        out = _escape_tooltip_title("Fundo Imobiliário | Clube FII")
        assert "|" not in out
        assert "&#124;" in out

    def test_escapa_caracteres_html(self):
        out = _escape_tooltip_title('a " b < c > d & e')
        assert "&quot;" in out
        assert "&lt;" in out
        assert "&gt;" in out
        assert "&amp;" in out

    def test_amp_nao_duplica(self):
        # '&' vira '&amp;' uma vez; a entidade do pipe não re-escapa esse '&'
        out = _escape_tooltip_title("x | y")
        assert "&amp;#124;" not in out
        assert "&#124;" in out

    def test_neutraliza_markdown_link_code_emphasis(self):
        # Markdown cru no title (link/imagem/code/ênfase) é re-parseado pelo frontend e
        # quebra a tabela (o href injeta aspas no title). Deve virar entidade.
        out = _escape_tooltip_title("* [Home](http://x) ``` `c` *bold* ![img](u)")
        for ch in ("[", "]", "`", "*"):
            assert ch not in out
        assert "&#91;" in out and "&#93;" in out  # [ ]
        assert "&#96;" in out and "&#42;" in out  # ` *

    def test_web_tooltip_com_link_markdown_nao_injeta_atributo(self):
        # Reproduz o caso real: preview com link/menu markdown não pode deixar '[' ou '`'
        # crus dentro do <a title="...">, senão o render forma <a href="..."> aninhado.
        metadata = {
            "url": "https://x",
            "preview": "* [Home](https://x/) ``` * [Ações](https://x/a) | Clube FII",
        }
        tooltip = create_web_search_tooltip(metadata, 1)
        title = tooltip.split('title="', 1)[1].rsplit('"', 1)[0]
        for ch in ("[", "]", "`", "|", "*"):
            assert ch not in title


class TestTooltipPipeNaoQuebraTabela:
    """Regressão: tooltip de citação não pode conter '|' literal (quebra tabela GFM).

    Era o bug de produção: o título de fonte scrapeado (ex.: 'Fundo Imobiliário | Clube
    FII') entrava cru no title="" dentro de uma célula de tabela e o '|' era lido como
    separador de coluna, quebrando a renderização.
    """

    def test_web_tooltip_sem_pipe_literal(self):
        metadata = {
            "url": "https://www.clubefii.com.br/fiis/KNRI11",
            "preview": "KNRI11 - Kinea Renda Imobiliária - Fundo Imobiliário | Clube FII",
        }
        tooltip = create_web_search_tooltip(metadata, 1)
        assert "|" not in tooltip
        assert "&#124;" in tooltip

    def test_chunk_tooltip_sem_pipe_literal(self):
        meta = {
            "id_documento_formatado": "123.456",
            "full_text": "texto com | pipe interno",
        }
        tooltip = create_chunk_tooltip(meta, 1)
        # nem o separador nem o '|' do conteúdo aparecem como '|' literal
        assert "|" not in tooltip
        assert "&#124;" in tooltip

    def test_doc_tooltip_sem_pipe_literal(self):
        tooltip = create_doc_tooltip("123", "123.456 | x", 1, 1)
        assert "|" not in tooltip

    def test_doc_tooltip_sem_numero_visivel_nao_expoe_id_interno(self):
        tooltip = create_doc_tooltip("123", None, 1, 1)
        assert "Documento SEI (número não disponível)" in tooltip
        assert "123" not in tooltip

    def test_linha_de_tabela_mantem_numero_de_colunas(self):
        """Com o tooltip numa célula, a contagem de '|' (delimitadores GFM) não muda."""
        metadata = {
            "url": "https://x",
            "preview": "Fundo Imobiliário | Clube FII ## menu ``` * item",
        }
        tooltip = create_web_search_tooltip(metadata, 1)
        # célula 'Segmento' com a citação embutida, igual ao caso de produção
        row = f"| 1 | KNRI11 | Lajes {tooltip} | 8,20% |"
        # 4 células -> 5 delimitadores; o '|' do tooltip não pode criar coluna fantasma
        assert row.count("|") == 5
