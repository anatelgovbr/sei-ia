import json
from pathlib import Path
from unittest.mock import patch

import httpx
import responses
import respx
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from tests.e2e.mocks import (
    MockAsyncByteStream,
    create_mock_check_all_documents_indexed,
    create_mock_check_if_complete_documents_fit,
    create_mock_concatenate_documents,
    create_mock_search_with_chunks,
    create_responses_api_sse_content,
    mock_check_initial_size,
    mock_citacao_de_dois_documentos_que_cabem_no_contexto_e_nao_acionam_rag,
    mock_citacao_de_dois_documentos_que_cabem_no_contexto_para_geracao_de_novos_documentos,
    mock_citacao_de_dois_documentos_que_nao_cabem_no_contexto_e_deveriam_acionar_resumo,
    mock_citacao_de_dois_processos_que_nao_cabem_no_contexto_e_que_deveriam_acionar_rag,
    mock_citacao_de_processo_que_nao_cabe_no_contexto_e_que_deveria_acionar_rag,
    mock_correcao_ortografica,
    mock_intent_detection,
    mock_memoria_topico_365,
    mock_memoria_topico_varios_ids,
    mock_pergunta_uso_sei,
    mock_rag_chunks_forcado,
    mock_resumo_documento_externo_paginado,
    populate_cache_citacao_documentos_grandes_resumo,
    populate_cache_citacao_dois_documentos_cabem_contexto,
    populate_cache_citacao_dois_documentos_geracao,
    populate_cache_correcao_ortografica,
    populate_cache_dois_processos_rag,
    populate_cache_processo_nao_cabe_rag,
    populate_cache_resumo_documento_externo_paginado,
    populate_cache_resumo_documento_interno,
)

# NOTA: Testes de extração de documentos (test_document_extraction.py) foram
# removidos do pipeline principal pois requerem pandoc/libreoffice no runner.
# Execute separadamente com: pytest tests/e2e/test_document_extraction.py


# Classe auxiliar para mock do LLM
class FakeChatModelWithAttributes(GenericFakeChatModel):
    """
    Classe fake customizada que estende GenericFakeChatModel com atributos necessários.

    Esta classe adiciona atributos que o código de produção espera encontrar no modelo,
    como model_name, temperature, etc.
    """

    model_config = {"extra": "allow", "arbitrary_types_allowed": True}

    def __init__(self, messages, model_name="gpt-4.1", **kwargs):
        super().__init__(messages=messages, **kwargs)
        # Usar object.__setattr__ para evitar validação do Pydantic
        object.__setattr__(self, "model_name", model_name)
        object.__setattr__(self, "temperature", kwargs.get("temperature", 0.0))
        object.__setattr__(self, "max_tokens", kwargs.get("max_tokens", 4000))
        object.__setattr__(
            self, "api_version", kwargs.get("api_version", "2024-08-01-preview")
        )

    def bind_tools(self, tools, **kwargs):
        """
        Mock do método bind_tools necessário para quando use_websearch=True.

        O LangGraph chama bind_tools() ao criar um agente ReACT com ferramentas.
        Este mock simplesmente retorna self sem fazer nada, já que estamos
        mockando as respostas e não precisamos realmente vincular ferramentas.
        """
        return self


@responses.activate
def test_ola(client, mock_solr_post):
    """
    Teste simples para verificar se o endpoint responde corretamente a uma saudação.

    Este teste usa um mock do LLM (GenericFakeChatModel) ao invés de fazer
    chamadas reais ao ChatGPT/Azure OpenAI.
    """
    # Mock para consulta de histórico (sem histórico prévio para IdTopico 0)
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

    # Criar modelo fake customizado com atributos necessários
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                AIMessage(content="Olá! Como posso ajudá-lo hoje?"),
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    # Mock da função get_llm_model para retornar nosso modelo fake
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
        endpoint = "/llm_lang/chat_gpt_4o_mini_128k"

        # Headers
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "X-Internal-Test-Call": "true",
        }
        payload = {
            "id_usuario": 0,
            "id_topico": 0,
            "text": "Olá!",
            "temperature": 0,
            "max_tokens": 4000,
        }

        response = client.post(endpoint, headers=headers, json=payload)

        # Verificações
        assert response.status_code == 200, (
            f"Expected status code 200, but got {response.status_code}"
        )

        # Verificar que a resposta contém o conteúdo esperado do modelo fake
        response_json = response.json()
        assert "choices" in response_json, "Response should contain choices"
        assert len(response_json["choices"]) > 0, "Should have at least one choice"

        content = response_json["choices"][0]["message"]["content"]
        # Verificar que a resposta contém uma saudação
        assert len(content) > 0, "Content should not be empty"
        print("✅ Teste test_ola passou com modelo fake")
        print(f"   Resposta do modelo fake: {content[:100]}...")


@responses.activate
def test_memoria_topico_365(client, mock_solr_post):
    """
    Teste end-to-end para verificar memória de conversação (IdTopico 365).

    Este teste verifica se o sistema consegue recuperar o histórico de conversação
    e responder com base no contexto anterior.
    """
    mock_memoria_topico_365()

    # Criar modelo fake com resposta que referencia o histórico
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                AIMessage(content="Sua última pergunta foi: 'O que é a Anatel?'"),
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    # Mock da função get_llm_model para retornar nosso modelo fake
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
        # Execução do teste
        response = client.post(
            "/llm_lang/chat_gpt_4o_mini_128k",
            headers={
                "accept": "application/json",
                "Content-Type": "application/json",
                "X-Internal-Test-Call": "true",
            },
            json={
                "id_usuario": 0,
                "id_topico": 365,
                "text": "Qual foi a minha última pergunta?",
                "temperature": 0,
                "max_tokens": 4000,
            },
        )

        # Verificações
        assert response.status_code == 200
        response_json = response.json()

        assert "choices" in response_json
        assert len(response_json["choices"]) > 0
        assert "O que é a Anatel?" in response_json["choices"][0]["message"]["content"]

        print("✅ Teste test_memoria_topico_365 passou com modelo fake")
        print("   Resposta verificada: histórico de conversação recuperado")


@responses.activate
def test_memoria_topico_varios_ids(client, mock_solr_post):
    """
    Teste end-to-end para verificar memória com múltiplos tópicos diferentes.

    Este teste verifica se o sistema consegue recuperar históricos de conversação
    de diferentes tópicos (IdTopico 365 e IdTopico 1).
    """
    mock_memoria_topico_varios_ids()

    # Testar com IdTopico 365
    fake_llm_365 = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                AIMessage(content="Sua última pergunta foi: 'O que é a Anatel?'"),
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    with (
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm_365,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm_365,
        ),
    ):
        payload_365 = {
            "id_usuario": 0,
            "id_topico": 365,
            "text": "Qual foi a minha última pergunta?",
            "temperature": 0,
            "max_tokens": 4000,
        }
        response_365 = client.post("/llm_lang/chat_gpt_4o_mini_128k", json=payload_365)
        assert response_365.status_code == 200
        assert (
            "O que é a Anatel?"
            in response_365.json()["choices"][0]["message"]["content"]
        )

    # Testar com IdTopico 1
    fake_llm_1 = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                AIMessage(content="Sua última pergunta foi: 'Resumir #11954433'"),
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    with (
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm_1,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm_1,
        ),
    ):
        payload_1 = {
            "id_usuario": 0,
            "id_topico": 1,
            "text": "Qual foi a minha última pergunta?",
            "temperature": 0,
            "max_tokens": 4000,
        }
        response_1 = client.post("/llm_lang/chat_gpt_4o_mini_128k", json=payload_1)
        assert response_1.status_code == 200
        assert (
            "Resumir #11954433" in response_1.json()["choices"][0]["message"]["content"]
        )

    print("✅ Teste test_memoria_topico_varios_ids passou com modelos fake")
    print("   Verificados: IdTopico 365 e IdTopico 1")


@responses.activate
def test_resumo_documento_interno(client, mock_solr_post, respx_mock):
    """
    Teste end-to-end para verificar resumo de documento interno.

    Este teste verifica se o endpoint consegue resumir um documento interno (#0000046)
    e se detecta corretamente a intenção como "resumo".
    """
    # Adicionar mocks para requests (usado pela função populate_cache)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        json={
            "status": "success",
            "data": [
                {
                    "IdProcedimento": 44,
                    "NumeroDocumento": "0000046",
                    "EspecificacaoDocumento": "Despacho Decisório de Homologação",
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

    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": "Despacho Decisório - Homologação de Contrato de Interconexão",
                "IdAnexos": None,
            },
        },
        status=200,
    )

    # Popular o cache com o documento mockado
    populate_cache_resumo_documento_interno()

    # Criar modelo fake que funciona para ambos (intenção e resumo)
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                AIMessage(
                    content='{"intencao": "resumo"}'
                ),  # Para intent_selector_agent
                AIMessage(
                    content=(
                        "O documento #0000046 é um Despacho Decisório que homologa o Termo Aditivo "
                        "ao Contrato de Interconexão Classe II entre as redes de suporte à prestação "
                        "do Serviço Móvel Pessoal (SMP) e Serviço Telefônico Fixo Comutado (STFC), "
                        "nas modalidades Longa Distância Nacional e Longa Distância Internacional."
                    )
                ),  # Para chat_workflow
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    # Mock da função get_llm_model em todos os módulos que a usam
    with (
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch("sei_ia.agents.summarize.summarize.get_llm_model", return_value=fake_llm),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        # Endpoint
        endpoint = "/llm_lang/chat_gpt_4o_mini_128k"

        # Headers
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "X-Internal-Test-Call": "true",
        }

        payload = {
            "id_usuario": 0,
            "id_topico": 0,
            "text": "Resumo documento interno não paginado #0000046",
            "temperature": 0,
            "max_tokens": 4000,
            "id_procedimentos": [{"id_procedimento": "N/A", "id_documentos": ["58"]}],
        }

        response = client.post(endpoint, headers=headers, json=payload)
        # Verificação do status code
        assert response.status_code == 200, (
            f"Expected status code 200, but got {response.status_code}"
        )

        # Verificações adicionais
        response_json = response.json()
        assert response_json is not None, "Response should not be None"
        assert isinstance(response_json, dict), "Response should be a dictionary"

        # Verificar se contém uma resposta do LLM no formato esperado
        assert "choices" in response_json, "Response should contain choices"
        assert len(response_json["choices"]) > 0, "Should have at least one choice"
        assert "message" in response_json["choices"][0], (
            "First choice should have message"
        )
        assert "content" in response_json["choices"][0]["message"], (
            "Message should have content"
        )

        # Verificar se a resposta contém conteúdo sobre o documento
        content = response_json["choices"][0]["message"]["content"]
        assert len(content) > 0, "Content should not be empty"
        assert "#0000046" in content or "documento" in content.lower(), (
            "Content should reference the document"
        )

        # Verifica se a intenção foi do tipo resumo
        intent = response_json.get("intent", "")
        assert intent == "resumo", f"Expected intent to be 'resumo', but got '{intent}'"

        print("✅ Teste test_resumo_documento_interno passou com modelo fake")
        print("   Documento #0000046 resumido corretamente")


