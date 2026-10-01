"""Testes unitários para SearxCrawlAgent."""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from sei_ia.agents.websearch.searx_crawl_tool import (
    _MIN_CONTENT_LEN,
    SearxCrawlAgent,
    _is_antibot_page,
)

_YEAR = str(datetime.now().year)


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def agent(mock_llm):
    return SearxCrawlAgent(
        searx_base_url="http://localhost:8092",
        fastcrw_base_url="http://infra-fastcrw:3001",
        llm=mock_llm,
    )


# ============================================================================
# Plano de busca (_build_search_plan)
# ============================================================================


def test_build_search_plan_sucesso(agent, mock_llm):
    expected = {
        "search_context": "Buscar legislação federal e regulações em sites gov.br",
        "information_needs": ["legislação federal", "regulações gov"],
        "allowed_urls": ["*.gov.br"],
        "blocked_urls": [],
    }
    mock_response = MagicMock()
    mock_response.content = json.dumps(expected)
    mock_llm.ainvoke.return_value = mock_response

    result = asyncio.run(agent._build_search_plan("busca em sites gov"))

    assert result["search_context"] == expected["search_context"]
    assert result["information_needs"] == ["legislação federal", "regulações gov"]
    assert result["allowed_urls"] == ["*.gov.br"]
    assert result["blocked_urls"] == []


def test_build_search_plan_fallback_em_erro(agent, mock_llm):
    mock_llm.ainvoke.side_effect = Exception("LLM indisponível")

    result = asyncio.run(agent._build_search_plan("minha busca"))

    assert result["search_context"] == "minha busca"
    assert result["information_needs"] == ["minha busca"]
    assert result["allowed_urls"] == []
    assert result["blocked_urls"] == []


def test_build_search_plan_fallback_nao_trunca_prompt_longo(agent, mock_llm):
    mock_llm.ainvoke.side_effect = Exception("Connection error")
    prompt_longo = "A" * 2000

    result = asyncio.run(agent._build_search_plan(prompt_longo))

    assert result["search_context"] == prompt_longo
    assert result["information_needs"] == [prompt_longo]


def test_build_search_plan_remove_markdown_code_block(agent, mock_llm):
    expected = {
        "search_context": "Buscar dado A",
        "information_needs": ["dado A"],
        "allowed_urls": [],
        "blocked_urls": [],
    }
    mock_response = MagicMock()
    mock_response.content = f"```json\n{json.dumps(expected)}\n```"
    mock_llm.ainvoke.return_value = mock_response

    result = asyncio.run(agent._build_search_plan("test"))

    assert result["information_needs"] == ["dado A"]
    assert result["search_context"] == "Buscar dado A"


# ============================================================================
# Geração de queries por necessidade (_generate_queries_for_need)
# ============================================================================


def test_generate_queries_for_need_sucesso(agent, mock_llm):
    mock_response = MagicMock()
    mock_response.content = json.dumps(
        {"queries": ["atributo ITEM1", "ITEM1 atributo detalhe"]}
    )
    mock_llm.ainvoke.return_value = mock_response

    result = asyncio.run(
        agent._generate_queries_for_need("atributo X do ITEM1", "busca de itens")
    )

    assert result == ["atributo ITEM1", "ITEM1 atributo detalhe"]


def test_generate_queries_for_need_fallback_em_erro(agent, mock_llm):
    mock_llm.ainvoke.side_effect = Exception("LLM indisponível")

    result = asyncio.run(
        agent._generate_queries_for_need("taxa de vacância", "contexto")
    )

    assert result == ["taxa de vacância"]


def test_generate_queries_for_need_lista_vazia_usa_fallback(agent, mock_llm):
    mock_response = MagicMock()
    mock_response.content = json.dumps({"queries": []})
    mock_llm.ainvoke.return_value = mock_response

    result = asyncio.run(
        agent._generate_queries_for_need("dado importante", "contexto")
    )

    assert result == ["dado importante"]


def test_generate_queries_for_need_remove_markdown_code_block(agent, mock_llm):
    payload = {"queries": ["q1", "q2"]}
    mock_response = MagicMock()
    mock_response.content = f"```json\n{json.dumps(payload)}\n```"
    mock_llm.ainvoke.return_value = mock_response

    result = asyncio.run(agent._generate_queries_for_need("dado", "contexto"))

    assert result == ["q1", "q2"]


# ============================================================================
# Construção de queries com operadores site:
# ============================================================================


def test_build_constrained_queries_sem_restricoes(agent):
    result = agent._build_constrained_queries("inflação 2024", [], [])
    assert result == ["inflação 2024"]


def test_build_constrained_queries_so_blocked(agent):
    result = agent._build_constrained_queries(
        "inflação 2024", [], ["*.wikipedia.org", "*.reddit.com"]
    )
    assert len(result) == 1
    assert result[0] == "inflação 2024 -site:wikipedia.org -site:reddit.com"


def test_build_constrained_queries_so_allowed(agent):
    result = agent._build_constrained_queries(
        "inflação 2024", ["*.gov.br", "ibge.gov.br"], []
    )
    assert len(result) == 2
    assert "inflação 2024 site:gov.br" in result
    assert "inflação 2024 site:ibge.gov.br" in result


def test_build_constrained_queries_allowed_e_blocked(agent):
    result = agent._build_constrained_queries(
        "query", ["*.gov.br"], ["*.wikipedia.org"]
    )
    assert len(result) == 1
    assert result[0] == "query site:gov.br -site:wikipedia.org"


def test_build_constrained_queries_strip_wildcard_prefix(agent):
    result = agent._build_constrained_queries("q", ["*.exemplo.com.br"], ["*.spam.net"])
    assert result[0] == "q site:exemplo.com.br -site:spam.net"


