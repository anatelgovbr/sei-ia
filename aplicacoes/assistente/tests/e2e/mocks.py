import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import responses
from httpx import Response

from tests.utils.in_memory_cache import populate_cache_with_document


async def _generate_sse_stream(
    reasoning_content: str, response_content: str
) -> AsyncIterator[bytes]:
    """Gera um stream SSE simulando a Responses API do LiteLLM Proxy.

    Args:
        reasoning_content: Conteúdo do reasoning/pensamento do modelo
        response_content: Conteúdo da resposta do modelo

    Yields:
        bytes: Linhas SSE formatadas como bytes
    """
    # Envia eventos de reasoning
    for char in reasoning_content:
        event = {
            "type": "response.reasoning_summary_text.delta",
            "delta": char,
        }
        yield f"data: {json.dumps(event)}\n\n".encode()
        await asyncio.sleep(0)  # Permite troca de contexto

    # Envia eventos de content
    for char in response_content:
        event = {
            "type": "response.output_text.delta",
            "delta": char,
        }
        yield f"data: {json.dumps(event)}\n\n".encode()
        await asyncio.sleep(0)  # Permite troca de contexto

    # Envia evento de conclusão
    yield b"data: [DONE]\n\n"


def create_responses_api_mock_handler(
    reasoning_content: str = "Analisando a pergunta...",
    response_content: str = "Esta é a resposta do modelo.",
):
    """Cria um handler para mockar a Responses API SSE do LiteLLM Proxy.

    Esta função retorna um handler compatível com respx que simula
    a Responses API com streaming SSE.

    Args:
        reasoning_content: Conteúdo do reasoning/pensamento do modelo
        response_content: Conteúdo da resposta do modelo

    Returns:
        Callable que gera a resposta mockada
    """

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        async def stream_generator():
            async for chunk in _generate_sse_stream(
                reasoning_content, response_content
            ):
                yield chunk

        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            stream=httpx.AsyncByteStream(stream_generator()),
        )

    return mock_handler


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


def mock_memoria_topico_365():
    """Mock para o endpoint md_ia_consulta_historico_topico com IdTopico 365."""
    responses.add(
        responses.GET,  # Alterado para GET
        "http://mock-sei-api:8000/md_ia_consulta_historico_topico",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_historico_topico",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdTopico": "365",
                }
            )
        ],  # Adicionado matcher para os parâmetros de consulta
        json={
            "status": "success",
            "data": [
                {
                    "Pergunta": "O que é a Anatel?",
                    "Resposta": (
                        "A Agência Nacional de Telecomunicações (Anatel) é uma "
                        "entidade reguladora federal brasileira responsável por regulamentar, fiscalizar e "
                        "supervisionar o setor de telecomunicações no Brasil. Criada pela Lei Geral de "
                        "Telecomunicações (Lei nº 9.472) em 16 de julho de 1997, a Anatel tem como "
                        "principais atribuições:\n\n1. **Regulamentação**: Estabelecer normas e "
                        "regulamentos para o setor de telecomunicações, garantindo que as empresas operem "
                        "de acordo com as leis e padrões estabelecidos.\n\n2. **Fiscalização**: Monitorar "
                        "e fiscalizar as atividades das empresas de telecomunicações para assegurar que "
                        "cumpram as normas e regulamentos.\n\n3. **Gestão do Espectro de "
                        "Radiofrequências**: Administrar o uso do espectro de radiofrequências, que é um "
                        "recurso limitado e essencial para a operação de serviços de telecomunicações, "
                        "como telefonia móvel e radiodifusão.\n\n4. **Proteção dos Direitos dos "
                        "Consumidores**: Garantir que os direitos dos consumidores de serviços de "
                        "telecomunicações sejam respeitados, promovendo a qualidade dos serviços e a "
                        "transparência nas relações de consumo.\n\n5. **Promoção da Competição**: "
                        "Incentivar a competição no setor de telecomunicações, visando a melhoria dos "
                        "serviços e a redução de preços para os consumidores.\n\n6. **Expansão dos "
                        "Serviços**: Promover a universalização e a expansão dos serviços de "
                        "telecomunicações, especialmente em áreas remotas e de difícil acesso.\n\nA Anatel "
                        "é uma autarquia especial, o que significa que possui autonomia administrativa e "
                        "financeira, além de independência em suas decisões. Ela desempenha um papel "
                        "crucial no desenvolvimento e na modernização das telecomunicações no Brasil, "
                        "contribuindo para a inclusão digital e o acesso à informação."
                    ),
                    "DthCadastro": "22/07/2024 17:15:20",
                    "TotalTokens": 483,
                }
            ],
        },
        status=200,
    )


def mock_memoria_topico_varios_ids():
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_historico_topico",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_historico_topico",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdTopico": "365",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "Pergunta": "O que é a Anatel?",
                    "Resposta": (
                        "A Agência Nacional de Telecomunicações (Anatel) é uma "
                        "entidade reguladora federal brasileira responsável por regulamentar, fiscalizar e "
                        "supervisionar o setor de telecomunicações no Brasil. Criada pela Lei Geral de "
                        "Telecomunicações (Lei nº 9.472) em 16 de julho de 1997, a Anatel tem como "
                        "principais atribuições:\n\n1. **Regulamentação**: Estabelecer normas e "
                        "regulamentos para o setor de telecomunicações, garantindo que as empresas operem "
                        "de acordo com as leis e padrões estabelecidos.\n\n2. **Fiscalização**: Monitorar "
                        "e fiscalizar as atividades das empresas de telecomunicações para assegurar que "
                        "cumpram as normas e regulamentos.\n\n3. **Gestão do Espectro de "
                        "Radiofrequências**: Administrar o uso do espectro de radiofrequências, que é um "
                        "recurso limitado e essencial para a operação de serviços de telecomunicações, "
                        "como telefonia móvel e radiodifusão.\n\n4. **Proteção dos Direitos dos "
                        "Consumidores**: Garantir que os direitos dos consumidores de serviços de "
                        "telecomunicações sejam respeitados, promovendo a qualidade dos serviços e a "
                        "transparência nas relações de consumo.\n\n5. **Promoção da Competição**: "
                        "Incentivar a competição no setor de telecomunicações, visando a melhoria dos "
                        "serviços e a redução de preços para os consumidores.\n\n6. **Expansão dos "
                        "Serviços**: Promover a universalização e a expansão dos serviços de "
                        "telecomunicações, especialmente em áreas remotas e de difícil acesso.\n\nA Anatel "
                        "é uma autarquia especial, o que significa que possui autonomia administrativa e "
                        "financeira, além de independência em suas decisões. Ela desempenha um papel "
                        "crucial no desenvolvimento e na modernização das telecomunicações no Brasil, "
                        "contribuindo para a inclusão digital e o acesso à informação."
                    ),
                    "DthCadastro": "22/07/2024 17:15:20",
                    "TotalTokens": 483,
                }
            ],
        },
        status=200,
    )

    # Configurar o mock do serviço fake para IdTopico 1
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_historico_topico",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_historico_topico",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdTopico": "1",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "Pergunta": "Resumir #11954433",
                    "Resposta": (
                        "O documento #11954433 é um Voto do Presidente da Anatel, Carlos Manuel Baigorri, "
                        "referente ao processo nº 53500.011633/2013-00, cujo assunto é a aprovação da "
                        "publicação do Rol de Informações Classificadas e Desclassificadas em Grau de Sigilo "
                        "pela Anatel. Este rol deve ser publicado anualmente no portal da Agência, conforme "
                        "determina a Lei de Acesso à Informação (LAI), Lei nº 12.527/2011, e abrange o período "
                        "de 16 de maio de 2023 a 15 de maio de 2024.\n\nO voto propõe a aprovação da publicação "
                        "da inexistência de informações classificadas e desclassificadas em grau de sigilo pela "
                        "Anatel no período mencionado, em conformidade com a legislação vigente e as recomendações "
                        "da Controladoria-Geral da União (CGU). O documento detalha as obrigações legais e "
                        "regulamentares da Anatel em relação à transparência e ao acesso à informação, incluindo a "
                        "publicação anual do rol de informações classificadas e desclassificadas, bem como as "
                        "competências do Conselho Diretor da Anatel para a publicação desse rol.\n\nO voto também "
                        "menciona que, desde 2013, a Anatel publica a inexistência de informações classificadas e "
                        "desclassificadas em grau de sigilo, e que para o período de 16 de maio de 2023 a 15 de maio "
                        "de 2024, não foram detectadas informações classificadas ou desclassificadas em grau de sigilo. "
                        "Além disso, destaca-se a importância de cumprir o prazo estabelecido para a publicação anual, "
                        "que é até o dia 1º de junho de cada ano.\n\nEm conclusão, o Presidente da Anatel recomenda a "
                        "aprovação da publicação da inexistência de informações classificadas e desclassificadas no "
                        "portal da Agência na internet, conforme a Minuta de Resolução Interna 11955471, atendendo assim "
                        "às exigências da LAI e do Decreto nº 7.724/2012."
                    ),
                    "DthCadastro": "09/05/2024 18:17:34",
                    "TotalTokens": 8387,
                }
            ],
        },
        status=200,
    )


def mock_resumo_documento_interno(respx_mock):
    """Mock usando respx para chamadas httpx."""
    # Mock para md_ia_consulta_documento
    respx_mock.get(
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        params={
            "servico": "md_ia_consulta_documento",
            "SiglaSistema": "Usuario_IA",
            "IdentificacaoServico": "mock-identifier",
            "IdDocumentos": "58",
            "SinFiltraDocumentosRelevantes": "N",
            "SinFiltraBloqueados": "N",
            "SinFiltraAtivos": "N",
        },
    ).mock(
        return_value=Response(
            200,
            json={
                "status": "success",
                "data": [
                    {
                        "IdProcedimento": 44,
                        "NumeroDocumento": "0000046",
                        "EspecificacaoDocumento": "Despacho Descisório de Homologação de Contrato de Interconexão",
                        "IdTipoDocumento": 4,
                        "DataInclusao": "26/12/2014",
                        "NomeTipoDocumento": "Despacho Decisório",
                        "StaTipoDocumento": "I",
                        "NomeArquivo": "",
                        "NumeroProcesso": "53500.000052/2006-13",
                        "IdDocumento": 58,
                    }
                ],
            },
        )
    )

    # Mock para md_ia_consulta_conteudo_documento
    respx_mock.get(
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        params={
            "servico": "md_ia_consulta_conteudo_documento",
            "SiglaSistema": "Usuario_IA",
            "IdentificacaoServico": "mock-identifier",
            "IdDocumento": "58",
        },
    ).mock(
        return_value=Response(
            200,
            json={
                "status": "success",
                "data": {
                    "TipoConteudo": "text/html",
                    "ConteudoDocumento": "Despacho Decisório - Homologação de Contrato de Interconexão",
                    "IdAnexos": None,
                },
            },
        )
    )

    # Mock para md_ia_consulta_processo
    respx_mock.get(
        responses.GET,  # Alterado para GET
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "44",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],  # Adicionado matcher para os parâmetros de consulta
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53500.000052/2006-13",
                    "EspecificacaoProcesso": "",
                    "IdTipoProcesso": 100000860,
                    "TipoProcesso": "Homologação de Contratos: Interconexão",
                    "IdUnidadeGeradoraProcesso": 110000839,
                    "SiglaUnidadeGeradoraProcesso": "Protocolo.Sede",
                    "DescricaoUnidadeGeradoraProcesso": "Protocolo da Sede",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": None,
                    "IdProcessosAnexados": [],
                    "Interessados": [
                        {
                            "IdInteressado": 100383155,
                            "NomeInteressado": "TELEMAR NORTE LESTE SA. - EM RECUPERACAO JUDICIAL",
                        },
                        {
                            "IdInteressado": 100131799,
                            "NomeInteressado": "Mario Girasole",
                        },
                        {"IdInteressado": 100390071, "NomeInteressado": "Tim S A"},
                        {
                            "IdInteressado": 100002350,
                            "NomeInteressado": "Maxitel S.A. (Área 4)",
                        },
                    ],
                    "IdProcedimento": 44,
                }
            ],
        },
        status=200,
    )

    # Mock para histórico de tópico (sem histórico prévio para IdTopico 0)
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

    # Mock para metadados de procedimentos
    responses.add(
        responses.POST,
        "http://mock-sei-api:8000/md_ia_consulta_metadados_procedimento",
        json={
            "status": "success",
            "data": [
                {
                    "IdProcedimento": 44,
                    "NumeroProcesso": "53500.000052/2006-13",
                    "EspecificacaoProcesso": "",
                    "IdTipoProcesso": 100000860,
                    "TipoProcesso": "Homologação de Contratos: Interconexão",
                }
            ],
        },
        status=200,
    )