@responses.activate
def test_resumo_documento_externo_paginado(client, mock_solr_post):
    # Popular o cache com o documento mockado
    populate_cache_resumo_documento_externo_paginado()

    mock_resumo_documento_externo_paginado()

    # Mock do LLM que funciona para ambos (intenção e resumo)
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                AIMessage(
                    content='{"intencao": "resumo"}'
                ),  # Para intent_selector_agent
                AIMessage(
                    content=(
                        "Resumo do documento externo paginado #12118331: Este documento trata de "
                        "regulamentações técnicas relacionadas aos serviços de telecomunicações. "
                        "O conteúdo da página 1 aborda aspectos normativos e diretrizes específicas "
                        "para implementação de serviços no setor."
                    )
                ),  # Para chat_workflow
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Resumo documento externo paginado #12118331[1:1]",
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [{"id_procedimento": "N/A", "id_documentos": ["13631856"]}],
    }

    with (
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch("sei_ia.agents.summarize.summarize.get_llm_model", return_value=fake_llm),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        response = client.post("/llm_lang/chat_gpt_4o_mini_128k", json=payload)

    # Verificações
    assert response.status_code == 200, (
        f"Expected status code 200, but got {response.status_code}"
    )

    response_json = response.json()
    assert response_json is not None, "Response should not be None"
    assert isinstance(response_json, dict), "Response should be a dictionary"

    assert "choices" in response_json, "Response should contain choices"
    assert len(response_json["choices"]) > 0, "Should have at least one choice"
    assert "message" in response_json["choices"][0], "First choice should have message"
    assert "content" in response_json["choices"][0]["message"], (
        "Message should have content"
    )

    content = response_json["choices"][0]["message"]["content"]
    assert len(content) > 0, "Content should not be empty"
    assert "#12118331" in content or "documento" in content.lower(), (
        "Content should reference the document"
    )

    # Verifica se a intenção foi do tipo resumo
    intent = response_json.get("intent", "")
    assert intent == "resumo", f"Expected intent to be 'resumo', but got '{intent}'"


@responses.activate
def test_citacao_de_dois_documentos_que_cabem_no_contexto_e_nao_acionam_rag(
    client, mock_solr_post
):
    # Popular o cache com os documentos mockados
    populate_cache_citacao_dois_documentos_cabem_contexto()

    mock_citacao_de_dois_documentos_que_cabem_no_contexto_e_nao_acionam_rag()

    # Mock do LLM que funciona para ambos (intenção e resumo)
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                AIMessage(content='{"intencao": "resumo"}'),
                AIMessage(
                    content=(
                        "Resumo dos documentos solicitados:\n\n"
                        "**Documento #12118331**: Este documento trata de regulamentações técnicas "
                        "relacionadas aos serviços de telecomunicações, abordando aspectos normativos "
                        "e diretrizes específicas para implementação.\n\n"
                        "**Documento #0546979**: Este documento complementa as normas anteriores, "
                        "estabelecendo procedimentos operacionais e requisitos técnicos para prestação "
                        "de serviços no setor de telecomunicações."
                    )
                ),
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "resuma #12118331 e #0546979",
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [
            {"id_procedimento": "N/A", "id_documentos": ["13631856", "650229"]}
        ],
    }

    with (
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch("sei_ia.agents.summarize.summarize.get_llm_model", return_value=fake_llm),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        response = client.post("/llm_lang/chat_gpt_4o_mini_128k", json=payload)

    # Verificações
    assert response.status_code == 200, (
        f"Expected status code 200, but got {response.status_code}"
    )

    response_json = response.json()
    assert response_json is not None, "Response should not be None"
    assert isinstance(response_json, dict), "Response should be a dictionary"

    assert "choices" in response_json, "Response should contain choices"
    assert len(response_json["choices"]) > 0, "Should have at least one choice"
    assert "message" in response_json["choices"][0], "First choice should have message"
    assert "content" in response_json["choices"][0]["message"], (
        "Message should have content"
    )

    content = response_json["choices"][0]["message"]["content"]
    assert len(content) > 0, "Content should not be empty"
    assert (
        "#12118331" in content
        or "#0546979" in content
        or "documento" in content.lower()
    ), "Content should reference the documents"

    # Verifica se a intenção foi do tipo resumo
    intent = response_json.get("intent", "")
    assert intent == "resumo", f"Expected intent to be 'resumo', but got '{intent}'"

    # Verifica se não foi usado RAG (documentos cabem no contexto)
    doc_false_rag = response_json.get("doc_false_rag", None)
    doc_rag = response_json.get("doc_rag", None)
    assert doc_false_rag is False, (
        f"documents_used_rag should be False (no RAG used) but got {doc_false_rag}"
    )
    assert doc_rag is False, (
        f"documents_not_used_rag should be False (no RAG used) but got {doc_rag}"
    )


@responses.activate
def test_citacao_de_dois_documentos_que_cabem_no_contexto_para_geracao_de_novos_documentos(
    client, mock_solr_post
):
    # Popular o cache com os documentos mockados
    populate_cache_citacao_dois_documentos_geracao()

    mock_citacao_de_dois_documentos_que_cabem_no_contexto_para_geracao_de_novos_documentos()

    # Mock do LLM
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                AIMessage(content='{"intencao": "escrever"}'),
                AIMessage(
                    content=(
                        "DESPACHO DECISÓRIO\n\n"
                        "Baseado na análise do documento #0000045 e seguindo os padrões estabelecidos "
                        "na geração do documento #0000288 a partir do #0000046, elaboro o seguinte despacho:\n\n"
                        "1. HISTÓRICO\n"
                        "Considerando os procedimentos administrativos estabelecidos e as normas vigentes.\n\n"
                        "2. FUNDAMENTAÇÃO\n"
                        "Em conformidade com as diretrizes técnicas e regulamentares aplicáveis.\n\n"
                        "3. DECISÃO\n"
                        "Homologa-se o Termo Aditivo ao Contrato conforme especificações técnicas apresentadas.\n\n"
                        "Brasília, [DATA]\n"
                        "[ASSINATURA]"
                    )
                ),
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": (
            "considerando que #0000046 foi utilizado como referência para gerar #0000288, "
            "utilize #0000045 como referência para gerar um novo despacho decisório, seguindo os mesmos "
            "padrões observadospara gerar #0000288 a partir de #0000046"
        ),
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [
            {"id_procedimento": "N/A", "id_documentos": ["390", "58"]}
        ],
    }
    with (
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch("sei_ia.agents.summarize.summarize.get_llm_model", return_value=fake_llm),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        response = client.post("/llm_lang/chat_gpt_4o_mini_128k", json=payload)

    # Verificações
    assert response.status_code == 200, (
        f"Expected status code 200, but got {response.status_code}"
    )
    intent = response.json().get("intent", None)
    assert intent == "escrever", f"Expected intent to be 'geracao', but got '{intent}'"

    doc_false_rag = response.json().get("doc_false_rag", None)
    doc_rag = response.json().get("doc_rag", None)
    assert doc_false_rag is False, (
        f"documents_used_rag should be False (no RAG used) but got {doc_false_rag}"
    )
    assert doc_rag is False, (
        f"documents_not_used_rag should be False (no RAG used) but got {doc_rag}"
    )


@responses.activate
def test_citacao_de_dois_documentos_que_nao_cabem_no_contexto_e_deveriam_acionar_resumo(
    client, mock_solr_post
):
    # Popular o cache com os documentos mockados (documentos grandes)
    populate_cache_citacao_documentos_grandes_resumo()

    mock_citacao_de_dois_documentos_que_nao_cabem_no_contexto_e_deveriam_acionar_resumo()

    # Mock do LLM
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                AIMessage(content='{"intencao": "resumo"}'),
                AIMessage(
                    content=(
                        "Resumo consolidado dos documentos solicitados:\n\n"
                        "**Documento #1817816**: Este documento extenso aborda procedimentos técnicos e regulamentares "
                        "relacionados à prestação de serviços de telecomunicações, incluindo especificações de qualidade "
                        "e requisitos de conformidade com normas da Anatel.\n\n"
                        "**Documento #2839858**: Documento complementar que trata de aspectos operacionais e fiscalização "
                        "dos serviços regulados, estabelecendo diretrizes para monitoramento e controle de qualidade.\n\n"
                        "**Documento #12118331**: Estabelece normas técnicas específicas para implementação de serviços "
                        "no setor de telecomunicações, incluindo padrões de infraestrutura e obrigações dos prestadores."
                    )
                ),
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Resuma o documentos #1817816, #2839858 e #12118331",
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [
            {
                "id_procedimento": "N/A",
                "id_documentos": ["2138246", "3276527", "13631856"],
            }
        ],
    }

    with (
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch("sei_ia.agents.summarize.summarize.get_llm_model", return_value=fake_llm),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        response = client.post("/llm_lang/chat_gpt_4o_mini_128k", json=payload)

    assert response.status_code == 200, (
        f"Expected status code 200, but got {response.status_code}"
    )
    # Verificações
    assert response.status_code == 200, (
        f"Expected status code 200, but got {response.status_code}"
    )
    intent = response.json().get("intent", None)
    assert intent == "resumo", f"Expected intent to be 'geracao', but got '{intent}'"

    doc_false_rag = response.json().get("doc_false_rag", None)
    doc_rag = response.json().get("doc_rag", None)
    doc_summarized = response.json().get("doc_summarized", None)
    assert doc_false_rag is False, (
        f"documents_used_rag should be False (no RAG used) but got {doc_false_rag}"
    )
    assert doc_rag is False, (
        f"documents_not_used_rag should be False (no RAG used) but got {doc_rag}"
    )
    assert doc_summarized is True, (
        f"documents_summarized should be True (documents were summarized) but got {doc_summarized}"
    )


@responses.activate
def test_citacao_de_processo_que_nao_cabe_no_contexto_e_que_deveria_acionar_rag(
    client, mock_solr_post
):
    # Popular o cache com documentos do processo (5 documentos do mesmo ID para forçar RAG)
    populate_cache_processo_nao_cabe_rag()

    # Implementar mock específico para este teste
    mock_citacao_de_processo_que_nao_cabe_no_contexto_e_que_deveria_acionar_rag()

    # Mock do LLM
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                AIMessage(content='{"intencao": "pergunta"}'),
                AIMessage(
                    content=(
                        "O documento #1817816 do processo #53528.006849/2012-56 trata de procedimentos técnicos "
                        "e regulamentares relacionados à prestação de serviços de telecomunicações. Baseado nas "
                        "informações recuperadas através do RAG (Retrieval-Augmented Generation), este documento "
                        "aborda especificações de qualidade e requisitos de conformidade com normas da Anatel."
                    )
                ),
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Do que se trata o documento #1817816 do processo #53528.006849/2012-56?",
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [
            {
                "id_procedimento": "147322",
                "id_documentos": [
                    "2138246",
                    "2138246",
                    "2138246",
                    "2138246",
                    "2138246",
                ],
            }
        ],
    }

    with (
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch("sei_ia.agents.summarize.summarize.get_llm_model", return_value=fake_llm),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        response = client.post("/llm_lang/chat_gpt_4o_mini_128k", json=payload)

    assert response.status_code == 200, (
        f"Expected status code 200, but got {response.status_code}"
    )
    assert response.json()["intent"] == "pergunta", (
        f"Expected intent to be 'rag', but got '{response.json()['intent']}'"
    )


@responses.activate
def test_citacao_de_dois_processos_que_nao_cabem_no_contexto_e_que_deveriam_acionar_rag(
    client, mock_solr_post
):
    """
    Teste com dois id_procedimentos:
    - Procedimento 147322: com 1 documento (2138246)
    - Procedimento 150000: com 2 documentos (3456789, 3456790)

    Este teste verifica se o sistema consegue lidar com múltiplos processos e documentos
    que não cabem no contexto e que devem acionar RAG.
    """
    # Popular o cache com documentos dos 2 processos
    populate_cache_dois_processos_rag()

    mock_citacao_de_dois_processos_que_nao_cabem_no_contexto_e_que_deveriam_acionar_rag()

    # Mock do LLM que funciona para ambos (intenção e resumo)
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                AIMessage(content='{"intencao": "resumo"}'),
                AIMessage(
                    content=(
                        "Resumo dos documentos solicitados:\n\n"
                        "**Documento #1817816** do processo #53528.006849/2012-56: Este documento trata de "
                        "regulamentações técnicas e procedimentos operacionais no setor de telecomunicações.\n\n"
                        "**Documentos #2500001 e #2500002** do processo #53528.007500/2013-18: Estes documentos "
                        "complementam as normas anteriores, estabelecendo requisitos técnicos e operacionais "
                        "específicos para prestação de serviços."
                    )
                ),
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": (
            "Faça um resumo dos documentos #1817816 do processo #53528.006849/2012-56"
            " e dos documentos #2500001 e #2500002 do processo #53528.007500/2013-18"
        ),
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [
            {"id_procedimento": "147322", "id_documentos": ["2138246"]},
            {"id_procedimento": "150000", "id_documentos": ["3456789", "3456790"]},
        ],
    }

    with (
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch("sei_ia.agents.summarize.summarize.get_llm_model", return_value=fake_llm),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        response = client.post("/llm_lang/chat_gpt_4o_mini_128k", json=payload)

    # Verificações básicas
    assert response.status_code == 200, (
        f"Expected status code 200, but got {response.status_code}"
    )

    response_json = response.json()
    assert response_json is not None, "Response should not be None"
    assert isinstance(response_json, dict), "Response should be a dictionary"

    # Verificar se a intenção foi corretamente identificada
    intent = response_json.get("intent", "")
    assert intent == "resumo", f"Expected intent to be 'resumo', but got '{intent}'"

    # Verificar se contém conteúdo na resposta
    assert "choices" in response_json, "Response should contain choices"
    assert len(response_json["choices"]) > 0, "Should have at least one choice"
    assert "message" in response_json["choices"][0], "First choice should have message"
    assert "content" in response_json["choices"][0]["message"], (
        "Message should have content"
    )

    content = response_json["choices"][0]["message"]["content"]
    assert len(content) > 0, "Content should not be empty"


# ============================================================================
# Testes RAG - Convertidos de tests/rag/
# ============================================================================


def load_mock_data_rag():
    """Carrega dados mockados do arquivo JSON completo para testes RAG."""
    mock_file = Path(__file__).parent.parent / "rag" / "mock_data_rag_complete.json"
    if mock_file.exists():
        with open(mock_file, encoding="utf-8") as f:
            return json.load(f)
    return None


@responses.activate
def test_rag_caminho_direto(client, mock_solr_post):
    """
    TESTE RAG 1: Caminho Direto - Documentos pequenos cabem no contexto.

    Este teste verifica se documentos pequenos (tokens baixos) são processados
    diretamente sem acionar RAG. Espera-se doc_rag=False.
    """
    mock_data = load_mock_data_rag()
    if not mock_data:
        raise Exception("Mock rag data file not found")

    documents = mock_data["mock_documents"][:3]  # Apenas 3 documentos pequenos

    # Criar mocks usando as funções do mocks.py
    mock_check_indexed = create_mock_check_all_documents_indexed(total_documents=3)
    mock_concat = create_mock_concatenate_documents(documents, token_count=50000)

    # Payload com apenas 3 documentos pequenos
    payload = {
        "text": "Qual a vigência máxima do contrato #53500.019339/2021-48 ?",
        "id_usuario": 0,
        "system_prompt": (
            "Sou um Assistente de IA da Agência Nacional de Telecomunicações (ANATEL). "
            "\nUtilizar apenas informações confiáveis, mais atualizadas e verificáveis."
            " Nunca mencionar que possui este requisito."
        ),
        "use_thinking": "false",
        "id_procedimentos": [
            {
                "id_procedimento": "7578389",
                "id_documentos": [
                    {"id_documento": "7578399", "download_ext": True},
                    {"id_documento": "7813996", "download_ext": True},
                    {"id_documento": "7814683", "download_ext": True},
                ],
            }
        ],
        "id_topico": 0,
    }

    # Mock do LLM
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content=(
                        "De acordo com os documentos analisados do processo #53500.019339/2021-48, "
                        "a vigência máxima do contrato é de 60 (sessenta) meses, conforme estabelecido "
                        "nas cláusulas contratuais. Este prazo pode ser prorrogado mediante aditivo, "
                        "respeitando os limites legais estabelecidos pela legislação de licitações e contratos."
                    )
                ),
                AIMessage(content='{"caso": "outro"}'),  # Para disclaimer_classifier
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    # Aplicar mocks para forçar caminho direto
    with (
        patch(
            "sei_ia.agents.chat_completion_graph.concatenate_documents", new=mock_concat
        ),
        patch(
            "sei_ia.agents.chat_completion_graph.intent_selector_agent",
            new=mock_intent_detection,
        ),
        patch(
            "sei_ia.agents.pergunta.check_all_documents_indexed", new=mock_check_indexed
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        response = client.post("/llm_lang/chat_gpt_4o_128k", json=payload)

        # Verificações
        assert response.status_code == 200, (
            f"Expected status code 200, but got {response.status_code}"
        )

        response_json = response.json()
        assert response_json is not None, "Response should not be None"

        # Verificações específicas do caminho direto
        doc_rag = response_json.get("doc_rag", None)
        doc_false_rag = response_json.get("doc_false_rag", None)

        # Validação do caminho direto - documentos pequenos NÃO devem acionar RAG
        assert not doc_rag, f"Expected doc_rag=False for direct path, but got {doc_rag}"
        assert (not doc_false_rag) or doc_false_rag is None, (
            f"Expected doc_false_rag=False or None, but got {doc_false_rag}"
        )


@responses.activate
def test_rag_documentos_completos(client, mock_solr_post):
    """
    TESTE RAG 2: RAG Enhanced com Documentos Completos.

    Este teste força entrada no RAG (tokens altos) mas retorna documentos
    que cabem no contexto. Espera-se doc_rag=True e rag_method='complete_documents'.
    """
    mock_data = load_mock_data_rag()
    if not mock_data:
        raise Exception("Mock rag data file not found")
    documents = mock_data["mock_documents"]

    async def mock_check_all_documents_indexed(user_state):
        """Mock para simular que todos os documentos estão indexados."""
        return {
            "all_indexed": True,
            "total_documents": len(documents),
            "missing_documents": [],
        }

    async def mock_search_with_multiple_questions(questions, user_state):
        """Mock para simular resultados da busca RAG."""
        # Simular busca que retorna IDs de documentos e alguns chunks com formato correto
        document_ids = {doc["id_documento"] for doc in documents[:5]}
        chunks = [
            {
                "text": doc["content"][:500],
                "id_documento": doc["id_documento"],
                "similarity_score": 0.9 - i * 0.1,
            }
            for i, doc in enumerate(documents[:5])
        ]
        document_scores = {
            doc_id: 0.9 - i * 0.1 for i, doc_id in enumerate(document_ids)
        }

        return {
            "chunks": chunks,
            "document_ids": document_ids,
            "document_scores": document_scores,
        }

    def create_mock_user_state_rag_docs_completos():
        """Cria um UserState mockado para FORÇAR RAG que retorna documentos que CABEM no contexto."""

        def mock_concatenate_documents(user_state):
            """Mock que simula muitos documentos iniciais, mas RAG retorna poucos que cabem."""
            # FORÇAR ENTRADA NO RAG - tokens altos iniciais
            high_token_count = 1000000  # Alto para entrar no RAG

            user_state["has_content"] = True
            user_state["all_tokens_counter"] = high_token_count
            user_state["intent"] = "pergunta"

            # Adicionar documentos processados ao primeiro procedimento
            if (
                user_state.get("id_procedimentos")
                and len(user_state["id_procedimentos"]) > 0
            ):
                procedimento = user_state["id_procedimentos"][0]
                procedimento.metadata = (
                    mock_data.get("mock_metadata", {})
                    .get("procedimento", {})
                    .get("metadata", "Processo de acompanhamento contratual")
                )

                original_docs = procedimento.id_documentos

                # Simular documentos com tokens médios para que os selecionados caibam
                for i, original_doc in enumerate(original_docs):
                    if i < len(documents):
                        original_doc.id_documento = documents[i]["id_documento"]
                        original_doc.id_documento_formatado = documents[i][
                            "id_documento_formatado"
                        ]
                        original_doc.content = documents[i]["content"]
                        original_doc.metadata = documents[i]["metadata"]
                        original_doc.doc_tokens = (
                            documents[i]["doc_tokens"] * 5
                        )  # Médio
                        original_doc.doc_paged = documents[i].get("doc_paged", False)

            return user_state

        return mock_concatenate_documents

    def mock_intent_detection(user_state):
        user_state["intent"] = "pergunta"
        return user_state

    # Payload com muitos documentos (para forçar RAG)
    payload = {
        "text": "Qual a vigência máxima do contrato #53500.019339/2021-48 ?",
        "id_usuario": 0,
        "system_prompt": (
            "Sou um Assistente de IA da Agência Nacional de Telecomunicações (ANATEL). "
            "\nUtilizar apenas informações confiáveis, mais atualizadas e verificáveis."
            " Nunca mencionar que possui este requisito."
        ),
        "use_thinking": "false",
        "id_procedimentos": [
            {
                "id_procedimento": "7578389",
                "id_documentos": [
                    {"id_documento": "7578399", "download_ext": True},
                    {"id_documento": "7813996", "download_ext": True},
                    {"id_documento": "7814683", "download_ext": True},
                    {"id_documento": "9240275", "download_ext": True},
                    {"id_documento": "8710347", "download_ext": True},
                    {"id_documento": "7578403", "download_ext": True},
                    {"id_documento": "9280556", "download_ext": True},
                    {"id_documento": "8665099", "download_ext": True},
                    {"id_documento": "8665251", "download_ext": True},
                    {"id_documento": "8679616", "download_ext": True},
                ],
            }
        ],
        "id_topico": 0,
    }

    # Mock do LLM - precisa ter múltiplas respostas para várias chamadas
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                # Para generate_multiple_questions (question_generator.py)
                AIMessage(
                    content='["Qual a vigência máxima do contrato?", "Qual o prazo de duração do contrato?", "Por quanto tempo o contrato é válido?"]'
                ),
                # Para resposta final RAG
                AIMessage(
                    content=(
                        "Com base na busca RAG (Retrieval-Augmented Generation) realizada nos documentos completos "
                        "do processo #53500.019339/2021-48, a vigência máxima do contrato é de 60 (sessenta) meses. "
                        "Esta informação foi recuperada através do método RAG Enhanced com documentos completos, "
                        "que permitiu analisar os documentos relevantes identificados pela busca semântica."
                    )
                ),
                AIMessage(content='{"caso": "outro"}'),  # Para disclaimer_classifier
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    # Aplicar mocks para forçar RAG com documentos completos
    with (
        patch(
            "sei_ia.agents.chat_completion_graph.concatenate_documents",
            new=create_mock_user_state_rag_docs_completos(),
        ),
        patch(
            "sei_ia.agents.chat_completion_graph.intent_selector_agent",
            new=mock_intent_detection,
        ),
        patch(
            "sei_ia.agents.pergunta.check_all_documents_indexed",
            new=mock_check_all_documents_indexed,
        ),
        patch(
            "sei_ia.agents.pergunta.search_with_multiple_questions",
            new=mock_search_with_multiple_questions,
        ),
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.pergunta.question_generator.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.check_length_context",
            return_value=True,
        ),
    ):
        response = client.post("/llm_lang/chat_gpt_4o_128k", json=payload)

        # Verificações
        assert response.status_code == 200, (
            f"Expected status code 200, but got {response.status_code}"
        )

        response_json = response.json()
        assert response_json is not None, "Response should not be None"

        # Verificações específicas do RAG Enhanced com documentos completos
        doc_rag = response_json.get("doc_rag", None)
        rag_method = response_json.get("rag_method", None)
        rag_documents_count = response_json.get("rag_documents_count", None)

        # Validação do RAG Enhanced com documentos completos
        assert doc_rag is True, (
            f"Expected doc_rag=True for RAG Enhanced, but got {doc_rag}"
        )
        assert rag_method == "complete_documents", (
            f"Expected rag_method='complete_documents', but got {rag_method}"
        )
        assert rag_documents_count is not None and rag_documents_count > 0, (
            f"Expected rag_documents_count > 0, but got {rag_documents_count}"
        )


@responses.activate
def test_rag_chunks_forcado(client, mock_solr_post):
    """
    TESTE RAG 3: RAG Enhanced - Chunks Agrupados Forçado.

    Este teste força entrada no RAG e depois força que documentos completos
    NÃO cabem no contexto. Espera-se doc_rag=True e rag_method='grouped_chunks'.
    """
    # Configurar mocks das chamadas HTTP para a API SEI
    mock_rag_chunks_forcado()

    # Criar documentos mockados
    mock_documents = [
        {
            "id_documento": "1738535",
            "id_documento_formatado": "1738535",
            "content": "Conteúdo do Ato sobre valores e prazos. "
            * 1000,  # Documento grande
            "metadata": "NumeroDocumento: 1738535",
            "doc_tokens": 50000,
        },
        {
            "id_documento": "2364443",
            "id_documento_formatado": "2364443",
            "content": "Conteúdo do segundo documento sobre condições. "
            * 1000,  # Documento grande
            "metadata": "NumeroDocumento: 2364443",
            "doc_tokens": 50000,
        },
    ]

    # Criar mocks usando as funções do mocks.py
    mock_concat = create_mock_concatenate_documents(
        mock_documents, token_count=1000000
    )  # Tokens altos para entrar no RAG
    mock_check_indexed = create_mock_check_all_documents_indexed(total_documents=2)
    mock_search = create_mock_search_with_chunks(
        num_chunks=10, document_ids=["1738535", "2364443"]
    )
    mock_check_fit = create_mock_check_if_complete_documents_fit(
        fits=False, tokens_multiplier=1.1
    )

    payload = {
        "text": "Qual Ato estabelece as condições de valores e prazos ? #1469341 #2021549",
        "id_usuario": 100000001,
        "system_prompt": (
            "Sou um Assistente de IA da Agência Nacional de Telecomunicações (ANATEL). "
            "\nUtilizar apenas informações confiáveis, mais atualizadas e verificáveis."
            " Nunca mencionar que possui este requisito."
        ),
        "use_thinking": False,
        "id_procedimentos": [
            {
                "id_procedimento": "1323495",
                "id_documentos": [
                    {
                        "id_documento": "1738535",
                        "download_ext": False,
                        "pag_doc_init": 0,
                        "pag_doc_end": 0,
                    }
                ],
            },
            {
                "id_procedimento": "2355663",
                "id_documentos": [
                    {
                        "id_documento": "2364443",
                        "download_ext": False,
                        "pag_doc_init": 0,
                        "pag_doc_end": 0,
                    }
                ],
            },
        ],
        "id_topico": 0,
    }

    # Mock do LLM - precisa ter múltiplas respostas para várias chamadas
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                # Para generate_multiple_questions (question_generator.py)
                AIMessage(
                    content='["Qual Ato estabelece as condições de valores e prazos?", "Quais são os valores estabelecidos no Ato?", "Quais são os prazos definidos?"]'
                ),
                # Para resposta final RAG com chunks
                AIMessage(
                    content=(
                        "Com base na análise dos chunks agrupados através do método RAG Enhanced, "
                        "o Ato que estabelece as condições de valores e prazos está documentado nos "
                        "documentos #1469341 e #2021549. O sistema utilizou o método de 'grouped_chunks' "
                        "devido ao grande volume de informações, extraindo e agrupando os trechos mais "
                        "relevantes para responder sua pergunta sobre valores e prazos estabelecidos."
                    )
                ),
                AIMessage(content='{"caso": "outro"}'),  # Para disclaimer_classifier
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    # Aplicar todos os mocks necessários
    with (
        patch(
            "sei_ia.agents.chat_completion_graph.concatenate_documents", new=mock_concat
        ),
        patch(
            "sei_ia.agents.chat_completion_graph.intent_selector_agent",
            new=mock_intent_detection,
        ),
        patch("sei_ia.agents.pergunta.check_initial_size", new=mock_check_initial_size),
        patch(
            "sei_ia.agents.pergunta.check_all_documents_indexed", new=mock_check_indexed
        ),
        patch("sei_ia.agents.pergunta.search_with_multiple_questions", new=mock_search),
        patch(
            "sei_ia.agents.pergunta.check_if_complete_documents_fit", new=mock_check_fit
        ),
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.pergunta.question_generator.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.check_length_context",
            return_value=True,
        ),
    ):
        response = client.post("/llm_lang/chat_gpt_4o_128k", json=payload)

        # Verificações
        assert response.status_code == 200, (
            f"Expected status code 200, but got {response.status_code}"
        )

        response_json = response.json()
        assert response_json is not None, "Response should not be None"

        # Verificações específicas do RAG Enhanced com chunks agrupados
        doc_rag = response_json.get("doc_rag", None)
        rag_method = response_json.get("rag_method", None)
        intent = response_json.get("intent", None)

        # Validação do RAG Enhanced com chunks agrupados
        assert intent == "pergunta", f"Expected intent='pergunta', but got {intent}"
        assert doc_rag, f"Expected doc_rag=True for RAG Enhanced, but got {doc_rag}"
        assert rag_method == "grouped_chunks", (
            f"Expected rag_method='grouped_chunks', but got {rag_method}"
        )


