"""Testes E2E para a funcionalidade de uploads do Assistente IA.

Verifica o fluxo completo de uma requisição de chat que inclui uploads:
  1. Recebimento do payload com a lista de UploadItems
  2. Download de cada arquivo via API SEI
  3. Extração de texto do arquivo baixado
  4. Inclusão do conteúdo no contexto do LLM (user_request)
  5. Geração da resposta pelo LLM

Endpoint testado: POST /llm_lang/chat_gpt_4o_mini_128k
"""

from unittest.mock import AsyncMock, patch

import responses
from langchain_core.messages import AIMessage

# Constante reutilizada em todos os testes
ENDPOINT = "/llm_lang/chat_gpt_4o_mini_128k"
HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json",
    "X-Internal-Test-Call": "true",
}

# URL base mockada da API SEI (definida em conftest.py via SEI_API_DB_ADDRESS)
SEI_API_BASE = "http://mock-sei-api:8000"


# ---------------------------------------------------------------------------
# Classe auxiliar — fake LLM (mesmo padrão do test_service.py)
# ---------------------------------------------------------------------------


class FakeChatModelWithAttributes:
    """Fake LLM compatível com o contrato esperado pelo LangGraph."""

    model_config = {"extra": "allow", "arbitrary_types_allowed": True}

    def __init__(self, messages, model_name="gpt-4.1", **kwargs):
        from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

        self._inner = GenericFakeChatModel(messages=messages)
        object.__setattr__(self._inner, "model_name", model_name)
        object.__setattr__(self._inner, "temperature", kwargs.get("temperature", 0.0))
        object.__setattr__(self._inner, "max_tokens", kwargs.get("max_tokens", 4000))
        object.__setattr__(
            self._inner, "api_version", kwargs.get("api_version", "2024-08-01-preview")
        )

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, *args, **kwargs):
        return self._inner.invoke(*args, **kwargs)

    def stream(self, *args, **kwargs):
        return self._inner.stream(*args, **kwargs)

    async def ainvoke(self, *args, **kwargs):
        return await self._inner.ainvoke(*args, **kwargs)

    async def astream(self, *args, **kwargs):
        async for chunk in self._inner.astream(*args, **kwargs):
            yield chunk