def mock_resumo_documento_externo_paginado():
    with open("tests/e2e/external_13631856.pdf", "rb") as f:
        pdf_data = f.read()

    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "13631856",
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
                    "IdProcedimento": 13428025,
                    "NumeroDocumento": "12118331",
                    "EspecificacaoDocumento": "",
                    "IdTipoDocumento": 63,
                    "DataInclusao": "13/06/2024",
                    "NomeTipoDocumento": "Relatório",
                    "StaTipoDocumento": "X",
                    "NomeArquivo": "220524.pdf",
                    "NumeroProcesso": "53504.003500/2024-74",
                    "IdDocumento": 13631856,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta de processo
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "13428025",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53504.003500/2024-74",
                    "EspecificacaoProcesso": "Conformidade de Registro de Gestão - Maio/2024",
                    "IdTipoProcesso": 100000266,
                    "TipoProcesso": "Contabilidade: Conformidade de Gestão",
                    "IdUnidadeGeradoraProcesso": 110000997,
                    "SiglaUnidadeGeradoraProcesso": "GR01AF",
                    "DescricaoUnidadeGeradoraProcesso": "Processo de Administração e Finanças",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": [
                        {"SiglaUnidadeGeradoraProcesso": "GR01AF", "Especificacao": ""}
                    ],
                    "IdProcessosAnexados": [],
                    "Interessados": [
                        {
                            "IdInteressado": 100014460,
                            "NomeInteressado": "Coordenador Regional de Processo de Administração e Finanças no Estado de São Paulo (GR01AF)",
                        }
                    ],
                    "IdProcedimento": 13428025,
                }
            ],
        },
        status=200,
    )

    # Mock para download do arquivo binário - ESTE É O PONTO PRINCIPAL
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_download_arquivo_documento_externo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_download_arquivo_documento_externo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "13631856",
                }
            )
        ],
        body=pdf_data,  # Dados binários do PDF
        headers={"Content-Type": "application/pdf"},
        status=200,
    )


def mock_citacao_de_dois_documentos_que_cabem_no_contexto_e_nao_acionam_rag():
    with open("tests/e2e/external_13631856.pdf", "rb") as f:
        pdf_data = f.read()

    # Mock para consulta de documento (2 documentos: 13631856)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "13631856",
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
                    "IdProcedimento": 13428025,
                    "NumeroDocumento": "12118331",
                    "EspecificacaoDocumento": "",
                    "IdTipoDocumento": 63,
                    "DataInclusao": "13/06/2024",
                    "NomeTipoDocumento": "Relatório",
                    "StaTipoDocumento": "X",
                    "NomeArquivo": "220524.pdf",
                    "NumeroProcesso": "53504.003500/2024-74",
                    "IdDocumento": 13631856,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta de documento (2 documentos: 650229)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "650229",
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
                    "IdProcedimento": 594199,
                    "NumeroDocumento": "0546979",
                    "EspecificacaoDocumento": "Despacho de aplicação de sanção",
                    "IdTipoDocumento": 4,
                    "DataInclusao": "06/06/2016",
                    "NomeTipoDocumento": "Despacho Decisório",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "53500.023651/2015-61",
                    "IdDocumento": 650229,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta de processo (procedimento 13428025)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "13428025",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53504.003500/2024-74",
                    "EspecificacaoProcesso": "Conformidade de Registro de Gestão - Maio/2024",
                    "IdTipoProcesso": 100000266,
                    "TipoProcesso": "Contabilidade: Conformidade de Gestão",
                    "IdUnidadeGeradoraProcesso": 110000997,
                    "SiglaUnidadeGeradoraProcesso": "GR01AF",
                    "DescricaoUnidadeGeradoraProcesso": "Processo de Administração e Finanças",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": [
                        {"SiglaUnidadeGeradoraProcesso": "GR01AF", "Especificacao": ""}
                    ],
                    "IdProcessosAnexados": [],
                    "Interessados": [
                        {
                            "IdInteressado": 100014460,
                            "NomeInteressado": "Coordenador Regional de Processo de Administração e Finanças no Estado de São Paulo (GR01AF)",
                        }
                    ],
                    "IdProcedimento": 13428025,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta de processo (procedimento 594199)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "594199",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53500.023651/2015-61",
                    "EspecificacaoProcesso": "Procedimento de Aplicação de Sanção: Oi Móvel S.A.",
                    "IdTipoProcesso": 100000026,
                    "TipoProcesso": "Sanção: Aplicação de Sanção",
                    "IdUnidadeGeradoraProcesso": 110000003,
                    "SiglaUnidadeGeradoraProcesso": "PFER",
                    "DescricaoUnidadeGeradoraProcesso": "Processo de Fiscalização e Enforcement",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": None,
                    "IdProcessosAnexados": [],
                    "Interessados": [
                        {"IdInteressado": 100383155, "NomeInteressado": "Oi Móvel S.A."}
                    ],
                    "IdProcedimento": 594199,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta conteúdo documento 13631856 (documento externo - PDF)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_download_arquivo_documento_externo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_download_arquivo_documento_externo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "13631856",
                }
            )
        ],
        body=pdf_data,
        headers={"Content-Type": "application/pdf"},
        status=200,
    )

    # Mock para consulta conteúdo documento 650229 (documento interno)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "650229",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": "<!DOCTYPE html><html><body><h1>Despacho de aplicação de sanção</h1><p>Processo nº [NUMERO_PROCESSO] - Procedimento de Aplicação de Sanção contra [EMPRESA]</p><p>Este despacho refere-se à aplicação de sanção administrativa à empresa [EMPRESA] por descumprimento de obrigações regulamentares.</p></body></html>",
                "IdAnexos": None,
            },
        },
        status=200,
    )


def mock_citacao_de_dois_documentos_que_cabem_no_contexto_para_geracao_de_novos_documentos():
    responses.add(
        responses.GET,  # Alterado para GET
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "58",
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
                    "IdProcedimento": 44,
                    "NumeroDocumento": "0000046",
                    "EspecificacaoDocumento": "Despacho Descisório de Homologação de Contrato de Interconexão",
                    "IdTipoDocumento": 4,
                    "DataInclusao": "26/12/2014",
                    "NomeTipoDocumento": "Despacho Decisório",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "53500.000052/2006-13",
                    "IdDocumento": 58,
                }
            ],
        },
        status=200,
    )

    # Adicionar mock para o serviço md_ia_consulta_conteudo_documento para o id documento 58
    responses.add(
        responses.GET,  # Alterado para GET
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "58",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd"><html lang="pt-br"><head><meta http-equiv="Pragma" content="no-cache" /><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1"><style type="text/css">/* CSS original mantido conforme enviado */ p.Citacao {font-size:10pt;font-family:Calibri;word-wrap:normal;margin:4pt 0 4pt 160px;text-align:justify;} p.Item_Alinea_Letra {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt 6pt 6pt 120px;counter-increment:letra_minuscula;} p.Item_Alinea_Letra:before {content:counter(letra_minuscula, lower-latin) ") ";display:inline-block;width:5mm;font-weight:normal;} p.Item_Inciso_Romano {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0mm;margin:6pt 6pt 6pt 120px;counter-increment:romano_maiusculo;counter-reset:letra_minuscula;} p.Item_Inciso_Romano:before {content:counter(romano_maiusculo, upper-roman) " - ";display:inline-block;width:15mm;font-weight:normal;} p.Item_Nivel1 {text-transform:uppercase;font-weight:bold;background-color:#e6e6e6;font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;counter-increment:item-n1;counter-reset:item-n2 item-n3 item-n4 romano_maiusculo letra_minuscula;} p.Item_Nivel1:before {content:counter(item-n1) ".";display:inline-block;width:25mm;font-weight:normal;} p.Item_Nivel2 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:item-n2;counter-reset:item-n3 item-n4 romano_maiusculo letra_minuscula;} p.Item_Nivel2:before {content:counter(item-n1) "." counter(item-n2) ".";display:inline-block;width:25mm;font-weight:normal;} p.Item_Nivel3 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:item-n3;counter-reset:item-n4 romano_maiusculo letra_minuscula;} p.Item_Nivel3:before {content:counter(item-n1) "." counter(item-n2) "." counter(item-n3) ".";display:inline-block;width:25mm;font-weight:normal;} p.Item_Nivel4 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:item-n4;counter-reset:romano_maiusculo letra_minuscula;} p.Item_Nivel4:before {content:counter(item-n1) "." counter(item-n2) "." counter(item-n3) "."  counter(item-n4) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel1 {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0mm;margin:6pt;counter-increment:paragrafo-n1;counter-reset:paragrafo-n2 paragrafo-n3 romano_maiusculo letra_minuscula;} p.Paragrafo_Numerado_Nivel1:before {content:counter(paragrafo-n1) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel2 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:paragrafo-n2;counter-reset:paragrafo-n3 romano_maiusculo letra_minuscula;} p.Paragrafo_Numerado_Nivel2:before {content:counter(paragrafo-n1) "." counter(paragrafo-n2) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel3 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:paragrafo-n3;counter-reset:romano_maiusculo letra_minuscula;} p.Paragrafo_Numerado_Nivel3:before {content:counter(paragrafo-n1) "." counter(paragrafo-n2) "." counter(paragrafo-n3) ".";display:inline-block;width:25mm;font-weight:normal;} p.Tabela_Texto_8 {font-size:8pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:0 3pt 0 3pt;} p.Tabela_Texto_Alinhado_Direita {font-size:11pt;font-family:Calibri;text-align:right;word-wrap:normal;margin:0 3pt 0 3pt;} p.Tabela_Texto_Alinhado_Esquerda {font-size:11pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:0 3pt 0 3pt;} p.Tabela_Texto_Centralizado {font-size:11pt;font-family:Calibri;text-align:center;word-wrap:normal;margin:0 3pt 0;} p.Tachado {font-size:11pt;font-family:Calibri;text-indent:1.18in;text-align:justify;word-wrap:normal;text-decoration:line-through;} p.Texto_Alinhado_Direita {font-size:12pt;font-family:Calibri;text-align:right;word-wrap:normal;margin:6pt;} p.Texto_Alinhado_Esquerda {font-size:12pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:6pt;} p.Texto_Alinhado_Esquerda_Espacamento_Simples {font-size:12pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:0;} p.Texto_Alinhado_Esquerda_Espacamento_Simples_Maiusc {font-size:12pt;font-family:Calibri;text-align:left;text-transform:uppercase;word-wrap:normal;margin:0;} p.Texto_Centralizado {font-size:12pt;font-family:Calibri;text-align:center;word-wrap:normal;margin:6pt;} p.Texto_Centralizado_Maiusculas {font-size:13pt;font-family:Calibri;text-align:center;text-transform:uppercase;word-wrap:normal;} p.Texto_Centralizado_Maiusculas_Negrito {font-weight:bold;font-size:13pt;font-family:Calibri;text-align:center;text-transform:uppercase;word-wrap:normal;} p.Texto_Espaco_Duplo_Recuo_Primeira_Linha {letter-spacing:0.2em;font-weight:bold;font-size:12pt;font-family:Calibri;text-indent:25mm;text-align:justify;word-wrap:normal;margin:6pt;} p.Texto_Fundo_Cinza_Maiusculas_Negrito {text-transform:uppercase;font-weight:bold;background-color:#e6e6e6;font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;} p.Texto_Fundo_Cinza_Negrito {font-weight:bold;background-color:#e6e6e6;font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;} p.Texto_Justificado {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;} p.Texto_Justificado_Maiusculas {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;text-transform:uppercase;} p.Texto_Justificado_Recuo_Primeira_Linha {font-size:12pt;font-family:Calibri;text-indent:25mm;text-align:justify;word-wrap:normal;margin:6pt;} p.Texto_Justificado_Recuo_Primeira_Linha_Esp_Simples {font-size:12pt;font-family:Calibri;text-indent:25mm;text-align:justify;word-wrap:normal;margin:0 0 0 6pt;} p.Texto_Mono_Espacado {font-size:8pt;font-family:Calibri;text-align:left;white-space:pre;word-wrap:normal;margin:2pt;} </style><title>:: SEI / Órgão Público - [XXXXXX] - Despacho Decisório (anonimizado) ::</title></head><body><p class="Texto_Centralizado_Maiusculas"> Despacho Decisório nº [NÚMERO]/[ANO]/SEI/[UNIDADE]/[UNIDADE]</p><p class="Texto_Justificado_Recuo_Primeira_Linha">&nbsp;&nbsp;</p><p class="Texto_Justificado_Recuo_Primeira_Linha">Processo nº [NÚMERO_PROCESSO]</p><p class="Texto_Justificado_Recuo_Primeira_Linha">Interessado: [EMPRESA_A], [EMPRESA_B], [EMPRESA_C], [EMPRESA_D], [EMPRESA_E]</p><p class="Texto_Justificado_Recuo_Primeira_Linha">&nbsp;&nbsp;</p><p class="Texto_Justificado_Recuo_Primeira_Linha">&nbsp;</p><p class="Texto_Justificado_Recuo_Primeira_Linha"><strong>O SUPERINTENDENTE DE COMPETIÇÃO DA AGÊNCIA NACIONAL DE TELECOMUNICAÇÕES</strong>, no uso das atribuições que lhe foram conferidas pelo art. 159, inciso I, do Regimento Interno da Anatel, aprovado pela <a href="http://legislacao.anatel.gov.br/resolucoes/2013/450-resolucao-612" target="_blank">Resolução nº 612, de 29 de abril de 2013</a>;</p><p class="Texto_Justificado_Recuo_Primeira_Linha">CONSIDERANDO o disposto no Regulamento Geral de Interconexão, aprovado pela <a href="http://legislacao.anatel.gov.br/resolucoes/2005/167-resolucao-410" target="_blank">Resolução nº 410, de 11 de julho de 2005</a>, em especial o seu art. 40; e</p><p class="Texto_Espaco_Duplo_Recuo_Primeira_Linha"><strong>DECIDE:</strong></p><p class="Paragrafo_Numerado_Nivel1" style="margin-left: 120px;">Homologar o Termo Aditivo nº [NÚMERO_TERMO] ao Contrato de Interconexão Classe II entre a rede de suporte à prestação do Serviço Móvel Pessoal - SMP de [EMPRESA_B], CNPJ nº [CNPJ_1], e a rede de suporte à prestação do Serviço Telefônico Fixo Comutado - STFC de [EMPRESA_A], CNPJ nº [CNPJ_2], nas modalidades Longa Distância Nacional e Longa Distância Internacional.</p><p class="Paragrafo_Numerado_Nivel1" style="margin-left: 120px;">Este Despacho Decisório entra em vigor na data de sua publicação.</p></body></html>',
                "IdAnexos": None,
            },
        },
        status=200,
    )

    # Adicionar mock para o serviço md_ia_consulta_documento para o id documento 390
    responses.add(
        responses.GET,  # Alterado para GET
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "390",
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
                    "IdProcedimento": 96,
                    "NumeroDocumento": "0000288",
                    "EspecificacaoDocumento": "Homologação de Contrato de Interconexão",
                    "IdTipoDocumento": 4,
                    "DataInclusao": "05/01/2015",
                    "NomeTipoDocumento": "Despacho Decisório",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "53500.027458/2014-45",
                    "IdDocumento": 390,
                }
            ],
        },
        status=200,
    )

    # Adicionar mock para o serviço md_ia_consulta_conteudo_documento para o id documento 390
    responses.add(
        responses.GET,  # Alterado para GET
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "390",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd"><html lang="pt-br"><head><meta http-equiv="Pragma" content="no-cache" /><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1"><style type="text/css">/* CSS original mantido conforme enviado */ p.Citacao {font-size:10pt;font-family:Calibri;word-wrap:normal;margin:4pt 0 4pt 160px;text-align:justify;} p.Item_Alinea_Letra {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;... /* e assim por diante, mantendo todo o CSS original */}</style><title>:: SEI / [Órgão Público] - [IDENTIFICADOR] - Despacho Decisório (anonimizado) ::</title></head><body><p class="Texto_Centralizado_Maiusculas">Despacho Decisório nº [NUMERO]/[ANO]/SEI/[UNIDADE]/[UNIDADE]</p><p class="Texto_Justificado_Recuo_Primeira_Linha">&nbsp;&nbsp;</p><p class="Texto_Justificado_Recuo_Primeira_Linha">Processo nº [NUMERO_PROCESSO]</p><p class="Texto_Justificado_Recuo_Primeira_Linha">Interessado: [EMPRESA_A], [EMPRESA_B]</p><p class="Texto_Justificado_Recuo_Primeira_Linha">&nbsp;&nbsp;</p><p class="Texto_Justificado_Recuo_Primeira_Linha"><strong>O SUPERINTENDENTE DE COMPETIÇÃO DA AGÊNCIA NACIONAL DE TELECOMUNICAÇÕES</strong>, no uso das atribuições que lhe foram conferidas pelo art. 159, inciso I, do Regimento Interno da Anatel, aprovado pela <a href="http://legislacao.anatel.gov.br/resolucoes/2013/450-resolucao-612" target="_blank">Resolução nº 612, de 29 de abril de 2013</a>;</p><p class="Texto_Justificado_Recuo_Primeira_Linha">CONSIDERANDO o disposto no Regulamento Geral de Interconexão, aprovado pela <a href="http://legislacao.anatel.gov.br/resolucoes/2005/167-resolucao-410" target="_blank">Resolução nº 410, de 11 de julho de 2005</a>, em especial o seu art. 40,</p><p class="Texto_Espaco_Duplo_Recuo_Primeira_Linha"><strong>DECIDE:</strong></p><p class="Paragrafo_Numerado_Nivel1" style="margin-left: 120px;">Homologar Contrato de Interconexão Classe I entre as redes de suporte à prestação do Serviço Telefônico Fixo Comutado - STFC de [EMPRESA_A], CNPJ nº [CNPJ_1], nas modalidades Longa Distância Nacional e Internacional e da [EMPRESA_B], CNPJ nº [CNPJ_2], na modalidade Local.</p><p class="Paragrafo_Numerado_Nivel1" style="margin-left: 120px;">Este Despacho Decisório entra em vigor na data de sua publicação.</p></body></html>',
                "IdAnexos": None,
            },
        },
        status=200,
    )

    # Mock para consulta de processo (procedimento 96)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "96",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53500.027458/2014-45",
                    "EspecificacaoProcesso": "",
                    "IdTipoProcesso": 100000860,
                    "TipoProcesso": "Homologação de Contratos: Interconexão",
                    "IdUnidadeGeradoraProcesso": 110000839,
                    "SiglaUnidadeGeradoraProcesso": "Protocolo.Sede",
                    "DescricaoUnidadeGeradoraProcesso": "Protocolo da Sede",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": None,
                    "IdProcessosAnexados": [],
                    "Interessados": [
                        {
                            "IdInteressado": 100383155,
                            "NomeInteressado": "TELEMAR NORTE LESTE SA. - EM RECUPERACAO JUDICIAL",
                        },
                        {
                            "IdInteressado": 100002366,
                            "NomeInteressado": "AUE PROVEDOR DE INTERNET LTDA",
                        },
                    ],
                    "IdProcedimento": 96,
                }
            ],
        },
        status=200,
    )