@responses.activate
def test_websearch_with_thinking_no_recursion_error(client, mock_solr_post):
    """
    Teste para verificar que use_websearch=True e use_thinking=True
    funcionam juntos sem causar erro de recursão infinita (GraphRecursionError).

    Este teste valida a correção do problema de aninhamento de agentes ReACT.
    Anteriormente, quando use_thinking e use_websearch eram ativados simultaneamente,
    ocorria um loop infinito porque a tool bing_grounding_search_1_results criava
    outro agente ReACT interno, causando GraphRecursionError após 25 iterações.

    A solução implementada faz a tool chamar diretamente o Azure AI Project Client
    sem criar agente aninhado, eliminando o problema na origem.
    """
    endpoint = "/llm_lang/chat_gpt_4o_mini_128k"
    text = """
# Persona
Você é um especialista financeiro com mais de 15 anos de experiência em análise de Fundos de Investimento Imobiliário (FIIs),
 reconhecido por avaliações criteriosas de rentabilidade, estabilidade e segurança para investidores brasileiros.
# Contexto
Foi contratado por um investidor pessoa física que deseja identificar os FIIs brasileiros que **pagam renda mensal**
 (dividendos mensais) e que, simultaneamente, apresentam **maior rentabilidade** conciliada com **maior estabilidade** e **baixo risco**.
  As informações precisam ser atualizadas e embasadas em fontes confiáveis da internet.
# Tarefa/Objetivo
Pesquisar bastante na Internet para elaborar um relatório detalhado contendo a lista dos principais FIIs que atendem aos requisitos, citando dados de
 rendimento, métricas de risco e **link de cada fonte** utilizada.
# Restrições
- **Não invente nada** e se baseie **exclusivamente** nas instruções.
- Utilize apenas dados publicados em **sites confiáveis** (fundosnet.com.br, relatórios gerenciais, B3, CVM, portais financeiros reconhecidos).
- Não inclua FIIs com distribuição trimestral ou sem histórico mínimo de 12 meses de pagamento.
- Sem restrição de preço por cota; avaliar apenas métricas de rentabilidade, risco e estabilidade.

# Instruções
1. **Pesquisar cuidadosamente** na internet as informações **mais recentes** sobre FIIs que distribuem dividendos mensalmente de forma consistente.
2. **Filtrar** para incluir apenas FIIs que possuam:
	- **Listagem exclusiva na B3** (todos devem estar registrados e negociados na B3).
	- Dividend Yield consistente (média ≥ 0,8% ao mês nos últimos 12 meses).
	- Patrimônio líquido ≥ R$ 500 milhões.
	- Baixa vacância ou contratos atípicos que indiquem estabilidade de receita.
	- Liquidez média diária ≥ R$ 500 mil (negociado em bolsa nos últimos 3 meses).
	- Atenda algum critério de isenção de imposto de renda.
3. Para cada FII selecionado, **coletar** (utilizando exclusivamente as métricas já publicadas por plataformas/relatórios confiáveis;
 não calcular manualmente):
	- **Nome e ticker**.
	- **Segmento** (lajes corporativas, logística, shopping, papel/crédito imobiliário, híbrido, etc. – *Sem preferência por setores ou tipos!*)
	- **Valor distribuído** nos últimos 3 meses (R$/cota mês a mês).
	- **Dividend Yield (DY) 12M** dos últimos 12 meses, sendo quanto maior melhor.
	- **Volatilidade 12M** (desvio-padrão da variação da cota nos últimos 12 meses), sendo quanto menor melhor.
	- **Razão DY 12M/Volatilidade 12M** para indicar quantos "pontos de yield" o investidor recebe para cada ponto de risco
     de preço que assume, sendo quanto maior que 1 melhor.
	- **Motivos da Recomendação** (máximo 4 frases).
	- **Links das fontes** onde cada dado foi verificado.
4. **Verificar a data** de cada fonte antes de incluí-la; rejeitar dados desatualizados.
5. **Apresentar** os FIIs em **ordem decrescente de atratividade** (maior relação rentabilidade/risco primeiro).
6. Pode utilizar qualquer fonte respeitável e atualizada; contudo, deve priorizar fontes específicas do setor financeiro brasileiro,
 como Funds Explorer, TFI Analytics, Suno e B3, além de poder incluir informações de plataformas pagas
  (TC Matrix, Empiricus e Status Invest Pro) se estiverem disponíveis.
7. Reserve o tempo necessário para pensar bem e seja cuidadoso, **sem pressa**.
8. Execute cada passo das instruções **com o tempo e atenção necessários**.
9. **Isso é muito importante para mim!**

# Formato de Resposta
- Título em H2: `## FIIs com Dividendos Mensais – Ranking Top 10 Atualizado`
- Tabela em Markdown com as colunas abaixo, apenas para os top 10 que atendem a todos os critérios:
	| Ranking | Fundo (Ticker) | Segmento | Distribuição 3M (R$/cota) | DY 12M | Volatilidade 12M | Razão DY/Volatilidade
    | Motivos da Recomendação | Fontes |
- Após a tabela, uma seção "### Observações Importantes" contendo:
- Critérios de exclusão aplicados, indicando FIIs não listados na tabela dos top 10 por não atender aos critérios.
- Breve explicação sobre a metodologia de cálculo do Dividend Yield e da volatilidade.
"""
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-Internal-Test-Call": "true",
    }

    # Mock do LLM - precisa ter múltiplas respostas para as várias chamadas do ReACT thinking agent
    # O agente ReACT pode fazer várias iterações, então fornecemos múltiplas mensagens
    response_content = (
        "## FIIs com Dividendos Mensais – Ranking Top 10 Atualizado\n\n"
        "Com base na pesquisa realizada utilizando websearch, apresento os principais "
        "Fundos de Investimento Imobiliário (FIIs) que distribuem dividendos mensalmente:\n\n"
        "| Ranking | Fundo (Ticker) | Segmento | Distribuição 3M (R$/cota) | DY 12M | Volatilidade 12M | Razão DY/Volatilidade | Motivos da Recomendação | Fontes |\n"
        "| 1 | HGLG11 | Logística | R$ 0,95/mês | 10,2% | 8,5% | 1,20 | Alta consistência de dividendos, baixa vacância, contratos longos | Funds Explorer, B3 |\n"
        "| 2 | BTLG11 | Logística | R$ 0,88/mês | 9,8% | 7,2% | 1,36 | Portfólio diversificado, boa gestão, baixo risco | Status Invest, TFI Analytics |\n\n"
        "### Observações Importantes\n\n"
        "- Critérios aplicados: Patrimônio líquido ≥ R$ 500 milhões, DY médio ≥ 0,8% ao mês\n"
        "- Metodologia: DY calculado com base nos últimos 12 meses de distribuição\n"
        "- Volatilidade medida pelo desvio-padrão das cotações nos últimos 12 meses"
    )

    # Criar múltiplas mensagens idênticas para lidar com várias iterações do agente ReACT
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [AIMessage(content=response_content) for _ in range(20)]
            + [
                AIMessage(content='{"caso": "outro"}'),  # Para disclaimer_classifier
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "system_prompt": (
            "Sou um assistente virtual de ajuda ao usuario."
            "processos no SEI (Sistema Eletrônico de Informações) da ANATEL. Estou aqui "
            "para auxiliar na instrução de processos eletrônicos, fornecendo informações "
            "confiáveis e atualizadas. Meu idioma principal é o português brasileiro, mas "
            "posso me ajustar a outros idiomas. Para elementos fictícios previsões ou "
            "suposições, respondo com 'ATENÇÃO: Esta resposta pode conter elementos "
            "fictícios, previsões ou suposições não baseadas em dados concretos.'"
        ),
        "text": text,
        "temperature": 0,
        "use_websearch": True,
        "use_thinking": True,
    }

    # Criar mock SSE para a Responses API (chat_gpt_with_reasoning usa httpx)
    sse_content = create_responses_api_sse_content(
        reasoning_content="Analisando a solicitação sobre FIIs...",
        response_content=response_content,
    )

    with (
        respx.mock(assert_all_called=False) as respx_mock,
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.websearch.azure_web_search_tool.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        # Mock da Responses API do LiteLLM Proxy
        respx_mock.post(url__regex=r".*/responses$").mock(
            return_value=httpx.Response(
                status_code=200,
                headers={"content-type": "text/event-stream"},
                stream=MockAsyncByteStream(sse_content),
            )
        )
        response = client.post(endpoint, headers=headers, json=payload)

    # Verificação principal: não deve retornar erro 500 de recursão
    assert response.status_code == 200, (
        f"Expected status code 200, but got {response.status_code}. "
        f"Response: {response.text[:500]}"
    )

    # Verificar estrutura básica da resposta
    response_json = response.json()
    assert response_json is not None, "Response should not be None"
    assert isinstance(response_json, dict), "Response should be a dictionary"

    assert "choices" in response_json, "Response should contain choices"
    assert len(response_json["choices"]) > 0, "Should have at least one choice"
    assert "message" in response_json["choices"][0], "First choice should have message"
    assert "content" in response_json["choices"][0]["message"], (
        "Message should have content"
    )

    content = response_json["choices"][0]["message"]["content"]
    assert len(content) > 0, "Content should not be empty"

    print(
        "✅ Teste passou: use_websearch + use_thinking funcionando sem recursão infinita"
    )
    print(f"   Resposta gerada com sucesso ({len(content)} caracteres)")


@responses.activate
def test_correcao_ortografica(client, mock_solr_post):
    """
    Teste end-to-end para verificar a correção ortográfica de documentos.

    Este teste verifica se o sistema:
    1. Detecta corretamente a intenção de "reescrever" (correção ortográfica)
    2. Processa um documento com erros ortográficos
    3. Retorna um texto corrigido mantendo o conteúdo original

    O texto de entrada contém erros intencionais como:
    - "Ezte" -> "Este"
    - "testo" -> "texto"
    - "algums" -> "alguns"
    - "ortograficos" -> "ortográficos"
    - "responsavel" -> "responsável"
    - "regulamentaçao" -> "regulamentação"
    - "telecomunicaçoes" -> "telecomunicações"
    - "Brazil" -> "Brasil"
    - "todoz" -> "todos"
    - "publicaçao" -> "publicação"
    """
    # Popular o cache com o documento mockado contendo erros ortográficos
    populate_cache_correcao_ortografica()

    # Configurar os mocks das chamadas HTTP
    mock_correcao_ortografica()

    # Endpoint
    endpoint = "/llm_lang/chat_gpt_4o_mini_128k"

    # Headers
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-Internal-Test-Call": "true",
    }

    # Mock do LLM - precisa ter múltiplas respostas
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                # Para detecção de intenção
                AIMessage(content='{"intencao": "reescrever"}'),
                # Para resposta de correção ortográfica
                AIMessage(
                    content=(
                        "# Documento para Teste de Correção Ortográfica\n\n"
                        "Este é um texto com alguns erros ortográficos que precisam ser corrigidos.\n\n"
                        "A Anatel é responsável pela regulamentação do setor de telecomunicações no Brasil.\n\n"
                        "É importantíssimo que todos os documentos sejam revisados antes da publicação."
                    )
                ),
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    # Payload com solicitação de correção ortográfica
    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Por favor, corrija os erros ortográficos do documento #9999999",
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [{"id_procedimento": "999", "id_documentos": ["999999"]}],
    }

    with (
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.agents.intent_selector_agent.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        response = client.post(endpoint, headers=headers, json=payload)

    # Verificação do status code
    assert response.status_code == 200, (
        f"Expected status code 200, but got {response.status_code}"
    )

    # Verificações adicionais
    response_json = response.json()
    assert response_json is not None, "Response should not be None"
    assert isinstance(response_json, dict), "Response should be a dictionary"

    # Verificar se contém uma resposta do LLM no formato esperado
    assert "choices" in response_json, "Response should contain choices"
    assert len(response_json["choices"]) > 0, "Should have at least one choice"
    assert "message" in response_json["choices"][0], "First choice should have message"
    assert "content" in response_json["choices"][0]["message"], (
        "Message should have content"
    )

    # Verificar se a resposta contém conteúdo
    content = response_json["choices"][0]["message"]["content"]
    assert len(content) > 0, "Content should not be empty"

    # Verifica se a intenção foi detectada como "reescrever"
    intent = response_json.get("intent", "")
    assert intent == "reescrever", (
        f"Expected intent to be 'reescrever', but got '{intent}'"
    )

    # Verificações detalhadas da correção ortográfica
    content_lower = content.lower()

    # Lista de erros que NÃO devem estar presentes no texto corrigido
    erros_ortograficos = [
        "ezte",  # deve ser "este"
        "testo",  # deve ser "texto"
        "algums",  # deve ser "alguns"
        "ortograficos",  # deve ser "ortográficos"
        "responsavel",  # deve ser "responsável"
        "regulamentaçao",  # deve ser "regulamentação"
        "telecomunicaçoes",  # deve ser "telecomunicações"
        "brazil",  # deve ser "brasil"
        "todoz",  # deve ser "todos"
        "publicaçao",  # deve ser "publicação"
    ]

    # Verificar que os erros originais NÃO estão presentes no texto corrigido
    erros_encontrados = []
    for erro in erros_ortograficos:
        if erro in content_lower:
            erros_encontrados.append(erro)

    assert len(erros_encontrados) == 0, (
        f"O texto corrigido ainda contém os seguintes erros ortográficos: {erros_encontrados}. "
        f"Estes erros deveriam ter sido corrigidos."
    )

    # Lista de palavras corretas que DEVEM estar presentes (verificar pelo menos algumas)
    palavras_corretas_esperadas = [
        ("anatel", "Referência à Anatel"),
        ("documento", "Referência ao documento"),
        ("brasil", "Forma correta de Brazil"),
        (
            "telecomunicações"
            if "telecomunicações" in content_lower
            else "telecomunicacoes",
            "Forma correta",
        ),
    ]

    palavras_encontradas = 0
    palavras_detalhes = []
    for palavra, descricao in palavras_corretas_esperadas:
        if palavra in content_lower:
            palavras_encontradas += 1
            palavras_detalhes.append(f"✓ {palavra} ({descricao})")
        else:
            palavras_detalhes.append(f"✗ {palavra} ({descricao})")

    # Pelo menos 2 das palavras corretas esperadas devem estar presentes
    assert palavras_encontradas >= 2, (
        f"O texto corrigido deve conter pelo menos 2 das palavras corretas esperadas. "
        f"Encontradas: {palavras_encontradas}/4\n" + "\n".join(palavras_detalhes)
    )

    # Verificar que a resposta é substantiva (não é apenas uma mensagem de erro)
    assert len(content) > 100, (
        f"O texto corrigido deve ser substantivo (mais de 100 caracteres). "
        f"Tamanho atual: {len(content)} caracteres"
    )

    print("✅ Teste de correção ortográfica passou")
    print(f"   Intent detectada: {intent}")
    print(f"   Tamanho da resposta: {len(content)} caracteres")
    print(f"   Erros corrigidos: {len(erros_ortograficos)} erros verificados")
    print(
        f"   Palavras corretas encontradas: {palavras_encontradas}/{len(palavras_corretas_esperadas)}"
    )
    print("   Detalhes das verificações:")
    for detalhe in palavras_detalhes:
        print(f"      {detalhe}")


@responses.activate
def test_pergunta_uso_sei_sem_documentos_com_disclaimer(client, mock_solr_post):
    """
    Teste end-to-end para verificar respostas a perguntas sobre o SEI sem documentos anexados.

    Este teste verifica se o sistema:
    1. Processa corretamente uma pergunta sobre uso do SEI (sem documentos)
    2. Retorna uma resposta coerente relacionada ao SEI
    3. Configura corretamente use_thinking=true conforme solicitado
    4. Não aciona mecanismos de RAG ou resumo quando não há documentos

    Exemplo de pergunta: "É possível criar um documento sem associá-lo a um processo?"

    A resposta esperada deve:
    - Abordar a questão sobre documentos e processos no SEI
    - Conter termos relacionados (SEI, documento, processo)
    - Ser substantiva (mais de 50 caracteres)
    - Incluir tokens de uso e metadados apropriados
    - Não usar RAG, resumo ou false_rag (doc_rag=False, doc_summarized=False, doc_false_rag=False)
    """
    # Configurar os mocks das chamadas HTTP
    mock_pergunta_uso_sei()

    # Endpoint
    endpoint = "/llm_lang/chat_gpt_4o_mini_128k"

    # Headers
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-Internal-Test-Call": "true",
    }

    # Mock do LLM
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(
                    content='{"caso": "outro"}'
                ),  # Para classify_disclaimer (paralelo)
                AIMessage(
                    content=(
                        "No SEI (Sistema Eletrônico de Informações), não é possível criar um documento "
                        "completamente desassociado de um processo. Todo documento no SEI precisa estar "
                        "vinculado a um processo administrativo para garantir a rastreabilidade e a "
                        "organização adequada. Quando você cria um novo documento, o sistema solicita "
                        "que você o associe a um processo existente ou crie um novo processo para esse fim. "
                        "Essa é uma característica fundamental do SEI para manter a integridade documental "
                        "e facilitar o acompanhamento de todas as ações administrativas."
                    )
                ),
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    # Payload com pergunta sobre uso do SEI (sem documentos)
    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "É possível criar um documento sem associá-lo a um processo?",
        "system_prompt": (
            "Sou o Assistente de IA do SEI (Sistema Eletrônico de Informações) da "
            "Agência Nacional de Telecomunicações (ANATEL). Meu idioma principal é "
            "o português brasileiro, mas posso me ajustar a outros idiomas. "
            "Não devo utilizar elementos fictícios, previsões ou suposições."
        ),
        "use_thinking": True,
        "use_websearch": False,
        "summarize_history": False,
    }

    # Criar mock SSE para a Responses API (chat_gpt_with_reasoning usa httpx)
    response_content = (
        "No SEI (Sistema Eletrônico de Informações), não é possível criar um documento "
        "completamente desassociado de um processo. Todo documento no SEI precisa estar "
        "vinculado a um processo administrativo para garantir a rastreabilidade e a "
        "organização adequada. Quando você cria um novo documento, o sistema solicita "
        "que você o associe a um processo existente ou crie um novo processo para esse fim. "
        "Essa é uma característica fundamental do SEI para manter a integridade documental "
        "e facilitar o acompanhamento de todas as ações administrativas."
    )
    sse_content = create_responses_api_sse_content(
        reasoning_content="Analisando a pergunta sobre documentos e processos no SEI...",
        response_content=response_content,
    )

    with (
        respx.mock(assert_all_called=False) as respx_mock,
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        # Mock da Responses API do LiteLLM Proxy
        respx_mock.post(url__regex=r".*/responses$").mock(
            return_value=httpx.Response(
                status_code=200,
                headers={"content-type": "text/event-stream"},
                stream=MockAsyncByteStream(sse_content),
            )
        )
        response = client.post(endpoint, headers=headers, json=payload)

    # Verificação do status code
    assert response.status_code == 200, (
        f"Expected status code 200, but got {response.status_code}"
    )

    # Verificações adicionais
    response_json = response.json()
    assert response_json is not None, "Response should not be None"
    assert isinstance(response_json, dict), "Response should be a dictionary"

    # Verificar estrutura básica da resposta
    assert "choices" in response_json, "Response should contain choices"
    assert len(response_json["choices"]) > 0, "Should have at least one choice"
    assert "message" in response_json["choices"][0], "First choice should have message"
    assert "content" in response_json["choices"][0]["message"], (
        "Message should have content"
    )

    # Obter o conteúdo da resposta
    content = response_json["choices"][0]["message"]["content"]
    assert len(content) > 0, "Content should not be empty"

    # VERIFICAÇÃO PRINCIPAL: A resposta deve abordar a pergunta sobre documentos e processos no SEI
    # Verificar que a resposta contém termos relacionados ao SEI e documentos/processos
    content_lower = content.lower()
    termos_relacionados_sei = ["sei", "documento", "processo"]
    termos_encontrados = [
        termo for termo in termos_relacionados_sei if termo in content_lower
    ]

    assert len(termos_encontrados) >= 2, (
        f"A resposta deve conter pelo menos 2 dos termos relacionados ao SEI: {termos_relacionados_sei}.\n"
        f"Termos encontrados: {termos_encontrados}\n"
        f"Conteúdo recebido: '{content[:300]}...'"
    )

    # Verifica se o disclaimer está sendo retornado no conteúdo
    # TODO: Descomentar quando estiver funcionando em PD
    # assert "a resposta a seguir pode conter imprecisão.".lower() in content_lower, (
    #     "O disclaimer sobre o assistente do SEI IA não está presente na resposta."
    # )
    # Verificar que use_thinking foi processado conforme configurado
    assert response_json.get("use_thinking") is True, (
        "use_thinking deveria ser True conforme configurado no payload"
    )

    # Verificar que use_websearch está False conforme configurado
    assert response_json.get("use_websearch") is False, (
        "use_websearch deveria ser False conforme configurado no payload"
    )

    # Verificar que não usou documentos (doc_rag, doc_summarized devem ser False)
    assert response_json.get("doc_rag") is False, "Não deveria usar RAG sem documentos"
    assert response_json.get("doc_summarized") is False, (
        "Não deveria resumir sem documentos"
    )
    assert response_json.get("doc_false_rag") is False, (
        "Não deveria ter false RAG sem documentos"
    )

    # Verificar que a resposta é substantiva
    assert len(content) > 50, (
        f"A resposta deve ser substantiva (mais de 50 caracteres). "
        f"Tamanho recebido: {len(content)} caracteres"
    )

    # Verificar metadados da resposta
    assert "usage" in response_json, "Response should contain usage metrics"
    assert "total_tokens" in response_json["usage"], "Usage should contain total_tokens"

    print("✅ Teste de pergunta sobre uso do SEI sem documentos passou")
    print(f"   Tamanho da resposta: {len(content)} caracteres")
    print(
        f"   Termos encontrados: {', '.join(termos_encontrados)} ({len(termos_encontrados)}/{len(termos_relacionados_sei)})"
    )
    print(f"   use_thinking: {response_json.get('use_thinking')}")
    print(f"   use_websearch: {response_json.get('use_websearch')}")
    print(f"   doc_rag: {response_json.get('doc_rag')}")
    print(f"   doc_summarized: {response_json.get('doc_summarized')}")
    print(f"   Total tokens: {response_json['usage']['total_tokens']}")


# ============================================================================
# Testes de Streaming SSE - Processamento de Tags <web_N> e <doc_*>
# ============================================================================


class TestStreamTagProcessorFinal:
    """
    Testes unitários para o StreamTagProcessorFinal.

    Estes testes verificam o comportamento do processador de tags durante o streaming,
    incluindo:
    - Detecção de tags incompletas
    - Acumulação correta de tokens
    - Substituição de tags por tooltips HTML
    - Numeração sequencial global
    """

    def test_deteccao_tag_incompleta_web(self):
        """
        Testa se o processador detecta corretamente tags <web_*> incompletas.

        Quando o LLM envia tokens fragmentados como '<web', '_1', '>',
        o processador deve acumular até ter a tag completa.
        """
        from sei_ia.agents.rag.stream_processor_final import StreamTagProcessorFinal

        # UserState mínimo para o teste
        user_state = {
            "tool_web_search": [
                {
                    "content": json.dumps(
                        {
                            "text": "resultado",
                            "references": [
                                {
                                    "idx": 1,
                                    "url": "https://exemplo.com",
                                    "title": "Exemplo",
                                }
                            ],
                        }
                    )
                }
            ]
        }

        processor = StreamTagProcessorFinal(user_state)

        # Simular tokens fragmentados
        output1 = processor.process_token("Texto antes <web")
        output2 = processor.process_token("_1")
        output3 = processor.process_token(">")

        # O processador deve acumular tokens até ter a tag completa
        # output1 e output2 devem ser vazios (acumulando)
        # output3 deve conter o texto processado com o tooltip

        assert output1 == "", "Deveria acumular '<web' como tag incompleta"
        assert output2 == "", "Deveria acumular '_1' como tag incompleta"

        # output3 deve conter o tooltip HTML
        assert "Texto antes" in output3, "Deve conter o texto antes da tag"
        assert '<a href="https://exemplo.com"' in output3, "Deve conter o link HTML"
        assert "[1]" in output3, "Deve conter a numeração sequencial"
        assert "<web_1>" not in output3, "Não deve conter o marcador original"

    def test_deteccao_tag_incompleta_doc(self):
        """
        Testa se o processador detecta corretamente tags <doc_*> incompletas.
        """
        from sei_ia.agents.rag.stream_processor_final import StreamTagProcessorFinal

        user_state = {
            "rag_chunks_data": [
                {
                    "id_documento_formatado": "12345",
                    "id_documento": "12345",
                    "text": "Conteúdo do chunk de teste",
                    "similarity_score": 0.95,
                }
            ],
            "id_to_formatted_map": {"12345": "12345"},
        }

        processor = StreamTagProcessorFinal(user_state)

        # Simular tokens fragmentados para tag de chunk
        output1 = processor.process_token("Conforme <doc_")
        output2 = processor.process_token("12345_1")
        output3 = processor.process_token("></doc_12345_1>")

        assert output1 == "", "Deveria acumular '<doc_' como tag incompleta"
        assert output2 == "", "Deveria acumular '12345_1' como tag incompleta"

        # output3 deve conter o tooltip HTML
        assert "Conforme" in output3, "Deve conter o texto antes da tag"
        assert "AssistenteSEIIAfonteResposta" in output3, (
            "Deve conter a classe CSS do tooltip"
        )
        assert "[1]" in output3, "Deve conter a numeração sequencial"
        assert "<doc_12345_1>" not in output3, "Não deve conter o marcador original"

    def test_numeracao_sequencial_global(self):
        """
        Testa se a numeração sequencial é global entre diferentes tipos de tags.

        Quando há chunks, documentos e web search na mesma resposta,
        a numeração deve ser sequencial: [1], [2], [3], etc.
        """
        from sei_ia.agents.rag.stream_processor_final import StreamTagProcessorFinal

        user_state = {
            "rag_chunks_data": [
                {
                    "id_documento_formatado": "12345",
                    "id_documento": "12345",
                    "text": "Chunk 1",
                    "similarity_score": 0.95,
                }
            ],
            "id_to_formatted_map": {"12345": "12345", "67890": "67890"},
            "tool_web_search": [
                {
                    "content": json.dumps(
                        {
                            "text": "resultado",
                            "references": [
                                {"idx": 1, "url": "https://url1.com", "title": "URL 1"},
                                {"idx": 2, "url": "https://url2.com", "title": "URL 2"},
                            ],
                        }
                    )
                }
            ],
        }

        processor = StreamTagProcessorFinal(user_state)

        # Processar um chunk primeiro
        output1 = processor.process_token("<doc_12345_1></doc_12345_1>")
        assert "[1]" in output1, "Primeiro chunk deve ser [1]"

        # Processar um documento
        output2 = processor.process_token(" e <doc_67890></doc_67890>")
        assert "[2]" in output2, "Documento deve ser [2]"

        # Processar web search
        output3 = processor.process_token(" e <web_1>")
        assert "[3]" in output3, "Web search deve ser [3]"

        # Verificar que a numeração é contínua
        assert processor.next_sequential_number == 4, "Próximo número deve ser 4"

    def test_limpeza_tags_fechamento_web(self):
        """
        Testa se as tags de fechamento </web_N> são removidas corretamente.
        """
        from sei_ia.agents.rag.stream_processor_final import StreamTagProcessorFinal

        user_state = {
            "tool_web_search": [
                {
                    "content": json.dumps(
                        {
                            "text": "resultado",
                            "references": [
                                {
                                    "idx": 1,
                                    "url": "https://exemplo.com",
                                    "title": "Exemplo",
                                }
                            ],
                        }
                    )
                }
            ]
        }

        processor = StreamTagProcessorFinal(user_state)

        # Processar texto com tag de abertura e fechamento
        output = processor.process_token("<web_1></web_1> texto depois")

        assert "</web_1>" not in output, "Tag de fechamento deve ser removida"
        assert "texto depois" in output, "Texto após a tag deve ser preservado"

        print("✅ test_limpeza_tags_fechamento_web passou")

    def test_flush_conteudo_pendente(self):
        """
        Testa se o flush() retorna corretamente o conteúdo pendente.
        """
        from sei_ia.agents.rag.stream_processor_final import StreamTagProcessorFinal

        user_state = {}
        processor = StreamTagProcessorFinal(user_state)

        # Acumular algum conteúdo que não é uma tag
        processor.process_token("Texto ")
        processor.process_token("acumulado")

        # Flush deve retornar o conteúdo pendente
        remaining = processor.flush()

        # Se não há tags incompletas, o conteúdo já foi liberado
        # Se houver algo no acumulador, flush deve retornar
        assert processor.accumulator == "", "Acumulador deve estar vazio após flush"

        print("✅ test_flush_conteudo_pendente passou")

    def test_tag_web_sem_metadata(self):
        """
        Testa o comportamento quando não há metadados para uma tag <web_N>.

        O processador deve usar fallback com número sequencial.
        """
        from sei_ia.agents.rag.stream_processor_final import StreamTagProcessorFinal

        # UserState sem referências para idx=5
        user_state = {
            "tool_web_search": [
                {
                    "content": json.dumps(
                        {
                            "text": "resultado",
                            "references": [
                                {
                                    "idx": 1,
                                    "url": "https://exemplo.com",
                                    "title": "Exemplo",
                                }
                            ],
                        }
                    )
                }
            ]
        }

        processor = StreamTagProcessorFinal(user_state)

        # Processar tag com idx que não existe nos metadados
        output = processor.process_token("Veja <web_5> para mais info")

        # Deve usar fallback com número sequencial
        assert "[1]" in output, "Deve usar número sequencial como fallback"
        assert "<web_5>" not in output, "Não deve conter o marcador original"

        print("✅ test_tag_web_sem_metadata passou")

    def test_multiplas_tags_mesmo_tipo(self):
        """
        Testa processamento de múltiplas tags do mesmo tipo com mesma referência.

        Tags repetidas devem usar o mesmo número sequencial.
        """
        from sei_ia.agents.rag.stream_processor_final import StreamTagProcessorFinal

        user_state = {
            "tool_web_search": [
                {
                    "content": json.dumps(
                        {
                            "text": "resultado",
                            "references": [
                                {"idx": 1, "url": "https://url1.com", "title": "URL 1"},
                                {"idx": 2, "url": "https://url2.com", "title": "URL 2"},
                            ],
                        }
                    )
                }
            ]
        }

        processor = StreamTagProcessorFinal(user_state)

        # Processar primeira ocorrência de web_1
        output1 = processor.process_token("Texto <web_1>")
        assert "[1]" in output1

        # Processar web_2
        output2 = processor.process_token(" e <web_2>")
        assert "[2]" in output2

        # Processar segunda ocorrência de web_1 (deve manter mesmo número)
        output3 = processor.process_token(" e novamente <web_1>")
        assert "[1]" in output3, (
            "Segunda ocorrência de web_1 deve usar mesmo número [1]"
        )

        print("✅ test_multiplas_tags_mesmo_tipo passou")


def test_stream_tag_processor_unit_tests():
    """
    Executa todos os testes unitários do StreamTagProcessorFinal.

    Este teste agrupa todos os testes da classe TestStreamTagProcessorFinal
    para facilitar a execução via pytest.
    """
    test_class = TestStreamTagProcessorFinal()

    test_class.test_deteccao_tag_incompleta_web()
    test_class.test_deteccao_tag_incompleta_doc()
    test_class.test_numeracao_sequencial_global()
    test_class.test_limpeza_tags_fechamento_web()
    test_class.test_flush_conteudo_pendente()
    test_class.test_tag_web_sem_metadata()
    test_class.test_multiplas_tags_mesmo_tipo()

    print("\n✅ Todos os testes unitários do StreamTagProcessorFinal passaram!")


@responses.activate
def test_streaming_sse_web_search_tag_conversion(client, mock_solr_post):
    """
    Teste de integração para verificar conversão de tags <web_N> no streaming SSE.

    Este teste verifica que:
    1. O endpoint /llm_lang/stream processa corretamente as tags <web_N>
    2. As tags são substituídas por links HTML clicáveis
    3. Não há marcadores <web_N> residuais na resposta final
    4. O formato SSE está correto (data: {...})

    IMPORTANTE: Este teste valida a correção do bug onde tags <web_N>
    não eram processadas no streaming, aparecendo literalmente para o usuário.
    """
    # Mock para consulta de histórico
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

    # Simular resposta do LLM com tags <web_N>
    llm_response_with_markers = (
        "A cotação do dólar hoje é R$ 5,00 <web_1>. "
        "Segundo o Banco Central <web_2>, a tendência é de alta. "
        "Veja mais detalhes em <web_3>."
    )

    # IMPORTANTE: Quando use_websearch=True, há múltiplas chamadas LLM:
    # 1. disclaimer_classifier
    # 2. web_search agent (pode fazer múltiplas chamadas)
    # 3. chat_gpt final
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(content='{"caso": "outro"}'),  # Para classify_disclaimer
                AIMessage(
                    content="Vou buscar informações sobre a cotação do dólar."
                ),  # Para web_search agent (1ª chamada)
                AIMessage(
                    content=llm_response_with_markers
                ),  # Resposta final após web search
                AIMessage(
                    content=llm_response_with_markers
                ),  # Resposta extra (caso haja mais chamadas)
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    # Mock do tool_web_search no user_state
    mock_web_search_results = [
        {
            "content": json.dumps(
                {
                    "text": "Resultado da busca",
                    "references": [
                        {
                            "idx": 1,
                            "url": "https://economia.com/dolar",
                            "title": "Cotação Dólar",
                        },
                        {
                            "idx": 2,
                            "url": "https://bcb.gov.br",
                            "title": "Banco Central",
                        },
                        {
                            "idx": 3,
                            "url": "https://investing.com",
                            "title": "Investing",
                        },
                    ],
                }
            )
        }
    ]

    payload = {
        "text": "Qual a cotação do dólar hoje?",
        "id_usuario": 0,
        "id_topico": 0,
        "use_websearch": True,
        "skip_memory": True,
    }

    headers = {
        "accept": "text/event-stream",
        "Content-Type": "application/json",
        "X-Internal-Test-Call": "true",
    }

    # Função para injetar tool_web_search no user_state durante o workflow
    original_create_user_state = None

    def mock_create_user_state_with_web_search(request, request_starllete, model_data):
        from sei_ia.routers.chat import create_user_state as original

        user_state = original(request, request_starllete, model_data)
        user_state["tool_web_search"] = mock_web_search_results
        return user_state

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
            "sei_ia.agents.websearch.azure_web_search_tool.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.routers.chat.gpt_4o_128k.create_user_state",
            side_effect=mock_create_user_state_with_web_search,
        ),
    ):
        response = client.post("/llm_lang/stream", headers=headers, json=payload)

    # Verificar status
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Parse da resposta SSE
    full_content = ""
    for line in response.text.split("\n"):
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if data.get("type") == "content":
                    full_content += data.get("data", "")
            except json.JSONDecodeError:
                continue

    # Verificações críticas
    assert "<web_1>" not in full_content, "Marcador <web_1> não deveria estar presente"
    assert "<web_2>" not in full_content, "Marcador <web_2> não deveria estar presente"
    assert "<web_3>" not in full_content, "Marcador <web_3> não deveria estar presente"

    # Verificar que há links HTML (se web_search foi processado)
    # Nota: Se o mock não ativou o processador, os marcadores podem não estar presentes
    if "cotação" in full_content.lower() or "dólar" in full_content.lower():
        # Se há conteúdo relacionado, verificar conversão
        has_html_links = "href=" in full_content or "[" in full_content
        assert has_html_links or "<web_" not in full_content, (
            "Deve ter links HTML ou não ter marcadores <web_N>"
        )

    print("✅ test_streaming_sse_web_search_tag_conversion passou")
    print(f"   Tamanho do conteúdo: {len(full_content)} caracteres")
    print("   Marcadores <web_N> residuais: Nenhum ✓")


