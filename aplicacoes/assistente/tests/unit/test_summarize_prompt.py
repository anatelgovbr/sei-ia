"""Testes unitários para sei_ia/agents/summarize/prompt_with_doc_summarization.py."""

from unittest.mock import MagicMock, patch

import pytest

from sei_ia.agents.summarize.prompt_with_doc_summarization import (
    make_prompt_with_doc_summarization,
)
from sei_ia.data.pydantic_models import (
    ItemDocumentRequest,
    ItemRequestIdProcedimento,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(content="Conteudo do documento.", metadata="Meta", doc_tokens=100):
    return ItemDocumentRequest(
        id_documento="doc_001",
        download_ext=False,
        pag_doc_init=0,
        pag_doc_end=0,
        id_documento_formatado="DOC-001",
        content=content,
        metadata=metadata,
        doc_tokens=doc_tokens,
        doc_paged=False,
    )


def _make_proc(docs):
    return ItemRequestIdProcedimento(
        id_procedimento="proc_001",
        id_documentos=docs,
        metadata="Meta proc",
    )


def _make_state(
    all_tokens_counter=1000,
    general_max_ctx_len=128000,
    docs=None,
    summarize_multiplier=2.0,  # noqa: ARG001
):
    if docs is None:
        docs = [_make_doc()]

    return {
        "id_request": "req_001",
        "id_usuario": "usr_001",
        "ip": "127.0.0.1",
        "endpoint_name": "/test",
        "id_topico": None,
        "id_procedimentos": [_make_proc(docs)],
        "all_procs": ["proc_001"],
        "all_documents": ["doc_001"],
        "user_request": "Resuma este documento.",
        "system_prompt": "Assistente.",
        "original_request_body": "{}",
        "intent": "resumo",
        "model_type": "standard",
        "model_name": "gpt-4",
        "temperature": 0.01,
        "general_max_output_tokens": 4000,
        "general_max_ctx_len": general_max_ctx_len,
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
        "all_tokens_counter": all_tokens_counter,
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


# ---------------------------------------------------------------------------
# Testes: caminho direto (tokens < general_max_ctx_len)
# ---------------------------------------------------------------------------


class TestMakePromptCaminhoDirecto:
    """Quando all_tokens_counter < general_max_ctx_len — sem sumarização."""

    def test_define_last_prompt_com_conteudo_doc(self):
        state = _make_state(all_tokens_counter=1000, general_max_ctx_len=128000)
        with patch(
            "sei_ia.agents.summarize.prompt_with_doc_summarization.settings"
        ) as mock_settings:
            mock_settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER = 4.0
            result = make_prompt_with_doc_summarization(state)

        assert result["last_prompt"] != ""
        assert "Conteudo do documento." in result["last_prompt"]

    def test_nao_marca_doc_summarized_verdadeiro_no_caminho_direto(self):
        """No caminho direto, doc_summarized é definido como True ao final (linha 86)."""
        state = _make_state(all_tokens_counter=100, general_max_ctx_len=128000)
        with patch(
            "sei_ia.agents.summarize.prompt_with_doc_summarization.settings"
        ) as mock_settings:
            mock_settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER = 4.0
            result = make_prompt_with_doc_summarization(state)

        # O código sempre define doc_summarized = True na linha 86
        assert result["doc_summarized"] is True

    def test_retorna_userstate(self):
        state = _make_state(all_tokens_counter=500, general_max_ctx_len=128000)
        with patch(
            "sei_ia.agents.summarize.prompt_with_doc_summarization.settings"
        ) as mock_settings:
            mock_settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER = 4.0
            result = make_prompt_with_doc_summarization(state)

        assert isinstance(result, dict)
        assert "last_prompt" in result

    def test_prompt_contem_user_request(self):
        state = _make_state(all_tokens_counter=500, general_max_ctx_len=128000)
        state["user_request"] = "Qual o prazo?"
        with patch(
            "sei_ia.agents.summarize.prompt_with_doc_summarization.settings"
        ) as mock_settings:
            mock_settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER = 4.0
            result = make_prompt_with_doc_summarization(state)

        assert "Qual o prazo?" in result["last_prompt"]

    def test_metadata_incluida_no_conteudo(self):
        doc = _make_doc(content="Texto.", metadata="MetaDados especiais")
        state = _make_state(
            docs=[doc], all_tokens_counter=100, general_max_ctx_len=128000
        )
        with patch(
            "sei_ia.agents.summarize.prompt_with_doc_summarization.settings"
        ) as mock_settings:
            mock_settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER = 4.0
            result = make_prompt_with_doc_summarization(state)

        assert "MetaDados especiais" in result["last_prompt"]

    def test_doc_sem_content_ignorado(self):
        doc_vazio = _make_doc(content=None)
        doc_com_conteudo = _make_doc(content="Texto real.")
        state = _make_state(
            docs=[doc_vazio, doc_com_conteudo],
            all_tokens_counter=100,
            general_max_ctx_len=128000,
        )
        with patch(
            "sei_ia.agents.summarize.prompt_with_doc_summarization.settings"
        ) as mock_settings:
            mock_settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER = 4.0
            result = make_prompt_with_doc_summarization(state)

        assert "Texto real." in result["last_prompt"]

    def test_doc_sem_metadata_nao_adiciona_none(self):
        doc = _make_doc(content="Texto.", metadata=None)
        state = _make_state(
            docs=[doc], all_tokens_counter=100, general_max_ctx_len=128000
        )
        with patch(
            "sei_ia.agents.summarize.prompt_with_doc_summarization.settings"
        ) as mock_settings:
            mock_settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER = 4.0
            result = make_prompt_with_doc_summarization(state)

        assert "None" not in result["last_prompt"]


# ---------------------------------------------------------------------------
# Testes: caminho de sumarização (general_max_ctx_len <= tokens < limit_summarize)
# ---------------------------------------------------------------------------


class TestMakePromptCaminhoSumarizacao:
    """Quando general_max_ctx_len <= all_tokens_counter < limit_summarize — com sumarização."""

    def _mock_summarize_chain(self, summary_text="Resumo do documento."):
        from langchain_core.documents import Document  # noqa: F401

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = {
            "collapsed_summaries": summary_text,
        }
        return mock_chain

    def test_sumarizacao_executada_quando_tokens_excedem_ctx(self):
        # tokens > general_max_ctx_len mas < limit_summarize
        state = _make_state(all_tokens_counter=200000, general_max_ctx_len=100000)
        mock_chain = self._mock_summarize_chain("Resumo gerado.")

        with (
            patch(
                "sei_ia.agents.summarize.prompt_with_doc_summarization.settings"
            ) as mock_settings,
            patch(
                "sei_ia.agents.summarize.prompt_with_doc_summarization.split_text_summarize"
            ) as mock_split,
            patch(
                "sei_ia.agents.summarize.prompt_with_doc_summarization.select_summarize_model",
                return_value=mock_chain,
            ),
        ):
            mock_settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER = 4.0
            from langchain_core.documents import Document

            mock_split.return_value = ([Document(page_content="chunk1")], "small")

            result = make_prompt_with_doc_summarization(state)

        assert result["doc_summarized"] is True
        assert "Resumo gerado." in result["last_prompt"]

    def test_lanca_http_408_em_rate_limit_error(self):
        from openai import RateLimitError  # noqa: I001
        from sei_ia.services.exceptions.http_exceptions import HTTPException408

        state = _make_state(all_tokens_counter=200000, general_max_ctx_len=100000)

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        mock_resp.request = MagicMock()
        rate_err = RateLimitError("rate limit", response=mock_resp, body={})

        mock_chain = MagicMock()
        mock_chain.invoke.side_effect = rate_err

        with (
            patch(
                "sei_ia.agents.summarize.prompt_with_doc_summarization.settings"
            ) as mock_settings,
            patch(
                "sei_ia.agents.summarize.prompt_with_doc_summarization.split_text_summarize"
            ) as mock_split,
            patch(
                "sei_ia.agents.summarize.prompt_with_doc_summarization.select_summarize_model",
                return_value=mock_chain,
            ),
        ):
            mock_settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER = 4.0
            from langchain_core.documents import Document

            mock_split.return_value = ([Document(page_content="chunk1")], "small")

            with pytest.raises(HTTPException408):
                make_prompt_with_doc_summarization(state)

    def test_lanca_http_408_em_api_timeout_error(self):
        from openai import APITimeoutError  # noqa: I001
        from sei_ia.services.exceptions.http_exceptions import HTTPException408

        state = _make_state(all_tokens_counter=200000, general_max_ctx_len=100000)

        mock_chain = MagicMock()
        mock_chain.invoke.side_effect = APITimeoutError("timeout")

        with (
            patch(
                "sei_ia.agents.summarize.prompt_with_doc_summarization.settings"
            ) as mock_settings,
            patch(
                "sei_ia.agents.summarize.prompt_with_doc_summarization.split_text_summarize"
            ) as mock_split,
            patch(
                "sei_ia.agents.summarize.prompt_with_doc_summarization.select_summarize_model",
                return_value=mock_chain,
            ),
        ):
            mock_settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER = 4.0
            from langchain_core.documents import Document

            mock_split.return_value = ([Document(page_content="chunk1")], "small")

            with pytest.raises(HTTPException408):
                make_prompt_with_doc_summarization(state)


# ---------------------------------------------------------------------------
# Testes: caminho de erro (tokens > limit_summarize)
# ---------------------------------------------------------------------------


class TestMakePromptCaminhoErro:
    """Quando all_tokens_counter >= limit_summarize — lança HTTPException413."""

    def test_lanca_http_413_quando_tokens_excedem_limite_sumarizacao(self):
        from sei_ia.services.exceptions.http_exceptions import HTTPException413

        # all_tokens_counter > limit_summarize (100000 * 2.0 = 200000)
        state = _make_state(all_tokens_counter=300000, general_max_ctx_len=100000)

        with patch(
            "sei_ia.agents.summarize.prompt_with_doc_summarization.settings"
        ) as mock_settings:
            mock_settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER = 2.0
            with pytest.raises(HTTPException413):
                make_prompt_with_doc_summarization(state)

    def test_mensagem_erro_413_contem_contador_tokens(self):
        from sei_ia.services.exceptions.http_exceptions import HTTPException413

        state = _make_state(all_tokens_counter=500000, general_max_ctx_len=100000)
        state["all_tokens_counter"] = 500000

        with patch(
            "sei_ia.agents.summarize.prompt_with_doc_summarization.settings"
        ) as mock_settings:
            mock_settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER = 2.0
            with pytest.raises(HTTPException413) as exc_info:
                make_prompt_with_doc_summarization(state)

        assert "500000" in str(exc_info.value.detail)