def mock_citacao_de_dois_documentos_que_nao_cabem_no_contexto_e_deveriam_acionar_resumo():
    with open("tests/e2e/external_13631856.pdf", "rb") as f:
        pdf_data = f.read()

    # Mock para consulta de documento 2138246:
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "2138246",
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
                    "IdProcedimento": 147322,
                    "NumeroDocumento": "1817816",
                    "EspecificacaoDocumento": "",
                    "IdTipoDocumento": 7,
                    "DataInclusao": "25/08/2017",
                    "NomeTipoDocumento": "Análise",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "53528.006849/2012-56",
                    "IdDocumento": 2138246,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta conteúdo documento 2138246 (documento interno)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "2138246",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": "<!DOCTYPE html><html><body><h1>Despacho de aplicação de sanção</h1><p>Processo nº [NUMERO_PROCESSO] - Procedimento de Aplicação de Sanção contra [EMPRESA]</p><p>Este despacho refere-se à aplicação de sanção administrativa à empresa [EMPRESA] por descumprimento de obrigações regulamentares.</p></body></html>",
                "IdAnexos": None,
            },
        },
        status=200,
    )

    # Mock para consulta de processo (procedimento 147322)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "147322",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53528.006849/2012-56",
                    "EspecificacaoProcesso": "",
                    "IdTipoProcesso": 100000590,
                    "TipoProcesso": "PADO: Irregularidade Técnica",
                    "IdUnidadeGeradoraProcesso": 110001193,
                    "SiglaUnidadeGeradoraProcesso": "Protocolo.RS",
                    "DescricaoUnidadeGeradoraProcesso": "Protocolo do Rio Grande do Sul",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": None,
                    "IdProcessosAnexados": ["140628"],
                    "Interessados": [
                        {
                            "IdInteressado": 100023183,
                            "NomeInteressado": "ASSOCIACAO CULTURAL RADIO COMUNITARIA DE AJURICABARS",
                        }
                    ],
                    "IdProcedimento": 147322,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta de documento 3276527:
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "3276527",
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
                    "IdProcedimento": 159274,
                    "NumeroDocumento": "2839858",
                    "EspecificacaoDocumento": "",
                    "IdTipoDocumento": 7,
                    "DataInclusao": "13/06/2018",
                    "NomeTipoDocumento": "Análise",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "53560.003106/2006-80",
                    "IdDocumento": 3276527,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta conteúdo documento 3276527 (documento interno)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "3276527",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">\n<html lang="pt-br" >\n<head>\n<meta http-equiv="Pragma" content="no-cache" />\n<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">\n<style type="text/css">\np.Citacao {font-size:10pt;font-family:Calibri;text-align:justify;word-wrap:normal;margin:4pt 0 4pt 160px;} p.Item_Alinea_Letra {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt 6pt 6pt 120px;counter-increment:letra_minuscula;} p.Item_Alinea_Letra:before {content:counter(letra_minuscula, lower-latin) ") ";display:inline-block;width:5mm;font-weight:normal;} p.Item_Inciso_Romano {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0mm;margin:6pt 6pt 6pt 120px;counter-increment:romano_maiusculo;counter-reset:letra_minuscula;} p.Item_Inciso_Romano:before {content:counter(romano_maiusculo, upper-roman) " - ";display:inline-block;width:15mm;font-weight:normal;} p.Item_Nivel1 {text-transform:uppercase;font-weight:bold;background-color:#e6e6e6;font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;counter-increment:item-n1;counter-reset:item-n2 item-n3 item-n4 romano_maiusculo letra_minuscula;} p.Item_Nivel1:before {content:counter(item-n1) ".";display:inline-block;width:25mm;font-weight:normal;} p.Item_Nivel2 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:item-n2;counter-reset:item-n3 item-n4 romano_maiusculo letra_minuscula;} p.Item_Nivel2:before {content:counter(item-n1) "." counter(item-n2) ".";display:inline-block;width:25mm;font-weight:normal;} p.Item_Nivel3 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:item-n3;counter-reset:item-n4 romano_maiusculo letra_minuscula;margin-left:40px;} p.Item_Nivel3:before {content:counter(item-n1) "." counter(item-n2) "." counter(item-n3) ".";display:inline-block;width:25mm;font-weight:normal;} p.Item_Nivel4 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:item-n4;counter-reset:romano_maiusculo letra_minuscula;margin-left:80px;} p.Item_Nivel4:before {content:counter(item-n1) "." counter(item-n2) "." counter(item-n3) "."  counter(item-n4) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel1 {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0mm;margin:6pt;counter-increment:paragrafo-n1;counter-reset:paragrafo-n2 paragrafo-n3 paragrafo-n4 romano_maiusculo letra_minuscula;} p.Paragrafo_Numerado_Nivel1:before {content:counter(paragrafo-n1) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel2 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:paragrafo-n2;counter-reset:paragrafo-n3 paragrafo-n4 romano_maiusculo letra_minuscula;margin-left:40px;} p.Paragrafo_Numerado_Nivel2:before {content:counter(paragrafo-n1) "." counter(paragrafo-n2) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel3 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:paragrafo-n3;counter-reset:paragrafo-n4 romano_maiusculo letra_minuscula;margin-left:80px;} p.Paragrafo_Numerado_Nivel3:before {content:counter(paragrafo-n1) "." counter(paragrafo-n2) "." counter(paragrafo-n3) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel4 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:paragrafo-n4;counter-reset:romano_maiusculo letra_minuscula;margin-left:120px;} p.Paragrafo_Numerado_Nivel4:before {content:counter(paragrafo-n1) "." counter(paragrafo-n2) "." counter(paragrafo-n3) "." counter(paragrafo-n4) ".";display:inline-block;width:25mm;font-weight:normal;} p.Tabela_Texto_8 {font-size:8pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:0 3pt 0 3pt;} p.Tabela_Texto_Alinhado_Direita {font-size:11pt;font-family:Calibri;text-align:right;word-wrap:normal;margin:0 3pt 0 3pt;} p.Tabela_Texto_Alinhado_Esquerda {font-size:11pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:0 3pt 0 3pt;} p.Tabela_Texto_Centralizado {font-size:11pt;font-family:Calibri;text-align:center;word-wrap:normal;margin:0 3pt 0;} p.Texto_Alinhado_Direita {font-size:12pt;font-family:Calibri;text-align:right;word-wrap:normal;margin:6pt;} p.Texto_Alinhado_Esquerda {font-size:12pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:6pt;} p.Texto_Alinhado_Esquerda_Espacamento_Simples {font-size:12pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:0 0 0 6pt;} p.Texto_Alinhado_Esquerda_Espacamento_Simples_Maiusc {font-size:12pt;font-family:Calibri;text-align:left;text-transform:uppercase;word-wrap:normal;margin:0 0 0 6pt;} p.Texto_Centralizado {font-size:12pt;font-family:Calibri;text-align:center;word-wrap:normal;margin:6pt;} p.Texto_Centralizado_Maiusculas {font-size:13pt;font-family:Calibri;text-align:center;text-transform:uppercase;word-wrap:normal;} p.Texto_Centralizado_Maiusculas_Negrito {font-weight:bold;font-size:13pt;font-family:Calibri;text-align:center;text-transform:uppercase;word-wrap:normal;} p.Texto_Espaco_Duplo_Recuo_Primeira_Linha {letter-spacing:1px;font-weight:bold;font-size:12pt;font-family:Calibri;text-indent:25mm;text-align:justify;word-wrap:normal;margin:6pt;} p.Texto_Fundo_Cinza_Maiusculas_Negrito {text-transform:uppercase;font-weight:bold;background-color:#e6e6e6;font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;} p.Texto_Fundo_Cinza_Negrito {font-weight:bold;background-color:#e6e6e6;font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;} p.Texto_Justificado {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;} p.Texto_Justificado_Maiusculas {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;text-transform:uppercase;} p.Texto_Justificado_Recuo_Primeira_Linha {font-size:12pt;font-family:Calibri;text-indent:25mm;text-align:justify;word-wrap:normal;margin:6pt;} p.Texto_Justificado_Recuo_Primeira_Linha_Esp_Simples {font-size:12pt;font-family:Calibri;text-indent:25mm;text-align:justify;word-wrap:normal;margin:0 0 0 6pt;} \n</style><title>SEI/ANATEL - 2839858 - Análise</title>\n</head>\n<body>\n<p class="Texto_Centralizado_Maiusculas">An&aacute;lise n&ordm; 129/2018/SEI/OR</p>\r\n<p class="Texto_Justificado">Processo n&ordm; 53560.003106/2006-80</p>\r\n\r\n<p class="Texto_Justificado">Interessado: EMPRESA TELECOM LTDA</p>\r\n<p class="Texto_Fundo_Cinza_Maiusculas_Negrito">CONSELHEIRO</p>\r\n\r\n<p class="Texto_Justificado_Recuo_Primeira_Linha"><strong>JOSE&nbsp; SILVA&nbsp;</strong><strong>SILVEIRA</strong></p>\r\n\r\n<p class="Item_Nivel1">ASSUNTO</p>\r\n\r\n<p class="Texto_Justificado"><esspan>Recurso Administrativo interposto em face de decis&atilde;o que aplicou <esspan class="__esHilite">multa</esspan>&nbsp;em virtude de irregularidades t&eacute;cnicas cometidas na presta&ccedil;&atilde;o do Servi&ccedil;o M&oacute;vel Pessoal (SMP).</esspan></p>\r\n\r\n<p class="Item_Nivel1">EMENTA</p>\r\n\r\n<p class="Texto_Justificado_Maiusculas">RECURSO ADMINISTRATIVO. PADO. IRREGULARIDADES T&Eacute;CNICAS. uso de faixa de frequ&ecirc;ncia de opera&ccedil;&atilde;o diferente do autorizado,&nbsp;altura do sistema irradiante acima do autorizado,&nbsp;polariza&ccedil;&atilde;o de antena diferente do autorizado&nbsp;e&nbsp;modelo do&nbsp;equipamento transmissor diferente do autorizado.&nbsp;INFRA&Ccedil;&Otilde;ES DE NATUREZA LEVE. <esspan>CONVERS&Atilde;O DA <esspan class="__esHilite">MULTA</esspan> EM ADVERT&Ecirc;NCIA</esspan><em><strong>.&nbsp;</strong></em>INDISPONIBILIDADE DE Relat&oacute;rio de Conformidade sobre Exposi&ccedil;&otilde;es a Campos El&eacute;tricos, Magn&eacute;ticos e Eletromagn&eacute;ticos - RNI.&nbsp; INFRA&Ccedil;&Atilde;O DE NATUREZA GRAVE. NECESSIDADE de utiliza&ccedil;&atilde;o da METODOLOGIA EM VIGOR &Agrave; &Eacute;POCA DO SANCIONAMENTO. PRINC&Iacute;PIO&nbsp;<em>TEMPUS&nbsp;REGIT&nbsp;ACTUM</em>. RASA/2003.&nbsp;REFORMA DE OF&Iacute;CIO DO VALOR DA SAN&Ccedil;&Atilde;O. INEXIST&Ecirc;NCIA DE ATENUANTES.&nbsp;AUS&Ecirc;NCIA DE INTIMA&Ccedil;&Atilde;O PARA APRESENTA&Ccedil;&Atilde;O DE ALEGA&Ccedil;&Otilde;ES FINAIS.&nbsp;INEXIST&Ecirc;NCIA DE PREJU&Iacute;ZO. CORRE&Ccedil;&Atilde;O DA IRREGULARIDADE&nbsp;N&Atilde;O AFASTA SEU COMETIMENTO. RECURSO CONHECIDO E PARCIALMENTE PROVIDO.&nbsp;</p>\r\n\r\n<p class="Texto_Justificado">1. Recurso Administrativo interposto pela EMPRESA TELECOM LTDA.,&nbsp;em face do Despacho n&ordm; 8.114/2015-Anatel, de 17&nbsp;de setembro&nbsp;de 2015, por meio do qual a Superintend&ecirc;ncia de Fiscaliza&ccedil;&atilde;o (SFI) aplicou san&ccedil;&atilde;o no valor de R$21.537,52 (vinte e um mil quinhentos e trinta e sete reais e cinquenta e dois centavos), em virtude da observa&ccedil;&atilde;o de irregularidades t&eacute;cnicas.</p>\r\n\r\n<p class="Texto_Justificado">2.&nbsp;N&atilde;o h&aacute;&nbsp;nulidade&nbsp;na aus&ecirc;ncia de&nbsp;notifica&ccedil;&atilde;o para apresenta&ccedil;&atilde;o de Alega&ccedil;&otilde;es Finais que n&atilde;o provocou dano &agrave; defesa da Recorrente, em raz&atilde;o do princ&iacute;pio&nbsp;<em>pas de&nbsp;nullit&eacute;&nbsp;sans&nbsp;grief.</em></p>\r\n\r\n<p class="Texto_Justificado">3. Eventual corre&ccedil;&atilde;o da conduta n&atilde;o afasta os efeitos jur&iacute;dicos do&nbsp;cometimento das irregularidades.</p>',
                "IdAnexos": None,
            },
        },
        status=200,
    )

    # Mock para consulta de processo (procedimento 159274)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "159274",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53560.003106/2006-80",
                    "EspecificacaoProcesso": "",
                    "IdTipoProcesso": 100000590,
                    "TipoProcesso": "PADO: Irregularidade Técnica",
                    "IdUnidadeGeradoraProcesso": 110001213,
                    "SiglaUnidadeGeradoraProcesso": "Protocolo.CE",
                    "DescricaoUnidadeGeradoraProcesso": "Protocolo do Ceará",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": None,
                    "IdProcessosAnexados": ["123577"],
                    "Interessados": [],
                    "IdProcedimento": 159274,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta de documento 13631856:
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "13631856",
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
                    "IdProcedimento": 13428025,
                    "NumeroDocumento": "12118331",
                    "EspecificacaoDocumento": "",
                    "IdTipoDocumento": 63,
                    "DataInclusao": "13/06/2024",
                    "NomeTipoDocumento": "Relatório",
                    "StaTipoDocumento": "X",
                    "NomeArquivo": "220524.pdf",
                    "NumeroProcesso": "53504.003500/2024-74",
                    "IdDocumento": 13631856,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta conteúdo documento 13631856 (documento interno)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "13631856",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "application/pdf",
                "ConteudoDocumento": "TRANSACAO        : IMPCONFREG\nUSUARIO          : 123.456.789-00\nARQUIVO GERADO EM: 10/06/2024 AS 21:51\n \n CRITERIO DE PESQUISA UTILIZADO:\n-------------------------------\nUNIDADE GESTORA     : 413002 - AGENCIA NACIONAL DE TELECOMUNICACOES-SP\nGESTAO              : 41231 - AGENCIA NACIONAL DE TELECOMUNICACOES\nDATA DO MOVIMENTO   : 22MAI24        QUANTIDADE EMITIDA\nDOCUMENTOS A SEREM GERADOS:          EMIT  TERC  TOTAL\nX OB - ORDEM BANCARIA                00008 00000 00008\nX PF - PROGRAMACAO FINANCEIRA        00001 00000 00001\nX NS - NOTA DE LANCAMENTO DE SISTEMA 00019 00000 00019\nABRANGENCIA: 1\n \n --------------------------------------------------------------------------------\n----------------------------------------------------\nSIAFI - SISTEMA INTEGRADO DE ADMINISTRACAO FINANCEIRA          CONFORMIDADE \nDIARIA EM 22MAI24                  PAGINA  -        1\nUNIDADE GESTORA/GESTAO : 413002 / 41231 - AGENCIA NACIONAL DE \nTELECOMUNICACOES-SP                              EMISSAO - 10/06/24\n                                                O R D E M    B A N C A R I A\nNUMERO  EMISSAO  DOM.BANCARIO EMITENTE FAVORECIDO                               \n       DOM.BANC. FAVORECIDO                VALOR\n000286  22MAI24  001/0712-997380632    JOÃO SILVA SANTOS               \n       341/4100-136748                    955,27\n       OBS: PROC 001228/24 DOC GERADO PELO SCDP. PCDP 001228/24 P/ PGTO. DE  2,5\nDIARIA(S)\n             REF. A VIAGEM EM TERRIT RIO NACIONAL NO PERIODO DE  27/05/2024 A  \n29/05/2024.\n  EVENTO INSCRICAO 1                    INSCRICAO 2                    CLASSIF.1\nCLASSIF.2 CL.ORC.1 CL.ORC.2                VALOR\n  401003 2024NE000001414                                                        \n          33901414                        955,27\n  531235 2024NE000001                   12345678901                             \n                                          955,27\n  561602 1120000000414C                                                         \n                                          955,27\n000287  22MAI24  001/0712-997380632    MARIA OLIVEIRA COSTA                           \n       001/8441-132                       955,27\n       OBS: PROC 001217/24 DOC GERADO PELO SCDP. PCDP 001217/24 P/ PGTO. DE  2,5\nDIARIA(S)\n             REF. A VIAGEM EM TERRIT RIO NACIONAL NO PERIODO DE  27/05/2024 A  \n29/05/2024.\n  EVENTO INSCRICAO 1                    INSCRICAO 2                    CLASSIF.1\nCLASSIF.2 CL.ORC.1 CL.ORC.2                VALOR\n  401003 2024NE000001414                                                        \n          33901414                        955,27\n  531235 2024NE000001                   98765432100                             \n                                          955,27\n  561602 1120000000414C                                                         \n                                          955,27\n000288  22MAI24  001/0712-997380632    PEDRO FERNANDES LIMA                  \n       341/2954-119091                    411,60\n       OBS: PROC 001237/24 DOC GERADO PELO SCDP. PCDP 001237/24 P/ PGTO. DE  1,5\nDIARIA(S)\n             REF. A VIAGEM EM TERRIT RIO NACIONAL NO PERIODO DE  27/05/2024 A  \n28/05/2024.\n  EVENTO INSCRICAO 1                    INSCRICAO 2                    CLASSIF.1\nCLASSIF.2 CL.ORC.1 CL.ORC.2                VALOR\n  401003 2024NE000001414                                                        \n          33901414                        411,60\n  531235 2024NE000001                   11122233445                             \n                                          411,60\n  561602 1120000000414C                                                         \n                                          411,60\n000289  22MAI24  001/0712-997380632    CARLOS ROBERTO SOUZA                 \n       001/4856-72397                     411,60\n       OBS: PROC 001285/24 DOC GERADO PELO SCDP. PCDP 001285/24 P/ PGTO. DE  1,5\nDIARIA(S)\n             REF. A VIAGEM EM TERRIT RIO NACIONAL NO PERIODO DE  27/05/2024 A  \n28/05/2024.\n  EVENTO INSCRICAO 1                    INSCRICAO 2                    CLASSIF.1\nCLASSIF.2 CL.ORC.1 CL.ORC.2                VALOR\n  401003 2024NE000001414                                                        \n          33901414                        411,60\n  531235 2024NE000001                   55544466778                             \n                                          411,60\n  561602 1120000000414C                                                         \n                                          411,60\n000290  22MAI24  001/0712-997380632    BANCO DO BRASIL SA                       \n       001/0712-FATURA                  9.591,40\n       NUMERO PROCESSO\n       53504.003743/2024-11\n       OBS: PAG.FATURA.SOR202444744135, DE 10/05/2024. REF.FORNECIMENTO DE  GUA \nE COLETA D\n            E ESGOTO PARA GR01 - PERIODO DE LEITURA:26/03/2024 A 26/04/2024. \nRETEN  O:9,45\n             POR CENTO DE R$10.534,20(AGUA/ESGOTO:R$10.534,20 E TAXA DE REGULA \nAO:R$52,68)\n            . ORDEM DE COMPRA:7885/2009/GR01. PROC:53504.008136/2009. \nSEI:53504.003743/202\n            4-11.\n  EVENTO INSCRICAO 1                    INSCRICAO 2                    CLASSIF.1\nCLASSIF.2 CL.ORC.1 CL.ORC.2                VALOR\n  401003 2024NE000028400                                                        \n          33903944                      9.538,72\n  401003 2024NE000029400                                                        \n          33904710                         52,68\n  531388 2024NE000029                                                  214110400\n          33904710                         52,68\n  531814 2024NE000028                                                  213110400\n          33903944                      9.538,72\n  561602 1120000000400C                                                         \n                                        9.591,40\n000291  22MAI24  001/0712-997380632    EMPRESA VIAGENS E TURISMO CORPORATIVO\nLTDA    237/2617-766569                  6.566,05\n       NUMERO PROCESSO\n       53504.003549/2024-27\n       OBS: PAG.FATURA.1186, DE 01/04/2024. REF:SERV.AGENCIAMENTO VIAGENS PARA V\nOS REGULA\n            RES INTERNACIONAIS/DOM STICOS PARA SERVIDORES DA GR01/SP(ADMINISTRA \nO) - MAR/\n            24. RETEN  O:2,40 E 1,00 PORCENTO DE R$6.640,15 E 7,05 POR CENTO DE \nR$163,16.\n            CONTRATO:104/2023-GR01. PROC:53504.009378/2023. \nSEI:53504.003549/2024-27.\n  EVENTO INSCRICAO 1                    INSCRICAO 2                    CLASSIF.1\nCLASSIF.2 CL.ORC.1 CL.ORC.2                VALOR\n  401003 2024NE000052400                                                        \n          33903301                      6.566,05\n  531814 2024NE000052                                                  213110400\n          33903301                      6.566,05\n  561602 1120000000400C                                                         \n                                        6.566,05",
            },
        },
        status=200,
    )

    # Mock para consulta de processo (procedimento 13428025)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "13428025",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53504.003500/2024-74",
                    "EspecificacaoProcesso": "Conformidade de Registro de Gestão - Maio/2024",
                    "IdTipoProcesso": 100000266,
                    "TipoProcesso": "Contabilidade: Conformidade de Gestão",
                    "IdUnidadeGeradoraProcesso": 110000997,
                    "SiglaUnidadeGeradoraProcesso": "GR01AF",
                    "DescricaoUnidadeGeradoraProcesso": "Processo de Administração e Finanças",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": [
                        {"SiglaUnidadeGeradoraProcesso": "GR01AF", "Especificacao": ""}
                    ],
                    "IdProcessosAnexados": [],
                    "Interessados": [
                        {
                            "IdInteressado": 100014460,
                            "NomeInteressado": "Coordenador Regional de Processo de Administração e Finanças no Estado de São Paulo (GR01AF)",
                        }
                    ],
                    "IdProcedimento": 13428025,
                }
            ],
        },
        status=200,
    )

    # Mock para download do arquivo binário - ESTE É O PONTO PRINCIPAL
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_download_arquivo_documento_externo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_download_arquivo_documento_externo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "13631856",
                }
            )
        ],
        body=pdf_data,  # Dados binários do PDF
        headers={"Content-Type": "application/pdf"},
        status=200,
    )