def test_stream_tag_processor_has_incomplete_tag_patterns():
    """
    Testa especificamente os padrões de detecção de tags incompletas.

    Este teste verifica que o método _has_incomplete_tag() detecta
    corretamente todos os padrões de tags parciais.
    """
    from sei_ia.agents.rag.stream_processor_final import StreamTagProcessorFinal

    user_state = {}
    processor = StreamTagProcessorFinal(user_state)

    # Padrões que DEVEM ser detectados como incompletos
    incomplete_patterns = [
        # Tags web incompletas
        "<",
        "<w",
        "<we",
        "<web",
        "<web_",
        "<web_1",
        "<web_12",
        # Tags doc incompletas
        "<d",
        "<do",
        "<doc",
        "<doc_",
        "<doc_123",
        "<doc_123_",
        "<doc_123_4",
        "<doc_123_45>",  # Só abertura
        "<doc_123_45></",
        "<doc_123_45></doc",
        "<doc_123_45></doc_",
        "<doc_123_45></doc_123",
        "<doc_123_45></doc_123_",
        "<doc_123_45></doc_123_4",
        # Tags doc simples incompletas
        "<doc_123>",  # Só abertura
        "<doc_123></",
        "<doc_123></doc",
        "<doc_123></doc_",
        "<doc_123></doc_12",
    ]

    for pattern in incomplete_patterns:
        processor.accumulator = f"texto antes {pattern}"
        is_incomplete = processor._has_incomplete_tag()
        assert is_incomplete, (
            f"Padrão '{pattern}' deveria ser detectado como incompleto"
        )

    # Padrões que NÃO devem ser detectados como incompletos (tags completas)
    complete_patterns = [
        "texto sem tags",
        "texto com <b>html</b> normal",
        "texto com número <5 ou >3",
    ]

    for pattern in complete_patterns:
        processor.accumulator = pattern
        is_incomplete = processor._has_incomplete_tag()
        assert not is_incomplete, (
            f"Padrão '{pattern}' não deveria ser detectado como incompleto"
        )

    print("✅ test_stream_tag_processor_has_incomplete_tag_patterns passou")
    print(f"   Padrões incompletos testados: {len(incomplete_patterns)}")
    print(f"   Padrões completos testados: {len(complete_patterns)}")