# ============================================================================
# Sanitização de queries geradas pelo LLM
# ============================================================================


def test_sanitize_query_injeta_ano_corrente(agent):
    result = agent._sanitize_query("inflação ipca")
    assert result == f"inflação ipca {_YEAR}"


def test_sanitize_query_nao_duplica_ano_existente(agent):
    result = agent._sanitize_query(f"jogos copa {_YEAR}")
    assert result.split().count(_YEAR) == 1
    assert result == f"jogos copa {_YEAR}"


def test_sanitize_query_descarta_caminho_de_url(agent):
    # caso real do Globo Esporte: site: com path completo + termos demais
    query = (
        "site:ge.globo.com/sp/campinas-e-regiao/futebol/brasileirao-serie-b/jogo/"
        "09-06-2026/ponte-preta-cuiaba.ghtml resultado placar final data competição link"
    )
    result = agent._sanitize_query(query)
    # site: reduzido ao domínio puro, sem o caminho
    assert "site:ge.globo.com" in result
    assert ".ghtml" not in result
    assert "/" not in result


def test_sanitize_query_limita_a_quatro_termos_de_conteudo(agent):
    query = "a b c d e f g h i j k l"
    result = agent._sanitize_query(query)
    assert result == f"a b c d {_YEAR}"


def test_sanitize_query_site_e_data_nao_contam_no_limite(agent):
    query = "a b c d e f site:exemplo.com"
    result = agent._sanitize_query(query)
    # 4 termos de conteúdo + ano + operador site: preservado ao final
    assert result == f"a b c d {_YEAR} site:exemplo.com"


def test_sanitize_query_remove_operadores_proibidos(agent):
    query = 'inurl:jogo intitle:placar "resultado" ponte preta'
    result = agent._sanitize_query(query)
    assert "inurl:" not in result
    assert "intitle:" not in result
    assert '"' not in result
    assert result == f"resultado ponte preta {_YEAR}"


def test_sanitize_query_descarta_url_crua_como_termo(agent):
    query = "resultado https://ge.globo.com/jogo/123 ponte preta"
    result = agent._sanitize_query(query)
    assert "://" not in result
    assert result == f"resultado ponte preta {_YEAR}"


def test_sanitize_query_reduz_site_de_url_completa_ao_dominio(agent):
    query = "placar site:https://ge.globo.com/sp/futebol/jogo.ghtml ponte"
    result = agent._sanitize_query(query)
    assert "site:ge.globo.com" in result
    assert ".ghtml" not in result


def test_sanitize_query_dedup_site_repetido(agent):
    query = "jogos site:ge.globo.com site:ge.globo.com"
    result = agent._sanitize_query(query)
    assert result.count("site:ge.globo.com") == 1


def test_sanitize_query_preserva_blocked_site(agent):
    query = "placar -site:wikipedia.org/wiki/Foo ponte"
    result = agent._sanitize_query(query)
    assert "-site:wikipedia.org" in result
    assert "/wiki" not in result


# ============================================================================
# Filtro de URLs binárias
# ============================================================================


def test_is_binary_url_pdf(agent):
    # PDFs são processados pelo Firecrawl — não são bloqueados
    assert agent._is_binary_url("https://b3.com.br/relatorio.pdf") is False


def test_is_binary_url_docx(agent):
    assert agent._is_binary_url("https://example.com/doc.docx") is True


def test_is_binary_url_html_nao_binario(agent):
    assert agent._is_binary_url("https://example.com/pagina") is False


def test_is_binary_url_query_string_nao_engana(agent):
    assert agent._is_binary_url("https://example.com/busca?q=relatorio.pdf") is False


# ============================================================================
# Filtro de URLs com wildcards (segurança pós-busca)
# ============================================================================


def test_filter_sem_restricoes(agent):
    urls = ["https://example.com", "https://test.org"]
    accepted, rejected = agent._filter_urls(urls, [], [])
    assert accepted == urls
    assert rejected == []


def test_filter_allowed_mantém_apenas_domínios_permitidos(agent):
    urls = ["https://www.gov.br/pagina", "https://example.com/pagina"]
    accepted, rejected = agent._filter_urls(urls, ["*.gov.br"], [])
    assert "https://www.gov.br/pagina" in accepted
    assert "https://example.com/pagina" not in accepted
    assert "https://example.com/pagina" in rejected


def test_filter_blocked_remove_domínios_bloqueados(agent):
    urls = ["https://pt.wikipedia.org/wiki/Algo", "https://anatel.gov.br/"]
    accepted, rejected = agent._filter_urls(urls, [], ["*.wikipedia.org"])
    assert "https://pt.wikipedia.org/wiki/Algo" not in accepted
    assert "https://anatel.gov.br/" in accepted
    assert "https://pt.wikipedia.org/wiki/Algo" in rejected


def test_filter_remove_duplicatas(agent):
    urls = ["https://example.com", "https://example.com", "https://other.com"]
    accepted, _rejected = agent._filter_urls(urls, [], [])
    assert len(accepted) == 2
    assert accepted.count("https://example.com") == 1


def test_filter_allowed_e_blocked_combinados(agent):
    urls = [
        "https://www.gov.br/pagina",
        "https://www.example.com/pagina",
        "https://spam.gov.br/anuncio",
    ]
    accepted, rejected = agent._filter_urls(urls, ["*.gov.br"], ["spam.gov.br"])
    assert "https://www.gov.br/pagina" in accepted
    assert "https://www.example.com/pagina" not in accepted
    assert "https://spam.gov.br/anuncio" not in accepted
    assert "https://www.example.com/pagina" in rejected
    assert "https://spam.gov.br/anuncio" in rejected


# ============================================================================
# Busca mockada no SearXNG
# ============================================================================