def mock_citacao_de_processo_que_nao_cabe_no_contexto_e_que_deveria_acionar_rag():
    # Mock para consulta de documento 2138246:
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "2138246",
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
                    "IdProcedimento": 147322,
                    "NumeroDocumento": "1817816",
                    "EspecificacaoDocumento": "",
                    "IdTipoDocumento": 7,
                    "DataInclusao": "25/08/2017",
                    "NomeTipoDocumento": "Análise",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "53528.006849/2012-56",
                    "IdDocumento": 2138246,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta conteúdo documento 2138246 (documento interno)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "2138246",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">\n<html lang="pt-br" >\n<head>\n<meta http-equiv="Pragma" content="no-cache" />\n<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">\n<style type="text/css"><!--/*--><![CDATA[/*><!--*/\np.Citacao {font-size:10pt;font-family:Calibri;text-align:justify;word-wrap:normal;margin:4pt 0 4pt 160px;} p.Item_Alinea_Letra {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt 6pt 6pt 120px;counter-increment:letra_minuscula;} p.Item_Alinea_Letra:before {content:counter(letra_minuscula, lower-latin) ") ";display:inline-block;width:5mm;font-weight:normal;} p.Item_Inciso_Romano {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0mm;margin:6pt 6pt 6pt 120px;counter-increment:romano_maiusculo;counter-reset:letra_minuscula;} p.Item_Inciso_Romano:before {content:counter(romano_maiusculo, upper-roman) " - ";display:inline-block;width:15mm;font-weight:normal;} p.Item_Nivel1 {text-transform:uppercase;font-weight:bold;background-color:#e6e6e6;font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;counter-increment:item-n1;counter-reset:item-n2 item-n3 item-n4 romano_maiusculo letra_minuscula;} p.Item_Nivel1:before {content:counter(item-n1) ".";display:inline-block;width:25mm;font-weight:normal;} p.Item_Nivel2 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:item-n2;counter-reset:item-n3 item-n4 romano_maiusculo letra_minuscula;} p.Item_Nivel2:before {content:counter(item-n1) "." counter(item-n2) ".";display:inline-block;width:25mm;font-weight:normal;} p.Item_Nivel3 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:item-n3;counter-reset:item-n4 romano_maiusculo letra_minuscula;margin-left:40px;} p.Item_Nivel3:before {content:counter(item-n1) "." counter(item-n2) "." counter(item-n3) ".";display:inline-block;width:25mm;font-weight:normal;} p.Item_Nivel4 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:item-n4;counter-reset:romano_maiusculo letra_minuscula;margin-left:80px;} p.Item_Nivel4:before {content:counter(item-n1) "." counter(item-n2) "." counter(item-n3) "."  counter(item-n4) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel1 {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0mm;margin:6pt;counter-increment:paragrafo-n1;counter-reset:paragrafo-n2 paragrafo-n3 paragrafo-n4 romano_maiusculo letra_minuscula;} p.Paragrafo_Numerado_Nivel1:before {content:counter(paragrafo-n1) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel2 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:paragrafo-n2;counter-reset:paragrafo-n3 paragrafo-n4 romano_maiusculo letra_minuscula;margin-left:40px;} p.Paragrafo_Numerado_Nivel2:before {content:counter(paragrafo-n1) "." counter(paragrafo-n2) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel3 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:paragrafo-n3;counter-reset:paragrafo-n4 romano_maiusculo letra_minuscula;margin-left:80px;} p.Paragrafo_Numerado_Nivel3:before {content:counter(paragrafo-n1) "." counter(paragrafo-n2) "." counter(paragrafo-n3) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel4 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:paragrafo-n4;counter-reset:romano_maiusculo letra_minuscula;margin-left:120px;} p.Paragrafo_Numerado_Nivel4:before {content:counter(paragrafo-n1) "." counter(paragrafo-n2) "." counter(paragrafo-n3) "." counter(paragrafo-n4) ".";display:inline-block;width:25mm;font-weight:normal;} p.Tabela_Texto_8 {font-size:8pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:0 3pt 0 3pt;} p.Tabela_Texto_Alinhado_Direita {font-size:11pt;font-family:Calibri;text-align:right;word-wrap:normal;margin:0 3pt 0 3pt;} p.Tabela_Texto_Alinhado_Esquerda {font-size:11pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:0 3pt 0 3pt;} p.Tabela_Texto_Centralizado {font-size:11pt;font-family:Calibri;text-align:center;word-wrap:normal;margin:0 3pt 0;} p.Tachado {font-size:11pt;font-family:Calibri;text-indent:1.18in;text-align:justify;word-wrap:normal;text-decoration:line-through;} p.Texto_Alinhado_Direita {font-size:12pt;font-family:Calibri;text-align:right;word-wrap:normal;margin:6pt;} p.Texto_Alinhado_Esquerda {font-size:12pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:6pt;} p.Texto_Alinhado_Esquerda_Espacamento_Simples {font-size:12pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:0 0 0 6pt;} p.Texto_Alinhado_Esquerda_Espacamento_Simples_Maiusc {font-size:12pt;font-family:Calibri;text-align:left;text-transform:uppercase;word-wrap:normal;margin:0 0 0 6pt;} p.Texto_Centralizado {font-size:12pt;font-family:Calibri;text-align:center;word-wrap:normal;margin:6pt;} p.Texto_Centralizado_Maiusculas {font-size:13pt;font-family:Calibri;text-align:center;text-transform:uppercase;word-wrap:normal;} p.Texto_Centralizado_Maiusculas_Negrito {font-weight:bold;font-size:13pt;font-family:Calibri;text-align:center;text-transform:uppercase;word-wrap:normal;} p.Texto_Espaco_Duplo_Recuo_Primeira_Linha {letter-spacing:1px;font-weight:bold;font-size:12pt;font-family:Calibri;text-indent:25mm;text-align:justify;word-wrap:normal;margin:6pt;} p.Texto_Fundo_Cinza_Maiusculas_Negrito {text-transform:uppercase;font-weight:bold;background-color:#e6e6e6;font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;} p.Texto_Fundo_Cinza_Negrito {font-weight:bold;background-color:#e6e6e6;font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;} p.Texto_Justificado {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;} p.Texto_Justificado_Maiusculas {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;text-transform:uppercase;} p.Texto_Justificado_Recuo_Primeira_Linha {font-size:12pt;font-family:Calibri;text-indent:25mm;text-align:justify;word-wrap:normal;margin:6pt;} p.Texto_Justificado_Recuo_Primeira_Linha_Esp_Simples {font-size:12pt;font-family:Calibri;text-indent:25mm;text-align:justify;word-wrap:normal;margin:0 0 0 6pt;} p.Texto_Mono_Espacado {font-size:10pt;font-family:Calibri;text-align:justify;word-wrap:normal;margin:6pt;} \n/*]]>*/-->\n</style><title>SEI/ANATEL - 1817816 - Análise</title>\n</head>\n<body>\n<p class="Texto_Centralizado_Maiusculas">An&aacute;lise n&ordm; 192/2017/SEI/AD</p>\r\n<p class="Texto_Justificado">Processo n&ordm; 53528.006849/2012-56</p>\r\n\r\n<p class="Texto_Justificado">Interessado: Associacao Cultural Radio Comunitaria Regional</p>\r\n<p class="Texto_Fundo_Cinza_Maiusculas_Negrito">CONSELHEIRO</p>\r\n\r\n<p class="Texto_Justificado_Recuo_Primeira_Linha">CARLOS ANTONIO SILVA</p>\r\n\r\n<p class="Item_Nivel1">ASSUNTO</p>\r\n\r\n<p class="Item_Nivel2"><span>Recurso Administrativo interposto por ASSOCIA&Ccedil;&Atilde;O CULTURAL RADIO COMUNIT&Aacute;RIA REGIONAL, inscrita no MF sob CNPJ n&ordm; 12.345.678/0001-90, executante do Servi&ccedil;o de Radiodifus&atilde;o Comunit&aacute;ria, no Munic&iacute;pio de Cidade Exemplo, no Estado do Rio Grande do Sul, contra Despacho Decis&oacute;rio n.&ordm; 193, de 31 de maio de 2016, do Superintendente de Fiscaliza&ccedil;&atilde;o da Anatel, exarado nos autos do Procedimento para Apura&ccedil;&atilde;o de Descumprimento de Obriga&ccedil;&otilde;es n.&ordm; 53528.006849/2012-56.</span></p>\r\n\r\n<p class="Item_Nivel1">EMENTA</p>\r\n\r\n<p class="Texto_Alinhado_Esquerda_Espacamento_Simples_Maiusc">PROCEDIMENTO PARA APURA&Ccedil;&Atilde;O DE DESCUMPRIMENTO DE OBRIGA&Ccedil;&Otilde;ES (PADO). SUPERINTEND&Ecirc;NCIA DE FISCALIZA&Ccedil;&Atilde;O (SFI). RECURSO ADMINISTRATIVO. INFRA&Ccedil;&Otilde;ES T&Eacute;CNICAS. INDISPONIBILIDADE DE RELAT&Oacute;RIO DE CONFORMIDADE. REPETI&Ccedil;&Atilde;O DOS ARGUMENTOS APRESENTADOS EM SEDE DE RECURSOS ANTERIORES. CONHECER PARA, NO M&Eacute;RITO, NEGAR PROVIMENTO. REVIS&Atilde;O DE OF&Iacute;CIO. POSSIBILIDADE DE PARCELAMENTO DA MULTA.</p>\r\n\r\n<p class="Item_Nivel2">As alega&ccedil;&otilde;es da Recorrente n&atilde;o trazem qualquer fato novo ou circunst&acirc;ncia relevante suscet&iacute;vel de justificar a reforma a decis&atilde;o recorrida.</p>\r\n\r\n<p class="Item_Nivel2">Recurso Administrativo conhecido e n&atilde;o provido.</p>\r\n\r\n<p class="Item_Nivel2">Revis&atilde;o de of&iacute;cio do valor da multa em virtude de caracteriza&ccedil;&atilde;o da infra&ccedil;&atilde;o referente &agrave; pot&ecirc;ncia diversa do autorizado como m&eacute;dia, no caso em comento.</p>\r\n\r\n<p class="Item_Nivel2">Determina&ccedil;&atilde;o &agrave; Superintend&ecirc;ncia de Fiscaliza&ccedil;&atilde;o da Anatel (SFI) no sentido de comunicar o Recorrente sobre a possibilidade de parcelamento dos valores devidos.</p>',
                "IdAnexos": None,
            },
        },
        status=200,
    )

    # Mock para consulta de processo (procedimento 147322)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "147322",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53528.006849/2012-56",
                    "EspecificacaoProcesso": "",
                    "IdTipoProcesso": 100000590,
                    "TipoProcesso": "PADO: Irregularidade Técnica",
                    "IdUnidadeGeradoraProcesso": 110001193,
                    "SiglaUnidadeGeradoraProcesso": "Protocolo.RS",
                    "DescricaoUnidadeGeradoraProcesso": "Protocolo do Rio Grande do Sul",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": None,
                    "IdProcessosAnexados": ["140628"],
                    "Interessados": [
                        {
                            "IdInteressado": 100023183,
                            "NomeInteressado": "ASSOCIACAO CULTURAL RADIO COMUNITARIA",
                        }
                    ],
                    "IdProcedimento": 147322,
                }
            ],
        },
        status=200,
    )


