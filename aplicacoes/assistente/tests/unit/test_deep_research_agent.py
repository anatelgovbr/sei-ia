"""Testes unitários para DeepResearchAgent."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sei_ia.agents.websearch.deep_research_agent import DeepResearchAgent


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    # _classify_search_mode faz .bind(extra_body={"tags": [...]}) antes de
    # invocar (rebind pra tag agents:triagem_busca) — mantém o mesmo
    # mock configurável em vez de virar um MagicMock novo sem ainvoke.
    # `.bind()` no LangChain de verdade é síncrono — em AsyncMock puro,
    # atributos filhos herdam o comportamento async por padrão, então precisa
    # forçar MagicMock aqui pra não virar um coroutine object não-esperado.
    llm.bind = MagicMock(return_value=llm)
    return llm


@pytest.fixture
def mock_compress_llm():
    llm = AsyncMock()
    llm.bind = MagicMock(return_value=llm)
    return llm


@pytest.fixture
def agent(mock_llm, mock_compress_llm):
    return DeepResearchAgent(
        searx_base_url="http://localhost:8092",
        fastcrw_base_url="http://infra-fastcrw:3001",
        llm=mock_llm,
        compress_llm=mock_compress_llm,
    )


# ============================================================================
# _identify_gaps
# ============================================================================


def test_identify_gaps_todos_vazios(agent):
    state = {
        "ALFA11": {"CAMPO_A": None, "campo_b": None},
        "BETA11": {"CAMPO_A": None, "campo_b": None},
    }
    fields = ["CAMPO_A", "campo_b"]
    gaps = agent._identify_gaps(state, fields)
    assert len(gaps) == 4
    assert ("ALFA11", "CAMPO_A") in gaps
    assert ("ALFA11", "campo_b") in gaps
    assert ("BETA11", "CAMPO_A") in gaps
    assert ("BETA11", "campo_b") in gaps


def test_identify_gaps_parcialmente_preenchido(agent):
    state = {
        "ALFA11": {"CAMPO_A": "10.5%", "campo_b": None},
        "BETA11": {"CAMPO_A": None, "campo_b": "logística"},
    }
    fields = ["CAMPO_A", "campo_b"]
    gaps = agent._identify_gaps(state, fields)
    assert len(gaps) == 2
    assert ("ALFA11", "campo_b") in gaps
    assert ("BETA11", "CAMPO_A") in gaps


def test_identify_gaps_todos_preenchidos(agent):
    state = {
        "ALFA11": {"CAMPO_A": "10.5%", "campo_b": "papel"},
    }
    fields = ["CAMPO_A", "campo_b"]
    gaps = agent._identify_gaps(state, fields)
    assert gaps == []


def test_identify_gaps_estado_vazio(agent):
    assert agent._identify_gaps({}, ["CAMPO_A"]) == []


# ============================================================================
# _check_coverage
# ============================================================================


def test_check_coverage_cobertura_total(agent):
    state = {
        "A": {"f1": "v1", "f2": "v2", "f3": "v3", "f4": "v4"},
        "B": {"f1": "v1", "f2": "v2", "f3": "v3", "f4": "v4"},
    }
    fields = ["f1", "f2", "f3", "f4"]
    assert agent._check_coverage(state, fields) is True


def test_check_coverage_insuficiente(agent):
    # Nenhuma entidade tem >= 75% dos campos
    state = {
        "A": {"f1": "v1", "f2": None, "f3": None, "f4": None},
        "B": {"f1": "v1", "f2": None, "f3": None, "f4": None},
    }
    fields = ["f1", "f2", "f3", "f4"]
    assert agent._check_coverage(state, fields) is False


def test_check_coverage_limiar_exato_80_pct(agent):
    # 8 de 10 entidades com 75%+ campos = 80% = sufficient
    fields = ["f1", "f2", "f3", "f4"]
    state = {}
    # 8 entidades com 4/4 campos
    for i in range(8):
        state[f"ENT{i}"] = {"f1": "v", "f2": "v", "f3": "v", "f4": "v"}
    # 2 entidades com 0/4 campos
    for i in range(8, 10):
        state[f"ENT{i}"] = {"f1": None, "f2": None, "f3": None, "f4": None}
    assert agent._check_coverage(state, fields) is True


def test_check_coverage_abaixo_do_limiar(agent):
    # 7 de 10 entidades com campos suficientes = 70% < 80%
    fields = ["f1", "f2", "f3", "f4"]
    state = {}
    for i in range(7):
        state[f"ENT{i}"] = {"f1": "v", "f2": "v", "f3": "v", "f4": "v"}
    for i in range(7, 10):
        state[f"ENT{i}"] = {"f1": None, "f2": None, "f3": None, "f4": None}
    assert agent._check_coverage(state, fields) is False


def test_check_coverage_estado_vazio(agent):
    assert agent._check_coverage({}, ["f1", "f2"]) is False


def test_check_coverage_campos_vazios(agent):
    state = {"A": {"f1": "v"}}
    assert agent._check_coverage(state, []) is False


# ============================================================================
# _match_entity
# ============================================================================


def test_match_entity_exato(agent):
    assert agent._match_entity("ALFA11", ["ALFA11", "BETA11"]) == "ALFA11"


def test_match_entity_case_insensitive(agent):
    assert agent._match_entity("alfa11", ["ALFA11", "BETA11"]) == "ALFA11"


def test_match_entity_parcial(agent):
    # "ALFA" está contido em "ALFA11"
    assert agent._match_entity("ALFA", ["ALFA11", "BETA11"]) == "ALFA11"


def test_match_entity_sem_match(agent):
    assert agent._match_entity("ZETA99", ["ALFA11", "BETA11"]) is None


def test_match_entity_lista_vazia(agent):
    assert agent._match_entity("ALFA11", []) is None


# ============================================================================
# _match_field
# ============================================================================


def test_match_field_exato(agent):
    fields = ["CAMPO_A", "campo_b", "METRICA_X"]
    assert agent._match_field("CAMPO_A", fields) == "CAMPO_A"


def test_match_field_case_insensitive(agent):
    fields = ["CAMPO_A", "campo_b"]
    assert agent._match_field("campo_a", fields) == "CAMPO_A"


def test_match_field_espaco_para_underscore(agent):
    fields = ["CAMPO_A", "campo_b"]
    assert agent._match_field("CAMPO A", fields) == "CAMPO_A"


def test_match_field_parcial(agent):
    fields = ["CAMPO_A", "campo_b", "METRICA_X"]
    # "metrica" está contido em "METRICA_X"
    assert agent._match_field("metrica", fields) == "METRICA_X"


def test_match_field_sem_match(agent):
    fields = ["CAMPO_A", "campo_b"]
    assert agent._match_field("liquidez_diaria", fields) is None


# ============================================================================
# _is_placeholder_value
# ============================================================================


@pytest.mark.parametrize(
    "valor",
    [
        "",
        "   ",
        "-",
        chr(0x2014),
        "--",
        "N/A",
        "-%",
        "[não encontrado]",
        "Dados não encontrados",
        "Ver dados da B3",
        "Indeterminado",
        "Não há dados de cotação neste período",
        "*" + chr(0x2014) + "*",
    ],
)
def test_is_placeholder_value_descarta(agent, valor):
    assert agent._is_placeholder_value(valor) is True


@pytest.mark.parametrize(
    "valor",
    [
        "R$ 1,3 bilhão",
        "13,60%",
        "Não há",
        "Não há restrição",
        "Isento de IR",
        "Mensal",
        "Papéis",
        "0,00%",
    ],
)
def test_is_placeholder_value_mantem_dado_real(agent, valor):
    assert agent._is_placeholder_value(valor) is False


# ============================================================================
# _filter_by_dominant_form
# ============================================================================


def test_filter_by_dominant_form_descarta_nomes_longos(agent):
    # Há um cluster claro de códigos compactos → nomes longos são anomalias.
    ents = [
        "XPML11",
        "TRXF11",
        "KNCR11",
        "BTLG11",
        "V8 SPEEDWAY VEGA LS XP SEG PREV FIC MULTIMERCADO RL",
        "NORTE EQUITY HEDGE FIF COTAS FIM",
    ]
    out = agent._filter_by_dominant_form(ents)
    assert out == ["XPML11", "TRXF11", "KNCR11", "BTLG11"]


def test_filter_by_dominant_form_nao_dispara_para_nomes_longos(agent):
    # Domínio cujos itens são nomes longos: sem cluster compacto → não filtra.
    ents = [
        "Universidade de São Paulo",
        "Universidade Federal do Rio de Janeiro",
        "Universidade Estadual de Campinas",
    ]
    assert agent._filter_by_dominant_form(ents) == ents


def test_filter_by_dominant_form_poucos_codigos_nao_dispara(agent):
    # Menos de _MIN_COMPACT_CLUSTER códigos compactos → não filtra (evita falso positivo).
    ents = ["AB12", "Nome Longo Um", "Nome Longo Dois", "Nome Longo Tres"]
    assert agent._filter_by_dominant_form(ents) == ents


# ============================================================================
# _compute_complexity
# ============================================================================


@pytest.mark.parametrize(
    "item_count, fields_per_item, expected",
    [
        # abaixo do mínimo de itens → simple
        (2, 5, "simple"),
        # abaixo do mínimo de campos → simple
        (3, 2, "simple"),
        # mínimo exato → medium
        (3, 3, "medium"),
        # teto máximo de medium
        (5, 7, "medium"),
        # itens acima do teto → complex
        (6, 7, "complex"),
        # campos acima do teto → complex
        (5, 8, "complex"),
        # prompt FII canonico (10 entidades x 12 campos) -> complex
        (10, 12, "complex"),
    ],
)
def test_compute_complexity(item_count, fields_per_item, expected):
    assert (
        DeepResearchAgent._compute_complexity(item_count, fields_per_item) == expected
    )


# ============================================================================
# _aggregate_state
# ============================================================================


def test_aggregate_state_completo(agent):
    state = {
        "ALFA11": {"CAMPO_A": "10.5%", "campo_b": "papel"},
        "BETA11": {"CAMPO_A": "8.2%", "campo_b": "logística"},
    }
    fields = ["CAMPO_A", "campo_b"]
    result = agent._aggregate_state(state, fields)
    assert "ALFA11" in result
    assert "BETA11" in result
    assert "10.5%" in result
    assert "8.2%" in result
    assert "papel" in result
    assert "logística" in result


def test_aggregate_state_campos_ausentes(agent):
    state = {
        "ALFA11": {"CAMPO_A": "10.5%", "campo_b": None},
    }
    fields = ["CAMPO_A", "campo_b"]
    result = agent._aggregate_state(state, fields)
    assert "não encontrado" in result
    assert "campo_b" in result
    assert "⚠" in result


def test_aggregate_state_vazio(agent):
    result = agent._aggregate_state({}, ["CAMPO_A"])
    assert "Nenhuma entidade" in result


def test_aggregate_state_inclui_bloco_nao_pesquisaveis(agent):
    """Campos não-pesquisáveis geram bloco de orientação para o LLM de resposta."""
    state = {"ALFA11": {"CAMPO_A": "10.5%", "METRICA_X": "2.1%"}}
    result = agent._aggregate_state(
        state,
        ["CAMPO_A", "METRICA_X"],
        ["identificador", "razao_derivada", "motivos", "fontes"],
    )
    assert "CAMPOS A PREENCHER SEM BUSCA" in result
    assert "razao_derivada" in result
    assert "motivos" in result
    # campos pesquisáveis continuam presentes
    assert "10.5%" in result


def test_format_fonte_mapeada_vira_marcador_web():
    from sei_ia.agents.websearch.deep_research_agent import DeepResearchAgent

    out = DeepResearchAgent._format_fonte("https://a.com", {"https://a.com": 3})
    assert out == " (fonte: <web_3>)"


def test_format_fonte_nao_mapeada_mantem_url():
    from sei_ia.agents.websearch.deep_research_agent import DeepResearchAgent

    out = DeepResearchAgent._format_fonte("https://a.com", {})
    assert out == " (fonte: https://a.com)"


def test_format_fonte_vazia():
    from sei_ia.agents.websearch.deep_research_agent import DeepResearchAgent

    assert DeepResearchAgent._format_fonte("", {"https://a.com": 2}) == ""


def test_aggregate_state_anota_fonte_com_marcador_web(agent):
    """Com url_to_idx, cada dado é anotado com (fonte: <web_N>) e há instrução de citação."""
    state = {
        "ALFA11": {
            "CAMPO_A": {"valor": "10.5%", "fonte": "https://a.com"},
            "campo_b": {"valor": "papel", "fonte": "https://b.com"},
        }
    }
    url_to_idx = {"https://a.com": 2, "https://b.com": 3}
    result = agent._aggregate_state(state, ["CAMPO_A", "campo_b"], None, url_to_idx)
    assert "(fonte: <web_2>)" in result
    assert "(fonte: <web_3>)" in result
    # instrução para o LLM reproduzir o marcador
    assert "REPRODUZA" in result
    # não vaza a URL crua quando há marcador
    assert "https://a.com" not in result


def test_aggregate_state_sem_mapa_mantem_url_textual(agent):
    """Sem url_to_idx, mantém o formato antigo (fonte: url) sem marcador."""
    state = {"ALFA11": {"CAMPO_A": {"valor": "10.5%", "fonte": "https://a.com"}}}
    result = agent._aggregate_state(state, ["CAMPO_A"])
    assert "(fonte: https://a.com)" in result
    assert "<web_" not in result


def test_aggregate_state_sem_nao_pesquisaveis_nao_gera_bloco(agent):
    """Sem campos não-pesquisáveis, não há bloco extra (compatível com chamada antiga)."""
    state = {"ALFA11": {"CAMPO_A": "10.5%"}}
    result = agent._aggregate_state(state, ["CAMPO_A"])
    assert "CAMPOS A PREENCHER SEM BUSCA" not in result


# ============================================================================
# _is_type_word
# ============================================================================


@pytest.mark.parametrize(
    ("identifier", "entity_type", "esperado"),
    [
        ("widget", "widget", True),  # igual ao tipo
        ("widgets", "widget", True),  # plural do tipo
        ("Widget", "widget", True),  # caixa diferente
        ("BETA11", "widget", False),  # instância real
        ("AGGR", "widget", False),  # índice (tratado pelo prompt, não por este guard)
        ("gizmo", "gizmo", True),
        ("Acme", "gizmo", False),
    ],
)
def test_is_type_word(identifier, entity_type, esperado):
    from sei_ia.agents.websearch.deep_research_agent import DeepResearchAgent

    assert DeepResearchAgent._is_type_word(identifier, entity_type) is esperado


def test_extract_entity_names_filtra_palavra_tipo(agent, mock_llm):
    """O termo genérico do tipo é descartado do resultado da extração."""
    resp = MagicMock()
    resp.content = json.dumps({"entities": ["widgets", "BETA11", "widget", "GAMA11"]})
    mock_llm.ainvoke.return_value = resp
    agent.compress_llm = None
    result = asyncio.run(
        agent._extract_entity_names("conteúdo", "widget", 10, ["campo_a"])
    )
    assert result == ["BETA11", "GAMA11"]


# ============================================================================
# _resolve_searchable_fields
# ============================================================================


def test_resolve_searchable_fields_subconjunto_valido():
    from sei_ia.agents.websearch.deep_research_agent import DeepResearchAgent

    plan = {
        "required_fields": [
            "nome",
            "identificador",
            "campo_a",
            "metrica",
            "razao",
            "fontes",
        ],
        "searchable_fields": ["campo_a", "metrica"],
    }
    # preserva a ordem de required_fields e mantém só os marcados
    assert DeepResearchAgent._resolve_searchable_fields(plan) == [
        "campo_a",
        "metrica",
    ]


def test_resolve_searchable_fields_fallback_quando_ausente():
    from sei_ia.agents.websearch.deep_research_agent import DeepResearchAgent

    plan = {"required_fields": ["a", "b", "c"]}  # sem searchable_fields
    assert DeepResearchAgent._resolve_searchable_fields(plan) == ["a", "b", "c"]


def test_resolve_searchable_fields_fallback_quando_vazio_ou_invalido():
    from sei_ia.agents.websearch.deep_research_agent import DeepResearchAgent

    req = ["a", "b"]
    # lista vazia → fallback para required
    assert (
        DeepResearchAgent._resolve_searchable_fields(
            {"required_fields": req, "searchable_fields": []}
        )
        == req
    )
    # tipo inválido → fallback para required
    assert (
        DeepResearchAgent._resolve_searchable_fields(
            {"required_fields": req, "searchable_fields": "dy"}
        )
        == req
    )
    # marcados que não existem em required → fallback (nenhuma interseção)
    assert (
        DeepResearchAgent._resolve_searchable_fields(
            {"required_fields": req, "searchable_fields": ["x", "y"]}
        )
        == req
    )


# ============================================================================
# _extract_research_plan
# ============================================================================


def test_extract_research_plan_sucesso(agent, mock_llm):
    expected = {
        "entity_type": "widget",
        "required_fields": ["CAMPO_A", "campo_b", "METRICA_X"],
        "known_entities": [],
        "discovery_queries": ["top widgets lista"],
        "expected_entity_count": 10,
        "search_context": "Top 10 widgets por métrica",
    }
    mock_response = MagicMock()
    mock_response.content = json.dumps(expected)
    mock_llm.ainvoke.return_value = mock_response

    result = asyncio.run(agent._extract_research_plan("prompt complexo"))

    assert result["entity_type"] == "widget"
    assert result["required_fields"] == ["CAMPO_A", "campo_b", "METRICA_X"]
    assert result["expected_entity_count"] == 10


def test_extract_research_plan_fallback_em_erro(agent, mock_llm):
    mock_llm.ainvoke.side_effect = Exception("LLM indisponível")

    result = asyncio.run(agent._extract_research_plan("prompt qualquer"))

    assert result["required_fields"] == []
    assert "entity_type" in result
    assert "discovery_queries" in result


def test_extract_research_plan_fallback_sem_required_fields(agent, mock_llm):
    # LLM retorna JSON sem required_fields — deve cair no fallback
    mock_response = MagicMock()
    mock_response.content = json.dumps({"entity_type": "widget"})
    mock_llm.ainvoke.return_value = mock_response

    result = asyncio.run(agent._extract_research_plan("prompt"))

    assert result["required_fields"] == []


# ============================================================================
# _arun — delega para pai em query simples
# ============================================================================


def test_arun_delega_para_pai_em_query_simples(agent, mock_llm):
    """Query com poucos campos/entidades deve delegar para SearxCrawlAgent._arun."""
    # Plano com apenas 2 campos e 1 entidade → não é multi-entidade
    plan_response = MagicMock()
    plan_response.content = json.dumps(
        {
            "entity_type": "clima",
            "required_fields": ["temperatura", "previsao"],
            "known_entities": [],
            "discovery_queries": ["clima brasilia hoje"],
            "expected_entity_count": 1,
            "search_context": "Clima em Brasília hoje",
        }
    )

    parent_result = [{"content": "resultado pai", "query": "q", "references": []}]

    with patch.object(
        agent.__class__.__bases__[0], "_arun", new=AsyncMock(return_value=parent_result)
    ) as mock_parent:
        mock_llm.ainvoke.return_value = plan_response
        result = asyncio.run(agent._arun("Como está o clima em Brasília?"))

    mock_parent.assert_called_once()
    assert result == parent_result


def test_arun_delega_quando_classificador_simple(agent):
    """Classificador 'simple' delega ao SearxCrawlAgent sem nem extrair o plano deep.

    Cenário do 'Caso 1': pedido respondível por uma página de índice não deve cair no
    fluxo profundo. O classificador é a porta primária.
    """
    parent_result = [{"content": "resultado pai", "query": "q", "references": []}]

    with (
        patch.object(
            agent,
            "_classify_search_mode",
            new=AsyncMock(
                return_value={
                    "mode": "simple",
                    "allowed_domain": "",
                    "target_url": "",
                    "language": "pt-BR",
                }
            ),
        ),
        patch.object(agent, "_extract_research_plan", new=AsyncMock()) as mock_plan,
        patch.object(
            agent.__class__.__bases__[0],
            "_arun",
            new=AsyncMock(return_value=parent_result),
        ) as mock_parent,
    ):
        agent.max_pages = 12
        agent.max_rounds = 4
        result = asyncio.run(agent._arun("Quais os jogos desta semana?"))

    mock_parent.assert_called_once()
    mock_plan.assert_not_called()  # nem extrai o plano profundo no modo simple
    assert result == parent_result
    # perfil leve aplicado antes de delegar
    assert agent.max_rounds == 1
    assert agent.max_pages == 4
    assert agent.byparr_base_url == ""
    assert agent.forced_allowed_urls == []  # simple não força domínio


def test_arun_site_restricted_forca_dominio(agent):
    """Modo site_restricted força o domínio em forced_allowed_urls e delega ao pai."""
    parent_result = [{"content": "resultado pai", "query": "q", "references": []}]
    with (
        patch.object(
            agent,
            "_classify_search_mode",
            new=AsyncMock(
                return_value={
                    "mode": "site_restricted",
                    "allowed_domain": "exemplo.com",
                    "target_url": "",
                    "language": "pt-BR",
                }
            ),
        ),
        patch.object(
            agent.__class__.__bases__[0],
            "_arun",
            new=AsyncMock(return_value=parent_result),
        ) as mock_parent,
    ):
        result = asyncio.run(agent._arun("Busque algo no site exemplo.com"))

    mock_parent.assert_called_once()
    assert result == parent_result
    assert agent.forced_allowed_urls == ["exemplo.com"]
    assert agent.max_rounds == 1


def test_arun_site_restricted_com_url_navega(agent):
    """site_restricted COM target_url navega a URL (fetch-first) sem busca site:."""
    fetch_result = [{"content": "conteúdo da página", "query": "q", "references": []}]
    with (
        patch.object(
            agent,
            "_classify_search_mode",
            new=AsyncMock(
                return_value={
                    "mode": "site_restricted",
                    "allowed_domain": "ge.globo.com",
                    "target_url": "https://ge.globo.com/",
                    "language": "pt-BR",
                }
            ),
        ),
        patch.object(
            agent, "_fetch_site_navigated", new=AsyncMock(return_value=fetch_result)
        ) as mock_fetch,
        patch.object(
            agent.__class__.__bases__[0], "_arun", new=AsyncMock()
        ) as mock_parent,
    ):
        result = asyncio.run(agent._arun("Resultados no site https://ge.globo.com/"))

    mock_fetch.assert_called_once()
    assert mock_fetch.call_args[0][0] == "https://ge.globo.com/"
    assert mock_fetch.call_args[0][1] == "ge.globo.com"
    mock_parent.assert_not_called()  # não dispara queries site: no SearXNG
    assert result == fetch_result


def test_extract_internal_links_filtra_dominio_e_dedup(agent):
    """_extract_internal_links mantém só links do domínio, dedup e sem fragmento."""
    content = (
        "[Agenda](https://ge.globo.com/agenda/) "
        "[Mesmo c/ âncora](https://ge.globo.com/agenda/#topo) "
        '[Time](https://ge.globo.com/ba/times/bahia/ "Bahia") '
        "[Externo](https://exemplo.com/x) "
        "[Sub](https://sub.ge.globo.com/y)"
    )
    links = agent._extract_internal_links(content, "ge.globo.com")
    urls = [u for u, _ in links]
    assert "https://ge.globo.com/agenda/" in urls
    assert "https://ge.globo.com/ba/times/bahia/" in urls
    assert "https://sub.ge.globo.com/y" in urls  # subdomínio entra
    assert "https://exemplo.com/x" not in urls  # domínio externo fica de fora
    assert urls.count("https://ge.globo.com/agenda/") == 1  # dedup do #topo


def test_select_relevant_links_valida_contra_candidatos(agent, mock_compress_llm):
    """_select_relevant_links só devolve URLs presentes nos candidatos, até k."""
    candidates = [
        ("https://ge.globo.com/agenda/", "Agenda"),
        ("https://ge.globo.com/futebol/", "Futebol"),
        ("https://ge.globo.com/institucional/", "Sobre"),
    ]
    mock_compress_llm.ainvoke.return_value = MagicMock(
        content=json.dumps(
            {
                "urls": [
                    "https://ge.globo.com/agenda/",
                    "https://inventada.com/x",  # descartada (não é candidato)
                    "https://ge.globo.com/futebol/",
                ]
            }
        )
    )
    selected = asyncio.run(
        agent._select_relevant_links("jogos da semana", candidates, k=2)
    )
    assert selected == [
        "https://ge.globo.com/agenda/",
        "https://ge.globo.com/futebol/",
    ]


def test_fetch_site_navigated_semente_mais_links(agent):
    """_fetch_site_navigated agrega semente + páginas seguidas com nó de metadados."""
    seed = {
        "url": "https://ge.globo.com/",
        "title": "GE",
        "content": "[Agenda](https://ge.globo.com/agenda/)",
    }
    agenda = {
        "url": "https://ge.globo.com/agenda/",
        "title": "Agenda",
        "content": "jogos da semana",
    }
    with (
        patch.object(agent, "_fetch_page", new=AsyncMock(side_effect=[seed, agenda])),
        patch.object(
            agent,
            "_select_relevant_links",
            new=AsyncMock(return_value=["https://ge.globo.com/agenda/"]),
        ),
    ):
        results = asyncio.run(
            agent._fetch_site_navigated(
                "https://ge.globo.com/", "ge.globo.com", "jogos da semana"
            )
        )

    content_items = [r for r in results if r.get("node") != "web_search_metadata"]
    meta = next(r for r in results if r.get("node") == "web_search_metadata")
    assert len(content_items) == 2  # semente + agenda
    assert {c["references"][0]["url"] for c in content_items} == {
        "https://ge.globo.com/",
        "https://ge.globo.com/agenda/",
    }
    assert meta["urls_consultadas"] == [
        "https://ge.globo.com/",
        "https://ge.globo.com/agenda/",
    ]


def test_fetch_site_navigated_semente_inacessivel(agent):
    """Semente inacessível → mensagem amigável de bloqueio, sem navegar."""
    with patch.object(agent, "_fetch_page", new=AsyncMock(return_value=None)):
        results = asyncio.run(
            agent._fetch_site_navigated(
                "https://bloqueado.com/", "bloqueado.com", "algo"
            )
        )
    assert len(results) == 1
    assert "Não foi possível acessar" in results[0]["content"]
    assert results[0]["references"] == []


def test_classify_search_mode_fallback_em_erro(agent, mock_llm):
    """Erro na classificação retorna modo 'simple' (default conservador)."""
    mock_llm.ainvoke.side_effect = Exception("timeout")
    agent.compress_llm = None  # força uso do self.llm mockado
    result = asyncio.run(agent._classify_search_mode("pedido qualquer"))
    assert result["mode"] == "simple"


def test_arun_single_url_fetch_direto(agent):
    """Modo single_url chama _fetch_single_url e não delega ao SearxCrawlAgent."""
    single_result = [{"content": "página traduzível", "query": "q", "references": []}]
    with (
        patch.object(
            agent,
            "_classify_search_mode",
            new=AsyncMock(
                return_value={
                    "mode": "single_url",
                    "allowed_domain": "",
                    "target_url": "https://exemplo.com/artigo",
                    "language": "pt-BR",
                }
            ),
        ),
        patch.object(
            agent, "_fetch_single_url", new=AsyncMock(return_value=single_result)
        ) as mock_fetch,
        patch.object(
            agent.__class__.__bases__[0], "_arun", new=AsyncMock()
        ) as mock_parent,
    ):
        result = asyncio.run(agent._arun("Traduza a página https://exemplo.com/artigo"))

    mock_fetch.assert_called_once()
    assert mock_fetch.call_args[0][0] == "https://exemplo.com/artigo"
    mock_parent.assert_not_called()  # não passa pelo SearxCrawlAgent
    assert result == single_result


def test_arun_url_search_base_mais_busca(agent):
    """Modo url_search baixa a página-base E delega a busca, juntando os dois."""
    base_page = {
        "url": "https://exemplo.com/base",
        "title": "Base",
        "content": "conteúdo base",
    }
    parent_result = [
        {
            "content": "fonte externa",
            "query": "q",
            "references": [{"url": "https://outro.com", "title": "Outro"}],
        },
        {"content": "", "query": "", "references": [], "node": "web_search_metadata"},
    ]
    with (
        patch.object(
            agent,
            "_classify_search_mode",
            new=AsyncMock(
                return_value={
                    "mode": "url_search",
                    "allowed_domain": "",
                    "target_url": "https://exemplo.com/base",
                    "language": "pt-BR",
                }
            ),
        ),
        patch.object(
            agent, "_fetch_page", new=AsyncMock(return_value=base_page)
        ) as mock_fetch,
        patch.object(
            agent.__class__.__bases__[0],
            "_arun",
            new=AsyncMock(return_value=parent_result),
        ) as mock_parent,
    ):
        result = asyncio.run(
            agent._arun("Resuma https://exemplo.com/base e consulte outras fontes")
        )

    mock_fetch.assert_called_once()
    mock_parent.assert_called_once()
    # página-base vem primeiro, seguida dos resultados da busca
    assert result[0]["content"] == "conteúdo base"
    assert result[0]["references"][0]["url"] == "https://exemplo.com/base"
    assert result[1:] == parent_result
    # perfil leve aplicado para a parte de busca
    assert agent.max_rounds == 1
    assert agent.byparr_base_url == ""


def test_arun_url_search_base_inacessivel(agent):
    """url_search com base inacessível retorna mensagem amigável e não busca."""
    with (
        patch.object(
            agent,
            "_classify_search_mode",
            new=AsyncMock(
                return_value={
                    "mode": "url_search",
                    "allowed_domain": "",
                    "target_url": "https://x.com/a",
                    "language": "pt-BR",
                }
            ),
        ),
        patch.object(agent, "_fetch_page", new=AsyncMock(return_value=None)),
        patch.object(
            agent.__class__.__bases__[0], "_arun", new=AsyncMock()
        ) as mock_parent,
    ):
        result = asyncio.run(agent._arun("Resuma https://x.com/a e veja outras fontes"))

    mock_parent.assert_not_called()  # base inacessível → não consulta outras fontes
    assert "Não foi possível acessar" in result[0]["content"]


def test_fetch_single_url_sucesso(agent):
    """_fetch_single_url formata o conteúdo da página e inclui metadados."""
    page = {"url": "https://exemplo.com/a", "title": "Artigo", "content": "texto"}
    with patch.object(agent, "_fetch_page", new=AsyncMock(return_value=page)):
        result = asyncio.run(
            agent._fetch_single_url("https://exemplo.com/a", "traduzir")
        )
    assert result[0]["content"] == "texto"
    assert result[0]["references"][0]["url"] == "https://exemplo.com/a"
    meta = result[-1]
    assert meta["node"] == "web_search_metadata"
    assert meta["urls_consultadas"] == ["https://exemplo.com/a"]


def test_fetch_single_url_inacessivel_msg_amigavel(agent):
    """Quando o fetch falha, retorna mensagem amigável de página inacessível."""
    with patch.object(agent, "_fetch_page", new=AsyncMock(return_value=None)):
        result = asyncio.run(
            agent._fetch_single_url("https://bloqueado.com/x", "traduzir")
        )
    assert "Não foi possível acessar" in result[0]["content"]
    assert result[0]["references"] == []


def test_classify_search_mode_normaliza_dominio(agent, mock_llm):
    """site_restricted com URL completa em allowed_domain → reduz ao host."""
    resp = MagicMock()
    resp.content = json.dumps(
        {"mode": "site_restricted", "allowed_domain": "https://exemplo.com/path/x"}
    )
    mock_llm.ainvoke.return_value = resp
    agent.compress_llm = None
    result = asyncio.run(agent._classify_search_mode("busque no exemplo.com"))
    assert result["mode"] == "site_restricted"
    assert result["allowed_domain"] == "exemplo.com"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("pt-BR", "pt-BR"),
        ("pt_br", "pt-BR"),  # underscore + caixa baixa normalizados
        ("EN", "en"),  # só idioma, sem região
        ("en-us", "en-US"),
        ("all", "all"),  # desativa filtro
        ("", "pt-BR"),  # vazio → default
        ("portugues", "pt-BR"),  # formato inválido → default
        (None, "pt-BR"),
    ],
)
def test_normalize_locale(entrada, esperado):
    from sei_ia.agents.websearch.deep_research_agent import DeepResearchAgent

    assert DeepResearchAgent._normalize_locale(entrada) == esperado


def test_classify_search_mode_emite_language(agent, mock_llm):
    """O classificador retorna o locale normalizado a partir do JSON do LLM."""
    resp = MagicMock()
    resp.content = json.dumps(
        {"mode": "simple", "allowed_domain": "", "target_url": "", "language": "en_us"}
    )
    mock_llm.ainvoke.return_value = resp
    agent.compress_llm = None
    result = asyncio.run(agent._classify_search_mode("latest tech news"))
    assert result["language"] == "en-US"


def test_classify_search_mode_promove_simple_para_deep(agent, mock_llm):
    """simple com sinais multi-entidade (itens e campos ≥ limiar) é promovido a deep."""
    resp = MagicMock()
    resp.content = json.dumps(
        {
            "mode": "simple",
            "allowed_domain": "",
            "target_url": "",
            "language": "pt-BR",
            "item_count": 10,
            "fields_per_item": 5,
        }
    )
    mock_llm.ainvoke.return_value = resp
    agent.compress_llm = None
    result = asyncio.run(agent._classify_search_mode("Top 10 itens com 5 dados cada"))
    assert result["mode"] == "deep"


@pytest.mark.parametrize(
    ("item_count", "fields_per_item"),
    [
        (10, 1),  # muitos itens mas 1 campo → não é multi-entidade
        (1, 5),  # 1 item com muitos campos → não é multi-entidade
        (2, 2),  # ambos abaixo do limiar
    ],
)
def test_classify_search_mode_nao_promove_sem_multi_entidade(
    agent, mock_llm, item_count, fields_per_item
):
    """simple não é promovido quando os sinais não indicam multi-entidade."""
    resp = MagicMock()
    resp.content = json.dumps(
        {
            "mode": "simple",
            "allowed_domain": "",
            "target_url": "",
            "language": "pt-BR",
            "item_count": item_count,
            "fields_per_item": fields_per_item,
        }
    )
    mock_llm.ainvoke.return_value = resp
    agent.compress_llm = None
    result = asyncio.run(agent._classify_search_mode("pedido qualquer"))
    assert result["mode"] == "simple"


def test_classify_search_mode_promocao_nao_afeta_single_url(agent, mock_llm):
    """Sinais multi-entidade NÃO sobrepõem um pedido explícito de URL (single_url)."""
    resp = MagicMock()
    resp.content = json.dumps(
        {
            "mode": "single_url",
            "allowed_domain": "",
            "target_url": "https://exemplo.com/a",
            "language": "pt-BR",
            "item_count": 10,
            "fields_per_item": 5,
        }
    )
    mock_llm.ainvoke.return_value = resp
    agent.compress_llm = None
    result = asyncio.run(agent._classify_search_mode("Resuma https://exemplo.com/a"))
    assert result["mode"] == "single_url"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        (10, 10),
        ("10", 10),  # string numérica
        (10.0, 10),  # float
        ("5.9", 5),  # trunca
        (None, 0),
        ("abc", 0),  # inválido → 0 (conservador, não promove)
        ([], 0),
    ],
)
def test_safe_int(entrada, esperado):
    from sei_ia.agents.websearch.deep_research_agent import DeepResearchAgent

    assert DeepResearchAgent._safe_int(entrada) == esperado


def test_arun_aplica_language_do_classificador(agent):
    """_arun grava o locale do classificador em self.search_language antes de buscar."""
    parent_result = [{"content": "x", "query": "q", "references": []}]
    with (
        patch.object(
            agent,
            "_classify_search_mode",
            new=AsyncMock(
                return_value={
                    "mode": "simple",
                    "allowed_domain": "",
                    "target_url": "",
                    "language": "en-US",
                }
            ),
        ),
        patch.object(
            agent.__class__.__bases__[0],
            "_arun",
            new=AsyncMock(return_value=parent_result),
        ),
    ):
        asyncio.run(agent._arun("latest news"))
    assert agent.search_language == "en-US"


# ============================================================================
# _generate_targeted_queries
# ============================================================================


def test_generate_targeted_queries_sucesso(agent, mock_llm):
    mock_response = MagicMock()
    mock_response.content = json.dumps(
        {
            "queries": [
                "ALFA11 CAMPO_A site:exemplo.com",
                "BETA11 atributo",
            ]
        }
    )
    mock_llm.ainvoke.return_value = mock_response

    gaps = [("ALFA11", "CAMPO_A"), ("BETA11", "CAMPO_A")]
    queries = asyncio.run(agent._generate_targeted_queries(gaps, "widgets", "widget"))

    # A garantia de bare query pode adicionar queries extras para entidades
    # que só têm queries com site: — verifica conteúdo em vez de contagem exata.
    assert len(queries) >= 2
    assert "ALFA11 CAMPO_A site:exemplo.com" in queries
    all_text = " ".join(queries)
    assert "BETA11" in all_text


def test_generate_targeted_queries_fallback_em_erro(agent, mock_llm):
    mock_llm.ainvoke.side_effect = Exception("timeout")

    gaps = [("ALFA11", "CAMPO_A"), ("BETA11", "campo_b")]
    queries = asyncio.run(agent._generate_targeted_queries(gaps, "widgets", "widget"))

    # Fallback gera queries simples: uma por entidade única
    assert len(queries) >= 1
    # Verifica que ao menos uma query menciona uma entidade
    all_text = " ".join(queries)
    assert "ALFA11" in all_text or "BETA11" in all_text
