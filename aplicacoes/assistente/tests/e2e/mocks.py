import asyncio
import json

import httpx
import responses

from tests.utils.in_memory_cache import populate_cache_with_document


class MockAsyncByteStream(httpx.AsyncByteStream):
    """Classe helper para criar um stream de bytes assíncrono."""

    def __init__(self, content: bytes):
        self._content = content
        self._sent = False

    async def __aiter__(self):
        if not self._sent:
            self._sent = True
            yield self._content

    async def aclose(self):
        pass


def create_responses_api_sse_content(
    reasoning_content: str = "Analisando a pergunta...",
    response_content: str = "Esta é a resposta do modelo.",
) -> bytes:
    """Cria o conteúdo SSE para mock da Responses API.

    Args:
        reasoning_content: Conteúdo do reasoning/pensamento do modelo
        response_content: Conteúdo da resposta do modelo

    Returns:
        bytes: Conteúdo SSE completo formatado
    """
    lines = []

    # Eventos de reasoning (um por caractere ou palavra)
    # Para simplificar, enviamos em chunks maiores
    for word in reasoning_content.split():
        event = {
            "type": "response.reasoning_summary_text.delta",
            "delta": word + " ",
        }
        lines.append(f"data: {json.dumps(event)}")

    # Eventos de content
    for word in response_content.split():
        event = {
            "type": "response.output_text.delta",
            "delta": word + " ",
        }
        lines.append(f"data: {json.dumps(event)}")

    # Evento de conclusão
    lines.append("data: [DONE]")

    return "\n\n".join(lines).encode() + b"\n\n"


def populate_cache_correcao_ortografica():
    """Popula o cache com documento mockado para teste de correção ortográfica."""
    # Conteúdo com erros ortográficos intencionais
    mock_content = (
        "# Documento para Teste de Correção Ortográfica\n\n"
        "Ezte é um testo com algums erros ortograficos que precisam ser corrigidos.\n\n"
        "A Anatel é responsavel pela regulamentaçao do setor de telecomunicaçoes no Brazil.\n\n"
        "É importantíssimo que todoz os documentos sejam revisados antes da publicaçao."
    )

    mock_metadata = (
        "NumeroDocumento: 9999999\n"
        "EspecificacaoDocumento: Documento para Teste de Correção Ortográfica\n"
        "NomeTipoDocumento: Documento\n"
        "NumeroProcesso: 99999.999999/2025-99"
    )

    # Popular o cache usando a função de utilidade
    asyncio.run(
        populate_cache_with_document(
            id_documento="999999",
            id_documento_formatado="9999999",
            content=mock_content,
            metadata=mock_metadata,
            doc_tokens=150,
            doc_paged=False,
        )
    )


def mock_pergunta_uso_sei():
    """Mock para teste de pergunta sobre uso do SEI (sem documentos)."""
    # Mock para consulta de histórico (sem histórico prévio)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_historico_topico",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_historico_topico",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdTopico": "0",
                }
            )
        ],
        json={"status": "success", "data": []},
        status=200,
    )


def mock_correcao_ortografica():
    """Mock para o teste de correção ortográfica."""
    # Mock para consulta de histórico (sem histórico prévio)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_historico_topico",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_historico_topico",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdTopico": "0",
                }
            )
        ],
        json={"status": "success", "data": []},
        status=200,
    )

    # Mock para consulta de documento
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "999999",
                    "SinFiltraDocumentosRelevantes": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraAtivos": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "IdProcedimento": 999,
                    "NumeroDocumento": "9999999",
                    "EspecificacaoDocumento": "Documento para Teste de Correção Ortográfica",
                    "IdTipoDocumento": 1,
                    "DataInclusao": "30/10/2025",
                    "NomeTipoDocumento": "Documento",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "99999.999999/2025-99",
                    "IdDocumento": 999999,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta de conteúdo do documento
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "999999",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": (
                    "<html><body>"
                    "<h1>Documento para Teste de Correção Ortográfica</h1>"
                    "<p>Ezte é um testo com algums erros ortograficos que precisam ser corrigidos.</p>"
                    "<p>A Anatel é responsavel pela regulamentaçao do setor de telecomunicaçoes no Brazil.</p>"
                    "<p>É importantíssimo que todoz os documentos sejam revisados antes da publicaçao.</p>"
                    "</body></html>"
                ),
                "IdAnexos": None,
            },
        },
        status=200,
    )