def mock_citacao_de_dois_processos_que_nao_cabem_no_contexto_e_que_deveriam_acionar_rag():
    """
    Mock para teste com dois id_procedimentos.
    Primeiro procedimento (147322): copiado do mock original
    Segundo procedimento (150000): novo procedimento com dois documentos
    """

    # ============ PRIMEIRO PROCEDIMENTO (147322) - COPIADO DO MOCK ORIGINAL ============

    # Mock para consulta de documento 2138246 (primeiro procedimento):
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "2138246",
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
                    "IdProcedimento": 147322,
                    "NumeroDocumento": "1817816",
                    "EspecificacaoDocumento": "",
                    "IdTipoDocumento": 7,
                    "DataInclusao": "25/08/2017",
                    "NomeTipoDocumento": "Análise",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "53528.006849/2012-56",
                    "IdDocumento": 2138246,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta conteúdo documento 2138246 (documento interno)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "2138246",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">\n<html lang="pt-br" >\n<head>\n<meta http-equiv="Pragma" content="no-cache" />\n<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">\n<style type="text/css"><!--/*--><![CDATA[/*><!--*/\np.Citacao {font-size:10pt;font-family:Calibri;text-align:justify;word-wrap:normal;margin:4pt 0 4pt 160px;} p.Item_Alinea_Letra {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt 6pt 6pt 120px;counter-increment:letra_minuscula;} p.Item_Alinea_Letra:before {content:counter(letra_minuscula, lower-latin) ") ";display:inline-block;width:5mm;font-weight:normal;} p.Item_Inciso_Romano {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0mm;margin:6pt 6pt 6pt 120px;counter-increment:romano_maiusculo;counter-reset:letra_minuscula;} p.Item_Inciso_Romano:before {content:counter(romano_maiusculo, upper-roman) " - ";display:inline-block;width:15mm;font-weight:normal;} p.Item_Nivel1 {text-transform:uppercase;font-weight:bold;background-color:#e6e6e6;font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;counter-increment:item-n1;counter-reset:item-n2 item-n3 item-n4 romano_maiusculo letra_minuscula;} p.Item_Nivel1:before {content:counter(item-n1) ".";display:inline-block;width:25mm;font-weight:normal;} p.Item_Nivel2 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:item-n2;counter-reset:item-n3 item-n4 romano_maiusculo letra_minuscula;} p.Item_Nivel2:before {content:counter(item-n1) "." counter(item-n2) ".";display:inline-block;width:25mm;font-weight:normal;} p.Item_Nivel3 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:item-n3;counter-reset:item-n4 romano_maiusculo letra_minuscula;margin-left:40px;} p.Item_Nivel3:before {content:counter(item-n1) "." counter(item-n2) "." counter(item-n3) ".";display:inline-block;width:25mm;font-weight:normal;} p.Item_Nivel4 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:item-n4;counter-reset:romano_maiusculo letra_minuscula;margin-left:80px;} p.Item_Nivel4:before {content:counter(item-n1) "." counter(item-n2) "." counter(item-n3) "."  counter(item-n4) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel1 {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0mm;margin:6pt;counter-increment:paragrafo-n1;counter-reset:paragrafo-n2 paragrafo-n3 paragrafo-n4 romano_maiusculo letra_minuscula;} p.Paragrafo_Numerado_Nivel1:before {content:counter(paragrafo-n1) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel2 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:paragrafo-n2;counter-reset:paragrafo-n3 paragrafo-n4 romano_maiusculo letra_minuscula;margin-left:40px;} p.Paragrafo_Numerado_Nivel2:before {content:counter(paragrafo-n1) "." counter(paragrafo-n2) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel3 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:paragrafo-n3;counter-reset:paragrafo-n4 romano_maiusculo letra_minuscula;margin-left:80px;} p.Paragrafo_Numerado_Nivel3:before {content:counter(paragrafo-n1) "." counter(paragrafo-n2) "." counter(paragrafo-n3) ".";display:inline-block;width:25mm;font-weight:normal;} p.Paragrafo_Numerado_Nivel4 {font-size:12pt;font-family:Calibri;text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;counter-increment:paragrafo-n4;counter-reset:romano_maiusculo letra_minuscula;margin-left:120px;} p.Paragrafo_Numerado_Nivel4:before {content:counter(paragrafo-n1) "." counter(paragrafo-n2) "." counter(paragrafo-n3) "." counter(paragrafo-n4) ".";display:inline-block;width:25mm;font-weight:normal;} p.Tabela_Texto_8 {font-size:8pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:0 3pt 0 3pt;} p.Tabela_Texto_Alinhado_Direita {font-size:11pt;font-family:Calibri;text-align:right;word-wrap:normal;margin:0 3pt 0 3pt;} p.Tabela_Texto_Alinhado_Esquerda {font-size:11pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:0 3pt 0 3pt;} p.Tabela_Texto_Centralizado {font-size:11pt;font-family:Calibri;text-align:center;word-wrap:normal;margin:0 3pt 0;} p.Tachado {font-size:11pt;font-family:Calibri;text-indent:1.18in;text-align:justify;word-wrap:normal;text-decoration:line-through;} p.Texto_Alinhado_Direita {font-size:12pt;font-family:Calibri;text-align:right;word-wrap:normal;margin:6pt;} p.Texto_Alinhado_Esquerda {font-size:12pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:6pt;} p.Texto_Alinhado_Esquerda_Espacamento_Simples {font-size:12pt;font-family:Calibri;text-align:left;word-wrap:normal;margin:0 0 0 6pt;} p.Texto_Alinhado_Esquerda_Espacamento_Simples_Maiusc {font-size:12pt;font-family:Calibri;text-align:left;text-transform:uppercase;word-wrap:normal;margin:0 0 0 6pt;} p.Texto_Centralizado {font-size:12pt;font-family:Calibri;text-align:center;word-wrap:normal;margin:6pt;} p.Texto_Centralizado_Maiusculas {font-size:13pt;font-family:Calibri;text-align:center;text-transform:uppercase;word-wrap:normal;} p.Texto_Centralizado_Maiusculas_Negrito {font-weight:bold;font-size:13pt;font-family:Calibri;text-align:center;text-transform:uppercase;word-wrap:normal;} p.Texto_Espaco_Duplo_Recuo_Primeira_Linha {letter-spacing:1px;font-weight:bold;font-size:12pt;font-family:Calibri;text-indent:25mm;text-align:justify;word-wrap:normal;margin:6pt;} p.Texto_Fundo_Cinza_Maiusculas_Negrito {text-transform:uppercase;font-weight:bold;background-color:#e6e6e6;font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;} p.Texto_Fundo_Cinza_Negrito {font-weight:bold;background-color:#e6e6e6;font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;} p.Texto_Justificado {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;} p.Texto_Justificado_Maiusculas {font-size:12pt;font-family:Calibri;text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;text-transform:uppercase;} p.Texto_Justificado_Recuo_Primeira_Linha {font-size:12pt;font-family:Calibri;text-indent:25mm;text-align:justify;word-wrap:normal;margin:6pt;} p.Texto_Justificado_Recuo_Primeira_Linha_Esp_Simples {font-size:12pt;font-family:Calibri;text-indent:25mm;text-align:justify;word-wrap:normal;margin:0 0 0 6pt;} p.Texto_Mono_Espacado {font-size:10pt;font-family:Calibri;text-align:justify;word-wrap:normal;margin:6pt;} \n/*]]>*/-->\n</style><title>SEI/ANATEL - 1817816 - Análise</title>\n</head>\n<body>\n<p class="Texto_Centralizado_Maiusculas">An&aacute;lise n&ordm; 192/2017/SEI/AD</p>\r\n<p class="Texto_Justificado">Processo n&ordm; 53528.006849/2012-56</p>\r\n\r\n<p class="Texto_Justificado">Interessado: Associacao Cultural Radio Comunitaria Regional</p>\r\n<p class="Texto_Fundo_Cinza_Maiusculas_Negrito">CONSELHEIRO</p>\r\n\r\n<p class="Texto_Justificado_Recuo_Primeira_Linha">CARLOS ANTONIO SILVA</p>\r\n\r\n<p class="Item_Nivel1">ASSUNTO</p>\r\n\r\n<p class="Item_Nivel2"><span>Recurso Administrativo interposto por ASSOCIA&Ccedil;&Atilde;O CULTURAL RADIO COMUNIT&Aacute;RIA REGIONAL, inscrita no MF sob CNPJ n&ordm; 12.345.678/0001-90, executante do Servi&ccedil;o de Radiodifus&atilde;o Comunit&aacute;ria, no Munic&iacute;pio de Cidade Exemplo, no Estado do Rio Grande do Sul, contra Despacho Decis&oacute;rio n.&ordm; 193, de 31 de maio de 2016, do Superintendente de Fiscaliza&ccedil;&atilde;o da Anatel, exarado nos autos do Procedimento para Apura&ccedil;&atilde;o de Descumprimento de Obriga&ccedil;&otilde;es n.&ordm; 53528.006849/2012-56.</span></p>\r\n\r\n<p class="Item_Nivel1">EMENTA</p>\r\n\r\n<p class="Texto_Alinhado_Esquerda_Espacamento_Simples_Maiusc">PROCEDIMENTO PARA APURA&Ccedil;&Atilde;O DE DESCUMPRIMENTO DE OBRIGA&Ccedil;&Otilde;ES (PADO). SUPERINTEND&Ecirc;NCIA DE FISCALIZA&Ccedil;&Atilde;O (SFI). RECURSO ADMINISTRATIVO. INFRA&Ccedil;&Otilde;ES T&Eacute;CNICAS. INDISPONIBILIDADE DE RELAT&Oacute;RIO DE CONFORMIDADE. REPETI&Ccedil;&Atilde;O DOS ARGUMENTOS APRESENTADOS EM SEDE DE RECURSOS ANTERIORES. CONHECER PARA, NO M&Eacute;RITO, NEGAR PROVIMENTO. REVIS&Atilde;O DE OF&Iacute;CIO. POSSIBILIDADE DE PARCELAMENTO DA MULTA.</p>\r\n\r\n<p class="Item_Nivel2">As alega&ccedil;&otilde;es da Recorrente n&atilde;o trazem qualquer fato novo ou circunst&acirc;ncia relevante suscet&iacute;vel de justificar a reforma a decis&atilde;o recorrida.</p>\r\n\r\n<p class="Item_Nivel2">Recurso Administrativo conhecido e n&atilde;o provido.</p>\r\n\r\n<p class="Item_Nivel2">Revis&atilde;o de of&iacute;cio do valor da multa em virtude de caracteriza&ccedil;&atilde;o da infra&ccedil;&atilde;o referente &agrave; pot&ecirc;ncia diversa do autorizado como m&eacute;dia, no caso em comento.</p>\r\n\r\n<p class="Item_Nivel2">Determina&ccedil;&atilde;o &agrave; Superintend&ecirc;ncia de Fiscaliza&ccedil;&atilde;o da Anatel (SFI) no sentido de comunicar o Recorrente sobre a possibilidade de parcelamento dos valores devidos.</p>',
                "IdAnexos": None,
            },
        },
        status=200,
    )

    # Mock para consulta de processo (procedimento 147322)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "147322",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53528.006849/2012-56",
                    "EspecificacaoProcesso": "",
                    "IdTipoProcesso": 100000590,
                    "TipoProcesso": "PADO: Irregularidade Técnica",
                    "IdUnidadeGeradoraProcesso": 110001193,
                    "SiglaUnidadeGeradoraProcesso": "Protocolo.RS",
                    "DescricaoUnidadeGeradoraProcesso": "Protocolo do Rio Grande do Sul",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": None,
                    "IdProcessosAnexados": ["140628"],
                    "Interessados": [
                        {
                            "IdInteressado": 100023183,
                            "NomeInteressado": "ASSOCIACAO CULTURAL RADIO COMUNITARIA",
                        }
                    ],
                    "IdProcedimento": 147322,
                }
            ],
        },
        status=200,
    )

    # ============ SEGUNDO PROCEDIMENTO (150000) - NOVO COM DOIS DOCUMENTOS ============

    # Mock para consulta de documento 3456789 (primeiro documento do segundo procedimento):
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "3456789",
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
                    "IdProcedimento": 150000,
                    "NumeroDocumento": "2500001",
                    "EspecificacaoDocumento": "",
                    "IdTipoDocumento": 8,
                    "DataInclusao": "10/03/2018",
                    "NomeTipoDocumento": "Despacho",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "53528.007500/2013-18",
                    "IdDocumento": 3456789,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta conteúdo documento 3456789 (primeiro documento interno do segundo procedimento)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "3456789",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": (
                    "<!DOCTYPE html PUBLIC "
                    '"-//W3C//DTD HTML 4.01//EN" '
                    '"http://www.w3.org/TR/html4/strict.dtd">\n'
                    '<html lang="pt-br">\n'
                    "<head>\n"
                    '<meta http-equiv="Pragma" content="no-cache" />\n'
                    '<meta http-equiv="Content-Type" '
                    'content="text/html; charset=iso-8859-1">\n'
                    '<style type="text/css"><!--/*--><![CDATA[/*><!--*/\n'
                    "p.Texto_Justificado {font-size:12pt;font-family:Calibri;"
                    "text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;}"
                    " p.Texto_Centralizado {font-size:12pt;font-family:Calibri;"
                    "text-align:center;word-wrap:normal;margin:6pt;}"
                    " p.Texto_Centralizado_Maiusculas {font-size:13pt;"
                    "font-family:Calibri;text-align:center;text-transform:uppercase;"
                    "word-wrap:normal;} p.Item_Nivel1 {text-transform:uppercase;"
                    "font-weight:bold;background-color:#e6e6e6;font-size:12pt;"
                    "font-family:Calibri;text-align:justify;word-wrap:normal;"
                    "text-indent:0;margin:6pt;} p.Item_Nivel2 {font-size:12pt;"
                    "font-family:Calibri;text-indent:0mm;text-align:justify;"
                    "word-wrap:normal;margin:6pt;}\n"
                    "/*]]>*/-->\n</style>"
                    "<title>SEI/ANATEL - 2500001 - Despacho</title>\n"
                    "</head>\n<body>\n"
                    '<p class="Texto_Centralizado_Maiusculas">'
                    "Despacho n&ordm; 45/2018/SEI/SPR</p>\r\n"
                    '<p class="Texto_Justificado">Processo n&ordm; '
                    "53528.007500/2013-18</p>\r\n"
                    '<p class="Texto_Justificado">Interessado: '
                    "Telecomunica&ccedil;&otilde;es Brasileiras S.A.</p>\r\n"
                    '<p class="Item_Nivel1">ASSUNTO</p>\r\n'
                    '<p class="Item_Nivel2">'
                    "<span>Solicita&ccedil;&atilde;o de autoriza&ccedil;&atilde;o "
                    "para opera&ccedil;&atilde;o de esta&ccedil;&atilde;o de "
                    "radiofrequ&ecirc;ncia na faixa de 2,4 GHz para presta&ccedil;&atilde;o "
                    "do Servi&ccedil;o de Comunica&ccedil;&atilde;o Multim&iacute;dia - "
                    "SCM na regi&atilde;o metropolitana de S&atilde;o Paulo.</span>"
                    "</p>\r\n"
                    '<p class="Item_Nivel1">PARECER</p>\r\n'
                    '<p class="Item_Nivel2">Ap&oacute;s an&aacute;lise t&eacute;cnica '
                    "da solicita&ccedil;&atilde;o apresentada pela empresa "
                    "Telecomunica&ccedil;&otilde;es Brasileiras S.A., inscrita no CNPJ "
                    "sob n&ordm; 33.530.486/0001-29, verificou-se que a mesma atende "
                    "aos requisitos t&eacute;cnicos estabelecidos pela Ag&ecirc;ncia "
                    "Nacional de Telecomunica&ccedil;&otilde;es.</p>\r\n"
                    '<p class="Item_Nivel2">A esta&ccedil;&atilde;o proposta n&atilde;o '
                    "causar&aacute; interfer&ecirc;ncia prejudicial a outros servi&ccedil;os "
                    "de telecomunica&ccedil;&otilde;es j&aacute; em opera&ccedil;&atilde;o "
                    "na regi&atilde;o.</p>\r\n"
                    '<p class="Item_Nivel2">Desta forma, sugere-se o deferimento da '
                    "presente solicita&ccedil;&atilde;o.</p>\r\n"
                    '<p class="Texto_Justificado">S&atilde;o Paulo, 10 de mar&ccedil;o '
                    "de 2018.</p>\r\n"
                    '<p class="Texto_Centralizado">MARIA FERNANDA OLIVEIRA</p>\r\n'
                    '<p class="Texto_Centralizado">Especialista em Regulação de '
                    "Serviços Públicos de Telecomunicações</p>"
                ),
                "IdAnexos": None,
            },
        },
        status=200,
    )

    # Mock para consulta de documento 3456790 (segundo documento do segundo procedimento):
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "3456790",
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
                    "IdProcedimento": 150000,
                    "NumeroDocumento": "2500002",
                    "EspecificacaoDocumento": "",
                    "IdTipoDocumento": 9,
                    "DataInclusao": "15/03/2018",
                    "NomeTipoDocumento": "Portaria",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "53528.007500/2013-18",
                    "IdDocumento": 3456790,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta conteúdo documento 3456790 (segundo documento interno do segundo procedimento)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "3456790",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": (
                    "<!DOCTYPE html PUBLIC "
                    '"-//W3C//DTD HTML 4.01//EN" '
                    '"http://www.w3.org/TR/html4/strict.dtd">\n'
                    '<html lang="pt-br">\n'
                    "<head>\n"
                    '<meta http-equiv="Pragma" content="no-cache" />\n'
                    '<meta http-equiv="Content-Type" '
                    'content="text/html; charset=iso-8859-1">\n'
                    '<style type="text/css"><!--/*--><![CDATA[/*><!--*/\n'
                    "p.Texto_Justificado {font-size:12pt;font-family:Calibri;"
                    "text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;}"
                    " p.Texto_Centralizado {font-size:12pt;font-family:Calibri;"
                    "text-align:center;word-wrap:normal;margin:6pt;}"
                    " p.Texto_Centralizado_Maiusculas {font-size:13pt;"
                    "font-family:Calibri;text-align:center;text-transform:uppercase;"
                    "word-wrap:normal;} p.Texto_Centralizado_Maiusculas_Negrito "
                    "{font-weight:bold;font-size:13pt;font-family:Calibri;"
                    "text-align:center;text-transform:uppercase;word-wrap:normal;}"
                    " p.Item_Nivel1 {text-transform:uppercase;font-weight:bold;"
                    "background-color:#e6e6e6;font-size:12pt;font-family:Calibri;"
                    "text-align:justify;word-wrap:normal;text-indent:0;margin:6pt;}"
                    " p.Item_Nivel2 {font-size:12pt;font-family:Calibri;"
                    "text-indent:0mm;text-align:justify;word-wrap:normal;margin:6pt;}\n"
                    "/*]]>*/-->\n</style>"
                    "<title>SEI/ANATEL - 2500002 - Portaria</title>\n"
                    "</head>\n<body>\n"
                    '<p class="Texto_Centralizado_Maiusculas_Negrito">'
                    "PORTARIA N&ordm; 1.234, DE 15 DE MAR&Ccedil;O DE 2018</p>\r\n"
                    '<p class="Texto_Justificado">O SUPERINTENDENTE DE '
                    "RADIOFREQU&Ecirc;NCIA E FISCALIZA&Ccedil;&Atilde;O DA "
                    "AG&Ecirc;NCIA NACIONAL DE TELECOMUNICA&Ccedil;&Otilde;ES - "
                    "ANATEL, no uso das atribui&ccedil;&otilde;es que lhe conferem "
                    "o art. 152 do Regimento Interno da Anatel, aprovado pela "
                    "Resolu&ccedil;&atilde;o n&ordm; 612, de 29 de abril de 2013,"
                    "</p>\r\n"
                    '<p class="Item_Nivel1">RESOLVE:</p>\r\n'
                    '<p class="Item_Nivel2">Art. 1&ordm; Autorizar a empresa '
                    "TELECOMUNICA&Ccedil;&Otilde;ES BRASILEIRAS S.A., inscrita no "
                    "CNPJ sob o n&ordm; 33.530.486/0001-29, a operar esta&ccedil;&atilde;o "
                    "de radiofrequ&ecirc;ncia na faixa de 2,4 GHz para presta&ccedil;&atilde;o "
                    "do Servi&ccedil;o de Comunica&ccedil;&atilde;o Multim&iacute;dia - SCM."
                    "</p>\r\n"
                    '<p class="Item_Nivel2">Art. 2&ordm; Esta Portaria entra em '
                    "vigor na data de sua publica&ccedil;&atilde;o.</p>\r\n"
                    '<p class="Texto_Centralizado">JO&Atilde;O CARLOS REZENDE</p>\r\n'
                    '<p class="Texto_Centralizado">Superintendente de '
                    "Radiofrequência e Fiscalização</p>"
                ),
                "IdAnexos": None,
            },
        },
        status=200,
    )

    # Mock para consulta de processo (procedimento 150000)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "150000",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53528.007500/2013-18",
                    "EspecificacaoProcesso": "",
                    "IdTipoProcesso": 100000591,
                    "TipoProcesso": "Autorização de Radiofrequência",
                    "IdUnidadeGeradoraProcesso": 110001194,
                    "SiglaUnidadeGeradoraProcesso": "Protocolo.SP",
                    "DescricaoUnidadeGeradoraProcesso": "Protocolo de São Paulo",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": None,
                    "IdProcessosAnexados": [],
                    "Interessados": [
                        {
                            "IdInteressado": 100023184,
                            "NomeInteressado": "TELECOMUNICACOES BRASILEIRAS S.A.",
                        }
                    ],
                    "IdProcedimento": 150000,
                }
            ],
        },
        status=200,
    )


