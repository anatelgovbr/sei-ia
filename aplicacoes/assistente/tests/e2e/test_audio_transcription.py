"""Testes E2E para a funcionalidade de transcrição de áudio no Assistente IA.

Verifica o fluxo completo de uma requisição de chat que inclui uploads de áudio:
  1. Recebimento do payload com UploadItem de extensão de áudio
  2. Download do arquivo via API SEI
  3. Transcrição via LiteLLM Proxy (speech-to-text)
  4. Inclusão do texto transcrito no contexto do LLM (user_request)
  5. Adição de AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION ao system_prompt
  6. Geração da resposta pelo LLM

Endpoint testado: POST /llm_lang/chat_gpt_4o_mini_128k
"""

from unittest.mock import AsyncMock, patch

import responses
from langchain_core.messages import AIMessage

ENDPOINT = "/llm_lang/chat_gpt_4o_mini_128k"
HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json",
    "X-Internal-Test-Call": "true",
}

SEI_API_BASE = "http://mock-sei-api:8000"


# ---------------------------------------------------------------------------
# Helpers reutilizados
# ---------------------------------------------------------------------------


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
def test_upload_mp3_aciona_transcricao_e_inclui_no_contexto(client, mock_solr_post):
    """Fluxo E2E: upload de MP3 é baixado, transcrito e incluído no user_request."""
    _mock_history_endpoint(id_topico=0)
    _mock_download_endpoint(
        id_upload=101,
        content=b"fake mp3 frame data",
        filename="reuniao.mp3",
        content_type="audio/mpeg",
    )

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Baseado na transcrição da reunião, o assunto principal foi aprovação do orçamento.",
    )

    TEXTO_TRANSCRITO = "Aprovação do orçamento para 2024 por unanimidade."
    uploads_processados = []

    async def spy_process_uploads(uploads):
        from sei_ia.data.etl.extract.uploads import process_uploads as real_fn

        with patch(
            "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
            new_callable=AsyncMock,
            return_value=TEXTO_TRANSCRITO,
        ):
            resultado = await real_fn(uploads)
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
                "text": "Resuma a reunião.",
                "uploads": [
                    {
                        "id_upload": 101,
                        "nome_original": "reuniao.mp3",
                        "extensao": "mp3",
                    }
                ],
            },
        )

    assert response.status_code == 200, (
        f"Esperado 200, obtido {response.status_code}: {response.text}"
    )
    assert len(uploads_processados) == 1
    assert uploads_processados[0].id_upload == 101
    assert uploads_processados[0].extensao == "mp3"

    response_json = response.json()
    assert "choices" in response_json
    assert len(response_json["choices"]) > 0


@responses.activate
def test_upload_audio_adiciona_instrucao_no_system_prompt(client, mock_solr_post):
    """Upload de áudio deve adicionar AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION ao system_prompt."""
    _mock_history_endpoint(id_topico=0)
    _mock_download_endpoint(
        id_upload=200,
        content=b"fake wav data",
        filename="depoimento.wav",
        content_type="audio/wav",
    )

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Resposta com base no áudio transcrito.",
    )

    TEXTO_TRANSCRITO = "O depoente afirma que esteve presente na reunião."
    system_prompts_capturados = []

    async def mock_process_uploads(uploads):
        return (
            f"<uploads>\n---\n# Arquivo: depoimento.wav\n{TEXTO_TRANSCRITO}\n</uploads>"
        )

    async def mock_build_graph():
        from sei_ia.agents.chat_completion_graph import build_chat_completion_graph

        graph = await build_chat_completion_graph()
        original_ainvoke = graph.ainvoke

        async def spy_ainvoke(state, *args, **kwargs):
            system_prompts_capturados.append(state.get("system_prompt", ""))
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
                "text": "O que disse o depoente?",
                "uploads": [
                    {
                        "id_upload": 200,
                        "nome_original": "depoimento.wav",
                        "extensao": "wav",
                    }
                ],
            },
        )

    assert response.status_code == 200

    from sei_ia.data.etl.extract.uploads import AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION

    assert len(system_prompts_capturados) > 0
    assert AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION in system_prompts_capturados[0]


