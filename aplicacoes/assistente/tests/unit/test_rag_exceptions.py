"""Testes unitários para o módulo rag_exceptions.

Módulo testado: sei_ia/services/exceptions/rag_exceptions.py
"""

from fastapi import HTTPException

from sei_ia.services.exceptions.rag_exceptions import (
    DocumentsNotIndexedException,
    EmbeddingVerificationException,
)


class TestDocumentsNotIndexedException:
    """Testes para DocumentsNotIndexedException."""

    def test_herda_de_http_exception(self):
        exc = DocumentsNotIndexedException(
            missing_documents=["doc1"], total_documents=1
        )
        assert isinstance(exc, HTTPException)

    def test_status_code_400(self):
        exc = DocumentsNotIndexedException(
            missing_documents=["doc1"], total_documents=1
        )
        assert exc.status_code == 400

    def test_todos_documentos_faltantes(self):
        exc = DocumentsNotIndexedException(
            missing_documents=["d1", "d2"], total_documents=2
        )
        assert "Nenhum dos 2" in exc.detail

    def test_alguns_documentos_faltantes(self):
        exc = DocumentsNotIndexedException(missing_documents=["d1"], total_documents=3)
        assert "1 de 3" in exc.detail

    def test_missing_count_correto(self):
        exc = DocumentsNotIndexedException(
            missing_documents=["a", "b", "c"], total_documents=10
        )
        assert exc.missing_count == 3

    def test_missing_documents_preservados(self):
        docs = ["doc_x", "doc_y"]
        exc = DocumentsNotIndexedException(missing_documents=docs, total_documents=5)
        assert exc.missing_documents == docs

    def test_total_documents_preservado(self):
        exc = DocumentsNotIndexedException(missing_documents=["d1"], total_documents=7)
        assert exc.total_documents == 7

    def test_detalhes_listados_quando_poucos(self):
        exc = DocumentsNotIndexedException(
            missing_documents=["doc_a", "doc_b"], total_documents=5
        )
        assert "doc_a" in exc.detail
        assert "doc_b" in exc.detail

    def test_trunca_lista_quando_muitos(self):
        docs = [f"doc_{i}" for i in range(10)]
        exc = DocumentsNotIndexedException(missing_documents=docs, total_documents=10)
        assert "..." in exc.detail

    def test_mensagem_contem_orientacao_indexacao(self):
        exc = DocumentsNotIndexedException(missing_documents=["d1"], total_documents=1)
        assert "indexar" in exc.detail.lower()


class TestEmbeddingVerificationException:
    """Testes para EmbeddingVerificationException."""

    def test_herda_de_http_exception(self):
        exc = EmbeddingVerificationException("conexão recusada")
        assert isinstance(exc, HTTPException)

    def test_status_code_400(self):
        exc = EmbeddingVerificationException("timeout")
        assert exc.status_code == 400

    def test_mensagem_contem_erro_original(self):
        exc = EmbeddingVerificationException("banco indisponível")
        assert "banco indisponível" in exc.detail

    def test_mensagem_contem_prefixo(self):
        exc = EmbeddingVerificationException("erro qualquer")
        assert "Erro ao verificar" in exc.detail

    def test_string_vazia_como_erro(self):
        exc = EmbeddingVerificationException("")
        assert isinstance(exc, HTTPException)