def mock_rag_chunks_forcado():
    """
    Mock para teste RAG com chunks forçados.
    Documentos: 1738535 (1469341) e 2364443 (2021549)
    """

    # Mock para consulta de documento 1738535:
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "1738535",
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
                    "IdProcedimento": 1323495,
                    "NumeroDocumento": "1469341",
                    "EspecificacaoDocumento": "",
                    "IdTipoDocumento": 10,
                    "DataInclusao": "15/05/2015",
                    "NomeTipoDocumento": "Ato",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "53500.012345/2015-01",
                    "IdDocumento": 1738535,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta conteúdo documento 1738535 (documento interno)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "1738535",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": "<!DOCTYPE html><html><head><title>Ato 1469341</title></head><body>"
                + (
                    "<p>Conteúdo extenso do ato que estabelece condições de valores e prazos. "
                    * 1000
                )
                + "</body></html>",
                "IdAnexos": None,
            },
        },
        status=200,
    )

    # Mock para consulta de processo (procedimento 1323495)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "1323495",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53500.012345/2015-01",
                    "EspecificacaoProcesso": "Estabelecimento de condições de valores e prazos",
                    "IdTipoProcesso": 100000600,
                    "TipoProcesso": "Processo Administrativo",
                    "IdUnidadeGeradoraProcesso": 110001200,
                    "SiglaUnidadeGeradoraProcesso": "SPB",
                    "DescricaoUnidadeGeradoraProcesso": "Superintendência de Planejamento e Regulação",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": None,
                    "IdProcessosAnexados": [],
                    "Interessados": [
                        {
                            "IdInteressado": 100025000,
                            "NomeInteressado": "Empresa de Telecomunicações Ltda",
                        }
                    ],
                    "IdProcedimento": 1323495,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta de documento 2364443:
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumentos": "2364443",
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
                    "IdProcedimento": 2355663,
                    "NumeroDocumento": "2021549",
                    "EspecificacaoDocumento": "",
                    "IdTipoDocumento": 10,
                    "DataInclusao": "20/08/2016",
                    "NomeTipoDocumento": "Ato",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "53500.023456/2016-02",
                    "IdDocumento": 2364443,
                }
            ],
        },
        status=200,
    )

    # Mock para consulta conteúdo documento 2364443 (documento interno)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_conteudo_documento",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdDocumento": "2364443",
                }
            )
        ],
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": "<!DOCTYPE html><html><head><title>Ato 2021549</title></head><body>"
                + ("<p>Conteúdo extenso do segundo ato sobre valores e prazos. " * 1000)
                + "</body></html>",
                "IdAnexos": None,
            },
        },
        status=200,
    )

    # Mock para consulta de processo (procedimento 2355663)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_processo",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_processo",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdProcedimentos": "2355663",
                    "SinFiltraAtivos": "N",
                    "SinFiltraBloqueados": "N",
                    "SinFiltraDocumentosRelevantes": "N",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "NumeroProcesso": "53500.023456/2016-02",
                    "EspecificacaoProcesso": "Revisão de valores e prazos contratuais",
                    "IdTipoProcesso": 100000600,
                    "TipoProcesso": "Processo Administrativo",
                    "IdUnidadeGeradoraProcesso": 110001200,
                    "SiglaUnidadeGeradoraProcesso": "SPB",
                    "DescricaoUnidadeGeradoraProcesso": "Superintendência de Planejamento e Regulação",
                    "ProcessosFilhoRelacionado": None,
                    "ProcessosPaiRelacionado": None,
                    "IdProcessosAnexados": [],
                    "Interessados": [
                        {
                            "IdInteressado": 100026000,
                            "NomeInteressado": "Operadora Nacional de Telecomunicações",
                        }
                    ],
                    "IdProcedimento": 2355663,
                }
            ],
        },
        status=200,
    )