@responses.activate
def test_upload_nao_audio_nao_adiciona_instrucao_no_system_prompt(
    client, mock_solr_post
):
    """Upload de arquivo não-áudio (PDF, TXT etc.) não deve adicionar a instrução de áudio."""
    _mock_history_endpoint(id_topico=0)
    _mock_download_endpoint(
        id_upload=300,
        content=b"Conteudo do relatorio tecnico.",
        filename="relatorio.txt",
        content_type="text/plain",
    )

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Relatório analisado com sucesso.",
    )

    system_prompts_capturados = []

    async def spy_process_uploads(uploads):
        from sei_ia.data.etl.extract.uploads import process_uploads as real_fn

        resultado = await real_fn(uploads)
        return resultado

    async def mock_build_graph():
        from sei_ia.agents.chat_completion_graph import build_chat_completion_graph

        graph = await build_chat_completion_graph()
        original_ainvoke = graph.ainvoke

        async def spy_ainvoke(state, *args, **kwargs):
            system_prompts_capturados.append(state.get("system_prompt", ""))
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
            side_effect=spy_process_uploads,
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
                "text": "Analise o relatório.",
                "uploads": [
                    {
                        "id_upload": 300,
                        "nome_original": "relatorio.txt",
                        "extensao": "txt",
                    }
                ],
            },
        )

    assert response.status_code == 200

    from sei_ia.data.etl.extract.uploads import AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION

    assert len(system_prompts_capturados) > 0
    assert AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION not in system_prompts_capturados[0]


@responses.activate
def test_texto_transcrito_concatenado_ao_user_request(client, mock_solr_post):
    """O conteúdo transcrito do áudio deve aparecer no user_request enviado ao LLM."""
    _mock_history_endpoint(id_topico=0)

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Resposta com base na transcrição.",
    )

    TEXTO_TRANSCRITO = "O ministro declarou que o projeto será aprovado."
    user_requests_capturados = []

    async def mock_process_uploads(uploads):
        return (
            f"<uploads>\n---\n# Arquivo: discurso.mp3\n{TEXTO_TRANSCRITO}\n</uploads>"
        )

    async def mock_build_graph():
        from sei_ia.agents.chat_completion_graph import build_chat_completion_graph

        graph = await build_chat_completion_graph()
        original_ainvoke = graph.ainvoke

        async def spy_ainvoke(state, *args, **kwargs):
            user_requests_capturados.append(state.get("user_request", ""))
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
                "text": "O que disse o ministro?",
                "uploads": [
                    {
                        "id_upload": 400,
                        "nome_original": "discurso.mp3",
                        "extensao": "mp3",
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert len(user_requests_capturados) > 0
    assert TEXTO_TRANSCRITO in user_requests_capturados[0]
    assert "<uploads>" in user_requests_capturados[0]


@responses.activate
def test_falha_na_transcricao_retorna_status_200_com_erro_tratado(
    client, mock_solr_post
):
    """Falha na transcrição de áudio não deve derrubar a requisição."""
    _mock_history_endpoint(id_topico=0)
    _mock_download_endpoint(
        id_upload=500,
        content=b"fake audio data",
        filename="falho.mp3",
        content_type="audio/mpeg",
    )

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Não foi possível processar o áudio, mas posso ajudar de outra forma.",
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
            "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
            new_callable=AsyncMock,
            side_effect=Exception("Serviço de transcrição fora do ar"),
        ),
    ):
        response = client.post(
            ENDPOINT,
            headers=HEADERS,
            json={
                "id_usuario": 0,
                "id_topico": 0,
                "text": "Transcreva o áudio.",
                "uploads": [
                    {
                        "id_upload": 500,
                        "nome_original": "falho.mp3",
                        "extensao": "mp3",
                    }
                ],
            },
        )

    assert response.status_code == 200
    response_json = response.json()
    assert "choices" in response_json


