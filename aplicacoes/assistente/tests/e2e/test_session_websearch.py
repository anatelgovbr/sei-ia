"""E2E hermético de busca web no ``/llm_lang/session_stream``."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import PrivateAttr

from sei_ia.agents.session_agent.web_evidence_gate import EvidenceGateVerdict
from tests.e2e.session_support import SessionStreamHarness

_WEB_URL = "https://fixture.invalid/boletim-regulatorio"
_WEB_TITLE = "Boletim regulatório de fixture"
_WEB_FACT = "CANARY_WEB_FACT_7429"
_WEB_QUERY = "indicador regulatório publicado em 2026"


class _EvidenceBoundWebModel(BaseChatModel):
    """Pede a busca e deriva a resposta do conteúdo devolvido pela ferramenta."""

    model_name: str = "evidence-bound-web-e2e"
    _bound_tool_names: set[str] = PrivateAttr(default_factory=set)

    @property
    def _llm_type(self) -> str:
        return "evidence-bound-web-e2e"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ARG002
        self._bound_tool_names = {
            str(getattr(tool, "name", ""))
            for tool in tools
            if getattr(tool, "name", "")
        }
        return self

    @staticmethod
    def _message_text(message: BaseMessage) -> str:
        if isinstance(message.content, str):
            return message.content
        return json.dumps(message.content, ensure_ascii=False, default=str)

    def _next_message(self, messages: list[BaseMessage]) -> AIMessage:
        tool_evidence = "\n".join(
            self._message_text(message)
            for message in messages
            if isinstance(message, ToolMessage)
        )
        if not tool_evidence:
            if "web_research_search" not in self._bound_tool_names:
                return AIMessage(content="WEB_TOOL_UNAVAILABLE")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "web_research_search",
                        "args": {"user_request": _WEB_QUERY},
                        "id": "web-search-e2e-call",
                        "type": "tool_call",
                    }
                ],
            )

        fact = re.search(r"PROVA_WEB=(CANARY_[A-Z0-9_]+)", tool_evidence)
        marker = re.search(r"Citação:\s*(<web_\d+>)", tool_evidence)
        if fact is None:
            return AIMessage(content="WEB_EVIDENCE_NOT_RECEIVED")
        if marker is None:
            return AIMessage(content="WEB_CITATION_NOT_RECEIVED")
        return AIMessage(
            content=f"Indicador confirmado: {fact.group(1)}{marker.group(1)}"
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,  # noqa: ANN001, ARG002
        **kwargs,
    ) -> ChatResult:
        _ = (stop, run_manager, kwargs)
        return ChatResult(
            generations=[ChatGeneration(message=self._next_message(messages))]
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,  # noqa: ANN001, ARG002
        **kwargs,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,  # noqa: ANN001, ARG002
        **kwargs,
    ):
        _ = (stop, run_manager, kwargs)
        message = self._next_message(messages)
        if message.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="", tool_calls=message.tool_calls)
            )
            return

        marker = re.search(r"<web_\d+>", str(message.content))
        pieces = (
            [message.content]
            if marker is None
            else [
                message.content[: marker.start()],
                marker.group()[:3],
                marker.group()[3:-1],
                marker.group()[-1:],
            ]
        )
        for piece in pieces:
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,  # noqa: ANN001, ARG002
        **kwargs,
    ):
        for chunk in self._stream(
            messages, stop=stop, run_manager=run_manager, **kwargs
        ):
            yield chunk
            await asyncio.sleep(0)


@pytest.mark.parametrize("gate_enabled", [False, True], ids=["sem-gate", "com-gate"])
def test_websearch_executa_tool_persiste_fontes_e_renderiza_citacoes(
    monkeypatch, tmp_path, gate_enabled
):
    from sei_ia.agents.websearch import web_research_agent as web_module
    from sei_ia.configs.settings_config import settings
    from sei_ia.routers.session import stream as stream_module

    async def classify_locally(
        _question: str, _doc_count: int, *, callbacks: list[Any] | None = None
    ) -> str:
        _ = callbacks
        return "easy"

    async def plan_speculative_searches(
        _question: str,
        _doc_hint: str,
        *,
        max_queries: int,
        callbacks: list[Any] | None = None,
    ) -> list[str]:
        _ = (max_queries, callbacks)
        return [_WEB_QUERY] if gate_enabled else []

    async def search_local_fixture(_agent, _query: str) -> list[dict[str, str]]:
        return [
            {
                "url": _WEB_URL,
                "title": _WEB_TITLE,
                "snippet": _WEB_TITLE,
            }
        ]

    async def fetch_local_fixture(
        _agent, _url: str, _title: str, _min_content_len: int
    ) -> dict[str, str]:
        body = (
            f"Relatório local. PROVA_WEB={_WEB_FACT}. "
            "Este conteúdo repetido mantém a página acima do mínimo aceito pelo "
            "crawler sem consultar qualquer serviço externo. "
        ) * 4
        return {"url": _WEB_URL, "title": _WEB_TITLE, "content": body}

    async def gate_local_evidence(_question, batches, **_kwargs):
        assert any(_WEB_FACT in batch for batch in batches)
        return EvidenceGateVerdict(
            ledger=(
                {
                    "entity": "indicador regulatório",
                    "criterion": "publicado em 2026",
                    "value": _WEB_FACT,
                    "url": _WEB_URL,
                    "evidence": f"PROVA_WEB={_WEB_FACT}",
                },
            ),
            gaps=(),
            next_query=None,
        )

    monkeypatch.setattr(stream_module, "classify_complexity", classify_locally)
    monkeypatch.setattr(
        stream_module,
        "plan_speculative_web_queries",
        plan_speculative_searches,
    )
    monkeypatch.setattr(
        web_module.WebResearchAgent, "_search_searx", search_local_fixture
    )
    monkeypatch.setattr(web_module.WebResearchAgent, "_fetch_page", fetch_local_fixture)
    monkeypatch.setattr(web_module, "assess_web_evidence", gate_local_evidence)
    monkeypatch.setattr(settings, "SESSION_WEB_TOOL", "web_research")
    monkeypatch.setattr(
        settings, "SESSION_WEBRESEARCH_EVIDENCE_GATE_ENABLED", gate_enabled
    )

    harness = SessionStreamHarness(
        monkeypatch,
        tmp_path,
        documents={},
        model_factory=_EvidenceBoundWebModel,
    )
    try:
        result = harness.post(
            "Consulte a web e informe o indicador regulatório.",
            request_overrides={"use_websearch": True},
        )
        manifest = harness.manifest()
    finally:
        harness.close()

    result.assert_completed()
    assert result.metadata["use_websearch"] is True
    assert _WEB_FACT in result.content
    assert "<web_" not in result.content
    assert "</web_" not in result.content

    rendered_sources = re.findall(
        r'<a\b[^>]*class="AssistenteSEIIAfonteWebSearch"[^>]*>.*?</a>',
        result.content,
    )
    assert len(rendered_sources) == 2
    assert all(f'href="{_WEB_URL}"' in source for source in rendered_sources)
    assert any(f'title="{_WEB_TITLE}"' in source for source in rendered_sources)
    assert "<strong>Referências:</strong>" in result.content

    content_without_sources = re.sub(
        r'<a\b[^>]*class="AssistenteSEIIAfonteWebSearch"[^>]*>.*?</a>',
        "",
        result.content,
    )
    assert _WEB_URL not in content_without_sources
    assert _WEB_TITLE not in content_without_sources

    web_files = list((harness.session_root / "web").glob("*.md"))
    assert len(web_files) == 1
    saved_page = web_files[0].read_text(encoding="utf-8")
    assert f"# {_WEB_TITLE}" in saved_page
    assert f"Fonte: {_WEB_URL}" in saved_page
    assert f"PROVA_WEB={_WEB_FACT}" in saved_page

    expected_source = {
        "url": _WEB_URL,
        "title": _WEB_TITLE,
        "path": f"web/{web_files[0].name}",
    }
    assert manifest["websearch"] == {
        "searched": True,
        "path": "web/",
        "latest_response_sources": [expected_source],
        "other_sources": [],
    }
