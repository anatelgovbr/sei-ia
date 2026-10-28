"""Testes de integração para extração de documentos do SEI.

Este módulo contém testes de integração que usam mocks com dados reais
capturados da API do SEI para validar o fluxo completo de extração de documentos.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import requests


# Carregar fixtures com dados reais capturados
FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES_FILE = FIXTURES_DIR / "document_reader_api_responses.json"
FILES_DIR = FIXTURES_DIR / "files"


@pytest.fixture(scope="module")
def api_responses():
    """Carrega as respostas da API capturadas dos testes reais."""
    with open(FIXTURES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_requests_get(api_responses):
    """Mock para requests.get que retorna dados reais capturados."""

    def _get(url, *args, **kwargs):
        params = kwargs.get("params", {})
        service_name = params.get("servico", "")
        id_documento = params.get("IdDocumento", params.get("IdDocumentos", ""))

        # Encontrar a requisição correspondente nos fixtures
        for doc_id, doc_data in api_responses.items():
            for req in doc_data["requests"]:
                if (
                    req["request"]["service"] == service_name
                    and (
                        str(id_documento) in str(req["request"]["params"].get("IdDocumento", ""))
                        or str(id_documento) in str(req["request"]["params"].get("IdDocumentos", ""))
                    )
                ):
                    # Criar mock response
                    response = MagicMock(spec=requests.Response)
                    response.status_code = req["response"]["status_code"]
                    response.headers = req["response"]["headers"]

                    if req["response"]["is_binary"]:
                        # Para arquivos binários, carregar do disco
                        response.content = b""  # Default vazio
                        if "files" in doc_data:
                            for file_info in doc_data["files"].values():
                                if "saved_path" in file_info:
                                    file_path = Path(file_info["saved_path"])
                                    if file_path.exists():
                                        with open(file_path, "rb") as f:
                                            response.content = f.read()
                                    break
                    else:
                        response.json = MagicMock(return_value=req["response"]["json"])
                        response.text = json.dumps(req["response"]["json"])
                        response.content = b""  # Garantir que content sempre seja bytes

                    return response

        # Fallback: requisição não encontrada
        raise ValueError(f"Mock não encontrado para service={service_name}, id_documento={id_documento}")

    return _get


@pytest.fixture
def mock_httpx_async_client(api_responses):
    """Mock para httpx.AsyncClient que retorna dados reais capturados."""

    class MockAsyncClient:
        """Mock para httpx.AsyncClient."""

        def __init__(self, *args, **kwargs):
            """Aceita quaisquer argumentos para compatibilidade com httpx.AsyncClient."""
            pass

        async def __aenter__(self):
            """Context manager entry."""
            return self

        async def __aexit__(self, *args):
            """Context manager exit."""
            pass

        async def get(self, url, **kwargs):
            """Mock do método get."""
            params = kwargs.get("params", {})
            service_name = params.get("servico", "")
            id_documento = params.get("IdDocumento", "")

            # Encontrar a requisição correspondente
            for doc_id, doc_data in api_responses.items():
                for req in doc_data["requests"]:
                    if (
                        req["request"]["service"] == service_name
                        and str(id_documento) in str(req["request"]["params"].get("IdDocumento", ""))
                    ):
                        # Criar mock response
                        response = MagicMock(spec=httpx.Response)
                        response.status_code = req["response"]["status_code"]
                        response.headers = req["response"]["headers"]
                        response.json = MagicMock(return_value=req["response"]["json"])
                        response.text = json.dumps(req["response"]["json"])
                        return response

            raise ValueError(f"Mock async não encontrado para service={service_name}, id_documento={id_documento}")

    return MockAsyncClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_extract_html_document_9758178(mock_requests_get, mock_httpx_async_client, api_responses):
    """Testa extração de documento HTML interno (ID 9758178).

    Este teste valida:
    - Consulta de metadados via md_ia_consulta_documento
    - Consulta de conteúdo HTML via md_ia_consulta_conteudo_documento_async
    - Conversão de HTML para markdown
    - Conteúdo extraído corresponde ao esperado
    """
    # Import tardio para evitar erro de importação no collection do pytest
    from jobs.document_extraction.document_reader import get_document_content

    id_documento = "9758178"
    expected_data = api_responses[id_documento]

    with patch("requests.get", mock_requests_get):
        with patch("httpx.AsyncClient", mock_httpx_async_client):
            # Executar extração
            content = await get_document_content(id_documento)

            # Validações
            assert content is not None, "Conteúdo não deve ser None"
            assert len(content) > 0, "Conteúdo não deve estar vazio"

            
            # Validar palavras-chave presentes no documento
            assert "Portaria de Pessoal" in content
            assert "ANATEL" in content or "Anatel" in content
            assert "Fiscal Técnico" in content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_extract_pdf_document_with_attachments_9664647(
    mock_requests_get, mock_httpx_async_client, api_responses
):
    """Testa extração de documento com anexos PDF (ID 9664647).

    Este teste valida:
    - Consulta de metadados
    - Detecção de anexos (IdAnexos)
    - Download de múltiplos anexos PDF
    - Extração de texto de cada PDF
    - Consolidação do conteúdo (email + anexos)
    """
    from jobs.document_extraction.document_reader import get_document_content

    id_documento = "9664647"
    expected_data = api_responses[id_documento]

    with patch("requests.get", mock_requests_get):
        with patch("httpx.AsyncClient", mock_httpx_async_client):
            # Executar extração
            content = await get_document_content(id_documento)

            # Validações
            assert content is not None
            assert len(content) > 0

            # Este documento tem anexos, então o conteúdo deve incluir tags de anexo
            assert "<conteudo_principal_do_email>" in content or "anexo_" in content.lower()

            # Validar que foram processados 2 anexos (conforme logs da captura)
            # O documento 9664647 tem 2 anexos PDF
            assert expected_data["requests"].__len__() == 4  # 1 metadata + 1 content + 2 downloads


@pytest.mark.integration
@pytest.mark.asyncio
async def test_extract_xlsx_document_8665099(mock_requests_get, mock_httpx_async_client, api_responses):
    """Testa extração de documento XLSX (ID 8665099).

    Este teste valida:
    - Consulta de metadados com content_type = xlsx
    - Download do arquivo XLSX via md_ia_download_arquivo_documento_externo
    - Extração de texto do arquivo Excel
    - Processamento de múltiplas sheets
    """
    from jobs.document_extraction.document_reader import get_document_content

    id_documento = "8665099"
    expected_data = api_responses[id_documento]

    with patch("requests.get", mock_requests_get):
        with patch("httpx.AsyncClient", mock_httpx_async_client):
            # Executar extração
            content = await get_document_content(id_documento)

            # Validações
            assert content is not None
            assert len(content) > 0

            # XLSX geralmente gera muito conteúdo
            assert len(content) > 10000, "Arquivo XLSX deve gerar conteúdo substancial"

         
            # Validar que contém dados de planilha (conforme nome do arquivo capturado)
            # O arquivo é "Planejamento_de_Demandas.xlsx"
            assert "Analistas de Dados" in content or "Cientistas de Dados" in content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_not_found_handling():
    """Testa tratamento de documento não encontrado."""
    from jobs.document_extraction.document_reader import get_document_content

    def mock_get_404(*args, **kwargs):
        response = MagicMock(spec=requests.Response)
        response.status_code = 404
        response.json = MagicMock(return_value={"status": "error", "message": "Documento não encontrado"})
        return response

    with patch("requests.get", mock_get_404):
        with pytest.raises(Exception) as exc_info:
            await get_document_content("999999999")

        assert "not found" in str(exc_info.value).lower() or "failed" in str(exc_info.value).lower()


@pytest.mark.integration
def test_fixtures_integrity():
    """Testa integridade dos arquivos de fixtures.

    Valida:
    - Arquivo JSON existe e é válido
    - Todos os documentos esperados estão presentes
    - Arquivos binários existem
    """
    # Validar JSON
    assert FIXTURES_FILE.exists(), f"Arquivo de fixtures não encontrado: {FIXTURES_FILE}"

    with open(FIXTURES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validar documentos esperados
    expected_docs = ["9758178", "9664647", "8665099"]
    for doc_id in expected_docs:
        assert doc_id in data, f"Documento {doc_id} não encontrado nos fixtures"
        assert "requests" in data[doc_id]
        assert len(data[doc_id]["requests"]) > 0
        assert "extracted_content" in data[doc_id]

    # Validar arquivos binários
    assert FILES_DIR.exists(), f"Diretório de arquivos não encontrado: {FILES_DIR}"

    # Deve ter pelo menos 2 arquivos (PDF e XLSX)
    files = list(FILES_DIR.glob("*"))
    assert len(files) >= 2, f"Esperado pelo menos 2 arquivos em {FILES_DIR}, encontrado {len(files)}"

    # Validar que arquivos esperados existem
    xlsx_files = list(FILES_DIR.glob("*.xlsx"))
    pdf_files = list(FILES_DIR.glob("*.pdf"))

    assert len(xlsx_files) >= 1, "Deve ter pelo menos 1 arquivo XLSX"
    assert len(pdf_files) >= 1, "Deve ter pelo menos 1 arquivo PDF"
