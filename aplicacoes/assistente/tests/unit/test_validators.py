"""
Testes unitários para o módulo validators.py
"""

import pytest

from sei_ia.data.pydantic_models import (
    ChatRequest,
    ItemDocumentRequest,
    ItemRequestIdProcedimento,
)
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException400,
    HTTPException403,
    HTTPException422,
)
from sei_ia.services.validators import has_id_process, validate_proc_reference


class TestHasIdProcess:
    """Testes para a função has_id_process."""

    def test_has_id_process_valid_request(self):
        """Testa validação com request válido."""
        request = ChatRequest(
            id_usuario=123,
            text="Teste",
            id_procedimentos=[
                ItemRequestIdProcedimento(
                    id_procedimento="proc_001",
                    id_documentos=[ItemDocumentRequest(id_documento="doc_001")],
                )
            ],
        )

        result = has_id_process(request, "TEST_INTENT")
        assert result is True

    def test_has_id_process_empty_procedimentos(self):
        """Testa validação com id_procedimentos vazio."""
        request = ChatRequest(id_usuario=123, text="Teste", id_procedimentos=[])

        with pytest.raises(HTTPException422) as exc_info:
            has_id_process(request, "TEST_INTENT")

        assert "id_procedimentos não pode ser vazio" in str(exc_info.value.detail)
        assert "TEST_INTENT" in str(exc_info.value.detail)

    def test_has_id_process_none_procedimentos(self):
        """Testa validação com id_procedimentos None."""
        request = ChatRequest(id_usuario=123, text="Teste", id_procedimentos=None)

        with pytest.raises(HTTPException422) as exc_info:
            has_id_process(request, "PERGUNTA")

        assert "id_procedimentos não pode ser vazio" in str(exc_info.value.detail)

    def test_has_id_process_empty_id_procedimento(self):
        """Testa validação com id_procedimento vazio."""
        request = ChatRequest(
            id_usuario=123,
            text="Teste",
            id_procedimentos=[
                ItemRequestIdProcedimento(
                    id_procedimento="",
                    id_documentos=[ItemDocumentRequest(id_documento="doc_001")],
                )
            ],
        )

        with pytest.raises(HTTPException422) as exc_info:
            has_id_process(request, "TEST_INTENT")

        assert "id_procedimento não pode ser vazio" in str(exc_info.value.detail)

    def test_has_id_process_empty_id_documentos(self):
        """Testa validação com id_documentos vazio."""
        request = ChatRequest(
            id_usuario=123,
            text="Teste",
            id_procedimentos=[
                ItemRequestIdProcedimento(id_procedimento="proc_001", id_documentos=[])
            ],
        )

        with pytest.raises(HTTPException422) as exc_info:
            has_id_process(request, "TEST_INTENT")

        assert "id_documentos não pode ser vazio" in str(exc_info.value.detail)

    def test_has_id_process_with_valid_single_document(self):
        """Testa validação com um único documento válido."""
        request = ChatRequest(
            id_usuario=123,
            text="Teste",
            id_procedimentos=[
                ItemRequestIdProcedimento(
                    id_procedimento="proc_001",
                    id_documentos=[ItemDocumentRequest(id_documento="doc_001")],
                )
            ],
        )

        # Deve passar sem exceção
        result = has_id_process(request, "TEST_INTENT")
        assert result is True

    def test_has_id_process_multiple_valid_procedimentos(self):
        """Testa validação com múltiplos procedimentos válidos."""
        request = ChatRequest(
            id_usuario=123,
            text="Teste",
            id_procedimentos=[
                ItemRequestIdProcedimento(
                    id_procedimento="proc_001",
                    id_documentos=[
                        ItemDocumentRequest(id_documento="doc_001"),
                        ItemDocumentRequest(id_documento="doc_002"),
                    ],
                ),
                ItemRequestIdProcedimento(
                    id_procedimento="proc_002",
                    id_documentos=[ItemDocumentRequest(id_documento="doc_003")],
                ),
            ],
        )

        result = has_id_process(request, "TEST_INTENT")
        assert result is True


class TestValidateProcReference:
    """Testes para a função validate_proc_reference."""

    def test_validate_proc_reference_single_proc_with_docs(self):
        """Testa validação com um único processo e documentos."""
        request = ChatRequest(
            id_usuario=123,
            text="Teste",
            id_procedimentos=[
                ItemRequestIdProcedimento(
                    id_procedimento="proc_001",
                    id_documentos=[ItemDocumentRequest(id_documento="doc_001")],
                )
            ],
        )

        # Não deve lançar exceção
        validate_proc_reference(request)

    def test_validate_proc_reference_multiple_procs(self):
        """Testa validação com múltiplos processos (deve falhar)."""
        request = ChatRequest(
            id_usuario=123,
            text="Teste",
            id_procedimentos=[
                ItemRequestIdProcedimento(
                    id_procedimento="proc_001",
                    id_documentos=[ItemDocumentRequest(id_documento="doc_001")],
                ),
                ItemRequestIdProcedimento(
                    id_procedimento="proc_002",
                    id_documentos=[ItemDocumentRequest(id_documento="doc_002")],
                ),
            ],
        )

        with pytest.raises(HTTPException403) as exc_info:
            validate_proc_reference(request)

        assert "mais de um processo" in str(exc_info.value.detail)

    def test_validate_proc_reference_no_documents(self):
        """Testa validação com processo sem documentos."""
        request = ChatRequest(
            id_usuario=123,
            text="Teste",
            id_procedimentos=[
                ItemRequestIdProcedimento(id_procedimento="proc_001", id_documentos=[])
            ],
        )

        with pytest.raises(HTTPException400) as exc_info:
            validate_proc_reference(request)

        assert "processo sem documentos" in str(exc_info.value.detail)

    def test_validate_proc_reference_empty_procedimentos(self):
        """Testa validação com lista de procedimentos vazia."""
        request = ChatRequest(id_usuario=123, text="Teste", id_procedimentos=[])

        # Não deve lançar exceção pois não há processo nem documentos
        # No entanto, all_documents_allowed() retorna [] então deve lançar HTTPException400
        with pytest.raises(HTTPException400) as exc_info:
            validate_proc_reference(request)

        assert "processo sem documentos" in str(exc_info.value.detail)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
