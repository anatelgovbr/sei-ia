"""
Testes unitários para o delimitador de documentos com protocolo de processo.

Verifica que o template INTERMEDIATE_COMPLETATION_WITH_DOC inclui corretamente
a informação do processo SEI ao qual cada documento pertence, evitando que o
modelo confunda o protocolo do processo com números encontrados no corpo do documento.
"""

import pytest

from sei_ia.agents.prompts.completation import INTERMEDIATE_COMPLETATION_WITH_DOC


class TestIntermediateCompletationWithDoc:
    """Testes do template de delimitação de documento com protocolo de processo."""

    def test_template_contem_placeholder_protocolo_processo(self):
        """Template deve conter o placeholder {protocolo_processo}."""
        assert "{protocolo_processo}" in INTERMEDIATE_COMPLETATION_WITH_DOC

    def test_template_contem_placeholder_id_documento(self):
        """Template deve conter o placeholder {id_documento_formatado}."""
        assert "{id_documento_formatado}" in INTERMEDIATE_COMPLETATION_WITH_DOC

    def test_template_formata_com_protocolo_do_processo(self):
        """Documento formatado deve conter o número do processo no cabeçalho."""
        result = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado="10000001",
            protocolo_processo="00000.000001/2020-01",
            doc="Conteúdo do documento de teste.",
        )

        assert "10000001" in result
        assert "00000.000001/2020-01" in result
        assert "Conteúdo do documento de teste." in result

    def test_cabecalho_associa_documento_ao_processo(self):
        """Cabeçalho do delimitador deve mencionar tanto o documento quanto o processo."""
        result = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado="10000002",
            protocolo_processo="00000.000002/2020-02",
            doc="Texto do documento.",
        )

        assert "#10000002" in result
        assert "do processo 00000.000002/2020-02" in result

    def test_delimitadores_de_abertura_e_fechamento_presentes(self):
        """Delimitadores de abertura e fechamento devem conter o ID do documento."""
        result = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado="10000001",
            protocolo_processo="00000.000001/2020-01",
            doc="Conteúdo.",
        )

        assert "[doc_10000001---]" in result
        assert "[\\doc_10000001---]" in result

    def test_protocolo_vazio_nao_causa_erro(self):
        """Protocolo vazio como fallback não deve lançar exceção."""
        result = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado="10000003",
            protocolo_processo="",
            doc="Conteúdo.",
        )

        assert "10000003" in result
        assert isinstance(result, str)

    def test_dois_documentos_processos_distintos_nao_se_confundem(self):
        """Dois documentos de processos diferentes devem ter protocolos isolados."""
        doc1 = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado="10000001",
            protocolo_processo="00000.000001/2020-01",
            doc="Conteúdo do documento 1.",
        )
        doc2 = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado="10000002",
            protocolo_processo="00000.000002/2020-02",
            doc="Conteúdo do documento 2.",
        )

        assert "00000.000001/2020-01" in doc1
        assert "00000.000002/2020-02" not in doc1

        assert "00000.000002/2020-02" in doc2
        assert "00000.000001/2020-01" not in doc2

    def test_conteudo_do_documento_preservado_integralmente(self):
        """Conteúdo do documento não deve ser alterado pelo template."""
        conteudo = "DOCUMENTO DE TESTE\nCláusula 1: ...\nReferência interna: 99999999"
        result = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado="10000001",
            protocolo_processo="00000.000001/2020-01",
            doc=conteudo,
        )

        assert conteudo in result


class TestProcessDocumentAsyncDelimiter:
    """Testes para garantir que process_document_async passa o protocolo ao template."""

    @pytest.mark.asyncio
    async def test_process_document_async_inclui_protocolo_no_conteudo(self):
        """process_document_async deve incluir o protocolo do processo no conteúdo."""
        from unittest.mock import AsyncMock, patch

        from sei_ia.data.etl.concatenate_documents import process_document_async
        from sei_ia.data.pydantic_models import ItemDocumentRequest

        id_documento_obj = ItemDocumentRequest(id_documento="20000001")

        with (
            patch("sei_ia.data.etl.concatenate_documents.get_cache") as mock_get_cache,
            patch(
                "sei_ia.data.etl.concatenate_documents.get_doc_from_id_async",
                new_callable=AsyncMock,
                return_value=("Texto do documento de teste.", "10000001", {}),
            ),
            patch(
                "sei_ia.data.etl.concatenate_documents.get_doc_metadata_dict",
                new_callable=AsyncMock,
                return_value={
                    "id_documento_formatado": "10000001",
                    "id_protocolo_formatado": "00000.000001/2020-01",
                    "type_doc": "I",
                    "formato_arquivo": "html",
                    "documento_especificacao": "Documento de teste",
                    "dta_inclusao": "2020-01-01",
                    "nome_id_tipo_documento": "Ofício",
                    "id_documento": "20000001",
                    "id_procedimento": "proc_001",
                    "id_tipo_documento": "1",
                },
            ),
            patch(
                "sei_ia.data.etl.concatenate_documents.get_doc_metadata_from_id",
                new_callable=AsyncMock,
                return_value="Número do Documento: 10000001\nNúmero do Processo: 00000.000001/2020-01",
            ),
        ):
            mock_cache = AsyncMock()
            mock_cache.get_document = AsyncMock(return_value=None)
            mock_cache.set_document = AsyncMock(return_value=True)
            mock_get_cache.return_value = mock_cache

            import asyncio

            semaphore = asyncio.Semaphore(1)
            result = await process_document_async(
                id_documento_obj=id_documento_obj,
                doc_paged=[],
                id_docs_paged=[],
                token_len_metadata=10,
                semaphore=semaphore,
            )

        assert "00000.000001/2020-01" in result["content"]
        assert "do processo 00000.000001/2020-01" in result["content"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
