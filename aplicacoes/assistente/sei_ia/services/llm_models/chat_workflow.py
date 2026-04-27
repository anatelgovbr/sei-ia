"""modulo de chat gpt com langchain."""

import inspect
import json
import logging
from typing import Any

import httpx
from azure.ai.agents.models import BingGroundingTool
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langgraph.types import StreamWriter

from sei_ia.agents.memory.session.conversation import (
    get_interacao_chat_by_topico_id_using_api,
)
from sei_ia.agents.prompts.web_search import WEB_SEARCH_PROMPT
from sei_ia.agents.websearch.azure_web_search_tool import (
    bing_grounding_search_1_results,
)
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.counter import token_counter
from sei_ia.services.llm_models.get_model import get_llm_model

setup_logging()

logger = logging.getLogger(__name__)
bing = BingGroundingTool(connection_id=settings.BING_CONNECTION_NAME)


class ChatError(Exception):
    """Exceção customizada para erros na chamada da Azure AI Project."""

    def __init__(self, status_code: int, detail: str):  # noqa: ANN204
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


def get_output_token_limit(model_type: str) -> int:
    model_type = model_type.lower()
    if model_type == "mini":
        return settings.OUTPUT_TOKENS_MINI_MODEL
    elif model_type == "standard":
        return settings.OUTPUT_TOKENS_STANDARD_MODEL
    elif model_type == "nano":
        return settings.OUTPUT_TOKENS_NANO_MODEL
    elif model_type == "think":
        return settings.OUTPUT_TOKENS_THINK_MODEL
    else:
        raise ValueError(f"Modelo desconhecido: {model_type}")


async def chat_gpt_with_reasoning(
    user_state: UserState,
    messages: list[BaseMessage],
    writer: StreamWriter | None = None,
) -> dict:
    """Executa chat usando Responses API para capturar reasoning separadamente.

    Esta função usa a Responses API do LiteLLM Proxy para obter o reasoning
    (pensamento do modelo) em streaming, separado do conteúdo da resposta.

    Args:
        user_state: Estado do usuário com configurações
        messages: Lista de mensagens (sistema, histórico, usuário)
        writer: StreamWriter para enviar tokens em tempo real

    Returns:
        dict com:
            - response: conteúdo da resposta
            - reasoning: pensamento do modelo
            - n_tokens: tupla (tokens_input, tokens_output)
    """
    logger.debug(">> entrou em chat_gpt_with_reasoning (Responses API)")

    # Monta o input para a Responses API
    # Converte mensagens LangChain para formato de texto simples
    input_parts = []
    system_content = ""

    for msg in messages:
        if isinstance(msg, SystemMessage):
            system_content += msg.content + "\n\n"
        elif isinstance(msg, HumanMessage):
            input_parts.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            input_parts.append(f"Assistant: {msg.content}")

    # Combina system prompt com o input
    if system_content:
        full_input = f"<system>\n{system_content.strip()}\n</system>\n\n" + "\n".join(
            input_parts
        )
    else:
        full_input = "\n".join(input_parts)

    # Configuração da requisição para Responses API
    proxy_url = settings.LITELLM_PROXY_URL.rstrip("/")
    url = f"{proxy_url}/responses"
    headers = {"Content-Type": "application/json"}

    payload = {
        "model": "think",
        "input": full_input,
        "stream": True,
        "reasoning": {
            "effort": "medium",
            "summary": "detailed",
        },
    }

    reasoning_content = ""
    assistant_content = ""

    async with (
        httpx.AsyncClient(timeout=settings.TIMEOUT_API) as client,
        client.stream("POST", url, headers=headers, json=payload) as response,
    ):
        if response.status_code != 200:
            error = await response.aread()
            error_msg = error.decode()[:500]
            logger.error(f"Erro na Responses API: {response.status_code} - {error_msg}")
            raise ChatError(response.status_code, f"Erro na API: {error_msg}")

        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue

            try:
                data = json.loads(line[6:])
                event_type = data.get("type", "")

                # Captura reasoning via streaming (se disponível)
                if event_type == "response.reasoning_summary_text.delta":
                    delta = data.get("delta", "")
                    if isinstance(delta, str) and delta:
                        reasoning_content += delta
                        if writer is not None:
                            writer(f"<reasoning>{delta}</reasoning>")

                # Captura reasoning completo quando o item termina
                if event_type == "response.output_item.done":
                    item = data.get("item", {})
                    if item.get("type") == "reasoning":
                        summary_list = item.get("summary", [])
                        for summary_item in summary_list:
                            if summary_item.get("type") == "summary_text":
                                text = summary_item.get("text", "")
                                if text and text not in reasoning_content:
                                    reasoning_content += text
                                    if writer is not None:
                                        writer(f"<reasoning>{text}</reasoning>")

                # Captura content token por token
                if event_type == "response.output_text.delta":
                    delta = data.get("delta", "")
                    if isinstance(delta, str) and delta:
                        assistant_content += delta
                        if writer is not None:
                            writer(delta)

            except json.JSONDecodeError:
                pass

    return {
        "response": assistant_content,
        "reasoning": reasoning_content,
        "n_tokens": (
            token_counter(full_input),
            token_counter(assistant_content) + token_counter(reasoning_content),
        ),
    }