# ============================================================================
# Funções auxiliares para popular cache em testes
# ============================================================================


def populate_cache_resumo_documento_interno():
    """Popula cache para test_resumo_documento_interno."""
    asyncio.run(
        populate_cache_with_document(
            id_documento="58",
            id_documento_formatado="0000046",
            content=(
                "# Despacho Decisório nº [NÚMERO]/[ANO]/SEI/[UNIDADE]/[UNIDADE]\n\n"
                "Processo nº [NÚMERO_PROCESSO]\n\n"
                "Interessado: [EMPRESA_A], [EMPRESA_B], [EMPRESA_C], "
                "[EMPRESA_D], [EMPRESA_E]\n\n"
                "**O SUPERINTENDENTE DE COMPETIÇÃO DA AGÊNCIA NACIONAL DE "
                "TELECOMUNICAÇÕES**, no uso das atribuições que lhe foram "
                "conferidas pelo art. 159, inciso I, do Regimento Interno da "
                "Anatel, aprovado pela [Resolução nº 612, de 29 de abril de "
                "2013](http://legislacao.anatel.gov.br/resolucoes/2013/450-resolucao-612);\n\n"
                "CONSIDERANDO o disposto no Regulamento Geral de Interconexão, "
                "aprovado pela [Resolução nº 410, de 11 de julho de "
                "2005](http://legislacao.anatel.gov.br/resolucoes/2005/167-resolucao-410), "
                "em especial o seu art. 40; e\n\n"
                "**DECIDE:**\n\n"
                "1. Homologar o Termo Aditivo nº [NÚMERO_TERMO] ao Contrato de "
                "Interconexão Classe II entre a rede de suporte à prestação do "
                "Serviço Móvel Pessoal - SMP de [EMPRESA_B], CNPJ nº [CNPJ_1], "
                "e a rede de suporte à prestação do Serviço Telefônico Fixo "
                "Comutado - STFC de [EMPRESA_A], CNPJ nº [CNPJ_2], nas modalidades "
                "Longa Distância Nacional e Longa Distância Internacional.\n"
                "2. Este Despacho Decisório entra em vigor na data de sua publicação."
            ),
            metadata=(
                "NumeroDocumento: 0000046\n"
                "EspecificacaoDocumento: Despacho Descisório de Homologação "
                "de Contrato de Interconexão\n"
                "NomeTipoDocumento: Despacho Decisório\n"
                "NumeroProcesso: 53500.000052/2006-13"
            ),
            doc_tokens=300,
            doc_paged=False,
        )
    )


