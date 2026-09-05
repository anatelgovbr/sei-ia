"""Regressao do grafo de sumarizacao: deve usar BaseChatModel.invoke.

O bug original (`'ChatOpenAI' object has no attribute 'predict'`) so disparava
quando o documento excedia o contexto e o caminho de sumarizacao era acionado.
Os testes de prompt_with_doc_summarization mockam select_summarize_model inteiro,
entao nunca exercitavam generate_summary e o bug ficou dormente. Aqui exercitamos
o grafo real com um BaseChatModel stub: como BaseChatModel nao possui .predict, o
teste falha se alguem reintroduzir a API legada.
"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from sei_ia.agents.summarize.summarize import _build_summarize_graph


class _StubChatModel(BaseChatModel):
    """Modelo minimo: responde via _generate (suporta .invoke) e nao tem .predict."""

    @property
    def _llm_type(self) -> str:
        return "stub-summarize"

    def get_num_tokens(self, text: str) -> int:
        return max(1, len(str(text).split()))

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):  # noqa: ANN001, ARG002
        ultimo = messages[-1].content if messages else ""
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content=f"RESUMO::{str(ultimo)[:12]}"))
            ]
        )


def test_base_chat_model_nao_tem_predict():
    """Premissa do fix: a API legada .predict foi removida do langchain 1.x."""
    assert not hasattr(BaseChatModel, "predict")


def test_generate_summary_usa_invoke_e_retorna_str():
    """generate_summary deve resumir via invoke().content (str).

    Com o bug (.predict) este teste levanta AttributeError, pois o stub
    BaseChatModel nao expoe .predict — exatamente o que ocorria em producao.
    """
    grafo = _build_summarize_graph(_StubChatModel(), max_ctx_tokens=100_000)

    resultado = grafo.invoke({"contents": ["um dois tres quatro cinco seis"]})

    resumos = resultado["collapsed_summaries"]
    assert len(resumos) == 1
    assert isinstance(resumos[0], Document)
    assert isinstance(resumos[0].page_content, str)
    assert resumos[0].page_content.startswith("RESUMO::")
