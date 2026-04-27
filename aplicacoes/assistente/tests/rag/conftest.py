"""
Configuração compartilhada para testes RAG.

Este módulo fornece fixtures reutilizáveis para mockar modelos LLM
e evitar chamadas reais à API OpenAI/Azure durante os testes.
"""

from contextlib import ExitStack
from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class FakeChatModelWithAttributes(GenericFakeChatModel):
    """
    Classe fake customizada que estende GenericFakeChatModel com atributos necessários.

    Esta classe adiciona atributos que o código de produção espera encontrar no modelo,
    como model_name, temperature, etc. É uma cópia da classe usada em tests/e2e/test_service.py.
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


@pytest.fixture
def mock_all_llm_calls():
    """
    Fixture que mocka TODAS as chamadas a get_llm_model para evitar chamadas reais à API.

    Esta fixture cria um context manager que aplica patches em todos os locais
    onde get_llm_model é chamado na aplicação.

    Uso:
        with mock_all_llm_calls(responses):
            # Código de teste aqui
            # Todas as chamadas LLM retornarão as respostas mockadas

    Args (via função retornada):
        responses: Lista de strings com as respostas que o modelo fake deve retornar.
                   Cada chamada ao LLM consumirá uma resposta da lista em ordem.

    Exemplo:
        responses = [
            '{"caso": "outro"}',  # Para disclaimer_classifier
            '{"intencao": "pergunta"}',  # Para intent_selector
            "Resposta do assistente sobre o documento",  # Resposta principal
        ]

        with mock_all_llm_calls(responses):
            response = client.post("/llm_lang/chat_gpt_4o_128k", json=payload)
    """

    def _create_mock_context(responses):
        """
        Cria e retorna um ExitStack com todos os patches aplicados.

        Args:
            responses: Lista de respostas mockadas
        """
        # Criar modelo fake com as respostas fornecidas
        fake_llm = FakeChatModelWithAttributes(
            messages=iter([AIMessage(content=resp) for resp in responses]),
            model_name="gpt-4.1",
            temperature=0.0,
            max_tokens=4000,
        )

        # Lista completa de todos os locais onde get_llm_model é chamado
        patches_to_apply = [
            "sei_ia.services.llm_models.chat_workflow.get_llm_model",
            "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
            "sei_ia.agents.intent_selector_agent.get_llm_model",
            "sei_ia.agents.summarize.summarize.get_llm_model",
            "sei_ia.agents.pergunta.question_generator.get_llm_model",
            "sei_ia.agents.websearch.azure_web_search_tool.get_llm_model",
        ]

        # Criar ExitStack e aplicar todos os patches
        stack = ExitStack()
        for patch_path in patches_to_apply:
            stack.enter_context(patch(patch_path, return_value=fake_llm))

        return stack

    return _create_mock_context


@pytest.fixture
def create_fake_llm():
    """
    Fixture auxiliar para criar instâncias de FakeChatModelWithAttributes.

    Útil quando você precisa de um modelo fake customizado para casos específicos.

    Uso:
        fake_llm = create_fake_llm(['Resposta 1', 'Resposta 2'])

    Returns:
        Função que cria FakeChatModelWithAttributes com as respostas fornecidas
    """

    def _create(responses, model_name="gpt-4.1", **kwargs):
        """
        Cria um modelo fake com as respostas fornecidas.

        Args:
            responses: Lista de strings com respostas mockadas
            model_name: Nome do modelo (default: gpt-4.1)
            **kwargs: Argumentos adicionais para o modelo

        Returns:
            FakeChatModelWithAttributes configurado
        """
        return FakeChatModelWithAttributes(
            messages=iter([AIMessage(content=resp) for resp in responses]),
            model_name=model_name,
            **kwargs,
        )

    return _create
