"""Testes unitários do contrato de reasoning/content em chat_workflow.

Congela o contrato downstream:
- `chat_gpt` com `use_thinking=True` retorna dict com `response` (str),
  `reasoning` (str), `n_tokens` (tuple).
- `chat_gpt` com `use_thinking=False` retorna dict com `response` (str)
  e `n_tokens` (tuple), sem reasoning.
- O `writer` recebe chunks de reasoning (envoltos em `<reasoning>...</reasoning>`)
  e chunks de content (string direta).
- `get_reasoning_model_kwargs` retorna kwargs corretos para
  `ChatOpenAI(use_responses_api=True, reasoning={...})` quando aplicável.
- Os helpers `extract_reasoning_delta`/`extract_content_delta` aceitam
  os dois formatos de `chunk.content`: str (Chat Completions) e
  list[dict] (Responses API).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user_state(
    *,
    use_thinking: bool = False,
    use_websearch: bool = False,
    model_override: str | None = None,
    reasoning_effort: str | None = None,
) -> dict:
    """UserState mínimo para o caminho hot de chat_gpt sem memória/RAG."""
    return {
        "id_request": 1,
        "id_usuario": 1,
        "ip": "127.0.0.1",
        "endpoint_name": "/llm_lang/stream",
        "id_topico": None,
        "id_procedimentos": None,
        "all_procs": [],
        "all_documents": [],
        "user_request": "pergunta de teste",
        "system_prompt": "system de teste",
        "original_request_body": "{}",
        "intent": "pergunta",
        "agent_tag": "principal",
        "model_override": model_override,
        "reasoning_effort": reasoning_effort,
        "model_name": "",
        "temperature": 0.0,
        "general_max_output_tokens": 1000,
        "general_max_ctx_len": 100_000,
        "limit_rag": 10,
        "use_websearch": use_websearch,
        "use_thinking": use_thinking,
        "summarize_history": False,
        "skip_memory": True,
        "doc_paged": False,
        "doc_summarized": False,
        "doc_rag": False,
        "doc_false_rag": False,
        "has_content": True,
        "all_tokens_counter": 0,
        "rag_method": None,
        "rag_documents_count": None,
        "rag_chunks_count": None,
        "rag_chunks_data": None,
        "id_to_formatted_map": None,
        "tool_web_search": None,
        "disclaimer_case": None,
        "disclaimer_text": None,
        "last_prompt": "pergunta de teste",
        "image_attachments": None,
    }


# ---------------------------------------------------------------------------
# get_reasoning_model_kwargs
# ---------------------------------------------------------------------------


class TestGetReasoningModelKwargs:
    def test_sem_thinking_retorna_dict_vazio(self):
        from sei_ia.services.llm_models.chat_workflow import (
            get_reasoning_model_kwargs,
        )

        assert get_reasoning_model_kwargs(_make_user_state(use_thinking=False)) == {}

    def test_com_thinking_ativa_responses_api_e_reasoning(self):
        from sei_ia.configs.settings_config import settings
        from sei_ia.services.llm_models.chat_workflow import (
            get_reasoning_model_kwargs,
        )

        kwargs = get_reasoning_model_kwargs(_make_user_state(use_thinking=True))

        assert kwargs["use_responses_api"] is True
        assert kwargs["reasoning"]["effort"] == settings.REASONING_EFFORT
        assert kwargs["reasoning"]["summary"] == settings.REASONING_SUMMARY

    def test_reasoning_effort_explicito_tem_prioridade_sobre_use_thinking(self):
        from sei_ia.services.llm_models.chat_workflow import (
            get_reasoning_model_kwargs,
        )

        kwargs = get_reasoning_model_kwargs(
            _make_user_state(use_thinking=False, reasoning_effort="high")
        )

        assert kwargs["use_responses_api"] is True
        assert kwargs["reasoning"]["effort"] == "high"

    def test_reasoning_effort_explicito_sobrescreve_default_do_use_thinking(self):
        from sei_ia.configs.settings_config import settings
        from sei_ia.services.llm_models.chat_workflow import (
            get_reasoning_model_kwargs,
        )

        kwargs = get_reasoning_model_kwargs(
            _make_user_state(use_thinking=True, reasoning_effort="none")
        )

        assert kwargs["reasoning"]["effort"] == "none"
        assert kwargs["reasoning"]["effort"] != settings.REASONING_EFFORT


# ---------------------------------------------------------------------------
# Extratores de delta dos chunks
# ---------------------------------------------------------------------------


class TestExtractDeltas:
    def test_content_str_legado(self):
        from sei_ia.services.llm_models.chat_workflow import (
            extract_content_delta,
            extract_reasoning_delta,
        )

        chunk = SimpleNamespace(content="Olá mundo")
        assert extract_content_delta(chunk) == "Olá mundo"
        assert extract_reasoning_delta(chunk) == ""

    def test_content_list_reasoning_blocks(self):
        from sei_ia.services.llm_models.chat_workflow import (
            extract_content_delta,
            extract_reasoning_delta,
        )

        chunk = SimpleNamespace(
            content=[
                {
                    "type": "reasoning",
                    "summary": [
                        {"type": "summary_text", "text": "analisando "},
                        {"type": "summary_text", "text": "agora"},
                    ],
                    "index": 0,
                },
            ]
        )
        assert extract_reasoning_delta(chunk) == "analisando agora"
        assert extract_content_delta(chunk) == ""

    def test_content_list_text_block(self):
        from sei_ia.services.llm_models.chat_workflow import (
            extract_content_delta,
            extract_reasoning_delta,
        )

        chunk = SimpleNamespace(
            content=[
                {"type": "text", "text": "resposta", "index": 1},
                {"type": "output_text", "text": " final"},
            ]
        )
        assert extract_content_delta(chunk) == "resposta final"
        assert extract_reasoning_delta(chunk) == ""

    def test_content_none_retorna_string_vazia(self):
        from sei_ia.services.llm_models.chat_workflow import (
            extract_content_delta,
            extract_reasoning_delta,
        )

        chunk = SimpleNamespace(content=None)
        assert extract_content_delta(chunk) == ""
        assert extract_reasoning_delta(chunk) == ""


# ---------------------------------------------------------------------------
# chat_gpt — orquestrador (thinking vs não-thinking)
# ---------------------------------------------------------------------------


class _StrChunk:
    def __init__(self, content: str) -> None:
        self.content = content


class _ListChunk:
    def __init__(self, content: list[dict[str, Any]]) -> None:
        self.content = content


def _make_astream_events(events: list[dict[str, Any]]):
    async def fake_astream_events(_payload, version, **_kwargs):  # noqa: ARG001
        for ev in events:
            yield ev

    return fake_astream_events


class TestChatGptOrchestration:
    @pytest.mark.asyncio
    async def test_nao_thinking_usa_chunk_str_e_nao_emite_reasoning(self):
        from sei_ia.services.llm_models import chat_workflow as cw

        events = [
            {"event": "on_chat_model_stream", "data": {"chunk": _StrChunk("Olá ")}},
            {"event": "on_chat_model_stream", "data": {"chunk": _StrChunk("mundo!")}},
        ]
        mock_agent = MagicMock()
        mock_agent.astream_events = _make_astream_events(events)

        chunks: list[Any] = []

        def writer(value: Any) -> None:
            chunks.append(value)

        mock_model = MagicMock()
        mock_model.model_name = "test-standard"
        with (
            patch.object(cw, "get_llm_model", return_value=mock_model),
            patch.object(cw, "create_react_agent", return_value=mock_agent),
        ):
            result = await cw.chat_gpt(
                _make_user_state(use_thinking=False), writer=writer
            )

        assert result["response"] == "Olá mundo!"
        assert "reasoning" not in result
        assert isinstance(result["n_tokens"], tuple)
        assert chunks == ["Olá ", "mundo!"]
        assert all(
            not (isinstance(c, str) and c.startswith("<reasoning>")) for c in chunks
        )

    @pytest.mark.asyncio
    async def test_thinking_usa_blocos_responses_api_e_emite_reasoning_e_content(self):
        from sei_ia.services.llm_models import chat_workflow as cw

        events = [
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": _ListChunk(
                        [
                            {
                                "type": "reasoning",
                                "summary": [
                                    {"type": "summary_text", "text": "analisando..."}
                                ],
                                "index": 0,
                            }
                        ]
                    )
                },
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": _ListChunk(
                        [{"type": "text", "text": "Resposta final", "index": 1}]
                    )
                },
            },
        ]
        mock_agent = MagicMock()
        mock_agent.astream_events = _make_astream_events(events)

        chunks: list[Any] = []

        def writer(value: Any) -> None:
            chunks.append(value)

        mock_model = MagicMock()
        mock_model.model_name = "test-standard-thinking"
        with (
            patch.object(cw, "get_llm_model", return_value=mock_model) as mock_get,
            patch.object(cw, "create_react_agent", return_value=mock_agent),
        ):
            result = await cw.chat_gpt(
                _make_user_state(use_thinking=True), writer=writer
            )

        assert result["response"] == "Resposta final"
        assert result["reasoning"] == "analisando..."
        assert isinstance(result["n_tokens"], tuple)
        # Writer recebeu o reasoning envolto na tag e o content cru.
        assert "<reasoning>analisando...</reasoning>" in chunks
        assert "Resposta final" in chunks

        # `get_llm_model` foi chamado com use_responses_api=True e reasoning={...}.
        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs.get("use_responses_api") is True
        assert "reasoning" in call_kwargs
        assert call_kwargs["reasoning"]["effort"]
        assert call_kwargs["reasoning"]["summary"]

    @pytest.mark.asyncio
    async def test_model_override_repassado_a_get_llm_model(self):
        from sei_ia.services.llm_models import chat_workflow as cw

        events = [
            {"event": "on_chat_model_stream", "data": {"chunk": _StrChunk("ok")}},
        ]
        mock_agent = MagicMock()
        mock_agent.astream_events = _make_astream_events(events)

        mock_model = MagicMock()
        mock_model.model_name = "openai/seiia-ds-gemini-pro"
        with (
            patch.object(cw, "get_llm_model", return_value=mock_model) as mock_get,
            patch.object(cw, "create_react_agent", return_value=mock_agent),
        ):
            await cw.chat_gpt(
                _make_user_state(model_override="openai/seiia-ds-gemini-pro"),
                writer=None,
            )

        assert (
            mock_get.call_args.kwargs["model_override"] == "openai/seiia-ds-gemini-pro"
        )

    @pytest.mark.asyncio
    async def test_upload_de_imagem_conta_tokens_so_do_texto(self):
        """Regressão: content multimodal (lista) em n_tokens não pode estourar.

        Com upload de imagem a última HumanMessage vira lista
        `[{"type":"text",...}, {"type":"image_url",...}]`; a contagem de
        tokens do prompt deve usar só as partes de texto (imagem conta 0),
        sem TypeError no tiktoken.
        """
        from pathlib import Path

        from sei_ia.services.counter import token_counter
        from sei_ia.services.llm_models import chat_workflow as cw

        png_path = (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "documents"
            / "sample.png"
        )
        attachment = SimpleNamespace(
            fs_path=str(png_path), filename="sample.png", mime="image/png"
        )
        user_state = _make_user_state(use_thinking=False)
        user_state["image_attachments"] = [attachment]

        events = [
            {"event": "on_chat_model_stream", "data": {"chunk": _StrChunk("ok")}},
        ]
        mock_agent = MagicMock()
        mock_agent.astream_events = _make_astream_events(events)

        mock_model = MagicMock()
        mock_model.model_name = "test-standard"
        with (
            patch.object(cw, "get_llm_model", return_value=mock_model),
            patch.object(cw, "create_react_agent", return_value=mock_agent),
        ):
            result = await cw.chat_gpt(user_state, writer=None)

        expected_prompt_tokens = token_counter("system de teste") + token_counter(
            "\n <context>pergunta de teste\n </context>"
        )
        assert result["response"] == "ok"
        assert result["n_tokens"][0] == expected_prompt_tokens


# ---------------------------------------------------------------------------
# chat_gpt — failover do reasoning
# ---------------------------------------------------------------------------


def _api_connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(
        message="boom", request=httpx.Request("POST", "http://proxy/responses")
    )


def _bad_request_error() -> openai.BadRequestError:
    request = httpx.Request("POST", "http://proxy/responses")
    return openai.BadRequestError(
        "conteúdo rejeitado",
        response=httpx.Response(400, request=request),
        body=None,
    )


def _flaky_astream_events(
    *,
    raise_on_call: set[int],
    exc_factory,
    events: list[dict[str, Any]],
    events_before_raise: list[dict[str, Any]] | None = None,
):
    """astream_events falso e com estado: levanta `exc_factory()` nas chamadas
    listadas em `raise_on_call` (1-indexado), emitindo antes os
    `events_before_raise`; nas demais chamadas emite `events`."""
    calls = {"n": 0}

    async def fake(_payload, version, **_kwargs):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] in raise_on_call:
            for ev in events_before_raise or []:
                yield ev
            raise exc_factory()
        for ev in events:
            yield ev

    fake.calls = calls
    return fake


class TestChatGptReasoningFailover:
    @pytest.mark.asyncio
    async def test_erro_do_provedor_antes_do_1o_byte_refaz_com_effort_none(self):
        from sei_ia.services.llm_models import chat_workflow as cw

        ok_events = [
            {
                "event": "on_chat_model_stream",
                "data": {"chunk": _StrChunk("resposta ok")},
            },
        ]
        mock_agent = MagicMock()
        mock_agent.astream_events = _flaky_astream_events(
            raise_on_call={1}, exc_factory=_api_connection_error, events=ok_events
        )

        chunks: list[Any] = []
        user_state = _make_user_state(use_thinking=True)
        mock_model = MagicMock()
        mock_model.model_name = "test-standard"
        with (
            patch.object(cw, "get_llm_model", return_value=mock_model) as mock_get,
            patch.object(cw, "create_react_agent", return_value=mock_agent),
        ):
            result = await cw.chat_gpt(user_state, writer=chunks.append)

        assert result["response"] == "resposta ok"
        assert user_state["reasoning_failover"] is True
        assert mock_agent.astream_events.calls["n"] == 2
        # 2 builds do modelo: 1º com o effort do use_thinking, 2º forçando "none".
        assert mock_get.call_count == 2
        assert mock_get.call_args_list[0].kwargs["reasoning"]["effort"] != "none"
        assert mock_get.call_args_list[1].kwargs["reasoning"]["effort"] == "none"

    @pytest.mark.asyncio
    async def test_sem_reasoning_ligado_nao_refaz_e_propaga(self):
        from sei_ia.services.llm_models import chat_workflow as cw

        mock_agent = MagicMock()
        mock_agent.astream_events = _flaky_astream_events(
            raise_on_call={1}, exc_factory=_api_connection_error, events=[]
        )
        mock_model = MagicMock()
        mock_model.model_name = "test-standard"
        with (
            patch.object(cw, "get_llm_model", return_value=mock_model) as mock_get,
            patch.object(cw, "create_react_agent", return_value=mock_agent),
            pytest.raises(openai.APIConnectionError),
        ):
            await cw.chat_gpt(_make_user_state(use_thinking=False), writer=None)

        assert mock_agent.astream_events.calls["n"] == 1
        assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_erro_apos_1o_byte_nao_refaz_e_propaga(self):
        from sei_ia.services.llm_models import chat_workflow as cw

        mock_agent = MagicMock()
        mock_agent.astream_events = _flaky_astream_events(
            raise_on_call={1},
            exc_factory=_api_connection_error,
            events=[],
            events_before_raise=[
                {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": _StrChunk("parcial ")},
                }
            ],
        )
        chunks: list[Any] = []
        mock_model = MagicMock()
        mock_model.model_name = "test-standard"
        with (
            patch.object(cw, "get_llm_model", return_value=mock_model),
            patch.object(cw, "create_react_agent", return_value=mock_agent),
            pytest.raises(openai.APIConnectionError),
        ):
            await cw.chat_gpt(_make_user_state(use_thinking=True), writer=chunks.append)

        assert mock_agent.astream_events.calls["n"] == 1
        assert chunks == ["parcial "]

    @pytest.mark.asyncio
    async def test_erro_4xx_deterministico_nao_refaz_e_propaga(self):
        from sei_ia.services.llm_models import chat_workflow as cw

        mock_agent = MagicMock()
        mock_agent.astream_events = _flaky_astream_events(
            raise_on_call={1}, exc_factory=_bad_request_error, events=[]
        )
        mock_model = MagicMock()
        mock_model.model_name = "test-standard"
        with (
            patch.object(cw, "get_llm_model", return_value=mock_model) as mock_get,
            patch.object(cw, "create_react_agent", return_value=mock_agent),
            pytest.raises(openai.BadRequestError),
        ):
            await cw.chat_gpt(_make_user_state(use_thinking=True), writer=None)

        assert mock_agent.astream_events.calls["n"] == 1
        assert mock_get.call_count == 1
