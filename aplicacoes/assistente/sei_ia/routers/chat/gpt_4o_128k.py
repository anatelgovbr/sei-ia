"""Rota para o modelo standard.

NOTA: O nome do endpoint contém "gpt_4o" por razões históricas (legado).
Este endpoint utiliza o modelo "standard" configurado em settings.
A família GPT-4o não é mais utilizada diretamente - o model_type "standard"
é mapeado para o modelo atual definido na configuração do Azure OpenAI.
"""

import asyncio
import inspect
import json
import logging
from datetime import datetime

import httpx
import openai
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langfuse.langchain import CallbackHandler

from sei_ia.agents.rag.stream_processor_final import StreamTagProcessorFinal
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.etl.extract.uploads import (
    AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION,
    EXT_AUDIO,
    process_uploads,
)
from sei_ia.data.pydantic_models import ChatRequest, UserState
from sei_ia.routers.chat import (
    _build_langfuse_tags,
    _flush_langfuse,
    _langfuse_span,
    _update_langfuse_trace,
    build_chat_completion_graph,
    create_user_state,
    process_chat_completion,
)
from sei_ia.routers.chat.model_response import ModelResponseWithMetadata
from sei_ia.routers.chat.status_heartbeat import (
    INTERMEDIATE_MESSAGES,
    get_next_intermediate_message,
)
from sei_ia.routers.chat.stream_error_handler import (
    handle_chat_error,
    handle_connection_error,
    handle_http_exception,
    handle_openai_bad_request,
    handle_openai_internal_server_error,
    handle_protocol_error,
    handle_rate_limit,
    handle_timeout,
    handle_unhandled_exception,
)
from sei_ia.services.counter import token_counter
from sei_ia.services.exceptions.http_exceptions import fast_api_responses
from sei_ia.services.llm_models.chat_workflow import ChatError

setup_logging()
logger = logging.getLogger(__name__)


def json_serializer(obj):
    """Serializa objetos não serializáveis por padrão."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


ENDPOINT_NAME = "/llm_lang/chat_gpt_4o_128k"

router = APIRouter()


@router.post(
    ENDPOINT_NAME,
    tags=["llm_lang"],
    summary="Chat com modelo standard (nome do endpoint é legado)",
    responses=fast_api_responses,
)
async def chat_completation_gpt_4o_128k(
    request: ChatRequest, request_starllete: Request
) -> dict:
    """Endpoint para chat usando o modelo 'standard'.

    NOTA: O nome "gpt_4o_128k" é legado. Este endpoint usa model_type="standard",
    que é mapeado para o modelo atual configurado no Azure OpenAI.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    result = await process_chat_completion(
        request=request,
        request_starllete=request_starllete,
        model_data={
            "model_type": "standard" if not request.use_thinking else "think",
            "endpoint_name": ENDPOINT_NAME,
            "temperature": 0.0,
        },
    )

    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
    return result