def _make_fake_llm(*responses_content):
    """Cria um FakeChatModel com os conteúdos de resposta fornecidos."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    messages = iter([AIMessage(content=c) for c in responses_content])

    class _Fake(GenericFakeChatModel):
        model_config = {"extra": "allow", "arbitrary_types_allowed": True}

        def __init__(self):
            super().__init__(messages=messages)
            object.__setattr__(self, "model_name", "gpt-4.1")
            object.__setattr__(self, "temperature", 0.0)
            object.__setattr__(self, "max_tokens", 4000)
            object.__setattr__(self, "api_version", "2024-08-01-preview")

        def bind_tools(self, tools, **kwargs):
            return self

    return _Fake()


def _mock_history_endpoint(id_topico: int = 0, data: list | None = None):
    """Registra mock para o endpoint de histórico de tópico."""
    responses.add(
        responses.GET,
        f"{SEI_API_BASE}/md_ia_consulta_historico_topico",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_historico_topico",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdTopico": str(id_topico),
                }
            )
        ],
        json={"status": "success", "data": data or []},
        status=200,
    )


def _mock_download_endpoint(
    id_upload: int,
    content: bytes,
    filename: str,
    content_type: str = "application/octet-stream",
):
    """Registra mock para o endpoint de download de arquivo de upload."""
    responses.add(
        responses.GET,
        f"{SEI_API_BASE}/md_ia_download_arquivo_upload_assistente",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_download_arquivo_upload_assistente",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdUpload": str(id_upload),
                }
            )
        ],
        body=content,
        headers={"content-disposition": f'attachment; filename="{filename}"'},
        content_type=content_type,
        status=200,
    )


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


@responses.activate
def test_upload_txt_incluido_no_contexto_do_llm(client, mock_solr_post, tmp_path):
    """Fluxo E2E: upload de TXT é baixado, extraído e incluído no user_request."""
    _mock_history_endpoint(id_topico=0)

    conteudo_txt = b"O requerente solicita acesso ao processo 12345/2024."
    _mock_download_endpoint(
        id_upload=101,
        content=conteudo_txt,
        filename="requerimento.txt",
        content_type="text/plain",
    )

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',  # classify_disclaimer
        "Analisando o requerimento enviado pelo usuário.",
    )

    uploads_processados = []

    async def spy_process_uploads(uploads):
        """Intercepta process_uploads para verificar que foi chamado."""
        from sei_ia.data.etl.extract.uploads import (
            process_uploads as real_process_uploads,
        )

        resultado = await real_process_uploads(uploads)
        uploads_processados.extend(uploads)
        return resultado

    with (
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.routers.chat.process_uploads",
            side_effect=spy_process_uploads,
        ),
    ):
        response = client.post(
            ENDPOINT,
            headers=HEADERS,
            json={
                "id_usuario": 0,
                "id_topico": 0,
                "text": "Analise o documento enviado.",
                "temperature": 0,
                "max_tokens": 4000,
                "uploads": [
                    {
                        "id_upload": 101,
                        "nome_original": "requerimento.txt",
                        "extensao": "txt",
                    }
                ],
            },
        )

    assert response.status_code == 200, (
        f"Esperado status 200, obtido {response.status_code}: {response.text}"
    )

    # Verificar que process_uploads foi chamado com o upload correto
    assert len(uploads_processados) == 1
    assert uploads_processados[0].id_upload == 101
    assert uploads_processados[0].nome_original == "requerimento.txt"
    assert uploads_processados[0].extensao == "txt"

    # Verificar estrutura da resposta
    response_json = response.json()
    assert "choices" in response_json
    assert len(response_json["choices"]) > 0
    assert "content" in response_json["choices"][0]["message"]


@responses.activate
def test_upload_xml_incluido_no_contexto_do_llm(client, mock_solr_post):
    """Fluxo E2E: upload de XML é baixado, extraído e incluído no contexto."""
    _mock_history_endpoint(id_topico=0)

    conteudo_xml = (
        b'<?xml version="1.0"?><processo><numero>SEI-001/2024</numero></processo>'
    )
    _mock_download_endpoint(
        id_upload=202,
        content=conteudo_xml,
        filename="processo.xml",
        content_type="application/xml",
    )

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "O processo XML foi recebido e analisado.",
    )

    uploads_processados = []

    async def spy_process_uploads(uploads):
        from sei_ia.data.etl.extract.uploads import (
            process_uploads as real_process_uploads,
        )

        resultado = await real_process_uploads(uploads)
        uploads_processados.extend(uploads)
        return resultado

    with (
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.routers.chat.process_uploads",
            side_effect=spy_process_uploads,
        ),
    ):
        response = client.post(
            ENDPOINT,
            headers=HEADERS,
            json={
                "id_usuario": 1,
                "id_topico": 0,
                "text": "Qual é o número do processo no XML?",
                "temperature": 0,
                "max_tokens": 4000,
                "uploads": [
                    {
                        "id_upload": 202,
                        "nome_original": "processo.xml",
                        "extensao": "xml",
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert len(uploads_processados) == 1
    assert uploads_processados[0].id_upload == 202


@responses.activate
def test_multiplos_uploads_todos_processados(client, mock_solr_post):
    """Fluxo E2E: múltiplos uploads são processados em paralelo."""
    _mock_history_endpoint(id_topico=0)

    _mock_download_endpoint(
        id_upload=301,
        content=b"Ata da reuniao de 10/01/2024.",
        filename="ata.txt",
        content_type="text/plain",
    )
    _mock_download_endpoint(
        id_upload=302,
        content=b"Parecer tecnico favoravel ao projeto.",
        filename="parecer.txt",
        content_type="text/plain",
    )

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Recebi dois documentos: a ata e o parecer.",
    )

    uploads_processados = []

    async def spy_process_uploads(uploads):
        from sei_ia.data.etl.extract.uploads import (
            process_uploads as real_process_uploads,
        )

        resultado = await real_process_uploads(uploads)
        uploads_processados.extend(uploads)
        return resultado

    with (
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.routers.chat.process_uploads",
            side_effect=spy_process_uploads,
        ),
    ):
        response = client.post(
            ENDPOINT,
            headers=HEADERS,
            json={
                "id_usuario": 0,
                "id_topico": 0,
                "text": "Analise os dois documentos.",
                "temperature": 0,
                "max_tokens": 4000,
                "uploads": [
                    {"id_upload": 301, "nome_original": "ata.txt", "extensao": "txt"},
                    {
                        "id_upload": 302,
                        "nome_original": "parecer.txt",
                        "extensao": "txt",
                    },
                ],
            },
        )

    assert response.status_code == 200
    assert len(uploads_processados) == 2
    ids_processados = {u.id_upload for u in uploads_processados}
    assert ids_processados == {301, 302}


@responses.activate
def test_uploads_none_nao_chama_process_uploads(client, mock_solr_post):
    """Sem uploads, process_uploads não deve ser chamado."""
    _mock_history_endpoint(id_topico=0)

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Olá! Como posso ajudar?",
    )

    with (
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.routers.chat.process_uploads",
            new_callable=AsyncMock,
        ) as mock_process_uploads,
    ):
        response = client.post(
            ENDPOINT,
            headers=HEADERS,
            json={
                "id_usuario": 0,
                "id_topico": 0,
                "text": "Olá!",
                "temperature": 0,
                "max_tokens": 4000,
                # uploads ausente (None por padrão)
            },
        )

    assert response.status_code == 200
    mock_process_uploads.assert_not_called()


@responses.activate
def test_uploads_lista_vazia_nao_chama_process_uploads(client, mock_solr_post):
    """Com lista de uploads vazia, process_uploads não deve ser chamado."""
    _mock_history_endpoint(id_topico=0)

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Pergunta recebida sem anexos.",
    )

    with (
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.routers.chat.process_uploads",
            new_callable=AsyncMock,
        ) as mock_process_uploads,
    ):
        response = client.post(
            ENDPOINT,
            headers=HEADERS,
            json={
                "id_usuario": 0,
                "id_topico": 0,
                "text": "Pergunta sem upload.",
                "temperature": 0,
                "max_tokens": 4000,
                "uploads": [],
            },
        )

    assert response.status_code == 200
    mock_process_uploads.assert_not_called()


@responses.activate
def test_falha_no_download_retorna_status_200_com_mensagem_de_erro(
    client, mock_solr_post
):
    """Falha no download de upload não deve derrubar a requisição (erro tratado)."""
    _mock_history_endpoint(id_topico=0)

    # Simula o SEI retornando 500 no download
    responses.add(
        responses.GET,
        f"{SEI_API_BASE}/md_ia_download_arquivo_upload_assistente",
        status=500,
        json={"error": "Internal Server Error"},
    )

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Houve um problema ao processar o arquivo.",
    )

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
            ENDPOINT,
            headers=HEADERS,
            json={
                "id_usuario": 0,
                "id_topico": 0,
                "text": "Analise o documento.",
                "temperature": 0,
                "max_tokens": 4000,
                "uploads": [
                    {
                        "id_upload": 999,
                        "nome_original": "arquivo_indisponivel.pdf",
                        "extensao": "pdf",
                    }
                ],
            },
        )

    # A requisição não deve falhar — o erro de download é tratado internamente
    assert response.status_code == 200
    response_json = response.json()
    assert "choices" in response_json


@responses.activate
def test_conteudo_upload_concatenado_ao_user_request(client, mock_solr_post):
    """O conteúdo do upload deve ser concatenado ao user_request antes do LLM."""
    _mock_history_endpoint(id_topico=0)

    conteudo_esperado = "Dados sigilosos do processo 9876/2023."
    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Resposta baseada no conteúdo do upload.",
    )

    user_request_capturado = []

    async def mock_process_uploads(uploads):
        # Retorna um bloco de uploads formatado com conteúdo conhecido
        return (
            f"<uploads>\n---\n# Arquivo: segredo.txt\n{conteudo_esperado}\n</uploads>"
        )

    original_build_graph = None

    async def mock_build_graph():
        """Captura o user_request no momento em que o grafo é invocado."""
        from sei_ia.agents.chat_completion_graph import build_chat_completion_graph

        graph = await build_chat_completion_graph()
        original_ainvoke = graph.ainvoke

        async def spy_ainvoke(state, *args, **kwargs):
            user_request_capturado.append(state.get("user_request", ""))
            return await original_ainvoke(state, *args, **kwargs)

        graph.ainvoke = spy_ainvoke
        return graph

    with (
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.routers.chat.process_uploads",
            side_effect=mock_process_uploads,
        ),
        patch(
            "sei_ia.routers.chat.build_chat_completion_graph",
            side_effect=mock_build_graph,
        ),
    ):
        response = client.post(
            ENDPOINT,
            headers=HEADERS,
            json={
                "id_usuario": 0,
                "id_topico": 0,
                "text": "O que está no arquivo?",
                "temperature": 0,
                "max_tokens": 4000,
                "uploads": [
                    {
                        "id_upload": 777,
                        "nome_original": "segredo.txt",
                        "extensao": "txt",
                    }
                ],
            },
        )

    assert response.status_code == 200

    # Verificar que o user_request contém o conteúdo do upload
    assert len(user_request_capturado) > 0
    user_req = user_request_capturado[0]
    assert conteudo_esperado in user_req
    assert "<uploads>" in user_req


@responses.activate
def test_upload_com_pdf_delega_ao_extrator_pdf(client, mock_solr_post):
    """Upload de PDF deve invocar o extrator de PDF (não o extrator de texto simples)."""
    _mock_history_endpoint(id_topico=0)

    fake_pdf_bytes = b"%PDF-1.4 1 0 obj << /Type /Catalog >> endobj"
    _mock_download_endpoint(
        id_upload=500,
        content=fake_pdf_bytes,
        filename="edital.pdf",
        content_type="application/pdf",
    )

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "PDF processado com sucesso.",
    )

    with (
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.data.etl.extract.uploads._get_text_pdf_from_file",
            return_value="Texto extraído do edital PDF.",
        ) as mock_pdf_extractor,
    ):
        response = client.post(
            ENDPOINT,
            headers=HEADERS,
            json={
                "id_usuario": 0,
                "id_topico": 0,
                "text": "Resuma o edital.",
                "temperature": 0,
                "max_tokens": 4000,
                "uploads": [
                    {
                        "id_upload": 500,
                        "nome_original": "edital.pdf",
                        "extensao": "pdf",
                    }
                ],
            },
        )

    assert response.status_code == 200
    # O extrator de PDF deve ter sido chamado
    mock_pdf_extractor.assert_called_once()


def test_payload_uploads_sem_id_upload_retorna_422(client):
    """Payload com upload sem id_upload obrigatório deve retornar 422."""
    response = client.post(
        ENDPOINT,
        headers=HEADERS,
        json={
            "id_usuario": 0,
            "id_topico": 0,
            "text": "Teste de validação.",
            "temperature": 0,
            "max_tokens": 4000,
            "uploads": [
                {
                    # id_upload ausente intencionalmente
                    "nome_original": "doc.txt",
                    "extensao": "txt",
                }
            ],
        },
    )

    assert response.status_code == 422


def test_payload_uploads_id_upload_tipo_invalido_retorna_422(client):
    """Payload com id_upload como string não numérica deve retornar 422."""
    response = client.post(
        ENDPOINT,
        headers=HEADERS,
        json={
            "id_usuario": 0,
            "id_topico": 0,
            "text": "Teste de validação.",
            "temperature": 0,
            "max_tokens": 4000,
            "uploads": [
                {
                    "id_upload": "nao-e-um-numero",
                    "nome_original": "doc.txt",
                    "extensao": "txt",
                }
            ],
        },
    )

    assert response.status_code == 422


def test_payload_uploads_sem_nome_original_retorna_422(client):
    """Payload com upload sem nome_original obrigatório deve retornar 422."""
    response = client.post(
        ENDPOINT,
        headers=HEADERS,
        json={
            "id_usuario": 0,
            "id_topico": 0,
            "text": "Teste de validação.",
            "temperature": 0,
            "max_tokens": 4000,
            "uploads": [
                {
                    "id_upload": 1,
                    # nome_original ausente intencionalmente
                    "extensao": "txt",
                }
            ],
        },
    )

    assert response.status_code == 422


def test_payload_uploads_sem_extensao_retorna_422(client):
    """Payload com upload sem extensao obrigatória deve retornar 422."""
    response = client.post(
        ENDPOINT,
        headers=HEADERS,
        json={
            "id_usuario": 0,
            "id_topico": 0,
            "text": "Teste de validação.",
            "temperature": 0,
            "max_tokens": 4000,
            "uploads": [
                {
                    "id_upload": 1,
                    "nome_original": "doc.txt",
                    # extensao ausente intencionalmente
                }
            ],
        },
    )

    assert response.status_code == 422


@responses.activate
def test_upload_e_chat_normal_coexistem(client, mock_solr_post):
    """Upload não deve interferir no fluxo normal de chat (campos coexistem no payload)."""
    _mock_history_endpoint(id_topico=10)

    conteudo_arquivo = b"Memorando de servico numero 42."
    _mock_download_endpoint(
        id_upload=600,
        content=conteudo_arquivo,
        filename="memorando.txt",
        content_type="text/plain",
    )

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Analisei o memorando junto com o histórico da conversa.",
    )

    # Histórico simulado
    responses.add(
        responses.GET,
        f"{SEI_API_BASE}/md_ia_consulta_historico_topico",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_historico_topico",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdTopico": "10",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "Pergunta": "Qual é o assunto?",
                    "Resposta": "O assunto é a gestão de processos.",
                    "DthCadastro": "01/01/2024 10:00:00",
                    "TotalTokens": 50,
                }
            ],
        },
        status=200,
    )

    uploads_recebidos = []

    async def spy_process_uploads(uploads):
        from sei_ia.data.etl.extract.uploads import process_uploads as real_fn

        resultado = await real_fn(uploads)
        uploads_recebidos.extend(uploads)
        return resultado

    with (
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.routers.chat.process_uploads",
            side_effect=spy_process_uploads,
        ),
    ):
        response = client.post(
            ENDPOINT,
            headers=HEADERS,
            json={
                "id_usuario": 5,
                "id_topico": 10,
                "text": "Analise o memorando considerando o contexto anterior.",
                "temperature": 0,
                "max_tokens": 4000,
                "uploads": [
                    {
                        "id_upload": 600,
                        "nome_original": "memorando.txt",
                        "extensao": "txt",
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert len(uploads_recebidos) == 1
    assert uploads_recebidos[0].id_upload == 600

    response_json = response.json()
    assert "choices" in response_json
    assert len(response_json["choices"][0]["message"]["content"]) > 0
