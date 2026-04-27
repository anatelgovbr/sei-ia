"""
Testes E2E para associação processo-documento na montagem do contexto.

Verifica que a função concatenate_procedimento_documents_async produz
conteúdo de documento com o protocolo do processo correto no delimitador,
impedindo que o modelo associe um documento ao processo errado.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from sei_ia.data.pydantic_models import ItemDocumentRequest, ItemRequestIdProcedimento


def _make_user_state(id_procedimento: str, id_documento: str) -> dict:
    """Cria um UserState mínimo para testes."""
    return {
        "id_request": "test_e2e_assoc",
        "id_usuario": "user_test",
        "ip": "127.0.0.1",
        "endpoint_name": "/test",
        "id_topico": None,
        "id_procedimentos": [
            ItemRequestIdProcedimento(
                id_procedimento=id_procedimento,
                metadata="",
                id_documentos=[
                    ItemDocumentRequest(id_documento=id_documento),
                ],
            )
        ],
        "all_procs": [id_procedimento],
        "all_documents": [id_documento],
        "user_request": f"A qual processo pertence o documento #{id_documento}?",
        "system_prompt": "Você é um assistente IA.",
        "original_request_body": "{}",
        "intent": "pergunta",
        "model_type": "standard",
        "model_name": "gpt-4.1",
        "temperature": 0.01,
        "general_max_output_tokens": 4000,
        "general_max_ctx_len": 900000,
        "limit_rag": 450000,
        "limit_false_rag": 90000,
        "use_websearch": False,
        "use_thinking": False,
        "summarize_history": False,
        "doc_paged": [],
        "doc_summarized": False,
        "doc_rag": False,
        "doc_false_rag": False,
        "all_tokens_counter": 0,
        "web_content": None,
        "last_prompt": "",
        "has_content": False,
        "rag_method": None,
        "rag_documents_count": None,
        "rag_chunks_count": None,
        "response": {},
        "last_status_code": None,
        "last_detail": None,
    }


def _make_doc_metadata(id_documento: str, num_doc: str, num_proc: str) -> dict:
    """Cria metadados de documento para mock."""
    return {
        "metadata": {
            "id_documento": id_documento,
            "id_procedimento": "proc_001",
            "id_tipo_documento": "1",
            "id_protocolo_formatado": num_proc,
            "id_documento_formatado": num_doc,
            "documento_especificacao": "Documento de teste",
            "formato_arquivo": "html",
            "dta_inclusao": "2020-01-01",
            "nome_id_tipo_documento": "Ofício",
            "type_doc": "I",
            "is_internal": True,
            "sin_armazena_cache": "S",
        },
        "metadata_str": (
            f"ID do Documento: {id_documento}\n"
            f"Número do Documento: {num_doc}\n"
            f"Número do Processo: {num_proc}"
        ),
        "id_documento_formatado": num_doc,
        "id_protocolo_formatado": num_proc,
        "type_doc": "I",
        "is_internal": True,
        "sin_armazena_cache": "S",
    }


_CLEANUP_MOCK = {"deleted_from_redis": [], "deleted_from_postgres": [], "errors": []}


@pytest.mark.asyncio
async def test_conteudo_documento_contem_protocolo_do_processo():
    """
    O conteúdo do documento após processamento deve incluir o protocolo do
    processo no delimitador, não apenas o ID do documento.
    """
    from sei_ia.data.etl.concatenate_documents import (
        concatenate_procedimento_documents_async,
    )

    user_state = _make_user_state(id_procedimento="proc_001", id_documento="20000001")

    doc_metadata_map = {
        "20000001": _make_doc_metadata("20000001", "10000001", "00000.000001/2020-01")
    }
    proc_metadata_map = {
        "proc_001": (
            "ID do Processo: proc_001\n"
            "Número do Processo: 00000.000001/2020-01\n"
            "Descrição/Especificação do Processo: Processo de teste\n"
            "Tipo do Processo: Administrativo"
        )
    }

    mock_cache = AsyncMock()
    mock_cache.get_document = AsyncMock(return_value=None)
    mock_cache.set_document = AsyncMock(return_value=True)

    with (
        patch(
            "sei_ia.data.etl.concatenate_documents.fetch_documentos_metadata_batch",
            new_callable=AsyncMock,
            return_value=doc_metadata_map,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.fetch_procedimentos_metadata_batch",
            new_callable=AsyncMock,
            return_value=proc_metadata_map,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.get_doc_from_id_async",
            new_callable=AsyncMock,
            return_value=("Texto do documento de teste.", "10000001", {}),
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.cleanup_non_cacheable_documents",
            new_callable=AsyncMock,
            return_value=_CLEANUP_MOCK,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.get_cache",
            return_value=mock_cache,
        ),
    ):
        semaphore = asyncio.Semaphore(5)
        result = await concatenate_procedimento_documents_async(semaphore, user_state)

    doc = result["id_procedimentos"][0].id_documentos[0]
    assert doc.content is not None
    assert "00000.000001/2020-01" in doc.content
    assert "do processo 00000.000001/2020-01" in doc.content


@pytest.mark.asyncio
async def test_dois_documentos_processos_distintos_delimitadores_corretos():
    """
    Com dois documentos de processos distintos, cada um deve ter seu respectivo
    protocolo de processo no delimitador, sem contaminação cruzada.
    """
    from sei_ia.data.etl.concatenate_documents import (
        concatenate_procedimento_documents_async,
    )

    user_state = {
        **_make_user_state("proc_001", "20000001"),
        "id_procedimentos": [
            ItemRequestIdProcedimento(
                id_procedimento="proc_001",
                metadata="",
                id_documentos=[ItemDocumentRequest(id_documento="20000001")],
            ),
            ItemRequestIdProcedimento(
                id_procedimento="proc_002",
                metadata="",
                id_documentos=[ItemDocumentRequest(id_documento="20000002")],
            ),
        ],
        "all_procs": ["proc_001", "proc_002"],
        "all_documents": ["20000001", "20000002"],
        "doc_paged": [],
    }

    doc_metadata_map = {
        "20000001": _make_doc_metadata("20000001", "10000001", "00000.000001/2020-01"),
        "20000002": _make_doc_metadata("20000002", "10000002", "00000.000002/2020-02"),
    }
    proc_metadata_map = {
        "proc_001": "Número do Processo: 00000.000001/2020-01",
        "proc_002": "Número do Processo: 00000.000002/2020-02",
    }

    async def mock_get_doc(id_documento, *args, **kwargs):
        conteudos = {
            "20000001": ("Conteúdo do primeiro documento de teste.", "10000001", {}),
            "20000002": ("Conteúdo do segundo documento de teste.", "10000002", {}),
        }
        return conteudos[id_documento]

    mock_cache = AsyncMock()
    mock_cache.get_document = AsyncMock(return_value=None)
    mock_cache.set_document = AsyncMock(return_value=True)

    with (
        patch(
            "sei_ia.data.etl.concatenate_documents.fetch_documentos_metadata_batch",
            new_callable=AsyncMock,
            return_value=doc_metadata_map,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.fetch_procedimentos_metadata_batch",
            new_callable=AsyncMock,
            return_value=proc_metadata_map,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.get_doc_from_id_async",
            side_effect=mock_get_doc,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.cleanup_non_cacheable_documents",
            new_callable=AsyncMock,
            return_value=_CLEANUP_MOCK,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.get_cache",
            return_value=mock_cache,
        ),
    ):
        semaphore = asyncio.Semaphore(5)
        result = await concatenate_procedimento_documents_async(semaphore, user_state)

    doc1 = result["id_procedimentos"][0].id_documentos[0]
    doc2 = result["id_procedimentos"][1].id_documentos[0]

    # Cada documento deve ter apenas o protocolo do seu próprio processo
    assert "00000.000001/2020-01" in doc1.content
    assert "00000.000002/2020-02" not in doc1.content

    assert "00000.000002/2020-02" in doc2.content
    assert "00000.000001/2020-01" not in doc2.content


@pytest.mark.asyncio
async def test_documento_sem_protocolo_no_corpo_associado_corretamente():
    """
    Documento que não menciona o número do processo em seu corpo ainda deve
    ter o protocolo correto no delimitador vindo dos metadados.
    """
    from sei_ia.data.etl.concatenate_documents import (
        concatenate_procedimento_documents_async,
    )

    user_state = _make_user_state("proc_001", "20000002")
    # Conteúdo que NÃO menciona o protocolo do processo
    conteudo_sem_protocolo = (
        "DOCUMENTO ADMINISTRATIVO DE TESTE\n"
        "Partes: Empresa A e Empresa B\n"
        "Cláusulas e condições gerais...\n"
        "Assinaturas: ..."
    )

    doc_metadata_map = {
        "20000002": _make_doc_metadata("20000002", "10000002", "00000.000002/2020-02")
    }
    proc_metadata_map = {"proc_001": "Número do Processo: 00000.000002/2020-02"}

    mock_cache = AsyncMock()
    mock_cache.get_document = AsyncMock(return_value=None)
    mock_cache.set_document = AsyncMock(return_value=True)

    with (
        patch(
            "sei_ia.data.etl.concatenate_documents.fetch_documentos_metadata_batch",
            new_callable=AsyncMock,
            return_value=doc_metadata_map,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.fetch_procedimentos_metadata_batch",
            new_callable=AsyncMock,
            return_value=proc_metadata_map,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.get_doc_from_id_async",
            new_callable=AsyncMock,
            return_value=(conteudo_sem_protocolo, "10000002", {}),
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.cleanup_non_cacheable_documents",
            new_callable=AsyncMock,
            return_value=_CLEANUP_MOCK,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.get_cache",
            return_value=mock_cache,
        ),
    ):
        semaphore = asyncio.Semaphore(5)
        result = await concatenate_procedimento_documents_async(semaphore, user_state)

    doc = result["id_procedimentos"][0].id_documentos[0]
    # Protocolo deve vir dos metadados, não do corpo do documento
    assert "00000.000002/2020-02" in doc.content
    assert "do processo 00000.000002/2020-02" in doc.content


@pytest.mark.asyncio
async def test_documento_com_numero_diferente_no_corpo_usa_protocolo_dos_metadados():
    """
    Documento que menciona um número diferente no corpo (ex: número de referência
    interna) deve ter o protocolo correto vindo dos metadados, não do conteúdo.
    Este é o cenário central do bug: o modelo confundia o protocolo do processo
    com números encontrados dentro do corpo do documento.
    """
    from sei_ia.data.etl.concatenate_documents import (
        concatenate_procedimento_documents_async,
    )

    user_state = _make_user_state("proc_001", "20000001")
    numero_interno_no_corpo = "99999999"
    # Conteúdo que menciona outro número — esse era o número que confundia o modelo
    conteudo_com_referencia_interna = (
        "DOCUMENTO ADMINISTRATIVO DE TESTE\n"
        f"Referência interna nº {numero_interno_no_corpo}\n"
        "Referente ao objeto de teste..."
    )

    doc_metadata_map = {
        "20000001": _make_doc_metadata("20000001", "10000001", "00000.000001/2020-01")
    }
    proc_metadata_map = {"proc_001": "Número do Processo: 00000.000001/2020-01"}

    mock_cache = AsyncMock()
    mock_cache.get_document = AsyncMock(return_value=None)
    mock_cache.set_document = AsyncMock(return_value=True)

    with (
        patch(
            "sei_ia.data.etl.concatenate_documents.fetch_documentos_metadata_batch",
            new_callable=AsyncMock,
            return_value=doc_metadata_map,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.fetch_procedimentos_metadata_batch",
            new_callable=AsyncMock,
            return_value=proc_metadata_map,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.get_doc_from_id_async",
            new_callable=AsyncMock,
            return_value=(conteudo_com_referencia_interna, "10000001", {}),
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.cleanup_non_cacheable_documents",
            new_callable=AsyncMock,
            return_value=_CLEANUP_MOCK,
        ),
        patch(
            "sei_ia.data.etl.concatenate_documents.get_cache",
            return_value=mock_cache,
        ),
    ):
        semaphore = asyncio.Semaphore(5)
        result = await concatenate_procedimento_documents_async(semaphore, user_state)

    doc = result["id_procedimentos"][0].id_documentos[0]
    # O protocolo correto deve estar no delimitador
    assert "do processo 00000.000001/2020-01" in doc.content
    # O número de referência interna do corpo não deve aparecer no cabeçalho do delimitador
    header_line = [line for line in doc.content.split("\n") if "do processo" in line]
    assert len(header_line) == 1
    assert numero_interno_no_corpo not in header_line[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
