"""Testes unitários para o módulo document_validation.

Módulo testado: sei_ia/agents/pergunta/document_validation.py
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd

from sei_ia.agents.pergunta.document_validation import (
    check_all_documents_indexed,
    get_missing_documents_error_message,
)


class TestGetMissingDocumentsErrorMessage:
    """Testes para get_missing_documents_error_message."""

    def test_lista_vazia_retorna_todos_indexados(self):
        resultado = get_missing_documents_error_message([], 5)
        assert resultado == "Todos os documentos estão indexados"

    def test_retorna_string(self):
        assert isinstance(get_missing_documents_error_message(["doc1"], 3), str)

    def test_contem_ids_dos_documentos_faltantes(self):
        resultado = get_missing_documents_error_message(["doc_a", "doc_b"], 5)
        assert "doc_a" in resultado
        assert "doc_b" in resultado

    def test_contem_orientacao_de_indexacao(self):
        resultado = get_missing_documents_error_message(["doc1"], 1)
        assert "indexar" in resultado.lower()

    def test_um_documento_faltante(self):
        resultado = get_missing_documents_error_message(["doc_xyz"], 1)
        assert "doc_xyz" in resultado

    def test_multiplos_documentos_faltantes(self):
        docs = ["d1", "d2", "d3"]
        resultado = get_missing_documents_error_message(docs, 10)
        for doc in docs:
            assert doc in resultado

    def test_total_docs_zero_com_lista_vazia(self):
        resultado = get_missing_documents_error_message([], 0)
        assert "Todos os documentos estão indexados" in resultado


# ---------------------------------------------------------------------------
# check_all_documents_indexed
# ---------------------------------------------------------------------------


def _make_proc_mock(doc_ids):
    docs = [MagicMock(id_documento=did) for did in doc_ids]
    proc = MagicMock()
    proc.id_documentos = docs
    return proc


def _make_state(doc_ids=None):
    if not doc_ids:
        return {"id_procedimentos": []}
    return {"id_procedimentos": [_make_proc_mock(doc_ids)]}


class TestCheckAllDocumentsIndexed:
    def test_sem_procedimentos_retorna_all_indexed_true(self):
        result = asyncio.run(check_all_documents_indexed({"id_procedimentos": []}))
        assert result["all_indexed"] is True
        assert result["total_documents"] == 0
        assert result["missing_documents"] == []

    def test_todos_os_documentos_indexados(self):
        state = _make_state(["doc1", "doc2"])
        df = pd.DataFrame({"id_documento": ["doc1", "doc2"]})
        with patch(
            "sei_ia.agents.pergunta.document_validation.app_db_instance"
        ) as mock_db:
            mock_db.select_native_async = AsyncMock(return_value=df)
            result = asyncio.run(check_all_documents_indexed(state))
        assert result["all_indexed"] is True
        assert result["missing_documents"] == []
        assert result["total_documents"] == 2

    def test_alguns_documentos_faltantes(self):
        state = _make_state(["doc1", "doc2", "doc3"])
        df = pd.DataFrame({"id_documento": ["doc1"]})
        with patch(
            "sei_ia.agents.pergunta.document_validation.app_db_instance"
        ) as mock_db:
            mock_db.select_native_async = AsyncMock(return_value=df)
            result = asyncio.run(check_all_documents_indexed(state))
        assert result["all_indexed"] is False
        assert set(result["missing_documents"]) == {"doc2", "doc3"}
        assert result["total_documents"] == 3

    def test_nenhum_documento_indexado(self):
        state = _make_state(["doc1", "doc2"])
        df = pd.DataFrame({"id_documento": pd.Series([], dtype=str)})
        with patch(
            "sei_ia.agents.pergunta.document_validation.app_db_instance"
        ) as mock_db:
            mock_db.select_native_async = AsyncMock(return_value=df)
            result = asyncio.run(check_all_documents_indexed(state))
        assert result["all_indexed"] is False
        assert set(result["missing_documents"]) == {"doc1", "doc2"}

    def test_excecao_retorna_all_indexed_false_com_erro(self):
        state = _make_state(["doc1"])
        with patch(
            "sei_ia.agents.pergunta.document_validation.app_db_instance"
        ) as mock_db:
            mock_db.select_native_async = AsyncMock(side_effect=Exception("DB error"))
            result = asyncio.run(check_all_documents_indexed(state))
        assert result["all_indexed"] is False
        assert "error" in result
        assert "doc1" in result["missing_documents"]

    def test_proc_sem_atributo_id_documentos_e_ignorado(self):
        proc = MagicMock(spec=[])  # sem atributo id_documentos
        state = {"id_procedimentos": [proc]}
        result = asyncio.run(check_all_documents_indexed(state))
        assert result["all_indexed"] is True
        assert result["total_documents"] == 0

    def test_doc_sem_atributo_id_documento_e_ignorado(self):
        doc = MagicMock(spec=[])  # sem atributo id_documento
        proc = MagicMock()
        proc.id_documentos = [doc]
        state = {"id_procedimentos": [proc]}
        result = asyncio.run(check_all_documents_indexed(state))
        assert result["all_indexed"] is True
        assert result["total_documents"] == 0
