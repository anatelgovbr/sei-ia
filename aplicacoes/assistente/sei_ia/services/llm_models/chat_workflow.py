"""modulo de chat gpt com langchain."""

import base64
import inspect
import logging
from pathlib import Path
from typing import Any

import openai
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langgraph.types import StreamWriter

from sei_ia.agents.attachments.topic_attachment_tool import (
    TOPIC_ATTACHMENTS_TOOL_SYSTEM_INSTRUCTION,
    make_consultar_anexos_topico_tool,
)
from sei_ia.agents.memory.session.conversation import (
    get_interacao_chat_by_topico_id_using_api,
)
from sei_ia.agents.prompts.web_search import WEB_SEARCH_PROMPT
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.counter import token_counter
from sei_ia.services.llm_models.get_model import AGENT_TAG_TO_TIER, get_llm_model

setup_logging()

logger = logging.getLogger(__name__)


def _build_multimodal_human_message(
    text_content: str, image_attachments: list
) -> HumanMessage:
    """Monta a HumanMessage final para envio ao LLM.

    Quando há `image_attachments` no `user_state`, constrói o content como
    lista multimodal `[{"type":"text","text":...}, {"type":"image_url",...}]`
    com cada imagem em base64 inline (`data:<mime>;base64,...`). Bytes só são
    lidos do FS aqui — última etapa antes do LLM — para evitar inflar o
    `user_state` (e os checkpoints LangGraph / traces Langfuse) com base64.

    Caso não haja imagens, devolve `HumanMessage(content=str)` como antes,
    preservando o caminho hot.

    Falhas de leitura do FS (arquivo apagado, permissão) viram
    `ArquivoAvulsoProcessingError` para o handler do endpoint converter em 4xx com
    o nome do arquivo — sem silent error.
    """
    if not image_attachments:
        return HumanMessage(content=text_content)

    # Importação tardia para evitar ciclo (uploads → ... → chat_workflow).
    from sei_ia.data.etl.extract.uploads import ArquivoAvulsoProcessingError

    parts: list[dict[str, Any]] = [{"type": "text", "text": text_content}]
    for att in image_attachments:
        try:
            raw = Path(att.fs_path).read_bytes()
        except OSError as exc:
            ext = Path(att.filename).suffix.lstrip(".") or "?"
            raise ArquivoAvulsoProcessingError(
                filename=att.filename,
                extensao=ext,
                message=f"falha ao ler imagem do FS para anexar à mensagem: {exc}",
            ) from exc
        b64 = base64.b64encode(raw).decode()
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{att.mime};base64,{b64}"},
            }
        )
    return HumanMessage(content=parts)