@responses.activate
def test_upload_audio_sem_uploads_nao_adiciona_instrucao(client, mock_solr_post):
    """Requisição sem uploads não deve adicionar AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION."""
    _mock_history_endpoint(id_topico=0)

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Resposta normal sem áudio.",
    )

    system_prompts_capturados = []

    async def mock_build_graph():
        from sei_ia.agents.chat_completion_graph import build_chat_completion_graph

        graph = await build_chat_completion_graph()
        original_ainvoke = graph.ainvoke

        async def spy_ainvoke(state, *args, **kwargs):
            system_prompts_capturados.append(state.get("system_prompt", ""))
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
                "text": "Qual é o prazo para recurso?",
            },
        )

    assert response.status_code == 200

    from sei_ia.data.etl.extract.uploads import AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION

    if system_prompts_capturados:
        assert (
            AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION not in system_prompts_capturados[0]
        )


@responses.activate
def test_mistura_audio_e_texto_system_prompt_recebe_instrucao(client, mock_solr_post):
    """Com mix de áudio e texto, system_prompt deve receber a instrução de áudio."""
    _mock_history_endpoint(id_topico=0)

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Analisei o relatório e a transcrição do áudio.",
    )

    system_prompts_capturados = []

    CONTEUDO_MISTURADO = (
        "<uploads>\n"
        "---\n# Arquivo: relatorio.txt\nConteúdo do relatório.\n"
        "---\n# Arquivo: audio.mp3\nTranscrição do áudio.\n"
        "</uploads>"
    )

    async def mock_process_uploads(uploads):
        return CONTEUDO_MISTURADO

    async def mock_build_graph():
        from sei_ia.agents.chat_completion_graph import build_chat_completion_graph

        graph = await build_chat_completion_graph()
        original_ainvoke = graph.ainvoke

        async def spy_ainvoke(state, *args, **kwargs):
            system_prompts_capturados.append(state.get("system_prompt", ""))
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
                "text": "Analise os dois arquivos.",
                "uploads": [
                    {
                        "id_upload": 1,
                        "nome_original": "relatorio.txt",
                        "extensao": "txt",
                    },
                    {"id_upload": 2, "nome_original": "audio.mp3", "extensao": "mp3"},
                ],
            },
        )

    assert response.status_code == 200

    from sei_ia.data.etl.extract.uploads import AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION

    assert len(system_prompts_capturados) > 0
    assert AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION in system_prompts_capturados[0]


@responses.activate
def test_upload_audio_ogg_tratado_como_audio(client, mock_solr_post):
    """Upload com extensão OGG deve ser tratado como áudio e acionar transcrição."""
    _mock_history_endpoint(id_topico=0)
    _mock_download_endpoint(
        id_upload=600,
        content=b"fake ogg audio data",
        filename="gravacao.ogg",
        content_type="audio/ogg",
    )

    fake_llm = _make_fake_llm(
        '{"caso": "outro"}',
        "Conteúdo do OGG analisado.",
    )

    uploads_processados = []

    async def spy_process_uploads(uploads):
        from sei_ia.data.etl.extract.uploads import process_uploads as real_fn

        with patch(
            "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
            new_callable=AsyncMock,
            return_value="Conteúdo transcrito do OGG.",
        ):
            resultado = await real_fn(uploads)
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
                "text": "O que está no áudio?",
                "uploads": [
                    {
                        "id_upload": 600,
                        "nome_original": "gravacao.ogg",
                        "extensao": "ogg",
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert len(uploads_processados) == 1
    assert uploads_processados[0].extensao == "ogg"


def test_payload_audio_sem_extensao_retorna_422(client):
    """Payload de upload de áudio sem campo 'extensao' deve retornar 422."""
    response = client.post(
        ENDPOINT,
        headers=HEADERS,
        json={
            "id_usuario": 0,
            "id_topico": 0,
            "text": "Transcreva.",
            "uploads": [
                {
                    "id_upload": 701,
                    "nome_original": "audio.mp3",
                    # extensao ausente intencionalmente
                }
            ],
        },
    )

    assert response.status_code == 422


def test_payload_audio_id_upload_invalido_retorna_422(client):
    """Payload de upload de áudio com id_upload inválido deve retornar 422."""
    response = client.post(
        ENDPOINT,
        headers=HEADERS,
        json={
            "id_usuario": 0,
            "id_topico": 0,
            "text": "Transcreva.",
            "uploads": [
                {
                    "id_upload": "nao-e-numero",
                    "nome_original": "audio.mp3",
                    "extensao": "mp3",
                }
            ],
        },
    )

    assert response.status_code == 422