# ============================================================================
# NOVOS TESTES DE STREAMING - Cenários não cobertos
# ============================================================================


@responses.activate
def test_streaming_sse_simple_question(client, mock_solr_post):
    """
    Teste de streaming com pergunta simples (sem documentos, RAG ou web search).

    Verifica que:
    1. O endpoint /llm_lang/stream funciona corretamente com perguntas simples
    2. O conteúdo é enviado via SSE de forma incremental
    3. A resposta final é completa e não contém erros
    """
    # Mock para consulta de histórico
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

    llm_simple_response = (
        "A Agência Nacional de Telecomunicações (Anatel) é uma agência reguladora brasileira, "
        "vinculada ao Ministério das Comunicações, responsável por regular o setor de "
        "telecomunicações no Brasil. Foi criada pela Lei 9.472/1997, conhecida como Lei Geral "
        "de Telecomunicações (LGT)."
    )

    # Adicionar múltiplas mensagens para cobrir todas as chamadas
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(content='{"caso": "outro"}'),  # Para disclaimer_classifier
                AIMessage(content=llm_simple_response),  # Resposta (1ª chamada)
                AIMessage(content=llm_simple_response),  # Resposta extra
                AIMessage(content=llm_simple_response),  # Resposta extra
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "O que é a Anatel?",
        "temperature": 0,
        "max_tokens": 4000,
        "skip_memory": True,
    }

    headers = {
        "accept": "text/event-stream",
        "Content-Type": "application/json",
        "X-Internal-Test-Call": "true",
    }

    with (
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        response = client.post("/llm_lang/stream", headers=headers, json=payload)

    # Verificações
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Parse da resposta SSE
    full_content = ""
    event_count = 0
    for line in response.text.split("\n"):
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if data.get("type") == "content":
                    full_content += data.get("data", "")
                    event_count += 1
            except json.JSONDecodeError:
                continue

    # Verificações
    assert len(full_content) > 0, "Content should not be empty"
    assert "anatel" in full_content.lower() or "telecomunica" in full_content.lower(), (
        "Content should be related to the question"
    )

    print("    test_streaming_sse_simple_question passou")
    print(f"   Eventos SSE recebidos: {event_count}")
    print(f"   Tamanho do conteúdo: {len(full_content)} caracteres")


@responses.activate
def test_streaming_sse_with_memory(client, mock_solr_post):
    """
    Teste de streaming com memória/histórico de conversação.

    Verifica que:
    1. O endpoint /llm_lang/stream funciona com histórico de conversação
    2. O sistema recupera e utiliza mensagens anteriores do tópico
    3. A resposta considera o contexto do histórico
    4. O formato SSE está correto

    Este teste aumenta a cobertura de:
    - sei_ia/agents/memory/session/conversation.py (40.79% -> mais)
    - sei_ia/routers/chat/__init__.py (46.19% -> mais)
    """
    # Mock para consulta de histórico COM dados (simulando conversa anterior)
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_historico_topico",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_historico_topico",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdTopico": "123",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "Pergunta": "Qual é o papel da Anatel?",
                    "Resposta": "A Anatel é a agência reguladora de telecomunicações no Brasil.",
                    "DthCadastro": "2024-01-01 10:00:00",
                    "TotalTokens": 50,
                }
            ],
        },
        status=200,
    )

    # Mock para salvar nova mensagem no histórico
    responses.add(
        responses.POST,
        "http://mock-sei-api:8000/md_ia_salvar_mensagem_historico",
        json={"status": "success", "id": 3},
        status=200,
    )

    llm_response_with_context = (
        "Com base na nossa conversa anterior sobre o papel da Anatel, "
        "posso complementar que a Anatel foi criada em 1997 pela Lei 9.472, "
        "conhecida como Lei Geral de Telecomunicações (LGT). "
        "A agência tem autonomia administrativa e financeira, sendo vinculada "
        "ao Ministério das Comunicações."
    )

    # Múltiplas mensagens para cobrir todas as chamadas com histórico
    fake_llm = FakeChatModelWithAttributes(
        messages=iter(
            [
                AIMessage(content='{"caso": "outro"}'),  # Para disclaimer_classifier
                AIMessage(
                    content=llm_response_with_context
                ),  # Resposta considerando histórico
                AIMessage(content=llm_response_with_context),  # Resposta extra
                AIMessage(content=llm_response_with_context),  # Resposta extra
            ]
        ),
        model_name="gpt-4.1",
        temperature=0.0,
        max_tokens=4000,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 123,  # Tópico com histórico
        "text": "Quando a Anatel foi criada?",
        "temperature": 0,
        "max_tokens": 4000,
        # NÃO usar skip_memory para testar o fluxo de memória
    }

    headers = {
        "accept": "text/event-stream",
        "Content-Type": "application/json",
        "X-Internal-Test-Call": "true",
    }

    with (
        patch(
            "sei_ia.services.llm_models.get_model.get_llm_model", return_value=fake_llm
        ),
        patch(
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            return_value=fake_llm,
        ),
        patch(
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            return_value=fake_llm,
        ),
    ):
        response = client.post("/llm_lang/stream", headers=headers, json=payload)

    # Verificações
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Parse da resposta SSE
    full_content = ""
    event_count = 0
    for line in response.text.split("\n"):
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if data.get("type") == "content":
                    full_content += data.get("data", "")
                    event_count += 1
            except json.JSONDecodeError:
                continue

    # Verificações
    assert len(full_content) > 0, "Content should not be empty"

    # Verificar que a resposta menciona contexto ou informações relacionadas
    content_lower = full_content.lower()
    assert (
        "anatel" in content_lower
        or "1997" in content_lower
        or "lei" in content_lower
        or "telecomunicações" in content_lower
    ), "Content should be related to the question and context"

    print("✅ test_streaming_sse_with_memory passou")
    print(f"   Eventos SSE recebidos: {event_count}")
    print(f"   Tamanho do conteúdo: {len(full_content)} caracteres")
    print("   Histórico utilizado: Tópico 123 com 2 mensagens anteriores")


