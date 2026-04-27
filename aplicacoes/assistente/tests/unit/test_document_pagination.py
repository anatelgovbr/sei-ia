"""Testes unitários para paginação de documentos baseada no payload."""

from unittest.mock import patch

import pytest

from sei_ia.data.etl.concatenate_documents import (
    build_docs_paged_from_payload,
    get_doc_from_id_async,
    initialize_document_processing_state,
)
from sei_ia.data.etl.extract.doc_content import _get_doc_content_internal
from sei_ia.data.pydantic_models import ItemDocumentRequest, ItemRequestIdProcedimento


class TestPayloadPaginationContract:
    """Testes para o contrato de paginação vindo do payload."""

    @pytest.mark.asyncio
    async def test_initialize_document_processing_state_ignores_prompt_text(self):
        """O texto do usuário não deve produzir paginação no estado inicial."""
        result = await initialize_document_processing_state(
            {
                "user_request": (
                    "liste os documentos do processo #0000036-47.2025.6.17.8000 "
                    "e considere #123[1:10]"
                )
            }
        )

        assert result["doc_paged"] == []

    def test_build_docs_paged_from_payload_uses_document_fields(self):
        """A paginação deve ser construída exclusivamente a partir do payload."""
        user_state = {
            "id_procedimentos": [
                ItemRequestIdProcedimento(
                    id_procedimento="proc-1",
                    id_documentos=[
                        ItemDocumentRequest(
                            id_documento="doc-1",
                            pag_doc_init=1,
                            pag_doc_end=10,
                        ),
                        ItemDocumentRequest(id_documento="doc-2"),
                    ],
                )
            ]
        }
        doc_metadata_map = {
            "doc-1": {"id_documento_formatado": "123"},
            "doc-2": {"id_documento_formatado": "456"},
        }

        doc_paged, id_docs_paged = build_docs_paged_from_payload(
            user_state=user_state,
            doc_metadata_map=doc_metadata_map,
        )

        assert doc_paged == [("123", 1, 10)]
        assert id_docs_paged == ["123"]

    def test_build_docs_paged_from_payload_normalizes_single_page_range(self):
        """Se só houver página inicial, a final deve assumir o mesmo valor."""
        user_state = {
            "id_procedimentos": [
                ItemRequestIdProcedimento(
                    id_procedimento="proc-1",
                    id_documentos=[
                        ItemDocumentRequest(
                            id_documento="doc-1",
                            pag_doc_init=5,
                        )
                    ],
                )
            ]
        }
        doc_metadata_map = {"doc-1": {"id_documento_formatado": "123"}}

        doc_paged, id_docs_paged = build_docs_paged_from_payload(
            user_state=user_state,
            doc_metadata_map=doc_metadata_map,
        )

        assert doc_paged == [("123", 5, 5)]
        assert id_docs_paged == ["123"]

    def test_build_docs_paged_from_payload_ignores_documents_without_pagination(self):
        """Documento sem paginação no payload deve ser processado inteiro."""
        user_state = {
            "id_procedimentos": [
                ItemRequestIdProcedimento(
                    id_procedimento="proc-1",
                    id_documentos=[ItemDocumentRequest(id_documento="doc-1")],
                )
            ]
        }
        doc_metadata_map = {"doc-1": {"id_documento_formatado": "123"}}

        doc_paged, id_docs_paged = build_docs_paged_from_payload(
            user_state=user_state,
            doc_metadata_map=doc_metadata_map,
        )

        assert doc_paged == []
        assert id_docs_paged == []


class TestDocContentPagination:
    """Testes para aplicação de paginação sem depender do prompt."""

    @pytest.mark.asyncio
    @patch("sei_ia.data.etl.extract.doc_content.get_doc_ext_from_id")
    @patch("sei_ia.data.etl.extract.doc_content.get_type_doc_from_id")
    async def test_sync_doc_content_ignores_pagination_for_other_documents(
        self, mock_get_type_doc_from_id, mock_get_doc_ext_from_id
    ):
        """Documento fora da lista de paginação deve ser processado normalmente."""
        mock_get_type_doc_from_id.return_value = (False, "pdf", "555", "proc-1")
        mock_get_doc_ext_from_id.return_value = "conteudo"

        content, formatted_id = await _get_doc_content_internal(
            "doc-1", [("123", 1, 10)], False
        )

        assert content == "conteudo"
        assert formatted_id == "555"
        mock_get_doc_ext_from_id.assert_called_once_with("doc-1", None, None, "pdf")

    @pytest.mark.asyncio
    @patch("sei_ia.data.etl.concatenate_documents.get_doc_ext_from_id")
    @patch("sei_ia.data.etl.concatenate_documents.get_type_doc_from_id")
    async def test_async_doc_content_applies_range_for_matching_document(
        self, mock_get_type_doc_from_id, mock_get_doc_ext_from_id
    ):
        """Documento paginado no payload deve manter o intervalo solicitado."""
        mock_get_type_doc_from_id.return_value = (False, "pdf", "123", "proc-1")
        mock_get_doc_ext_from_id.return_value = "conteudo"

        content, formatted_id, _ = await get_doc_from_id_async(
            "doc-1", [("123", 1, 10)], False
        )

        assert content == "conteudo"
        assert formatted_id == "123"
        mock_get_doc_ext_from_id.assert_called_once_with("doc-1", 1, 10, "pdf")

    @pytest.mark.asyncio
    @patch("sei_ia.data.etl.concatenate_documents.get_doc_ext_from_id")
    @patch("sei_ia.data.etl.concatenate_documents.get_type_doc_from_id")
    async def test_async_doc_content_does_not_raise_for_non_matching_document(
        self, mock_get_type_doc_from_id, mock_get_doc_ext_from_id
    ):
        """Documento fora da lista de paginação não deve falhar nem ser paginado."""
        mock_get_type_doc_from_id.return_value = (False, "pdf", "555", "proc-1")
        mock_get_doc_ext_from_id.return_value = "conteudo"

        content, formatted_id, _ = await get_doc_from_id_async(
            "doc-1", [("123", 1, 10)], False
        )

        assert content == "conteudo"
        assert formatted_id == "555"
        mock_get_doc_ext_from_id.assert_called_once_with("doc-1", None, None, "pdf")