def summary_websearch_if_necessary(user_state: UserState) -> str:
    """
    Resume o conteúdo da busca web se necessário.

    Inclui o conteúdo da busca web no prompt se estiver dentro do limite de tokens,
    caso contrário ignora o conteúdo excedente.

    Parameters:
        user_state (UserState): Estado do usuário
        max_tokens (int): Limite máximo de tokens permitidos

    Returns:
        str: Prompt atualizado com conteúdo web resumido

    Raises:
        ValueError: Se max_tokens <= 0 ou user_state é None
    """
    base_prompt = user_state.get("last_prompt", user_state["user_request"])

    if user_state[
        "use_thinking"
    ]:  # Se o modelo de pensamento é usado, o limite de tokens output+ctx é limite output ctx do modelo
        max_tokens = get_output_token_limit(user_state.get("model_type", "standard"))
    else:
        max_tokens = user_state["general_max_ctx_len"]

    tool_web_search = user_state.get("tool_web_search", [])
    if not tool_web_search:
        return base_prompt

    NEWLINE = chr(10)
    token_user_request = token_counter(base_prompt)
    available_tokens = max_tokens - token_user_request

    filtered_content = []
    current_tokens = 0

    for item in tool_web_search:
        query = item.get("query")
        content = item.get("content")
        idx = item.get("idx", 0)
        formatted = (
            f'<busca_{idx} query="{query}">{content}</busca_{idx}>'
            if query
            else content
        )

        content_tokens = token_counter(formatted)
        if current_tokens + content_tokens < available_tokens:
            filtered_content.append(formatted)
            current_tokens += content_tokens
        else:
            logger.warning(
                "Conteúdo da busca web excede o limite de tokens. Ignorando conteúdo adicional."
            )
            break

    if filtered_content:
        web_summary = NEWLINE.join(filtered_content)
        last_prompt = f"{web_summary}\n\n{base_prompt}"
    else:
        logger.info(
            "Nenhum conteúdo de busca web incluído - todos excediam o limite de tokens disponíveis"
        )
        last_prompt = base_prompt

    return last_prompt