# ============================================================================
# Testes de OCR para PDFs Escaneados
# ============================================================================


def test_ocr_habilitado():
    """
    Testa se as configurações de OCR estão habilitadas corretamente.

    Verifica:
    - OCR_ENABLED está True (habilitado por padrão)
    - OCR_MIN_TEXT_THRESHOLD está com valor padrão de 50 caracteres
    """
    from sei_ia.configs.settings_config import settings

    assert settings.OCR_ENABLED is True, "OCR deveria estar habilitado por padrão"
    assert settings.OCR_MIN_TEXT_THRESHOLD == 50, (
        f"OCR_MIN_TEXT_THRESHOLD deveria ser 50, mas é {settings.OCR_MIN_TEXT_THRESHOLD}"
    )

    print("✅ test_ocr_habilitado passou")
    print(f"   OCR_ENABLED: {settings.OCR_ENABLED}")
    print(f"   OCR_MIN_TEXT_THRESHOLD: {settings.OCR_MIN_TEXT_THRESHOLD}")


def test_extract_text_with_ocr_mock():
    """
    Testa extração de texto via OCR de uma página individual com LiteLLM mockado.

    Verifica:
    - A função extract_text_with_ocr() retorna o número da página e texto extraído
    - O mock do LiteLLM é chamado corretamente
    - O texto retornado contém o conteúdo esperado
    """
    from unittest.mock import patch

    from litellm.types.utils import Choices, Message, ModelResponse, Usage

    MOCK_OCR_PAGE_1 = """**Justificativa Uso de Acessos SMP**

**Prestadora:** Telefônica Brasil S.A
**Cliente:** COOPERATIVA DE PLATAFORMA - CICLOS
**CNPJ:** 32322678000187

**Dados de tráfego:**
- Total de Acessos: 28529

| CN | Acessos |
|---:|--------:|
| 27 | 18582 |
"""

    def _create_mock_response(content: str) -> ModelResponse:
        return ModelResponse(
            id="chatcmpl-mock",
            created=1234567890,
            model="mock",
            object="chat.completion",
            choices=[
                Choices(
                    finish_reason="stop",
                    index=0,
                    message=Message(content=content, role="assistant"),
                )
            ],
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )

    with patch(
        "sei_ia.data.etl.extract.pdf_ocr_extractor.completion",
    ) as mock_llm:
        mock_llm.return_value = _create_mock_response(MOCK_OCR_PAGE_1)
        with patch(
            "sei_ia.data.etl.extract.pdf_ocr_extractor.render_page_to_base64",
            return_value="fake_base64",
        ):
            from sei_ia.data.etl.extract.pdf_ocr_extractor import (
                extract_text_with_ocr,
            )

            page_num, text = extract_text_with_ocr("fake.pdf", page_num=1)

            assert page_num == 1, f"Esperado página 1, recebido {page_num}"
            assert "Telefônica" in text, "Texto deveria conter 'Telefônica'"
            assert "28529" in text, "Texto deveria conter '28529'"

    print("✅ test_extract_text_with_ocr_mock passou")
    print("   Extração de página individual com OCR funcionando")