class ChatError(Exception):
    """Exceção customizada para erros na chamada da Azure AI Project."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


def get_reasoning_model_kwargs(user_state: UserState) -> dict[str, Any]:
    """Retorna os kwargs para ativar Responses API/reasoning no `get_llm_model`.

    `reasoning_effort` (explícito no payload, já validado contra o catálogo do
    proxy em `create_user_state`) tem prioridade: quando presente, liga
    reasoning com ESSE valor, independente de `use_thinking`. Sem ele, cai no
    comportamento antigo — `use_thinking=True` liga reasoning com o effort
    fixo do servidor (`settings.REASONING_EFFORT`); `use_thinking` falso/ausente
    retorna {}.
    """
    reasoning_effort = user_state.get("reasoning_effort")
    if not reasoning_effort and not user_state.get("use_thinking"):
        return {}
    return {
        "use_responses_api": True,
        "reasoning": {
            "effort": reasoning_effort or settings.REASONING_EFFORT,
            "summary": settings.REASONING_SUMMARY,
        },
    }


# Erros do provedor que costumam pipocar na janela de reasoning oculto (dezenas
# de segundos antes do 1º byte do stream): 5xx cru, conexão derrubada, timeout e
# o APIError genérico. Nesses casos o `chat_gpt` refaz UMA vez a MESMA chamada
# com `reasoning_effort="none"` — encurta a janela e chega antes à resposta.
# `openai.InternalServerError`/`APIConnectionError`/`APITimeoutError` já são
# subclasses de `openai.APIError`.
REASONING_FAILOVER_ERRORS = (openai.APIError,)
# 4xx determinístico e rate limit: refazer com menos reasoning não muda o
# desfecho (e o rate limit tem política de retry própria no proxy).
REASONING_FAILOVER_EXCLUDE = (
    openai.BadRequestError,
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    openai.NotFoundError,
    openai.UnprocessableEntityError,
    openai.ConflictError,
    openai.RateLimitError,
)


def _collect_summary_texts(block: dict) -> list[str]:
    texts = []
    for summary in block.get("summary") or []:
        if isinstance(summary, dict):
            text = summary.get("text")
            if text:
                texts.append(text)
    return texts


def extract_reasoning_delta_from_content(content: Any) -> str:
    """Delta de reasoning a partir do `content` de um chunk já desembrulhado.

    Na Responses API (`use_responses_api=True`) o `content` vira `list[dict]`
    com blocos `{"type": "reasoning", "summary": [{"type": "summary_text",
    "text": "..."}, ...]}`; concatena os `summary_text`. Para `content` string
    (Chat Completions), retorna "".

    Núcleo compartilhado: o session/stream.py chama esta forma direto (tem o
    `content` na mão), sem embrulhar num objeto só para reexpor `.content`.
    """
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "reasoning":
            continue
        parts.extend(_collect_summary_texts(block))
    return "".join(parts)


def extract_reasoning_delta(chunk: Any) -> str:
    """Wrapper de compat: lê `chunk.content` e delega ao núcleo.

    Mantido para os call sites do clássico (que têm o `AIMessageChunk` na mão).
    """
    return extract_reasoning_delta_from_content(getattr(chunk, "content", None))


def extract_content_delta(chunk: Any) -> str:
    """Extrai o delta de conteúdo de um `AIMessageChunk`.

    Suporta os dois formatos:
    - `chunk.content` como `str` (Chat Completions clássica).
    - `chunk.content` como `list[dict]` com blocos `{"type": "text"|"output_text",
      "text": "..."}` (Responses API).
    """
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") in {"text", "output_text"}:
            text = block.get("text")
            if text:
                parts.append(text)
    return "".join(parts)


_OUTPUT_TOKENS_BY_TIER = {
    "standard": lambda: settings.OUTPUT_TOKENS_STANDARD_MODEL,
    "mini": lambda: settings.OUTPUT_TOKENS_MINI_MODEL,
    "nano": lambda: settings.OUTPUT_TOKENS_NANO_MODEL,
}


def get_output_token_limit(agent_tag: str) -> int:
    tier = AGENT_TAG_TO_TIER.get(agent_tag.lower())
    if tier is None:
        raise ValueError(f"Papel de agente desconhecido: {agent_tag}")
    return _OUTPUT_TOKENS_BY_TIER[tier]()


def _message_content_as_text(content: Any) -> str:
    """Extrai texto de content de mensagem LangChain para contagem aproximada."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _remaining_context_tokens_for_tools(
    user_state: UserState, messages: list[BaseMessage]
) -> int:
    """Calcula orçamento restante antes de a tool devolver conteúdo integral."""
    prompt_tokens = token_counter(user_state.get("system_prompt", ""))
    prompt_tokens += sum(
        token_counter(_message_content_as_text(msg.content)) for msg in messages
    )
    output_tokens = int(user_state.get("general_max_output_tokens", 0))
    max_ctx = int(user_state["general_max_ctx_len"])
    return max(0, max_ctx - prompt_tokens - output_tokens)


def summary_websearch_if_necessary(user_state: UserState) -> str:  # NOSONAR
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
        max_tokens = get_output_token_limit(user_state.get("agent_tag", "principal"))
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