async def chat_gpt(user_state: UserState, writer: StreamWriter | None = None) -> dict:
    """Função de chamada do chat_gpt.

    Args:
        user_state: UserState objeto contendo o estado do usuário.

    Returns:
        dict: Dicionário contendo a resposta do modelo e seu uso.
    """
    logger.debug(">> entrou em _chat_gpt")

    # Determina se usa modelo de thinking
    use_thinking = user_state.get("use_thinking", False)
    model_type = "think" if use_thinking else user_state["model_type"]

    model = get_llm_model(
        model_type=model_type,
        temperature=user_state["temperature"],
    )
    user_state["model_name"] = (
        model.model_name
    )  # Mostrar no response de fato qual modelo foi utilizado
    type_choiced_summary = None
    last_prompt = user_state.get("last_prompt", user_state["user_request"])

    if user_state["use_websearch"]:
        last_prompt = summary_websearch_if_necessary(user_state)
        user_state["system_prompt"] = (
            f"{user_state['system_prompt']}\n\n{WEB_SEARCH_PROMPT}"
        )
        user_state["last_prompt"] = last_prompt

    if user_state["id_topico"] and not user_state.get("skip_memory", False):
        logger.debug(">> chat_gpt: tem topico e nao skip_memory")
        messages, type_choiced_summary = get_gpt_with_memory_in_prompt(
            topico_id=user_state["id_topico"],
            prompt=last_prompt,
            system=user_state["system_prompt"],
            model=model,
            max_memory_tokens=settings.MEMORY_ITERATION_TOKENS_LIMIT,
            iter_memory_limit=settings.MEMORY_ITERATION_LIMIT,
            summarize_history=user_state["summarize_history"],
        )
    else:
        logger.debug(
            f">> chat_gpt: id_topico {user_state['id_topico']} e skip_memory {user_state.get('skip_memory', False)}"
        )
        messages: list[BaseMessage] = []
        # Adiciona system prompt se existir
        if user_state.get("system_prompt"):
            messages.append(SystemMessage(content=user_state["system_prompt"]))
        messages.append(HumanMessage(content=last_prompt))

    # Se use_thinking=True, usa a Responses API para capturar o reasoning
    if use_thinking:
        logger.debug(">> chat_gpt: usando Responses API para capturar reasoning")

        # Adiciona tag de contexto na última mensagem
        if messages and isinstance(messages[-1], HumanMessage):
            messages[-1] = HumanMessage(
                content="\n <context>" + messages[-1].content + "\n </context>"
            )

        result = await chat_gpt_with_reasoning(user_state, messages, writer)
        result["type_choiced_summary"] = type_choiced_summary
        return result

    # Fluxo normal para modelos sem reasoning
    agent_react = create_react_agent(
        model=model,
        tools=[bing_grounding_search_1_results] if user_state["use_websearch"] else [],
        prompt=user_state["system_prompt"],
    )

    assistant_content = ""
    messages[-1] = HumanMessage(
        content="\n <context>" + messages[-1].content + "\n </context>"
    )  # Adicionar tag de contexto para o modelo entender melhor qual é a pergunta do usuário e o ultimo contexto
    websearch_status_sent = False
    async for event in agent_react.astream_events({"messages": messages}, version="v2"):
        if event["event"] == "on_tool_start":
            tool_name = event.get("name", "")
            if (
                tool_name.startswith("bing_grounding")
                and writer is not None
                and not websearch_status_sent
            ):
                writer({"_status": "Pesquisando informações na Internet"})
                websearch_status_sent = True
        elif event["event"] == "on_tool_end":
            tool_name = event.get("name", "")
            if tool_name.startswith("bing_grounding") and writer is not None:
                writer({"_status": "Pesquisa na Internet concluída"})
        elif event["event"] == "on_chat_model_stream":
            # Processa streaming de tokens
            chunk = event["data"]["chunk"]  # type: ignore
            if hasattr(chunk, "content"):
                assistant_content += chunk.content
                if writer is not None:
                    writer(chunk.content)

    return {
        "response": assistant_content,
        "n_tokens": (
            sum([token_counter(msg.content) for msg in messages]),
            token_counter(assistant_content),
        ),
        "type_choiced_summary": type_choiced_summary,
    }


def get_gpt_with_memory_in_prompt(
    topico_id: int,
    prompt: str,
    system: str,
    model: Any,
    max_memory_tokens: int | None = settings.MEMORY_ITERATION_TOKENS_LIMIT,
    iter_memory_limit: int | None = settings.MEMORY_ITERATION_LIMIT,
    summarize_history: bool = False,
) -> tuple[list[BaseMessage], str]:
    """Generates a response using conversation memory.

    Args:
        topico_id (int): The ID of the session.
        model: Objeto de conexao do langchain com azure.
        prompt (str): The prompt text.
        system (str): The system prompt text.
        max_memory_tokens(int): maximo de tokens de memoria
        iter_memory_limit(int): maximo de iteracoes de memoria

    Returns:
        dict: The response from the GPT-3 model, including the generated
                response and the number of tokens used.
            - response (str): The generated response.
            - n_tokens (tuple[int, int]): The number of tokens used by the
            prompt, system prompt, and assistant.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    md_ia_interacao_chat_schema_list, type_choiced_summary = (
        get_interacao_chat_by_topico_id_using_api(
            topico_id=topico_id,
            model=model,
            max_tokens=settings.MEMORY_ITERATION_TOKENS_LIMIT,
            iter_limit=iter_memory_limit,
            summarize_history=summarize_history,
        )
    )
    logger.debug(
        f">> {inspect.currentframe().f_code.co_name}: buscou memoria "
        f"(max_tokens={max_memory_tokens}, / "
        f"iter_limit={iter_memory_limit})"
    )
    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    if isinstance(md_ia_interacao_chat_schema_list, str):
        message_historico = (
            "Histórico de interações com perguntas e respostas:\n"
            + md_ia_interacao_chat_schema_list
        )
        messages.append(SystemMessage(content=message_historico))
    else:
        for _, entity in md_ia_interacao_chat_schema_list.iterrows():
            if entity.resposta:
                messages.append(HumanMessage(entity.pergunta_data))
                messages.append(AIMessage(entity.resposta))

    messages.append(HumanMessage(content=prompt))

    # Adicionar tags <memory> mantendo os tipos BaseMessage
    first_msg = messages[0]
    last_msg = messages[-1]

    if isinstance(first_msg, HumanMessage):
        messages[0] = HumanMessage(content=f"<memory>{first_msg.content}")

    if isinstance(last_msg, HumanMessage):
        messages[-1] = HumanMessage(content=f"{last_msg.content}</memory>")

    return messages, type_choiced_summary
