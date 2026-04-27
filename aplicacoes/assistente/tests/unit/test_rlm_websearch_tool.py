"""Testes unitários para _make_websearch_tool no pipeline RLM.

Cobre:
- Renumeracao global de referencias entre chamadas concorrentes
- Normalizacao de marcadores <web_N></web_N> → <web_N>
- Acumulacao de shared.web_references
- Fallback quando bing retorna JSON inválido
"""

import json
import threading
from unittest.mock import patch

from sei_ia.services.rlm.tools import RLMSharedState, _make_websearch_tool


def _make_shared() -> RLMSharedState:
    return RLMSharedState(
        context="",
        doc_contents={},
        boundary_positions=[],
        boundary_seis=[],
        catalog="",
    )


def _bing_result(text: str, refs: list[dict]) -> str:
    return json.dumps({"text": text, "references": refs}, ensure_ascii=False)


# ============================================================================
# Renumeracao de referencias
# ============================================================================


def test_primeira_chamada_numera_a_partir_de_1():
    shared = _make_shared()
    tool = _make_websearch_tool(shared, todo_id=1)

    with patch(
        "sei_ia.agents.websearch.azure_web_search_tool.bing_grounding_search"
    ) as mock_bg:
        mock_bg.invoke.return_value = _bing_result(
            "Texto <web_1></web_1> e <web_2></web_2>",
            [
                {"idx": 1, "url": "https://a.com", "title": "A"},
                {"idx": 2, "url": "https://b.com", "title": "B"},
            ],
        )
        result = tool.invoke({"query": "test"})

    assert "<web_1>" in result
    assert "<web_2>" in result
    assert len(shared.web_references) == 2
    assert shared.web_references[0] == {"idx": 1, "url": "https://a.com", "title": "A"}
    assert shared.web_references[1] == {"idx": 2, "url": "https://b.com", "title": "B"}
    assert shared._web_ref_counter[0] == 2


def test_segunda_chamada_continua_numeracao():
    shared = _make_shared()
    tool = _make_websearch_tool(shared, todo_id=1)

    resultado_bing = _bing_result(
        "Info <web_1></web_1>",
        [{"idx": 1, "url": "https://x.com", "title": "X"}],
    )

    with patch(
        "sei_ia.agents.websearch.azure_web_search_tool.bing_grounding_search"
    ) as mock_bg:
        mock_bg.invoke.return_value = resultado_bing
        tool.invoke({"query": "primeira busca"})
        # Segunda chamada — contador já está em 1, nova ref deve ser idx=2
        result2 = tool.invoke({"query": "segunda busca"})

    assert "<web_2>" in result2
    assert len(shared.web_references) == 2
    assert shared.web_references[0]["idx"] == 1
    assert shared.web_references[1]["idx"] == 2
    assert shared._web_ref_counter[0] == 2


def test_dois_exploradores_diferentes_nao_colidem():
    """Dois exploradores chamando web_search em paralelo devem ter idx globais únicos."""
    shared = _make_shared()
    tool_1 = _make_websearch_tool(shared, todo_id=1)
    tool_2 = _make_websearch_tool(shared, todo_id=2)

    results = {}

    def busca(tool, key):
        with patch(
            "sei_ia.agents.websearch.azure_web_search_tool.bing_grounding_search"
        ) as mock_bg:
            mock_bg.invoke.return_value = _bing_result(
                f"Resultado {key} <web_1></web_1> <web_2></web_2>",
                [
                    {"idx": 1, "url": f"https://{key}-1.com", "title": f"{key}-1"},
                    {"idx": 2, "url": f"https://{key}-2.com", "title": f"{key}-2"},
                ],
            )
            results[key] = tool.invoke({"query": f"query {key}"})

    t1 = threading.Thread(target=busca, args=(tool_1, "A"))
    t2 = threading.Thread(target=busca, args=(tool_2, "B"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # 4 refs no total, todos com idx únicos
    assert len(shared.web_references) == 4
    idxs = [r["idx"] for r in shared.web_references]
    assert len(idxs) == len(set(idxs)), f"idx duplicados: {idxs}"
    assert shared._web_ref_counter[0] == 4


# ============================================================================
# Normalizacao de marcadores
# ============================================================================


def test_normaliza_marcador_com_fechamento():
    """<web_N></web_N> deve ser convertido para <web_N>."""
    shared = _make_shared()
    tool = _make_websearch_tool(shared, todo_id=1)

    with patch(
        "sei_ia.agents.websearch.azure_web_search_tool.bing_grounding_search"
    ) as mock_bg:
        mock_bg.invoke.return_value = _bing_result(
            "Fonte <web_1></web_1> aqui",
            [{"idx": 1, "url": "https://gov.br", "title": "Gov"}],
        )
        result = tool.invoke({"query": "q"})

    # Tag com fechamento deve ter sido normalizada
    assert "</web_" not in result
    assert "<web_1>" in result


def test_texto_sem_refs_retorna_direto():
    shared = _make_shared()
    tool = _make_websearch_tool(shared, todo_id=1)

    with patch(
        "sei_ia.agents.websearch.azure_web_search_tool.bing_grounding_search"
    ) as mock_bg:
        mock_bg.invoke.return_value = json.dumps(
            {"text": "Sem fontes.", "references": []}
        )
        result = tool.invoke({"query": "q"})

    assert result == "Sem fontes."
    assert len(shared.web_references) == 0
    assert shared._web_ref_counter[0] == 0


# ============================================================================
# Fallback
# ============================================================================


def test_fallback_quando_bing_retorna_json_invalido():
    shared = _make_shared()
    tool = _make_websearch_tool(shared, todo_id=1)

    with patch(
        "sei_ia.agents.websearch.azure_web_search_tool.bing_grounding_search"
    ) as mock_bg:
        mock_bg.invoke.return_value = "não é json"
        result = tool.invoke({"query": "q"})

    assert result == "não é json"
    assert len(shared.web_references) == 0
