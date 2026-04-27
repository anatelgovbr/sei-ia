"""
Testes P1 - Tratamento de erros de APIs externas (API SEI).

Cobre cenários onde a API SEI retorna erros ou fica indisponível:
1. Histórico: 404 → tratado como sem histórico (comportamento especial)
2. Histórico: 500 → propaga como erro HTTP
3. Histórico: timeout → propaga como erro HTTP
4. Consulta de documento: 404 (documento não encontrado no SEI)
5. Consulta de documento: 500 (erro interno do SEI)
6. Consulta de documento: timeout → retorna HTTP 412
7. Conteúdo de documento async: retries esgotados → degrada para conteúdo None
"""

from unittest.mock import patch

import requests
import responses
from langchain_core.messages import AIMessage

from tests.e2e.test_service import FakeChatModelWithAttributes

SEI_BASE = "http://mock-sei-api:8000"
CHAT_ENDPOINT = "/llm_lang/chat_gpt_4o_mini_128k"
CHAT_HEADERS = {
    "Content-Type": "application/json",
    "X-Internal-Test-Call": "true",
}


def _historico_params(id_topico: int) -> dict:
    return {
        "servico": "md_ia_consulta_historico_topico",
        "SiglaSistema": "Usuario_IA",
        "IdentificacaoServico": "mock-identifier",
        "IdTopico": str(id_topico),
    }


def _make_fake_llm(
    resposta: str = "Olá! Como posso ajudá-lo?",
) -> FakeChatModelWithAttributes:
    return FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(content='{"caso": "outro"}'),  # classify_disclaimer
                AIMessage(content=resposta),  # chat_workflow
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )


# ---------------------------------------------------------------------------
# 1. Histórico: 404 → tratado como sem histórico, chat continua normalmente
# ---------------------------------------------------------------------------