def test_search_searx_sucesso(agent):
    mock_response_data = {
        "results": [
            {"url": "https://gov.br/noticia", "title": "Notícia", "content": "Trecho"},
            {"url": "https://anatel.gov.br/", "title": "Anatel", "content": "Trecho 2"},
        ]
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response_data
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        results = asyncio.run(agent._search_searx("consulta pública"))

    assert len(results) == 2
    assert results[0]["url"] == "https://gov.br/noticia"
    assert results[0]["title"] == "Notícia"


def test_search_searx_respeita_limite_de_concorrencia(agent):
    """O semáforo limita buscas SearXNG simultâneas a search_concurrency."""
    agent.search_concurrency = 3
    inflight = 0
    max_inflight = 0

    async def fake_get(*args, **kwargs):
        nonlocal inflight, max_inflight
        inflight += 1
        max_inflight = max(max_inflight, inflight)
        await asyncio.sleep(0.01)  # mantém a chamada "em voo" para forçar overlap
        inflight -= 1
        resp = MagicMock()
        resp.json.return_value = {"results": []}
        resp.raise_for_status = MagicMock()
        return resp

    async def run_many():
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=fake_get)
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            await asyncio.gather(*[agent._search_searx(f"q{i}") for i in range(12)])

    asyncio.run(run_many())
    assert max_inflight <= 3


def test_search_searx_passa_language(agent):
    """O locale configurado vai ao SearXNG como parâmetro 'language'."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": []}
    mock_resp.raise_for_status = MagicMock()

    agent.search_language = "pt-BR"
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        asyncio.run(agent._search_searx("consulta pública"))

    _, kwargs = mock_client.get.call_args
    assert kwargs["params"]["language"] == "pt-BR"


def test_search_searx_language_all_omite_param(agent):
    """search_language='all' desativa o filtro — não envia 'language'."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": []}
    mock_resp.raise_for_status = MagicMock()

    agent.search_language = "all"
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        asyncio.run(agent._search_searx("consulta pública"))

    _, kwargs = mock_client.get.call_args
    assert "language" not in kwargs["params"]


def test_fetch_page_byparr_usa_maxtimeout_configurado(mock_llm):
    """O Byparr recebe o maxTimeout configurado — não pode estourar o _BYPARR_TIMEOUT."""
    from sei_ia.agents.websearch.searx_crawl_tool import _BYPARR_MAX_TIMEOUT_MS

    agent_bp = SearxCrawlAgent(
        searx_base_url="http://localhost:8092",
        fastcrw_base_url="http://infra-fastcrw:3001",
        byparr_base_url="http://infra-byparr:8191",
        llm=mock_llm,
    )
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "status": "ok",
        "solution": {"response": "<html><body>" + "conteúdo " * 300 + "</body></html>"},
    }
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=resp)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        result = asyncio.run(
            agent_bp._fetch_page_byparr("https://exemplo.com/x", "Título", 0)
        )

    _, kwargs = mock_http.post.call_args
    assert kwargs["json"]["maxTimeout"] == _BYPARR_MAX_TIMEOUT_MS
    assert _BYPARR_MAX_TIMEOUT_MS <= 30000  # cabe na janela do httpx
    assert result is not None  # conteúdo renderizado é aproveitado


def test_extract_data_attributes_captura_valores_numericos():
    """Atributos data-* numéricos são capturados; flags de UI sem número são ignorados."""
    from bs4 import BeautifulSoup

    from sei_ia.agents.websearch.searx_crawl_tool import (
        _extract_data_attributes_from_soup,
    )

    html = """
      <div data-ativo="ITEM1" data-ativo-vol="715,63"
           data-indice="IDX" data-indice-vol="4,80"></div>
      <span data-toggle="tooltip" data-html="true"></span>
    """
    out = _extract_data_attributes_from_soup(BeautifulSoup(html, "lxml"))
    assert "[ATRIBUTOS DE DADOS]" in out
    # o valor métrico e seu identificador no mesmo elemento são preservados juntos
    assert "ativo=ITEM1" in out
    assert "ativo-vol=715,63" in out
    # elemento puramente de UI (sem valor numérico) é descartado
    assert "toggle=tooltip" not in out


def test_extract_data_attributes_vazio_quando_sem_dados():
    from bs4 import BeautifulSoup

    from sei_ia.agents.websearch.searx_crawl_tool import (
        _extract_data_attributes_from_soup,
    )

    html = "<div class='x'><p>texto sem atributos data</p></div>"
    assert _extract_data_attributes_from_soup(BeautifulSoup(html, "lxml")) == ""


def test_search_searx_timeout_retorna_lista_vazia(agent):
    import httpx

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        results = asyncio.run(agent._search_searx("query"))

    assert results == []