@router.post(
    "/llm_lang/stream",
    tags=["llm_lang"],
    summary="Modelo de resposta em streaming",
    responses=fast_api_responses,
)
async def chat_completation_stream(request: ChatRequest, request_starllete: Request):
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    async def stream_generator():
        model_data = {
            "model_type": settings.DEFAULT_RESPONSE_MODEL
            if not request.use_thinking
            else "think",
            "endpoint_name": ENDPOINT_NAME,
            "temperature": 0.0,
        }

        user_state: UserState = create_user_state(
            request, request_starllete, model_data
        )

        if getattr(request, "uploads", None):
            has_audio = any(
                u.extensao.lower().strip(".") in EXT_AUDIO for u in request.uploads
            )
            uploads_content = await process_uploads(request.uploads)
            if uploads_content:
                user_state["user_request"] += f"\n\n{uploads_content}"
                user_state["all_tokens_counter"] += token_counter(uploads_content)
            if has_audio and user_state.get("system_prompt"):
                user_state["system_prompt"] += AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION

        config = {"callbacks": [CallbackHandler()]}
        graph_workflow = await build_chat_completion_graph()

        # Inicializa o processador de tags apenas se houver RAG ou potencial de tags
        stream_processor = None
        final_user_state = None
        current_status: str | None = None
        last_intermediate_msg: str | None = None
        _HEARTBEAT_INTERVAL = float(settings.STREAMING_HEARTBEAT_INTERVAL)
        _status_start_time: float | None = None
        _last_heartbeat_time: float | None = None

        # Usar span do Langfuse como no endpoint 4o
        with _langfuse_span("LangGraph") as span:
            # Registrar input inicial
            initial_tags = _build_langfuse_tags(user_state)
            if initial_tags:
                _update_langfuse_trace(
                    span,
                    session_id=str(user_state.get("id_topico")),
                    input=user_state,
                    tags=initial_tags,
                )
            else:
                _update_langfuse_trace(
                    span,
                    session_id=str(user_state.get("id_topico")),
                    input=user_state,
                )

            astream_iter = graph_workflow.astream(
                user_state, config=config, stream_mode=["custom", "values"]
            )

            try:
                _next_task: asyncio.Task | None = None
                while True:
                    if _next_task is None:
                        _next_task = asyncio.ensure_future(astream_iter.__anext__())

                    # Calcula timeout dinâmico: tempo restante até o próximo heartbeat
                    # baseado no tempo de parede desde o último status/heartbeat,
                    # independente da frequência de eventos internos do generator.
                    now = asyncio.get_running_loop().time()
                    if current_status and _status_start_time is not None:
                        ref = (
                            _last_heartbeat_time
                            if _last_heartbeat_time
                            else _status_start_time
                        )
                        _timeout = max(0.1, _HEARTBEAT_INTERVAL - (now - ref))
                    else:
                        _timeout = None

                    done, _ = await asyncio.wait({_next_task}, timeout=_timeout)

                    if not done:
                        if current_status:
                            intermediate = get_next_intermediate_message(
                                current_status, last_intermediate_msg
                            )
                            if intermediate:
                                last_intermediate_msg = intermediate
                                _last_heartbeat_time = asyncio.get_running_loop().time()
                                heartbeat_data = {
                                    "type": "status",
                                    "data": f" {intermediate}",
                                    "timestamp": _last_heartbeat_time,
                                }
                                yield f"data: {json.dumps(heartbeat_data, ensure_ascii=False, default=json_serializer)}\n\n"
                        continue

                    _next_task = None
                    try:
                        event = done.pop().result()
                    except StopAsyncIteration:
                        break
                    except HTTPException as exc:
                        error_data = handle_http_exception(exc, span)
                        yield f"data: {json.dumps(error_data, ensure_ascii=False, default=json_serializer)}\n\n"
                        return
                    except openai.BadRequestError as exc:
                        error_data = handle_openai_bad_request(exc, span)
                        yield f"data: {json.dumps(error_data, ensure_ascii=False, default=json_serializer)}\n\n"
                        return
                    except openai.InternalServerError as exc:
                        error_data = handle_openai_internal_server_error(exc, span)
                        yield f"data: {json.dumps(error_data, ensure_ascii=False, default=json_serializer)}\n\n"
                        return
                    except openai.RateLimitError as exc:
                        error_data = handle_rate_limit(exc, span)
                        yield f"data: {json.dumps(error_data, ensure_ascii=False, default=json_serializer)}\n\n"
                        return
                    except (openai.APIConnectionError, httpx.ConnectError) as exc:
                        error_data = handle_connection_error(exc, span)
                        yield f"data: {json.dumps(error_data, ensure_ascii=False, default=json_serializer)}\n\n"
                        return
                    except (openai.APITimeoutError, httpx.TimeoutException) as exc:
                        error_data = handle_timeout(exc, span)
                        yield f"data: {json.dumps(error_data, ensure_ascii=False, default=json_serializer)}\n\n"
                        return
                    except ChatError as exc:
                        error_data = handle_chat_error(exc, span)
                        yield f"data: {json.dumps(error_data, ensure_ascii=False, default=json_serializer)}\n\n"
                        return
                    except (httpx.ReadError, httpx.RemoteProtocolError) as exc:
                        error_data = handle_protocol_error(exc, span)
                        yield f"data: {json.dumps(error_data, ensure_ascii=False, default=json_serializer)}\n\n"
                        return

                    # Ignora eventos None ou inválidos que podem ocorrer quando branches paralelos terminam
                    if event is None:
                        continue
                    if not isinstance(event, tuple):
                        logger.warning(f"Skipping non-tuple event: {type(event)}")
                        continue
                    if len(event) != 2:
                        logger.warning(
                            f"Skipping tuple with wrong length: {len(event)}"
                        )
                        continue
                    node, msg = event
                    if msg is None:
                        continue

                    if node == "values" and msg.get("endpoint_name"):
                        user_state = msg
                        final_user_state = user_state
                        # Inicializa o processador após ter o user_state completo com RAG, documentos ou web search
                        rag_doc_count = user_state.get("rag_documents_count", 0)
                        has_web_search = bool(user_state.get("tool_web_search"))
                        needs_processor = (
                            user_state.get("doc_rag")  # RAG com chunks
                            or (
                                rag_doc_count is not None and rag_doc_count > 0
                            )  # Documentos completos com tags
                            or has_web_search  # Web search com marcadores <web_N>
                        )
                        if needs_processor and stream_processor is None:
                            stream_processor = StreamTagProcessorFinal(user_state)

                    if (
                        node == "custom"
                        and isinstance(msg, dict)
                        and msg.get("_status")
                    ):
                        status_value = msg["_status"]
                        if status_value in INTERMEDIATE_MESSAGES:
                            current_status = status_value
                            last_intermediate_msg = None
                            _status_start_time = asyncio.get_running_loop().time()
                            _last_heartbeat_time = None
                        else:
                            current_status = None
                            _status_start_time = None
                            _last_heartbeat_time = None
                        status_data = {
                            "type": "status",
                            "data": f" {status_value}",
                            "timestamp": asyncio.get_running_loop().time(),
                        }
                        yield f"data: {json.dumps(status_data, ensure_ascii=False, default=json_serializer)}\n\n"

                    elif node == "custom" and isinstance(msg, str):
                        # Verifica se é um token de reasoning (vem com tag <reasoning>)
                        if msg.startswith("<reasoning>") and msg.endswith(
                            "</reasoning>"
                        ):
                            # Extrai o conteúdo do reasoning
                            reasoning_text = msg[11:-12]  # Remove tags
                            if reasoning_text:
                                chunk_data = {
                                    "type": "reasoning",
                                    "data": reasoning_text,
                                    "timestamp": asyncio.get_running_loop().time(),
                                }
                                yield f"data: {json.dumps(chunk_data, ensure_ascii=False, default=json_serializer)}\n\n"
                        elif stream_processor:
                            output = stream_processor.process_token(msg)
                            if output:
                                # Envia o chunk como JSON Lines
                                chunk_data = {
                                    "type": "content",
                                    "data": output,
                                    "timestamp": asyncio.get_running_loop().time(),
                                }
                                yield f"data: {json.dumps(chunk_data, ensure_ascii=False, default=json_serializer)}\n\n"
                        else:
                            # Sem RAG, envia diretamente
                            chunk_data = {
                                "type": "content",
                                "data": msg,
                                "timestamp": asyncio.get_running_loop().time(),
                            }
                            yield f"data: {json.dumps(chunk_data, ensure_ascii=False, default=json_serializer)}\n\n"

            except Exception as exc:
                error_data = handle_unhandled_exception(exc, span)
                yield f"data: {json.dumps(error_data, ensure_ascii=False, default=json_serializer)}\n\n"
                return

            if stream_processor:
                remaining = stream_processor.flush()
                if remaining:
                    chunk_data = {
                        "type": "content",
                        "data": remaining,
                        "timestamp": asyncio.get_running_loop().time(),
                    }
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False, default=json_serializer)}\n\n"

            final_tags = _build_langfuse_tags(final_user_state)
            if final_tags:
                _update_langfuse_trace(span, output=final_user_state, tags=final_tags)
            else:
                _update_langfuse_trace(span, output=final_user_state)

            if final_user_state and final_user_state.get("response"):
                model_response = ModelResponseWithMetadata(user_state=final_user_state)
                model_response_dict = model_response.to_dict()

                final_data = {
                    "type": "metadata",
                    "data": model_response_dict,
                    "timestamp": asyncio.get_running_loop().time(),
                }
                yield f"data: {json.dumps(final_data, ensure_ascii=False, default=json_serializer)}\n\n"

            else:
                raise ValueError(
                    "final_user_state presente mas sem 'response' possível erro não capturado"
                )

            end_data = {
                "type": "end",
                "data": "Stream completed",
                "timestamp": asyncio.get_running_loop().time(),
            }
            yield f"data: {json.dumps(end_data, ensure_ascii=False, default=json_serializer)}\n\n"

        _flush_langfuse()

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Desabilita buffering em Nginx/Gunicorn
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


@router.post(
    "/llm_lang/chat_gpt_4_128k",
    tags=["llm_lang"],
    summary="Chat com modelo default (nome do endpoint é legado)",
    responses=fast_api_responses,
)
async def chat_completation_gpt_4_128k(
    request: ChatRequest, request_starllete: Request
) -> dict:
    """Endpoint para chat usando o modelo default configurado em settings.

    NOTA: O nome "gpt_4_128k" é legado. Este endpoint usa DEFAULT_RESPONSE_MODEL
    que é mapeado para o modelo atual configurado no Azure OpenAI.
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    result = await process_chat_completion(
        request=request,
        request_starllete=request_starllete,
        model_data={
            "model_type": settings.DEFAULT_RESPONSE_MODEL
            if not request.use_thinking
            else "think",
            "endpoint_name": ENDPOINT_NAME,
            "temperature": 0.0,
        },
    )

    logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
    return result