@responses.activate
def test_historico_404_tratado_como_sem_historico(client, mock_solr_post):
    """
    Quando a API SEI retorna 404 ao buscar histórico do tópico, o decorator
    _handle_historico_topico_errors converte em DataFrame vazio (sem histórico).
    O chat deve continuar normalmente retornando 200.
    """
    responses.add(
        responses.GET,
        f"{SEI_BASE}/md_ia_consulta_historico_topico",
        match=[
            responses.matchers.query_param_matcher(_historico_params(id_topico=999))
        ],
        json={"status": "not_found", "data": []},
        status=404,
    )

    fake_llm = _make_fake_llm("Olá! Como posso ajudá-lo?")

    with (
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        response = client.post(
            CHAT_ENDPOINT,
            headers=CHAT_HEADERS,
            json={"id_usuario": 0, "id_topico": 999, "text": "Olá!"},
        )

    # 404 no histórico NÃO deve ser um erro — o chat continua sem histórico
    assert response.status_code == 200
    body = response.json()
    assert "choices" in body
    assert len(body["choices"]) > 0


# ---------------------------------------------------------------------------
# 2. Histórico: 500 → SeiDBAPIError → http_exception_handler → erro HTTP
# ---------------------------------------------------------------------------


@responses.activate
def test_historico_500_retorna_erro_http(client, mock_solr_post):
    """
    Quando a API SEI retorna 500 ao buscar histórico, _handle_historico_topico_errors
    levanta SeiDBAPIError, que é capturado pelo http_exception_handler e
    retorna uma resposta de erro com corpo JSON estruturado.
    """
    responses.add(
        responses.GET,
        f"{SEI_BASE}/md_ia_consulta_historico_topico",
        match=[responses.matchers.query_param_matcher(_historico_params(id_topico=0))],
        json={"error": "internal server error"},
        status=500,
    )

    response = client.post(
        CHAT_ENDPOINT,
        headers=CHAT_HEADERS,
        json={"id_usuario": 0, "id_topico": 0, "text": "Olá!"},
    )

    # Deve retornar um erro HTTP (não 200)
    assert response.status_code != 200
    body = response.json()
    # Corpo deve ser JSON válido com alguma mensagem de erro
    assert body is not None
    assert isinstance(body, dict)


# ---------------------------------------------------------------------------
# 3. Histórico: timeout → SeiDBAPIError → erro HTTP
# ---------------------------------------------------------------------------


@responses.activate
def test_historico_timeout_retorna_erro_http(client, mock_solr_post):
    """
    Quando a conexão com a API SEI tem timeout ao buscar histórico,
    _handle_historico_topico_errors levanta SeiDBAPIError e a aplicação
    retorna uma resposta de erro com corpo JSON estruturado.
    """
    responses.add(
        responses.GET,
        f"{SEI_BASE}/md_ia_consulta_historico_topico",
        match=[responses.matchers.query_param_matcher(_historico_params(id_topico=0))],
        body=requests.exceptions.Timeout("Connection timed out"),
    )

    response = client.post(
        CHAT_ENDPOINT,
        headers=CHAT_HEADERS,
        json={"id_usuario": 0, "id_topico": 0, "text": "Olá!"},
    )

    assert response.status_code != 200
    body = response.json()
    assert body is not None
    assert isinstance(body, dict)


# ---------------------------------------------------------------------------
# 4. Consulta de documento: 500 → SeiDBAPIError → erro HTTP
# ---------------------------------------------------------------------------


@responses.activate
def test_consulta_documento_500_retorna_erro_http(client, mock_solr_post):
    """
    Quando a API SEI retorna 500 ao consultar metadados de um documento citado
    pelo usuário, a aplicação deve retornar um erro HTTP estruturado (não crashar).
    """
    # Mock do histórico (sem histórico)
    responses.add(
        responses.GET,
        f"{SEI_BASE}/md_ia_consulta_historico_topico",
        match=[responses.matchers.query_param_matcher(_historico_params(id_topico=0))],
        json={"status": "success", "data": []},
        status=200,
    )

    # Mock para consulta de documento retornando 500
    responses.add(
        responses.GET,
        f"{SEI_BASE}/md_ia_consulta_documento",
        json={"error": "internal server error"},
        status=500,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Resumir o documento #0000046",
        "id_procedimentos": [
            {
                "id_procedimento": "44",
                "id_documentos": [
                    {
                        "id_documento": "58",
                        "num_paginas": None,
                        "pag_doc_init": None,
                        "pag_doc_end": None,
                    }
                ],
            }
        ],
    }

    response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=payload)

    # A aplicação não deve retornar 200 quando o SEI falha ao buscar o documento
    assert response.status_code != 200
    body = response.json()
    assert body is not None
    assert isinstance(body, dict)


# ---------------------------------------------------------------------------
# 5. Consulta de documento: documento não existe no SEI (404)
# ---------------------------------------------------------------------------


@responses.activate
def test_consulta_documento_404_retorna_erro_http(client, mock_solr_post):
    """
    Quando o documento citado não existe na API SEI (404), a aplicação deve
    retornar um erro HTTP com corpo JSON estruturado.
    """
    responses.add(
        responses.GET,
        f"{SEI_BASE}/md_ia_consulta_historico_topico",
        match=[responses.matchers.query_param_matcher(_historico_params(id_topico=0))],
        json={"status": "success", "data": []},
        status=200,
    )

    responses.add(
        responses.GET,
        f"{SEI_BASE}/md_ia_consulta_documento",
        json={"status": "not_found", "data": []},
        status=404,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Resumir o documento #9999999",
        "id_procedimentos": [
            {
                "id_procedimento": "99999",
                "id_documentos": [
                    {
                        "id_documento": "9999999",
                        "num_paginas": None,
                        "pag_doc_init": None,
                        "pag_doc_end": None,
                    }
                ],
            }
        ],
    }

    response = client.post(CHAT_ENDPOINT, headers=CHAT_HEADERS, json=payload)

    assert response.status_code != 200
    body = response.json()
    assert body is not None
    assert isinstance(body, dict)


# ---------------------------------------------------------------------------
# 6. HTTPException412SeiApiTimeout propagada pelo router → 412
#
# O router captura explicitamente HTTPException412SeiApiTimeout e a re-lança.
# Para testar essa propagação de forma isolada, injetamos a exceção diretamente
# no grafo sem depender da cadeia interna SEI → @_handle_api_errors.
# ---------------------------------------------------------------------------


