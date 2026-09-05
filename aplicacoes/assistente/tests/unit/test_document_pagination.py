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

ADAPTERS = "sei_ia.data.etl.extract.sei_adapters"


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
    """Testes para roteamento orientado por `download_ext` no payload."""

    @pytest.mark.asyncio
    @patch(f"{ADAPTERS}.SeiApiContentSource.fetch_content_doc")
    @patch("sei_ia.data.etl.extract.doc_content.get_type_doc_from_id")
    async def test_sync_uses_content_doc_when_download_ext_false(
        self, mock_get_type_doc_from_id, mock_fetch_content
    ):
        """download_ext=False com num_doc fora da lista de paginação → Rota A direta."""
        mock_get_type_doc_from_id.return_value = (False, "pdf", "555", "proc-1")
        mock_fetch_content.return_value = {
            "content_doc": "conteudo",
            "extra_metadata": {},
        }

        content, formatted_id = await _get_doc_content_internal(
            "doc-1", [("123", 1, 10)], False
        )

        assert content == "conteudo"
        assert formatted_id == "555"
        mock_fetch_content.assert_called_once_with("doc-1")

    @pytest.mark.asyncio
    @patch("sei_extraction.document_fetch.extract_document", return_value="conteudo")
    @patch(f"{ADAPTERS}.SeiApiFileDownloader.download", return_value="/tmp/fake.pdf")
    @patch("sei_ia.data.etl.concatenate_documents.get_type_doc_from_id")
    async def test_async_applies_range_when_download_ext_true(
        self, mock_get_type_doc_from_id, mock_download, mock_extract
    ):
        """Paginação só vale quando o payload autoriza download (`download_ext=True`)."""
        mock_get_type_doc_from_id.return_value = (False, "pdf", "123", "proc-1")

        content, formatted_id, _ = await get_doc_from_id_async(
            "doc-1", [("123", 1, 10)], True
        )

        assert content == "conteudo"
        assert formatted_id == "123"
        mock_download.assert_called_once_with("doc-1", "pdf")
        mock_extract.assert_called_once()
        _, kwargs = mock_extract.call_args
        assert kwargs.get("pag_ini") == 1
        assert kwargs.get("pag_fim") == 10

    @pytest.mark.asyncio
    @patch(f"{ADAPTERS}.SeiApiContentSource.fetch_content_doc")
    @patch("sei_ia.data.etl.concatenate_documents.get_type_doc_from_id")
    async def test_async_uses_content_doc_for_non_paginated_document(
        self, mock_get_type_doc_from_id, mock_fetch_content
    ):
        """Documento sem paginação no payload e download_ext=False → Rota A direta."""
        mock_get_type_doc_from_id.return_value = (False, "pdf", "555", "proc-1")
        mock_fetch_content.return_value = {
            "content_doc": "conteudo",
            "extra_metadata": {},
        }

        content, formatted_id, _ = await get_doc_from_id_async(
            "doc-1", [("123", 1, 10)], False
        )

        assert content == "conteudo"
        assert formatted_id == "555"
        mock_fetch_content.assert_called_once_with("doc-1")

    @pytest.mark.asyncio
    @patch("sei_ia.data.etl.concatenate_documents.get_type_doc_from_id")
    async def test_async_rejects_pagination_without_download_ext(
        self, mock_get_type_doc_from_id
    ):
        """Paginação sem download_ext=True deve falhar com 406."""
        from sei_ia.services.exceptions.http_exceptions import HTTPException406

        mock_get_type_doc_from_id.return_value = (False, "pdf", "123", "proc-1")

        with pytest.raises(HTTPException406):
            await get_doc_from_id_async("doc-1", [("123", 1, 10)], False)
