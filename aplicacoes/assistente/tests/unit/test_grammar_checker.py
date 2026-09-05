"""Testes unitários para sei_ia/agents/grammar_checker.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sei_ia.agents.grammar_checker import (
    get_documents,
    make_prompt_with_doc_grammar_correction,
)
from sei_ia.data.pydantic_models import ItemDocumentRequest, ItemRequestIdProcedimento
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException204,
    HTTPException404,
    HTTPException409,
    HTTPException411DocumentTimeout,
    HTTPException412SeiApiTimeout,
    HTTPException415,
    HTTPException500,
)


def _make_doc(
    id_documento="doc001",
    id_documento_formatado="001",
    content="conteúdo do documento",
):
    return ItemDocumentRequest(
        id_documento=id_documento,
        id_documento_formatado=id_documento_formatado,
        content=content,
    )


def _make_proc(
    id_procedimento="123456", metadata="Número do Processo: 123456", docs=None
):
    return ItemRequestIdProcedimento(
        id_procedimento=id_procedimento,
        id_documentos=docs or [_make_doc()],
        metadata=metadata,
    )


def _make_state(procs=None):
    return {
        "id_procedimentos": procs if procs is not None else [_make_proc()],
        "user_request": "Corrija o texto",
    }


# ---------------------------------------------------------------------------
# make_prompt_with_doc_grammar_correction
# ---------------------------------------------------------------------------


class TestMakePromptWithDocGrammarCorrection:
    def test_retorna_user_state_com_last_prompt(self):
        result = make_prompt_with_doc_grammar_correction(_make_state())
        assert "last_prompt" in result
        assert isinstance(result["last_prompt"], str)

    def test_prompt_contem_id_documento_formatado(self):
        doc = _make_doc(id_documento_formatado="DOC-42", content="texto do doc")
        state = _make_state(procs=[_make_proc(docs=[doc])])
        result = make_prompt_with_doc_grammar_correction(state)
        assert "DOC-42" in result["last_prompt"]

    def test_prompt_contem_protocolo_extraido_do_metadata(self):
        proc = _make_proc(metadata="Número do Processo: 98765-X")
        result = make_prompt_with_doc_grammar_correction(_make_state(procs=[proc]))
        assert "98765-X" in result["last_prompt"]

    def test_metadata_vazio_nao_quebra(self):
        proc = _make_proc(metadata="")
        result = make_prompt_with_doc_grammar_correction(_make_state(procs=[proc]))
        assert "last_prompt" in result

    def test_metadata_sem_numero_processo_nao_quebra(self):
        proc = _make_proc(metadata="sem informação de processo")
        result = make_prompt_with_doc_grammar_correction(_make_state(procs=[proc]))
        assert "last_prompt" in result

    def test_procedimentos_vazios_gera_prompt(self):
        result = make_prompt_with_doc_grammar_correction(_make_state(procs=[]))
        assert "last_prompt" in result

    def test_multiplos_docs_aparecem_no_prompt(self):
        docs = [
            _make_doc("d1", "D1", "conteúdo 1"),
            _make_doc("d2", "D2", "conteúdo 2"),
        ]
        state = _make_state(procs=[_make_proc(docs=docs)])
        result = make_prompt_with_doc_grammar_correction(state)
        assert "D1" in result["last_prompt"]
        assert "D2" in result["last_prompt"]

    def test_conteudo_documento_aparece_no_prompt(self):
        doc = _make_doc(content="conteúdo específico do documento")
        state = _make_state(procs=[_make_proc(docs=[doc])])
        result = make_prompt_with_doc_grammar_correction(state)
        assert "conteúdo específico do documento" in result["last_prompt"]


# ---------------------------------------------------------------------------
# get_documents
# ---------------------------------------------------------------------------


class TestGetDocuments:
    def _request(self, doc_ids=None):
        mock = MagicMock()
        mock.all_documents_allowed.return_value = (
            doc_ids if doc_ids is not None else ["doc1"]
        )
        return mock

    def test_retorna_dicionario_com_documento(self):
        with patch(
            "sei_ia.agents.grammar_checker.get_doc_from_id",
            new=AsyncMock(return_value=("conteúdo", "doc_fmt_1")),
        ):
            result = asyncio.run(get_documents(self._request(["doc1"]), docs_paged=[]))
        assert result == {"doc_fmt_1": "conteúdo"}

    def test_sem_documentos_retorna_dict_vazio(self):
        result = asyncio.run(get_documents(self._request([]), docs_paged=[]))
        assert result == {}

    def test_multiplos_documentos_retornados(self):
        call_count = {"n": 0}

        async def fake_get_doc(id_doc, docs_paged):  # noqa: ARG001
            call_count["n"] += 1
            return (f"conteúdo_{call_count['n']}", f"fmt_{call_count['n']}")

        with patch(
            "sei_ia.agents.grammar_checker.get_doc_from_id", side_effect=fake_get_doc
        ):
            result = asyncio.run(
                get_documents(self._request(["a", "b"]), docs_paged=[])
            )
        assert len(result) == 2

    def test_propaga_exception_411_document_timeout(self):
        exc = HTTPException411DocumentTimeout(document_id="doc1")
        with (
            patch(
                "sei_ia.agents.grammar_checker.get_doc_from_id",
                new=AsyncMock(side_effect=exc),
            ),
            pytest.raises(HTTPException411DocumentTimeout),
        ):
            asyncio.run(get_documents(self._request(), docs_paged=[]))

    def test_propaga_exception_412_sei_api_timeout(self):
        exc = HTTPException412SeiApiTimeout(document_id="doc1")
        with (
            patch(
                "sei_ia.agents.grammar_checker.get_doc_from_id",
                new=AsyncMock(side_effect=exc),
            ),
            pytest.raises(HTTPException412SeiApiTimeout),
        ):
            asyncio.run(get_documents(self._request(), docs_paged=[]))

    def test_propaga_exception_404(self):
        with (
            patch(
                "sei_ia.agents.grammar_checker.get_doc_from_id",
                new=AsyncMock(side_effect=HTTPException404()),
            ),
            pytest.raises(HTTPException404),
        ):
            asyncio.run(get_documents(self._request(), docs_paged=[]))

    def test_propaga_exception_204(self):
        with (
            patch(
                "sei_ia.agents.grammar_checker.get_doc_from_id",
                new=AsyncMock(side_effect=HTTPException204()),
            ),
            pytest.raises(HTTPException204),
        ):
            asyncio.run(get_documents(self._request(), docs_paged=[]))

    def test_propaga_exception_409(self):
        with (
            patch(
                "sei_ia.agents.grammar_checker.get_doc_from_id",
                new=AsyncMock(side_effect=HTTPException409()),
            ),
            pytest.raises(HTTPException409),
        ):
            asyncio.run(get_documents(self._request(), docs_paged=[]))

    def test_propaga_exception_415(self):
        with (
            patch(
                "sei_ia.agents.grammar_checker.get_doc_from_id",
                new=AsyncMock(side_effect=HTTPException415()),
            ),
            pytest.raises(HTTPException415),
        ):
            asyncio.run(get_documents(self._request(), docs_paged=[]))

    def test_propaga_exception_500(self):
        with (
            patch(
                "sei_ia.agents.grammar_checker.get_doc_from_id",
                new=AsyncMock(side_effect=HTTPException500()),
            ),
            pytest.raises(HTTPException500),
        ):
            asyncio.run(get_documents(self._request(), docs_paged=[]))