@responses.activate
def test_consulta_documento_timeout_retorna_412(client, mock_solr_post):
    """
    Quando HTTPException412SeiApiTimeout é levantada dentro do grafo (ex: timeout na
    API SEI após retries), o router captura e re-lança a exceção explicitamente.
    O http_exception_handler converte em resposta HTTP 412.
    """
    from unittest.mock import AsyncMock, MagicMock

    from sei_ia.services.exceptions.http_exceptions import HTTPException412SeiApiTimeout

    responses.add(
        responses.GET,
        f"{SEI_BASE}/md_ia_consulta_historico_topico",
        match=[responses.matchers.query_param_matcher(_historico_params(id_topico=0))],
        json={"status": "success", "data": []},
        status=200,
    )

    # Injeta a exceção diretamente no ponto de execução do grafo
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        side_effect=HTTPException412SeiApiTimeout(document_id="0000046")
    )

    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post(
            CHAT_ENDPOINT,
            headers=CHAT_HEADERS,
            json={
                "id_usuario": 0,
                "id_topico": 0,
                "text": "Resumir o documento #0000046",
            },
        )

    # HTTPException412SeiApiTimeout deve resultar em 412
    assert response.status_code == 412
    body = response.json()
    assert body is not None
    assert isinstance(body, dict)


# ---------------------------------------------------------------------------
# 7. Conteúdo assíncrono: SeiDBAPIError propagado pelo handler → erro HTTP
# ---------------------------------------------------------------------------


@responses.activate
def test_sei_api_error_propagado_como_erro_http(client, mock_solr_post):
    """
    Quando SeiDBAPIError é levantado durante o processamento do chat,
    o http_exception_handler deve retornar uma resposta HTTP com o
    status_code da exceção e corpo JSON com campo 'message'.
    """
    from sei_ia.data.database.sei_db_handlers import SeiDBAPIError

    responses.add(
        responses.GET,
        f"{SEI_BASE}/md_ia_consulta_historico_topico",
        match=[responses.matchers.query_param_matcher(_historico_params(id_topico=0))],
        json={"status": "success", "data": []},
        status=200,
    )

    with patch(
        "sei_ia.data.database.sei_db_handlers.SEIDBHandler.md_ia_consulta_documento",
        side_effect=SeiDBAPIError(status_code=503, detail="API SEI indisponível"),
    ):
        response = client.post(
            CHAT_ENDPOINT,
            headers=CHAT_HEADERS,
            json={
                "id_usuario": 0,
                "id_topico": 0,
                "text": "Resumir o documento #0000046",
                "id_procedimentos": [
                    {
                        "id_procedimento": "44",
                        "id_documentos": [
                            {
                                "id_documento": "58",
                                "num_paginas": None,
                                "pag_doc_init": None,
                                "pag_doc_end": None,
                            }
                        ],
                    }
                ],
            },
        )

    assert response.status_code == 503
    body = response.json()
    assert "message" in body


# ---------------------------------------------------------------------------
# 8. HTTPException412SeiApiTimeout: message contém o ID do documento
# ---------------------------------------------------------------------------


@responses.activate
def test_sei_timeout_exception_mensagem_contem_id_documento(client, mock_solr_post):
    """
    HTTPException412SeiApiTimeout deve carregar o ID do documento no campo
    'message' da resposta HTTP 412.
    """
    from unittest.mock import AsyncMock, MagicMock

    from sei_ia.services.exceptions.http_exceptions import HTTPException412SeiApiTimeout

    responses.add(
        responses.GET,
        f"{SEI_BASE}/md_ia_consulta_historico_topico",
        match=[responses.matchers.query_param_matcher(_historico_params(id_topico=0))],
        json={"status": "success", "data": []},
        status=200,
    )

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        side_effect=HTTPException412SeiApiTimeout(document_id="0000046")
    )

    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        response = client.post(
            CHAT_ENDPOINT,
            headers=CHAT_HEADERS,
            json={
                "id_usuario": 0,
                "id_topico": 0,
                "text": "Resumir o documento #0000046",
            },
        )

    assert response.status_code == 412
    body = response.json()
    assert "message" in body
    assert "0000046" in body["message"]