def populate_cache_resumo_documento_externo_paginado():
    """Popula cache para test_resumo_documento_externo_paginado."""
    asyncio.run(
        populate_cache_with_document(
            id_documento="13631856",
            id_documento_formatado="12118331",
            content=(
                "# Relatório de Conformidade de Gestão - Maio/2024\n\n"
                "Conteúdo do relatório mockado para teste.\n\n"
                "Resumo executivo dos processos de conformidade realizados "
                "em maio de 2024.\n\n"
                "Principais pontos:\n"
                "- Item 1: Conformidade verificada\n"
                "- Item 2: Processos auditados\n"
                "- Item 3: Recomendações"
            ),
            metadata=(
                "NumeroDocumento: 12118331\n"
                "NomeTipoDocumento: Relatório\n"
                "NumeroProcesso: 53504.003500/2024-74\n"
                "EspecificacaoProcesso: Conformidade de Registro de Gestão - Maio/2024"
            ),
            doc_tokens=200,
            doc_paged=False,
        )
    )


def populate_cache_citacao_dois_documentos_cabem_contexto():
    """Popula cache para test_citacao_de_dois_documentos_que_cabem_no_contexto_e_nao_acionam_rag."""
    asyncio.run(
        populate_cache_with_document(
            id_documento="13631856",
            id_documento_formatado="12118331",
            content="# Relatório 12118331\n\nConteúdo do primeiro relatório mockado.",
            metadata="NumeroDocumento: 12118331\nNomeTipoDocumento: Relatório",
            doc_tokens=150,
            doc_paged=False,
        )
    )

    asyncio.run(
        populate_cache_with_document(
            id_documento="650229",
            id_documento_formatado="0546979",
            content="# Documento 0546979\n\nConteúdo do segundo documento mockado.",
            metadata="NumeroDocumento: 0546979\nNomeTipoDocumento: Despacho",
            doc_tokens=150,
            doc_paged=False,
        )
    )


def populate_cache_citacao_dois_documentos_geracao():
    """Popula cache para test_citacao_de_dois_documentos_que_cabem_no_contexto_para_geracao_de_novos_documentos."""
    asyncio.run(
        populate_cache_with_document(
            id_documento="390",
            id_documento_formatado="0000288",
            content="# Despacho Decisório 0000288\n\nDespacho decisório de exemplo para geração de novos documentos.",
            metadata="NumeroDocumento: 0000288\nNomeTipoDocumento: Despacho Decisório",
            doc_tokens=150,
            doc_paged=False,
        )
    )

    asyncio.run(
        populate_cache_with_document(
            id_documento="58",
            id_documento_formatado="0000046",
            content="# Despacho Decisório 0000046\n\nDespacho de homologação usado como referência.",
            metadata="NumeroDocumento: 0000046\nNomeTipoDocumento: Despacho Decisório",
            doc_tokens=150,
            doc_paged=False,
        )
    )


def populate_cache_citacao_documentos_grandes_resumo():
    """Popula cache para test_citacao_de_dois_documentos_que_nao_cabem_no_contexto_e_deveriam_acionar_resumo."""
    asyncio.run(
        populate_cache_with_document(
            id_documento="2138246",
            id_documento_formatado="1817816",
            content="# Documento 1817816\n\n"
            + ("Conteúdo extenso do documento mockado. " * 500),
            metadata="NumeroDocumento: 1817816\nNomeTipoDocumento: Relatório",
            doc_tokens=5000,
            doc_paged=False,
        )
    )

    asyncio.run(
        populate_cache_with_document(
            id_documento="3276527",
            id_documento_formatado="2839858",
            content="# Documento 2839858\n\n"
            + ("Conteúdo extenso do documento mockado. " * 500),
            metadata="NumeroDocumento: 2839858\nNomeTipoDocumento: Relatório",
            doc_tokens=5000,
            doc_paged=False,
        )
    )

    asyncio.run(
        populate_cache_with_document(
            id_documento="13631856",
            id_documento_formatado="12118331",
            content="# Documento 12118331\n\n"
            + ("Conteúdo extenso do documento mockado. " * 500),
            metadata="NumeroDocumento: 12118331\nNomeTipoDocumento: Relatório",
            doc_tokens=5000,
            doc_paged=False,
        )
    )


def populate_cache_processo_nao_cabe_rag():
    """Popula cache para test_citacao_de_processo_que_nao_cabe_no_contexto_e_que_deveria_acionar_rag."""
    # Popular o cache com 5 documentos do mesmo ID para forçar RAG
    for _ in range(5):
        asyncio.run(
            populate_cache_with_document(
                id_documento="2138246",
                id_documento_formatado="1817816",
                content="# Documento 1817816\n\n"
                + ("Conteúdo extenso do documento mockado. " * 500),
                metadata="NumeroDocumento: 1817816\nNomeTipoDocumento: Relatório\nNumeroProcesso: 53528.006849/2012-56",
                doc_tokens=5000,
                doc_paged=False,
            )
        )


def populate_cache_dois_processos_rag():
    """Popula cache para test_citacao_de_dois_processos_que_nao_cabem_no_contexto_e_que_deveriam_acionar_rag."""
    asyncio.run(
        populate_cache_with_document(
            id_documento="2138246",
            id_documento_formatado="1817816",
            content="# Documento 1817816\n\n"
            + ("Conteúdo extenso do documento mockado do processo 1. " * 500),
            metadata="NumeroDocumento: 1817816\nNomeTipoDocumento: Relatório\nNumeroProcesso: 53528.006849/2012-56",
            doc_tokens=5000,
            doc_paged=False,
        )
    )

    asyncio.run(
        populate_cache_with_document(
            id_documento="3456789",
            id_documento_formatado="2500001",
            content="# Documento 2500001\n\n"
            + ("Conteúdo extenso do documento mockado do processo 2a. " * 500),
            metadata="NumeroDocumento: 2500001\nNomeTipoDocumento: Relatório\nNumeroProcesso: 53528.007500/2013-18",
            doc_tokens=5000,
            doc_paged=False,
        )
    )

    asyncio.run(
        populate_cache_with_document(
            id_documento="3456790",
            id_documento_formatado="2500002",
            content="# Documento 2500002\n\n"
            + ("Conteúdo extenso do documento mockado do processo 2b. " * 500),
            metadata="NumeroDocumento: 2500002\nNomeTipoDocumento: Relatório\nNumeroProcesso: 53528.007500/2013-18",
            doc_tokens=5000,
            doc_paged=False,
        )
    )


# =============================================================================
# Mocks para funções internas do sistema
# =============================================================================


def create_mock_concatenate_documents(
    documents, token_count=50000, token_multiplier=1, procedimento_metadata=None
):
    """
    Cria um mock para a função concatenate_documents.

    Args:
        documents: Lista de documentos para simular
        token_count: Quantidade de tokens para simular (default: 50000 - caminho direto)
        token_multiplier: Multiplicador para os tokens dos documentos individuais (default: 1)
        procedimento_metadata: Metadata customizada para o procedimento (optional)

    Returns:
        Função async mockada
    """

    async def mock_concatenate_documents(user_state):
        """Mock que simula processamento de documentos."""
        # Simular que os documentos foram processados
        user_state["has_content"] = True
        user_state["all_tokens_counter"] = token_count
        user_state["intent"] = "pergunta"

        # Adicionar documentos processados ao primeiro procedimento
        if (
            user_state.get("id_procedimentos")
            and len(user_state["id_procedimentos"]) > 0
        ):
            procedimento = user_state["id_procedimentos"][0]

            # Adicionar metadata customizada ao procedimento, se fornecida
            if procedimento_metadata:
                procedimento.metadata = procedimento_metadata

            original_docs = procedimento.id_documentos

            # Simular documentos
            for i, original_doc in enumerate(original_docs):
                if i < len(documents):
                    original_doc.id_documento = documents[i].get(
                        "id_documento", f"doc_{i}"
                    )
                    original_doc.id_documento_formatado = documents[i][
                        "id_documento_formatado"
                    ]
                    original_doc.content = documents[i]["content"]
                    original_doc.metadata = documents[i]["metadata"]
                    original_doc.doc_tokens = (
                        documents[i]["doc_tokens"] * token_multiplier
                    )
                    original_doc.doc_paged = documents[i].get("doc_paged", False)

        return user_state

    return mock_concatenate_documents


async def mock_intent_detection(user_state):
    """Mock para forçar a detecção de intenção como 'pergunta'."""
    user_state["intent"] = "pergunta"
    return user_state


def create_mock_check_all_documents_indexed(total_documents=3, missing_documents=None):
    """
    Cria um mock para a função check_all_documents_indexed.

    Args:
        total_documents: Total de documentos (default: 3)
        missing_documents: Lista de documentos faltantes (default: [])

    Returns:
        Função async mockada
    """
    if missing_documents is None:
        missing_documents = []

    async def mock_check_all_documents_indexed(user_state):
        """Mock para simular que todos os documentos estão indexados."""
        return {
            "all_indexed": len(missing_documents) == 0,
            "total_documents": total_documents,
            "missing_documents": missing_documents,
        }

    return mock_check_all_documents_indexed


def create_mock_search_with_multiple_questions(documents, max_chunks=5):
    """
    Cria um mock para a função search_with_multiple_questions.

    Args:
        documents: Lista de documentos para retornar na busca
        max_chunks: Número máximo de chunks para retornar (default: 5)

    Returns:
        Função async mockada
    """

    async def mock_search_with_multiple_questions(questions, user_state):
        """Mock para simular resultados da busca RAG."""
        # Simular busca que retorna IDs de documentos e alguns chunks
        document_ids = {doc["id_documento"] for doc in documents[:max_chunks]}
        chunks = [
            {
                "text": doc["content"][:500],  # Primeiros 500 chars
                "id_documento": doc["id_documento"],
                "similarity_score": 0.9 - i * 0.1,
            }
            for i, doc in enumerate(documents[:max_chunks])
        ]
        document_scores = {
            doc_id: 0.9 - i * 0.1 for i, doc_id in enumerate(document_ids)
        }

        return {
            "chunks": chunks,
            "document_ids": document_ids,
            "document_scores": document_scores,
        }

    return mock_search_with_multiple_questions


def create_mock_search_with_chunks(num_chunks=10, document_ids=None):
    """
    Cria um mock para search_with_multiple_questions retornando chunks genéricos.

    Args:
        num_chunks: Número de chunks para gerar (default: 10)
        document_ids: Lista de IDs de documentos (default: ['1738535', '2364443'])

    Returns:
        Função async mockada
    """
    if document_ids is None:
        document_ids = ["1738535", "2364443"]

    async def mock_search_with_multiple_questions(questions, user_state):
        """Mock para simular resultados da busca RAG com chunks."""
        chunks = [
            {
                "text": f"Conteúdo do chunk {i} relacionado às condições de valores e prazos.",
                "id_documento": document_ids[i % len(document_ids)],
                "similarity_score": 0.95 - i * 0.05,
            }
            for i in range(num_chunks)
        ]
        document_scores = {
            doc_id: 0.95 - i * 0.05 for i, doc_id in enumerate(document_ids)
        }

        return {
            "chunks": chunks,
            "document_ids": set(document_ids),
            "document_scores": document_scores,
        }

    return mock_search_with_multiple_questions


def mock_check_initial_size(user_state):
    """Mock para forçar entrada no RAG Enhanced (simula documentos grandes)."""
    return False  # Força entrada no RAG


def create_mock_check_if_complete_documents_fit(fits=False, tokens_multiplier=1.1):
    """
    Cria um mock para check_if_complete_documents_fit.

    Args:
        fits: Se os documentos cabem no contexto (default: False)
        tokens_multiplier: Multiplicador para calcular tokens simulados (default: 1.1)

    Returns:
        Função mockada
    """

    def mock_check_if_complete_documents_fit(document_ids, user_state):
        """Mock para controlar se documentos completos cabem no contexto."""
        if fits:
            fake_total_tokens = 50000  # Baixo - cabem
        else:
            # Simular tokens altos para forçar não caber
            fake_total_tokens = int(
                user_state.get("general_max_ctx_len", 900000) * tokens_multiplier
            )
        return fits, fake_total_tokens

    return mock_check_if_complete_documents_fit


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