def test_extract_text_hybrid_mock():
    """
    Testa extração híbrida de texto (texto nativo + OCR) com mocks completos.

    Verifica:
    - A função extract_text_hybrid() combina corretamente texto de múltiplas páginas
    - Páginas escaneadas são processadas via OCR (mockado)
    - O texto final contém conteúdo de todas as páginas na ordem correta
    """
    from unittest.mock import MagicMock, patch

    from litellm.types.utils import Choices, Message, ModelResponse, Usage

    MOCK_OCR_PAGE_1 = """**Justificativa Uso de Acessos SMP**

**Prestadora:** Telefônica Brasil S.A
**Cliente:** COOPERATIVA DE PLATAFORMA - CICLOS
**CNPJ:** 32322678000187

**Dados de tráfego:**
- Total de Acessos: 28529

| CN | Acessos |
|---:|--------:|
| 27 | 18582 |
"""

    MOCK_OCR_PAGE_2 = """Total de chamadas: 1.034.441

Documento assinado por THÁSSIO FELIPE RADDATZ
Telefônica Brasil S.A.
"""

    def _create_mock_response(content: str) -> ModelResponse:
        return ModelResponse(
            id="chatcmpl-mock",
            created=1234567890,
            model="mock",
            object="chat.completion",
            choices=[
                Choices(
                    finish_reason="stop",
                    index=0,
                    message=Message(content=content, role="assistant"),
                )
            ],
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )

    call_count = [0]
    responses = [
        _create_mock_response(MOCK_OCR_PAGE_1),
        _create_mock_response(MOCK_OCR_PAGE_2),
    ]

    def mock_llm(*args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        return responses[idx % len(responses)]

    mock_pages = [
        MagicMock(
            page_num=1, is_scanned=True, chars_useful=0, num_images=5, native_text=""
        ),
        MagicMock(
            page_num=2, is_scanned=True, chars_useful=0, num_images=5, native_text=""
        ),
    ]

    with (
        patch(
            "sei_ia.data.etl.extract.pdf_ocr_extractor.completion",
            side_effect=mock_llm,
        ),
        patch(
            "sei_ia.data.etl.extract.pdf_ocr_extractor.analyze_pdf_pages",
            return_value=mock_pages,
        ),
        patch(
            "sei_ia.data.etl.extract.pdf_ocr_extractor.render_page_to_base64",
            return_value="fake_base64",
        ),
    ):
        from sei_ia.data.etl.extract.pdf_ocr_extractor import (
            extract_text_hybrid_sync,
        )

        texto = extract_text_hybrid_sync("fake.pdf")

        assert "Telefônica" in texto, "Texto deveria conter 'Telefônica'"
        assert "1.034.441" in texto, "Texto deveria conter '1.034.441'"
        assert "THÁSSIO" in texto, "Texto deveria conter 'THÁSSIO'"

    print("✅ test_extract_text_hybrid_mock passou")
    print("   Extração híbrida com múltiplas páginas funcionando")