def test_search_searx_erro_generico_retorna_lista_vazia(agent):
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("erro de rede"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        results = asyncio.run(agent._search_searx("query"))

    assert results == []


# ============================================================================
# Extração de conteúdo via Crawl4AI (chamada síncrona)
# ============================================================================


def _c4a_resp(markdown: str, success: bool = True) -> MagicMock:
    """Constrói resposta mockada do POST /v1/scrape do fastCRW."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    if success and markdown:
        resp.json.return_value = {"success": True, "data": {"markdown": markdown}}
    elif success:
        resp.json.return_value = {"success": True, "data": {"markdown": ""}}
    else:
        resp.json.return_value = {"success": False, "data": {}}
    return resp


def _c4a_mock_ctx(markdown: str, success: bool = True):
    """Retorna (mock_cls, mock_client) prontos para patch('httpx.AsyncClient')."""
    crawl_resp = _c4a_resp(markdown, success)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=crawl_resp)
    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_cls, mock_client


def test_fetch_page_sucesso(agent):
    mock_cls, _ = _c4a_mock_ctx("# Conteúdo da página")
    with patch("httpx.AsyncClient", mock_cls):
        result = asyncio.run(
            agent._fetch_page("https://example.com", "Exemplo", min_content_len=0)
        )

    assert result is not None
    assert result["url"] == "https://example.com"
    assert result["title"] == "Exemplo"
    assert result["content"] == "# Conteúdo da página"


def test_fetch_page_sem_resultados_retorna_none(agent):
    """Crawl4AI com lista de resultados vazia deve retornar None."""
    mock_cls, _ = _c4a_mock_ctx("", success=False)
    with patch("httpx.AsyncClient", mock_cls):
        result = asyncio.run(
            agent._fetch_page("https://example.com", "", min_content_len=0)
        )

    assert result is None


def test_fetch_page_markdown_vazio_retorna_none(agent):
    mock_cls, _ = _c4a_mock_ctx("")
    with patch("httpx.AsyncClient", mock_cls):
        result = asyncio.run(
            agent._fetch_page("https://example.com", "", min_content_len=0)
        )

    assert result is None


def test_fetch_page_conteudo_insuficiente_retorna_none(agent):
    mock_cls, _ = _c4a_mock_ctx("# Pouco")
    with patch("httpx.AsyncClient", mock_cls):
        result = asyncio.run(
            agent._fetch_page("https://example.com", "", min_content_len=500)
        )

    assert result is None


def test_fetch_page_erro_retorna_none(agent):
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("erro de rede"))
    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", mock_cls):
        result = asyncio.run(
            agent._fetch_page("https://example.com", "", min_content_len=0)
        )

    assert result is None


def test_fetch_page_429_local_nao_dispara_byparr(agent, monkeypatch):
    agent.byparr_base_url = "http://infra-byparr:8191"
    request = httpx.Request("POST", "http://infra-fastcrw:3001/v1/scrape")
    response = httpx.Response(429, request=request)
    crawl_resp = MagicMock()
    crawl_resp.status_code = 429
    crawl_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "rate limit local", request=request, response=response
    )
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=crawl_resp)
    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    byparr = AsyncMock(return_value=None)
    monkeypatch.setattr(agent, "_fetch_page_byparr", byparr)

    with patch("httpx.AsyncClient", mock_cls):
        result = asyncio.run(
            agent._fetch_page("https://example.com", "", min_content_len=0)
        )

    assert result is None
    byparr.assert_not_awaited()


def test_crawl_pages_sucesso(agent):
    mock_cls, _ = _c4a_mock_ctx("# Conteúdo da página")
    with patch("httpx.AsyncClient", mock_cls):
        results = asyncio.run(
            agent._crawl_pages(
                ["https://example.com"],
                title_map={"https://example.com": "Exemplo"},
            )
        )

    assert len(results) == 1
    assert results[0]["content"] == "# Conteúdo da página"
    assert results[0]["url"] == "https://example.com"
    assert results[0]["title"] == "Exemplo"


def test_crawl_pages_status_failed_ignorado(agent):
    mock_cls, _ = _c4a_mock_ctx("", success=False)
    with patch("httpx.AsyncClient", mock_cls):
        results = asyncio.run(agent._crawl_pages(["https://example.com"]))

    assert results == []


def test_crawl_pages_markdown_vazio_ignorado(agent):
    mock_cls, _ = _c4a_mock_ctx("")
    with patch("httpx.AsyncClient", mock_cls):
        results = asyncio.run(agent._crawl_pages(["https://example.com"]))

    assert results == []


def test_crawl_pages_erro_ignorado_continua(agent):
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("erro de crawl"))
    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", mock_cls):
        results = asyncio.run(agent._crawl_pages(["https://example.com"]))

    assert results == []


def test_crawl_pages_lista_vazia_retorna_vazia(agent):
    results = asyncio.run(agent._crawl_pages([]))
    assert results == []


# ============================================================================
# Formatação de saída
# ============================================================================


def test_format_results_estrutura_correta(agent):
    pages = [
        {
            "url": "https://gov.br/pagina",
            "title": "Página Gov",
            "content": "# Conteúdo markdown",
            "query": "consulta pública",
        }
    ]
    result = agent._format_results(pages)

    assert len(result) == 1
    item = result[0]
    assert item["content"] == "# Conteúdo markdown"
    assert item["query"] == "consulta pública"
    assert len(item["references"]) == 1
    assert item["references"][0]["url"] == "https://gov.br/pagina"
    assert item["references"][0]["title"] == "Página Gov"


def test_format_results_lista_vazia(agent):
    result = agent._format_results([])
    assert result == []


def test_format_results_multiplas_paginas(agent):
    pages = [
        {"url": "https://a.com", "title": "A", "content": "conteúdo A", "query": "q1"},
        {"url": "https://b.com", "title": "B", "content": "conteúdo B", "query": "q2"},
    ]
    result = agent._format_results(pages)

    assert len(result) == 2
    assert result[0]["references"][0]["url"] == "https://a.com"
    assert result[1]["references"][0]["url"] == "https://b.com"


# ============================================================================
# Item de metadados e fluxo _arun completo
# ============================================================================


def _build_arun_mocks(agent, mock_llm, searx_results, crawl_markdown):  # noqa: ARG001
    """Monta todos os mocks necessários para executar _arun completo."""
    needs_response = MagicMock()
    needs_response.content = json.dumps(
        {
            "search_context": "Buscar: informação principal",
            "information_needs": ["informação principal"],
            "allowed_urls": [],
            "blocked_urls": ["*.spam.com"],
        }
    )
    queries_response = MagicMock()
    queries_response.content = json.dumps({"queries": ["query teste", "busca teste"]})
    eval_response = MagicMock()
    eval_response.content = json.dumps(
        {"sufficient": True, "additional_queries": [], "reason": "OK"}
    )
    mock_llm.ainvoke.side_effect = [needs_response, queries_response, eval_response]

    searx_resp = MagicMock()
    searx_resp.raise_for_status = MagicMock()
    searx_resp.json.return_value = {"results": searx_results}

    padded_markdown = crawl_markdown.ljust(_MIN_CONTENT_LEN, " ")
    # Mock crawl4ai: POST /crawl retorna resultado síncrono
    crawl_resp = _c4a_resp(padded_markdown)

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=searx_resp)
    mock_http.post = AsyncMock(return_value=crawl_resp)
    return mock_http


def test_arun_inclui_item_de_metadados(agent, mock_llm):
    searx_results = [
        {"url": "https://gov.br/pagina", "title": "Gov", "content": "trecho"},
        {"url": "https://www.spam.com/anuncio", "title": "Spam", "content": "trecho"},
    ]
    mock_http = _build_arun_mocks(
        agent, mock_llm, searx_results, "# Conteúdo relevante"
    )

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        results = asyncio.run(agent._arun("busca sobre gov"))

    metadata = next(
        (r for r in results if r.get("node") == "web_search_metadata"), None
    )
    assert metadata is not None
    assert "urls_consultadas" in metadata
    assert "urls_bloqueadas" in metadata
    assert "conteudos_utilizados" in metadata
    assert any("spam.com" in u for u in metadata["urls_bloqueadas"])


def test_arun_metadados_urls_consultadas(agent, mock_llm):
    searx_results = [
        {
            "url": "https://anatel.gov.br/resolucao",
            "title": "Resolução",
            "content": "trecho",
        },
    ]
    mock_http = _build_arun_mocks(agent, mock_llm, searx_results, "# Resolução 123")

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        results = asyncio.run(agent._arun("resolução anatel"))

    metadata = next(
        (r for r in results if r.get("node") == "web_search_metadata"), None
    )
    assert "https://anatel.gov.br/resolucao" in metadata["urls_consultadas"]
    assert (
        metadata["conteudos_utilizados"][0]["url"] == "https://anatel.gov.br/resolucao"
    )


def test_arun_respeita_max_pages(mock_llm):
    """Confirma que o agente crawlea no máximo max_pages URLs."""
    agent_limitado = SearxCrawlAgent(
        searx_base_url="http://localhost:8092",
        fastcrw_base_url="http://infra-fastcrw:3001",
        llm=mock_llm,
        max_pages=2,
    )

    needs_response = MagicMock()
    needs_response.content = json.dumps(
        {
            "search_context": "Buscar: dado A",
            "information_needs": ["dado A"],
            "allowed_urls": [],
            "blocked_urls": [],
        }
    )
    queries_response = MagicMock()
    queries_response.content = json.dumps({"queries": ["q", "q2"]})
    eval_response = MagicMock()
    eval_response.content = json.dumps(
        {"sufficient": True, "additional_queries": [], "reason": "OK"}
    )
    mock_llm.ainvoke.side_effect = [needs_response, queries_response, eval_response]

    searx_results = [
        {"url": f"https://site{i}.com/p", "title": f"Site {i}", "content": "t"}
        for i in range(5)
    ]
    searx_resp = MagicMock()
    searx_resp.raise_for_status = MagicMock()
    searx_resp.json.return_value = {"results": searx_results}

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=searx_resp)
    mock_http.post = AsyncMock(return_value=_c4a_resp("# conteúdo"))

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        results = asyncio.run(agent_limitado._arun("busca"))

    metadata = next(
        (r for r in results if r.get("node") == "web_search_metadata"), None
    )
    assert len(metadata["urls_consultadas"]) <= 2


def test_arun_nao_bloqueia_pdf(agent, mock_llm):
    """PDFs não são bloqueados — o Firecrawl os processa nativamente."""
    searx_results = [
        {
            "url": "https://b3.com.br/relatorio.pdf",
            "title": "Relatório PDF",
            "content": "t",
        },
        {"url": "https://b3.com.br/pagina", "title": "Página HTML", "content": "t"},
    ]
    mock_http = _build_arun_mocks(agent, mock_llm, searx_results, "# Conteúdo HTML")

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        results = asyncio.run(agent._arun("relatório b3"))

    metadata = next(
        (r for r in results if r.get("node") == "web_search_metadata"), None
    )
    assert "https://b3.com.br/relatorio.pdf" not in metadata["urls_bloqueadas"]


def test_arun_bloqueia_docx(agent, mock_llm):
    """DOCX deve ser bloqueado pois o Firecrawl não processa arquivos Office."""
    searx_results = [
        {
            "url": "https://example.com/arquivo.docx",
            "title": "Documento",
            "content": "t",
        },
        {"url": "https://example.com/pagina", "title": "Página", "content": "t"},
    ]
    mock_http = _build_arun_mocks(agent, mock_llm, searx_results, "# Conteúdo HTML")

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        results = asyncio.run(agent._arun("documento"))

    metadata = next(
        (r for r in results if r.get("node") == "web_search_metadata"), None
    )
    assert "https://example.com/arquivo.docx" in metadata["urls_bloqueadas"]


# ============================================================================
# Seleção de URLs por necessidade (_select_urls_for_need)
# ============================================================================


def _make_results_and_urls(n: int):
    """Helper: cria lista de resultados SearXNG e lista de URLs filtradas."""
    results = [
        {"url": f"https://site{i}.com", "title": f"Site {i}", "snippet": "trecho"}
        for i in range(n)
    ]
    filtered = [r["url"] for r in results]
    return results, filtered


def test_select_urls_for_need_sem_excesso_retorna_todas(agent):
    """Quando filtered_urls <= max_urls, retorna todas sem chamar LLM."""
    results, filtered = _make_results_and_urls(3)
    result = asyncio.run(
        agent._select_urls_for_need("dado A", results, filtered, max_urls=5)
    )
    assert result == filtered


def test_select_urls_for_need_lista_vazia_retorna_vazia(agent):
    result = asyncio.run(agent._select_urls_for_need("dado A", [], [], max_urls=5))
    assert result == []


def test_select_urls_for_need_com_excesso_chama_llm(agent, mock_llm):
    """Quando filtered_urls > max_urls, chama LLM para selecionar."""
    results, filtered = _make_results_and_urls(10)
    llm_response = MagicMock()
    llm_response.content = json.dumps({"selected": [1, 3, 5]})
    mock_llm.ainvoke.return_value = llm_response

    result = asyncio.run(
        agent._select_urls_for_need("dado A", results, filtered, max_urls=3)
    )

    mock_llm.ainvoke.assert_called_once()
    assert result == ["https://site0.com", "https://site2.com", "https://site4.com"]


def test_select_urls_for_need_ignora_indices_invalidos(agent, mock_llm):
    results, filtered = _make_results_and_urls(10)
    llm_response = MagicMock()
    llm_response.content = json.dumps({"selected": [0, 99, 2, -1]})  # só 2 é válido
    mock_llm.ainvoke.return_value = llm_response

    result = asyncio.run(
        agent._select_urls_for_need("dado A", results, filtered, max_urls=3)
    )

    assert result == ["https://site1.com"]


def test_select_urls_for_need_fallback_em_erro_llm(agent, mock_llm):
    """Erro no LLM cai no fallback de slice simples."""
    results, filtered = _make_results_and_urls(10)
    mock_llm.ainvoke.side_effect = Exception("LLM indisponível")

    result = asyncio.run(
        agent._select_urls_for_need("dado A", results, filtered, max_urls=3)
    )

    assert result == filtered[:3]


def test_select_urls_for_need_deduplica_indices_repetidos(agent, mock_llm):
    results, filtered = _make_results_and_urls(10)
    llm_response = MagicMock()
    llm_response.content = json.dumps({"selected": [1, 1, 2]})
    mock_llm.ainvoke.return_value = llm_response

    result = asyncio.run(
        agent._select_urls_for_need("dado A", results, filtered, max_urls=3)
    )

    assert result.count("https://site0.com") == 1
    assert len(result) == 2


# ============================================================================
# Avaliação de suficiência (_evaluate_sufficiency)
# ============================================================================


def test_evaluate_sufficiency_retorna_sufficient_true(agent, mock_llm):
    mock_response = MagicMock()
    mock_response.content = json.dumps(
        {"sufficient": True, "additional_queries": [], "reason": "Conteúdo completo."}
    )
    mock_llm.ainvoke.return_value = mock_response

    pages = [
        {"url": "https://example.com", "title": "Exemplo", "content": "# Conteúdo"}
    ]
    result = asyncio.run(agent._evaluate_sufficiency("busca", pages))

    assert result["sufficient"] is True
    assert result["additional_queries"] == []


def test_evaluate_sufficiency_retorna_queries_adicionais(agent, mock_llm):
    mock_response = MagicMock()
    mock_response.content = json.dumps(
        {
            "sufficient": False,
            "missing_fields": ["Metrica A", "Metrica B"],
            "additional_queries": [
                "dados específicos ITEM1",
                "metrica A ITEM2",
            ],
            "reason": "Faltam dados de uma métrica.",
        }
    )
    mock_llm.ainvoke.return_value = mock_response

    pages = [
        {"url": "https://example.com", "title": "Ranking", "content": "# Ranking geral"}
    ]
    result = asyncio.run(agent._evaluate_sufficiency("ranking de itens", pages))

    assert result["sufficient"] is False
    assert result["missing_fields"] == ["Metrica A", "Metrica B"]
    assert len(result["additional_queries"]) == 2


def test_evaluate_sufficiency_fallback_em_erro(agent, mock_llm):
    mock_llm.ainvoke.side_effect = Exception("LLM indisponível")

    result = asyncio.run(agent._evaluate_sufficiency("busca", []))

    assert result["sufficient"] is False
    assert result["additional_queries"] == []


# ============================================================================
# Multi-round: _arun com max_rounds > 1
# ============================================================================


def test_arun_segunda_rodada_quando_insuficiente(mock_llm):
    """Confirma que _arun executa segunda rodada quando a avaliação indica insuficiência."""
    agent_multi = SearxCrawlAgent(
        searx_base_url="http://localhost:8092",
        fastcrw_base_url="http://infra-fastcrw:3001",
        llm=mock_llm,
        max_pages=2,
        max_rounds=2,
    )

    needs_response = MagicMock()
    needs_response.content = json.dumps(
        {
            "search_context": "Buscar: dado A",
            "information_needs": ["dado A"],
            "allowed_urls": [],
            "blocked_urls": [],
        }
    )
    queries_response = MagicMock()
    queries_response.content = json.dumps({"queries": ["query geral"]})
    eval_response = MagicMock()
    eval_response.content = json.dumps(
        {
            "sufficient": False,
            "additional_queries": ["query específica"],
            "reason": "Faltam dados.",
        }
    )
    mock_llm.ainvoke.side_effect = [needs_response, queries_response, eval_response]

    searx_resp = MagicMock()
    searx_resp.raise_for_status = MagicMock()
    searx_resp.json.return_value = {
        "results": [{"url": "https://site1.com/p", "title": "Site 1", "content": "t"}]
    }
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=searx_resp)
    mock_http.post = AsyncMock(return_value=_c4a_resp("# " + "x" * _MIN_CONTENT_LEN))

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        results = asyncio.run(agent_multi._arun("busca complexa"))

    # Round 1: build_search_plan + generate_queries; Round 2: evaluate → 3 calls total
    assert mock_llm.ainvoke.call_count == 3
    metadata = next(
        (r for r in results if r.get("node") == "web_search_metadata"), None
    )
    assert metadata is not None


def test_arun_para_na_primeira_rodada_quando_suficiente(mock_llm):
    """Confirma que _arun para na primeira rodada se avaliação indicar suficiência."""
    agent_multi = SearxCrawlAgent(
        searx_base_url="http://localhost:8092",
        fastcrw_base_url="http://infra-fastcrw:3001",
        llm=mock_llm,
        max_pages=2,
        max_rounds=3,
    )

    needs_response = MagicMock()
    needs_response.content = json.dumps(
        {
            "search_context": "Buscar: dado A",
            "information_needs": ["dado A"],
            "allowed_urls": [],
            "blocked_urls": [],
        }
    )
    queries_response = MagicMock()
    queries_response.content = json.dumps({"queries": ["query"]})
    eval_response = MagicMock()
    eval_response.content = json.dumps(
        {"sufficient": True, "additional_queries": [], "reason": "Completo."}
    )
    mock_llm.ainvoke.side_effect = [needs_response, queries_response, eval_response]

    searx_resp = MagicMock()
    searx_resp.raise_for_status = MagicMock()
    searx_resp.json.return_value = {
        "results": [{"url": "https://site1.com/p", "title": "T", "content": "t"}]
    }

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=searx_resp)
    mock_http.post = AsyncMock(return_value=_c4a_resp("# " + "x" * _MIN_CONTENT_LEN))

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        results = asyncio.run(agent_multi._arun("busca simples"))

    # Round 1: build_search_plan + generate_queries; Round 2: evaluate → 3 calls total
    assert mock_llm.ainvoke.call_count == 3


def test_evaluate_sufficiency_inclui_insufficient_urls_no_prompt(agent, mock_llm):
    """Quando insufficient_urls é passado, deve aparecer no prompt enviado ao LLM."""
    mock_response = MagicMock()
    mock_response.content = json.dumps(
        {"sufficient": True, "additional_queries": [], "reason": "OK"}
    )
    mock_llm.ainvoke.return_value = mock_response

    asyncio.run(
        agent._evaluate_sufficiency(
            "busca",
            [{"url": "https://ok.com", "title": "OK", "content": "# conteúdo"}],
            insufficient_urls=[
                "https://blocked.com/items/item1",
                "https://blocked.com/items/item2",
            ],
        )
    )

    prompt_used = mock_llm.ainvoke.call_args[0][0]
    assert "blocked.com" in prompt_used
    assert "item1" in prompt_used


def test_evaluate_sufficiency_sem_insufficient_urls_nao_inclui_secao(agent, mock_llm):
    """Sem insufficient_urls, o prompt não deve conter a seção de bloqueados."""
    mock_response = MagicMock()
    mock_response.content = json.dumps(
        {"sufficient": True, "additional_queries": [], "reason": "OK"}
    )
    mock_llm.ainvoke.return_value = mock_response

    asyncio.run(
        agent._evaluate_sufficiency(
            "busca",
            [{"url": "https://ok.com", "title": "OK", "content": "# conteúdo"}],
        )
    )

    prompt_used = mock_llm.ainvoke.call_args[0][0]
    assert "anti-bot" not in prompt_used


def test_arun_passa_insufficient_urls_para_evaluate_na_rodada_2(mock_llm):
    """URLs que falharam no Round 1 devem ser passadas ao _evaluate_sufficiency."""
    agent_multi = SearxCrawlAgent(
        searx_base_url="http://localhost:8092",
        fastcrw_base_url="http://infra-fastcrw:3001",
        llm=mock_llm,
        max_pages=2,
        max_rounds=2,
    )

    needs_response = MagicMock()
    needs_response.content = json.dumps(
        {
            "search_context": "Buscar: dado A",
            "information_needs": ["dado A"],
            "allowed_urls": [],
            "blocked_urls": [],
        }
    )
    queries_response = MagicMock()
    queries_response.content = json.dumps({"queries": ["query"]})
    eval_response = MagicMock()
    eval_response.content = json.dumps(
        {"sufficient": True, "additional_queries": [], "reason": "OK."}
    )
    mock_llm.ainvoke.side_effect = [needs_response, queries_response, eval_response]

    blocked_url = "https://blocked-source.com/items/item1"
    good_url = "https://good-source.com/items/item1"
    searx_resp = MagicMock()
    searx_resp.raise_for_status = MagicMock()
    searx_resp.json.return_value = {
        "results": [
            {"url": blocked_url, "title": "Blocked", "content": "t"},
            {"url": good_url, "title": "Good", "content": "t"},
        ]
    }

    def post_side_effect(url, **kwargs):  # noqa: ARG001
        body = kwargs.get("json", {})
        crawl_url = (body.get("urls") or [""])[0]
        if "blocked-source" in crawl_url:
            return _c4a_resp("x" * 10)  # conteúdo insuficiente (< _MIN_CONTENT_LEN)
        return _c4a_resp("# " + "x" * _MIN_CONTENT_LEN)

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=searx_resp)
    mock_http.post = AsyncMock(side_effect=post_side_effect)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        asyncio.run(agent_multi._arun("busca"))

    # Call 0: build_search_plan, Call 1: generate_queries, Call 2: evaluate_sufficiency
    eval_call_args = mock_llm.ainvoke.call_args_list[2][0][0]
    assert "blocked-source" in eval_call_args


def test_arun_nao_revisita_urls_entre_rodadas(mock_llm):
    """URLs já crawleadas na rodada 1 não são repetidas na rodada 2."""
    agent_multi = SearxCrawlAgent(
        searx_base_url="http://localhost:8092",
        fastcrw_base_url="http://infra-fastcrw:3001",
        llm=mock_llm,
        max_pages=5,
        max_rounds=2,
    )

    needs_response = MagicMock()
    needs_response.content = json.dumps(
        {
            "search_context": "Buscar: dado A",
            "information_needs": ["dado A"],
            "allowed_urls": [],
            "blocked_urls": [],
        }
    )
    queries_response = MagicMock()
    queries_response.content = json.dumps({"queries": ["q"]})
    eval_response = MagicMock()
    eval_response.content = json.dumps(
        {"sufficient": False, "additional_queries": ["q2"], "reason": "Falta algo."}
    )
    mock_llm.ainvoke.side_effect = [needs_response, queries_response, eval_response]

    url_repetida = "https://site1.com/pagina"
    searx_resp = MagicMock()
    searx_resp.raise_for_status = MagicMock()
    searx_resp.json.return_value = {
        "results": [{"url": url_repetida, "title": "T", "content": "t"}]
    }
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=searx_resp)
    mock_http.post = AsyncMock(return_value=_c4a_resp("# " + "x" * _MIN_CONTENT_LEN))

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        results = asyncio.run(agent_multi._arun("busca"))

    metadata = next(
        (r for r in results if r.get("node") == "web_search_metadata"), None
    )
    assert metadata["urls_consultadas"].count(url_repetida) == 1


# ============================================================================
# Detecção de páginas anti-bot (_is_antibot_page)
# ============================================================================


def test_is_antibot_page_detecta_cloudflare():
    md = "Just a moment...\nDDoS protection by Cloudflare\nRay ID: abc123"
    assert _is_antibot_page(md) is True


def test_is_antibot_page_detecta_verificacao_humano():
    md = "Please verify you are human to continue accessing this website."
    assert _is_antibot_page(md) is True


def test_is_antibot_page_detecta_checking_browser():
    md = "Checking your browser before accessing example.com"
    assert _is_antibot_page(md) is True


def test_is_antibot_page_permite_conteudo_real():
    md = "# Relatório Financeiro\nEste relatório apresenta dados de rentabilidade."
    assert _is_antibot_page(md) is False


def test_is_antibot_page_insensivel_a_maiusculas():
    md = "VERIFY YOU ARE HUMAN"
    assert _is_antibot_page(md) is True


# ============================================================================
# Parada antecipada progressiva (_crawl_pages com early_stop_checker)
# ============================================================================


def test_crawl_pages_para_quando_early_stop_retorna_true(agent):
    """Quando early_stop_checker retorna True após 2 páginas, para imediatamente."""
    mock_cls, _ = _c4a_mock_ctx("# " + "x" * _MIN_CONTENT_LEN)

    chamadas: list[int] = []

    async def checker(pages: list) -> bool:
        chamadas.append(len(pages))
        return len(pages) >= 2

    with patch("httpx.AsyncClient", mock_cls):
        results = asyncio.run(
            agent._crawl_pages(
                [f"https://site{i}.com" for i in range(6)],
                early_stop_checker=checker,
            )
        )

    assert len(results) == 2
    assert 2 in chamadas


def test_crawl_pages_continua_quando_early_stop_retorna_false(agent):
    """Quando early_stop_checker sempre retorna False, coleta até max_pages."""
    mock_cls, _ = _c4a_mock_ctx("# " + "x" * _MIN_CONTENT_LEN)

    async def checker(pages: list) -> bool:
        return False

    with patch("httpx.AsyncClient", mock_cls):
        results = asyncio.run(
            agent._crawl_pages(
                [f"https://site{i}.com" for i in range(10)],
                early_stop_checker=checker,
            )
        )

    assert len(results) == agent.max_pages


def test_crawl_pages_sem_early_stop_checker_comportamento_padrao(agent):
    """Sem early_stop_checker, comportamento original é mantido."""
    mock_cls, _ = _c4a_mock_ctx("# " + "x" * _MIN_CONTENT_LEN)

    with patch("httpx.AsyncClient", mock_cls):
        results = asyncio.run(
            agent._crawl_pages(
                [f"https://site{i}.com" for i in range(10)],
            )
        )

    assert len(results) == agent.max_pages


def test_fetch_page_rejeita_pagina_antibot(agent):
    """_fetch_page deve retornar None quando markdown contém sinais de anti-bot."""
    antibot_content = "Just a moment...\nDDoS protection by Cloudflare\n" + "x" * 2000
    mock_cls, _ = _c4a_mock_ctx(antibot_content)

    with patch("httpx.AsyncClient", mock_cls):
        result = asyncio.run(
            agent._fetch_page("https://example.com", "Exemplo", min_content_len=0)
        )

    assert result is None


def test_circuit_breaker_segunda_url_do_mesmo_dominio_e_pulada(agent):
    """Quando o primeiro URL de um domínio causa timeout, o segundo é pulado."""
    call_count = 0

    async def fake_fetch_timeout(url, title, min_content_len):
        nonlocal call_count
        call_count += 1

    # Zerando o threshold garante que qualquer elapsed (>=0) dispara o circuit breaker,
    # sem precisar mockar time.monotonic.
    with (
        patch.object(agent, "_fetch_page", side_effect=fake_fetch_timeout),
        patch("sei_ia.agents.websearch.searx_crawl_tool._SCRAPE_TIMEOUT", 0),
        patch("sei_ia.agents.websearch.searx_crawl_tool._DOMAIN_TIMEOUT_RATIO", 0),
    ):
        asyncio.run(
            agent._crawl_pages(
                [
                    "https://mesmo-dominio.com/pagina1",
                    "https://mesmo-dominio.com/pagina2",
                ]
            )
        )

    assert call_count == 1