async def chat_gpt(  # noqa: C901, PLR0912, PLR0915  # NOSONAR
    user_state: UserState, writer: StreamWriter | None = None
) -> dict:
    """Função de chamada do chat_gpt.

    Caminho único via LangChain agent (`create_react_agent`). Quando
    `use_thinking=True`, o modelo é configurado com `use_responses_api=True`
    e `reasoning={...}`, fazendo o LiteLLM Proxy roteie para `POST /responses`
    com blocos de reasoning expostos nos chunks de streaming.

    Args:
        user_state: UserState com configurações da requisição.
        writer: StreamWriter opcional para emitir reasoning/content em tempo real.

    Returns:
        dict com `response` (str), `n_tokens` (tuple), `type_choiced_summary`
        e — quando `use_thinking=True` — também `reasoning` (str).
    """
    logger.debug(">> entrou em _chat_gpt")

    use_thinking = bool(user_state.get("use_thinking", False))
    reasoning_kwargs = get_reasoning_model_kwargs(user_state)
    model = get_llm_model(
        agent_tag=user_state["agent_tag"],
        model_override=user_state.get("model_override"),
        **reasoning_kwargs,
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
        if user_state.get("system_prompt"):
            messages.append(SystemMessage(content=user_state["system_prompt"]))
        messages.append(HumanMessage(content=last_prompt))

    tools: list = []

    # Tool de consulta de anexos do tópico. `id_topico` vem do user_state,
    # NUNCA do LLM — a factory devolve None quando não há tópico ou o cache
    # de anexos está desabilitado. A tool permanece disponível também no fluxo
    # com reasoning/Responses API porque agora há um caminho único de agente.
    attachment_tool_enabled = bool(user_state.get("id_topico")) and bool(
        settings.ARQUIVOS_AVULSOS_CACHE_ENABLED
    )
    if attachment_tool_enabled:
        user_state["system_prompt"] = (
            f"{user_state['system_prompt']}{TOPIC_ATTACHMENTS_TOOL_SYSTEM_INSTRUCTION}"
        )
        remaining_context_tokens = _remaining_context_tokens_for_tools(
            user_state, messages
        )
        attachment_tool = make_consultar_anexos_topico_tool(
            user_state.get("id_topico"),
            remaining_context_tokens=remaining_context_tokens,
        )
        if attachment_tool is not None:
            tools.append(attachment_tool)

    image_attachments = user_state.get("image_attachments") or []

    # Tag de contexto na última HumanMessage; embrulha em multimodal quando há
    # anexos de imagem no user_state. Isso acontece antes do agente tanto para
    # thinking quanto para não-thinking.
    if messages and isinstance(messages[-1], HumanMessage):
        wrapped_text = "\n <context>" + messages[-1].content + "\n </context>"
        messages[-1] = _build_multimodal_human_message(wrapped_text, image_attachments)

    agent_react = create_react_agent(
        model=model,
        tools=tools,
        prompt=user_state["system_prompt"],
    )

    assistant_content = ""
    reasoning_content = ""

    async def _run_agent_stream(active_agent: Any) -> None:
        """Consome o astream do agente, acumulando e streamando os deltas.

        Muta `assistant_content`/`reasoning_content` do escopo externo — o
        failover abaixo só refaz a chamada se NADA foi transmitido ainda.
        """
        nonlocal assistant_content, reasoning_content
        attachments_status_sent = False
        async for event in active_agent.astream_events(
            {"messages": messages},
            config={"recursion_limit": 50},
            version="v2",
        ):
            if event["event"] == "on_tool_start":
                tool_name = event.get("name", "")
                if (
                    tool_name == "consultar_anexos_do_topico"
                    and writer is not None
                    and not attachments_status_sent
                ):
                    writer({"_status": "Consultando anexo do tópico"})
                    attachments_status_sent = True
            elif event["event"] == "on_tool_end":
                tool_name = event.get("name", "")
                if tool_name == "consultar_anexos_do_topico" and writer is not None:
                    writer({"_status": "Consulta de anexo concluída"})
            elif event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]  # type: ignore
                reasoning_delta = extract_reasoning_delta(chunk)
                if reasoning_delta:
                    reasoning_content += reasoning_delta
                    if writer is not None:
                        writer(f"<reasoning>{reasoning_delta}</reasoning>")
                content_delta = extract_content_delta(chunk)
                if content_delta:
                    assistant_content += content_delta
                    if writer is not None:
                        writer(content_delta)

    # Failover do reasoning: erro do provedor ANTES do 1º byte (janela de
    # reasoning oculto) com reasoning ligado → refaz UMA vez a MESMA chamada
    # (mesmo modelo/tools/prompt) com `reasoning_effort="none"`, encurtando a
    # janela. Não é fallback silencioso — vai pro log e pro `user_state`.
    reasoning_failover_used = False
    while True:
        try:
            await _run_agent_stream(agent_react)
            break
        except REASONING_FAILOVER_ERRORS as exc:
            if (
                reasoning_failover_used
                or not reasoning_kwargs
                or assistant_content
                or reasoning_content
                or isinstance(exc, REASONING_FAILOVER_EXCLUDE)
            ):
                raise
            reasoning_failover_used = True
            user_state["reasoning_failover"] = True
            logger.warning(
                "chat_gpt: failover de reasoning (effort=none) após %s do provedor",
                type(exc).__name__,
            )
            retry_kwargs = {
                **reasoning_kwargs,
                "reasoning": {**reasoning_kwargs["reasoning"], "effort": "none"},
            }
            retry_model = get_llm_model(
                agent_tag=user_state["agent_tag"],
                model_override=user_state.get("model_override"),
                **retry_kwargs,
            )
            agent_react = create_react_agent(
                model=retry_model,
                tools=tools,
                prompt=user_state["system_prompt"],
            )

    result: dict[str, Any] = {
        "response": assistant_content,
        "n_tokens": (
            sum(
                token_counter(_message_content_as_text(msg.content)) for msg in messages
            ),
            token_counter(assistant_content) + token_counter(reasoning_content),
        ),
        "type_choiced_summary": type_choiced_summary,
    }
    if use_thinking:
        result["reasoning"] = reasoning_content
    return result


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
