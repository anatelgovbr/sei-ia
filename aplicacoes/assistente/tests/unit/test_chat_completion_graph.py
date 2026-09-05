"""Testes unitários para sei_ia/agents/chat_completion_graph.py."""

import asyncio  # noqa: I001
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sei_ia.agents.chat_completion_graph import (
    detect_document_condition,
    handle_question,
    handle_response,
    merge_web_search_node,
    route_condition,
    web_search_node,
    websearch_condition,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(**overrides):
    """Cria um UserState mínimo para os testes."""
    base = {
        "id_request": "req_001",
        "id_usuario": "usr_001",
        "ip": "127.0.0.1",
        "endpoint_name": "/test",
        "id_topico": None,
        "id_procedimentos": [],
        "all_procs": [],
        "all_documents": [],
        "user_request": "Qual o assunto?",
        "system_prompt": "Você é um assistente.",
        "original_request_body": "{}",
        "intent": "pergunta",
        "agent_tag": "principal",
        "model_override": None,
        "model_name": "gpt-4",
        "temperature": 0.01,
        "general_max_output_tokens": 4000,
        "general_max_ctx_len": 128000,
        "limit_rag": 64000,
        "limit_false_rag": 12000,
        "use_websearch": False,
        "use_thinking": False,
        "summarize_history": False,
        "skip_memory": False,
        "doc_paged": False,
        "doc_summarized": False,
        "doc_rag": False,
        "doc_false_rag": False,
        "has_content": True,
        "all_tokens_counter": 1000,
        "rag_method": None,
        "rag_documents_count": None,
        "rag_chunks_count": None,
        "rag_chunks_data": None,
        "id_to_formatted_map": None,
        "tool_web_search": None,
        "disclaimer_case": None,
        "disclaimer_text": None,
        "last_prompt": "",
        "response": {},
        "web_content": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# websearch_condition
# ---------------------------------------------------------------------------


class TestWebsearchCondition:
    def test_retorna_use_web_search_quando_habilitado(self):
        state = _make_state(use_websearch=True)
        assert websearch_condition(state) == "use_web_search"

    def test_retorna_skip_web_search_quando_desabilitado(self):
        state = _make_state(use_websearch=False)
        assert websearch_condition(state) == "skip_web_search"

    def test_retorna_skip_quando_ausente(self):
        state = _make_state()
        state.pop("use_websearch", None)
        assert websearch_condition(state) == "skip_web_search"

    def test_retorna_skip_quando_none(self):
        state = _make_state(use_websearch=None)
        assert websearch_condition(state) == "skip_web_search"


# ---------------------------------------------------------------------------
# route_condition
# ---------------------------------------------------------------------------


class TestRouteCondition:
    def test_reescrever_retorna_grammar(self):
        state = _make_state(intent="reescrever")
        assert route_condition(state) == "grammar"

    def test_pergunta_retorna_question(self):
        state = _make_state(intent="pergunta")
        assert route_condition(state) == "question"

    def test_multi_pergunta_retorna_question(self):
        state = _make_state(intent="multi_pergunta")
        assert route_condition(state) == "question"

    def test_analise_retorna_question(self):
        state = _make_state(intent="analise")
        assert route_condition(state) == "question"

    def test_resumo_retorna_summarize(self):
        state = _make_state(intent="resumo")
        assert route_condition(state) == "summarize"

    def test_escrever_retorna_summarize(self):
        state = _make_state(intent="escrever")
        assert route_condition(state) == "summarize"

    def test_outras_retorna_summarize(self):
        state = _make_state(intent="outras")
        assert route_condition(state) == "summarize"

    def test_conversar_retorna_summarize(self):
        state = _make_state(intent="conversar")
        assert route_condition(state) == "summarize"


# ---------------------------------------------------------------------------
# detect_document_condition
# ---------------------------------------------------------------------------


class TestDetectDocumentCondition:
    def test_com_documentos_retorna_refer_docs(self):
        state = _make_state(all_documents=["doc_001", "doc_002"])
        assert detect_document_condition(state) == "refer_docs"

    def test_sem_documentos_retorna_dont_refer_docs(self):
        state = _make_state(all_documents=[])
        assert detect_document_condition(state) == "dont_refer_docs"

    def test_um_documento_retorna_refer_docs(self):
        state = _make_state(all_documents=["doc_001"])
        assert detect_document_condition(state) == "refer_docs"


# ---------------------------------------------------------------------------
# handle_question
# ---------------------------------------------------------------------------


class TestHandleQuestion:
    def test_chama_process_question_intent_e_retorna_state(self):
        state = _make_state()
        expected_state = _make_state(last_prompt="prompt gerado")

        with patch(
            "sei_ia.agents.chat_completion_graph.process_question_intent",
            new_callable=AsyncMock,
            return_value=expected_state,
        ) as mock_pq:
            result = asyncio.run(handle_question(state))

        mock_pq.assert_called_once_with(state)
        assert result == expected_state

    def test_propaga_http_exception_204(self):
        from sei_ia.services.exceptions.http_exceptions import HTTPException204

        with patch(  # noqa: SIM117
            "sei_ia.agents.chat_completion_graph.process_question_intent",
            new_callable=AsyncMock,
            side_effect=HTTPException204,
        ):
            with pytest.raises(HTTPException204):
                asyncio.run(handle_question(_make_state()))

    def test_propaga_http_exception_404(self):
        from sei_ia.services.exceptions.http_exceptions import HTTPException404

        with patch(  # noqa: SIM117
            "sei_ia.agents.chat_completion_graph.process_question_intent",
            new_callable=AsyncMock,
            side_effect=HTTPException404,
        ):
            with pytest.raises(HTTPException404):
                asyncio.run(handle_question(_make_state()))

    def test_propaga_http_exception_408(self):
        from sei_ia.services.exceptions.http_exceptions import HTTPException408

        with patch(  # noqa: SIM117
            "sei_ia.agents.chat_completion_graph.process_question_intent",
            new_callable=AsyncMock,
            side_effect=HTTPException408,
        ):
            with pytest.raises(HTTPException408):
                asyncio.run(handle_question(_make_state()))


# ---------------------------------------------------------------------------
# web_search_node
# ---------------------------------------------------------------------------


class TestWebSearchNode:
    def _mock_agent_arun(self, return_value):
        mock_agent = MagicMock()
        mock_agent._arun = AsyncMock(return_value=return_value)
        return mock_agent

    def test_retorna_resultados_quando_agente_tem_resultados(self):
        results = [
            {
                "content": "Resultado 1",
                "query": "busca",
                "references": [],
                "idx": 1,
                "node": "web_search_node",
            },
        ]
        mock_agent_instance = MagicMock()
        mock_agent_instance._arun = AsyncMock(return_value=results)

        state = _make_state(user_request="O que é isso?", agent_tag="principal")

        with (
            patch(
                "sei_ia.agents.chat_completion_graph.DeepResearchAgent",
                return_value=mock_agent_instance,
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_llm_model",
                return_value=MagicMock(),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
            patch("sei_ia.agents.chat_completion_graph.settings") as mock_settings,
        ):
            mock_settings.SEARX_BASE_URL = "http://searx"
            mock_settings.FASTCRW_BASE_URL = "http://infra-fastcrw:3001"

            async def _run():
                await web_search_node(state)
                return await merge_web_search_node(state)

            result = asyncio.run(_run())

        assert "tool_web_search" in result
        assert len(result["tool_web_search"]) == 1
        assert result["tool_web_search"][0]["content"] == "Resultado 1"

    def test_fallback_quando_agente_retorna_lista_vazia(self):
        mock_agent_instance = MagicMock()
        mock_agent_instance._arun = AsyncMock(return_value=[])

        state = _make_state(user_request="O que é isso?", agent_tag="principal")

        with (
            patch(
                "sei_ia.agents.chat_completion_graph.DeepResearchAgent",
                return_value=mock_agent_instance,
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_llm_model",
                return_value=MagicMock(),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
            patch("sei_ia.agents.chat_completion_graph.settings") as mock_settings,
        ):
            mock_settings.SEARX_BASE_URL = "http://searx"
            mock_settings.FASTCRW_BASE_URL = "http://infra-fastcrw:3001"

            async def _run():
                await web_search_node(state)
                return await merge_web_search_node(state)

            result = asyncio.run(_run())

        assert (
            result["tool_web_search"][0]["content"]
            == "Não foi necessário buscar na web."
        )

    def test_stream_writer_chamado_quando_disponivel(self):
        results = [{"content": "X", "query": "q", "references": []}]
        mock_agent_instance = MagicMock()
        mock_agent_instance._arun = AsyncMock(return_value=results)

        mock_writer = MagicMock()

        state = _make_state(user_request="Q?", agent_tag="principal")

        with (
            patch(
                "sei_ia.agents.chat_completion_graph.DeepResearchAgent",
                return_value=mock_agent_instance,
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_llm_model",
                return_value=MagicMock(),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                return_value=mock_writer,
            ),
            patch("sei_ia.agents.chat_completion_graph.settings") as mock_settings,
        ):
            mock_settings.SEARX_BASE_URL = "http://searx"
            mock_settings.FASTCRW_BASE_URL = "http://infra-fastcrw:3001"

            asyncio.run(web_search_node(state))

        mock_writer.assert_any_call({"_status": "Pesquisando na Internet"})

    def test_resultados_recebem_idx_e_node(self):
        results = [
            {"content": "A", "query": "q", "references": []},
            {"content": "B", "query": "q2", "references": []},
        ]
        mock_agent_instance = MagicMock()
        mock_agent_instance._arun = AsyncMock(return_value=results)

        state = _make_state(user_request="Pergunta?", agent_tag="principal")

        with (
            patch(
                "sei_ia.agents.chat_completion_graph.DeepResearchAgent",
                return_value=mock_agent_instance,
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_llm_model",
                return_value=MagicMock(),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
            patch("sei_ia.agents.chat_completion_graph.settings") as mock_settings,
        ):
            mock_settings.SEARX_BASE_URL = "http://searx"
            mock_settings.FASTCRW_BASE_URL = "http://infra-fastcrw:3001"

            async def _run():
                await web_search_node(state)
                return await merge_web_search_node(state)

            result = asyncio.run(_run())

        for i, item in enumerate(result["tool_web_search"], 1):
            assert item["idx"] == i
            assert item["node"] == "web_search_node"


# ---------------------------------------------------------------------------
# handle_response
# ---------------------------------------------------------------------------


class TestHandleResponse:
    def _mock_chat_gpt(self, return_value):
        return AsyncMock(return_value=return_value)

    def test_resposta_simples_sem_disclaimer(self):
        state = _make_state(disclaimer_text=None, doc_rag=False)
        chat_response = {"response": "Resposta do LLM", "tokens": 100}

        with (
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                return_value=chat_response,
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
        ):
            result = asyncio.run(handle_response(state))

        assert result["response"] == chat_response

    def test_disclaimer_adicionado_no_inicio_da_resposta(self):
        state = _make_state(disclaimer_text="⚠️ Aviso importante. ", doc_rag=False)
        chat_response = {"response": "Conteúdo da resposta", "tokens": 50}

        with (
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                return_value=chat_response,
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
        ):
            result = asyncio.run(handle_response(state))

        assert result["response"]["response"].startswith("⚠️")

    def test_disclaimer_nao_duplicado_quando_ja_comeca_com_aviso(self):
        state = _make_state(disclaimer_text="⚠️ Aviso. ", doc_rag=False)
        chat_response = {"response": "⚠️ Aviso. Resposta já com aviso", "tokens": 50}

        with (
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                return_value=chat_response,
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
        ):
            result = asyncio.run(handle_response(state))

        # Não duplica o aviso
        assert result["response"]["response"].count("⚠️") == 1

    def test_timeout_lanca_http_exception_408(self):
        import openai  # noqa: I001
        from sei_ia.services.exceptions.http_exceptions import HTTPException408

        state = _make_state()

        with (  # noqa: SIM117
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                side_effect=openai.APITimeoutError("timeout"),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
        ):
            with pytest.raises(HTTPException408):
                asyncio.run(handle_response(state))

    def test_rate_limit_lanca_http_exception_429(self):
        import openai  # noqa: I001
        from sei_ia.services.exceptions.http_exceptions import HTTPException429

        state = _make_state()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}

        with (  # noqa: SIM117
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                side_effect=openai.RateLimitError(
                    "rate limit", response=mock_resp, body={}
                ),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
        ):
            with pytest.raises(HTTPException429):
                asyncio.run(handle_response(state))

    def test_bad_request_context_length_lanca_http_exception_413(self):
        import openai  # noqa: I001
        from sei_ia.services.exceptions.http_exceptions import HTTPException413

        state = _make_state(all_tokens_counter=999999)
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.headers = {}
        mock_resp.json.return_value = {"error": {"code": "context_length_exceeded"}}

        with (  # noqa: SIM117
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                side_effect=openai.BadRequestError(
                    "bad request", response=mock_resp, body={}
                ),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
        ):
            with pytest.raises(HTTPException413):
                asyncio.run(handle_response(state))

    def test_conteudo_responsavel_ai_policy_violation_lanca_http_403(self):
        import openai  # noqa: I001
        from sei_ia.services.exceptions.http_exceptions import HTTPException403

        state = _make_state()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.headers = {}
        mock_resp.json.return_value = {
            "error": {
                "code": "content_filter",
                "innererror": {"code": "ResponsibleAIPolicyViolation"},
            }
        }

        with (  # noqa: SIM117
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                side_effect=openai.BadRequestError(
                    "content filter", response=mock_resp, body={}
                ),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
        ):
            with pytest.raises(HTTPException403):
                asyncio.run(handle_response(state))

    def test_erro_generico_com_status_code_lanca_http_exception(self):
        from fastapi import HTTPException

        state = _make_state()

        class CustomError(Exception):
            status_code = 422
            detail = "Erro de validação"

        with (  # noqa: SIM117
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                side_effect=CustomError(),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(handle_response(state))
        assert exc_info.value.status_code == 422

    def test_erro_desconhecido_lanca_http_500(self):
        from sei_ia.services.exceptions.http_exceptions import HTTPException500

        state = _make_state()

        with (  # noqa: SIM117
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                side_effect=RuntimeError("erro inesperado"),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
        ):
            with pytest.raises(HTTPException500):
                asyncio.run(handle_response(state))

    def test_resposta_com_marcador_doc_processa_sources(self):
        state = _make_state(doc_rag=False)
        chat_response = {"response": "<doc_001>referência</doc_001>", "tokens": 50}
        processed = {"response": "referência processada", "tokens": 50}

        with (
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                return_value=chat_response,
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.transform_response_sources_enhanced",
                return_value=processed,
            ),
        ):
            result = asyncio.run(handle_response(state))

        assert result["response"] == processed

    def test_resposta_com_marcador_web_processa_sources(self):
        state = _make_state(doc_rag=False)
        chat_response = {"response": "<web_1>conteúdo web</web_1>", "tokens": 50}
        processed = {"response": "conteúdo processado", "tokens": 50}

        with (
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                return_value=chat_response,
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.transform_response_sources_enhanced",
                return_value=processed,
            ),
        ):
            result = asyncio.run(handle_response(state))

        assert result["response"] == processed

    def test_doc_rag_true_processa_sources(self):
        state = _make_state(doc_rag=True)
        chat_response = {"response": "Resposta sem marcador", "tokens": 50}
        processed = {"response": "com fontes", "tokens": 50}

        with (
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                return_value=chat_response,
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.transform_response_sources_enhanced",
                return_value=processed,
            ),
        ):
            result = asyncio.run(handle_response(state))

        assert result["response"] == processed

    def test_read_timeout_lanca_http_exception_408(self):
        from httpx._exceptions import ReadTimeout  # noqa: I001
        from sei_ia.services.exceptions.http_exceptions import HTTPException408

        state = _make_state()

        with (  # noqa: SIM117
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                side_effect=ReadTimeout("timeout"),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
        ):
            with pytest.raises(HTTPException408):
                asyncio.run(handle_response(state))

    def test_remote_protocol_error_lanca_http_500(self):
        import httpx  # noqa: I001
        from sei_ia.services.exceptions.http_exceptions import HTTPException500

        state = _make_state()

        with (  # noqa: SIM117
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                side_effect=httpx.RemoteProtocolError("protocol error"),
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                side_effect=Exception("no writer"),
            ),
        ):
            with pytest.raises(HTTPException500):
                asyncio.run(handle_response(state))

    def test_stream_writer_envia_disclaimer_antes_da_resposta(self):
        state = _make_state(disclaimer_text="⚠️ Aviso. ")
        chat_response = {"response": "Resposta", "tokens": 10}
        mock_writer = MagicMock()

        with (
            patch(
                "sei_ia.agents.chat_completion_graph.chat_gpt",
                new_callable=AsyncMock,
                return_value=chat_response,
            ),
            patch(
                "sei_ia.agents.chat_completion_graph.get_stream_writer",
                return_value=mock_writer,
            ),
        ):
            asyncio.run(handle_response(state))

        mock_writer.assert_any_call("⚠️ Aviso. ")


# ---------------------------------------------------------------------------
# build_chat_completion_graph
# ---------------------------------------------------------------------------


class TestBuildChatCompletionGraph:
    def test_retorna_compiled_state_graph(self):
        from langgraph.graph.state import CompiledStateGraph  # noqa: I001
        from sei_ia.agents.chat_completion_graph import build_chat_completion_graph

        result = asyncio.run(build_chat_completion_graph())

        assert isinstance(result, CompiledStateGraph)
