"""Rota /llm_lang/stream — resposta em streaming (SSE).

Endpoint consumido pelo frontend do SEISU.
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

from sei_ia.agents.chat_completion_graph import build_chat_completion_graph
from sei_ia.agents.rag.stream_processor_final import StreamTagProcessorFinal
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.etl.extract.uploads import cleanup_arquivos_avulsos_temp_files
from sei_ia.data.pydantic_models import ChatRequest, UserState
from sei_ia.routers.chat import (
    _apply_arquivos_avulsos_to_state,
    _build_langfuse_tags,
    _flush_langfuse,
    _langfuse_span,
    _new_trace_id,
    _update_langfuse_trace,
    create_user_state,
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
from sei_ia.services.benchmark_metrics import (
    BenchmarkToolHandler,
    reset_current_collector,
    set_current_collector,
)
from sei_ia.services.exceptions.http_exceptions import fast_api_responses
from sei_ia.services.llm_models.chat_workflow import ChatError

setup_logging()
logger = logging.getLogger(__name__)


def json_serializer(obj):
    """Serializa objetos não serializáveis por padrão."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


ENDPOINT_NAME = "/llm_lang/stream"

router = APIRouter()


def _trace_id_for_request(request: Request) -> str | None:
    """Reusa o trace do harness quando presente; requests normais criam um novo."""
    return request.headers.get("X-Langfuse-Trace-Id") or _new_trace_id()


@router.post(
    ENDPOINT_NAME,
    tags=["llm_lang"],
    summary="Modelo de resposta em streaming",
    responses=fast_api_responses,
)
async def chat_completation_stream(  # NOSONAR  # noqa: C901, PLR0915
    request: ChatRequest, request_starllete: Request
):
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    async def stream_generator():  # pragma: no cover  # noqa: C901, PLR0911, PLR0912, PLR0915  # NOSONAR
        # use_thinking não troca o agent_tag: o mesmo modelo base é reusado e
        # o reasoning é ativado via Responses API (ChatOpenAI(use_responses_api=True)).
        model_data = {
            "agent_tag": settings.DEFAULT_RESPONSE_MODEL,
            "endpoint_name": ENDPOINT_NAME,
        }

        arquivos_avulsos_temp_files: set[str] = set()

        # Inicializa o processador de tags apenas se houver RAG ou potencial de tags
        stream_processor = None
        final_user_state = None
        current_status: str | None = None
        last_intermediate_msg: str | None = None
        _HEARTBEAT_INTERVAL = float(settings.STREAMING_HEARTBEAT_INTERVAL)
        _status_start_time: float | None = None
        _last_heartbeat_time: float | None = None
        _last_keepalive_time: float | None = None

        trace_id = _trace_id_for_request(request_starllete)
        request_starllete.state.trace_id = trace_id
        benchmark_tools = (
            BenchmarkToolHandler()
            if request_starllete.headers.get("X-Experiment-Collect-Tools") == "1"
            else None
        )
        benchmark_context_token = set_current_collector(benchmark_tools)
        span = None  # passado para os handle_*_exception abaixo

        try:
            # Dentro do try: uma HTTPException aqui (ex.: reasoning_effort
            # inválido pro modelo alvo) precisa cair no catch-all de baixo
            # (linha ~400) pra virar frame SSE de erro, não estourar cru —
            # a resposta já é 200 streaming nesse ponto, não dá mais pra
            # devolver um 422 "de verdade" na resposta HTTP.
            user_state: UserState = await create_user_state(
                request, request_starllete, model_data
            )
            with _langfuse_span("setup", trace_id=trace_id) as setup_span:
                span = setup_span
                initial_tags = _build_langfuse_tags(user_state)
                if initial_tags:
                    _update_langfuse_trace(
                        setup_span,
                        session_id=str(user_state.get("id_topico")),
                        input=user_state,
                        tags=initial_tags,
                    )
                else:
                    _update_langfuse_trace(
                        setup_span,
                        session_id=str(user_state.get("id_topico")),
                        input=user_state,
                    )
                try:
                    arquivos_avulsos_temp_files = (
                        await _apply_arquivos_avulsos_to_state(request, user_state)
                    )
                except HTTPException as exc:
                    error_data = handle_http_exception(exc, setup_span)
                    yield f"data: {json.dumps(error_data, ensure_ascii=False, default=json_serializer)}\n\n"
                    return

                callbacks = [CallbackHandler()]
                if benchmark_tools is not None:
                    callbacks.append(benchmark_tools)
                config = {"callbacks": callbacks}
                graph_workflow = await build_chat_completion_graph()

            # Span ativo no OTel context para o CallbackHandler herdar.
            with _langfuse_span("langgraph", trace_id=trace_id) as graph_span:
                span = graph_span

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
                            ref = _last_heartbeat_time or _status_start_time
                            _timeout = max(0.1, _HEARTBEAT_INTERVAL - (now - ref))
                        else:
                            # Sem status intermediário ativo (ex.: geração da resposta
                            # final, onde o reasoning pode ficar dezenas de segundos sem
                            # emitir token). Mantém um keep-alive periódico para o
                            # consumidor (recurso SEI / proxy) não interpretar o silêncio
                            # do stream como conexão morta e abortar com timeout/500.
                            ref = (
                                _last_keepalive_time
                                if _last_keepalive_time is not None
                                else now
                            )
                            _timeout = max(0.1, _HEARTBEAT_INTERVAL - (now - ref))

                        done, _ = await asyncio.wait({_next_task}, timeout=_timeout)

                        if not done:
                            if current_status:
                                intermediate = get_next_intermediate_message(
                                    current_status, last_intermediate_msg
                                )
                                if intermediate:
                                    last_intermediate_msg = intermediate
                                    _last_heartbeat_time = (
                                        asyncio.get_running_loop().time()
                                    )
                                    heartbeat_data = {
                                        "type": "status",
                                        "data": f" {intermediate}",
                                        "timestamp": _last_heartbeat_time,
                                    }
                                    yield f"data: {json.dumps(heartbeat_data, ensure_ascii=False, default=json_serializer)}\n\n"
                            else:
                                # Keep-alive neutro como comentário SSE (linha iniciada
                                # por ':'). O parser de eventos `data:` do frontend ignora
                                # comentários, mas o byte trafegado reseta o read-timeout
                                # do proxy/cliente durante fases silenciosas do stream.
                                _last_keepalive_time = asyncio.get_running_loop().time()
                                yield ": keepalive\n\n"
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
                        except (
                            openai.APITimeoutError,
                            httpx.TimeoutException,
                        ) as exc:
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

            with _langfuse_span("finalize", trace_id=trace_id) as final_span:
                span = final_span
                final_tags = _build_langfuse_tags(final_user_state)
                if final_tags:
                    _update_langfuse_trace(
                        final_span, output=final_user_state, tags=final_tags
                    )
                else:
                    _update_langfuse_trace(final_span, output=final_user_state)

                if final_user_state and final_user_state.get("response"):
                    model_response = ModelResponseWithMetadata(
                        user_state=final_user_state
                    )
                    model_response_dict = model_response.to_dict()
                    if benchmark_tools is not None:
                        model_response_dict["benchmark_metrics"] = (
                            benchmark_tools.summary()
                        )

                    final_data = {
                        "type": "metadata",
                        "data": model_response_dict,
                        "timestamp": asyncio.get_running_loop().time(),
                    }
                    yield f"data: {json.dumps(final_data, ensure_ascii=False, default=json_serializer)}\n\n"
                else:
                    # Sem `response` no estado final → emite erro 500 em vez de
                    # bubblar ValueError (frontend ficaria travado).
                    logger.error(
                        "final_user_state ausente ou sem 'response' ao final do stream "
                        f"[trace_id={trace_id}]"
                    )
                    error_data = handle_unhandled_exception(
                        RuntimeError(
                            "Stream encerrou sem resposta do modelo. Tente novamente."
                        ),
                        final_span,
                    )
                    yield f"data: {json.dumps(error_data, ensure_ascii=False, default=json_serializer)}\n\n"
                    return

                end_data = {
                    "type": "end",
                    "data": "Stream completed",
                    "timestamp": asyncio.get_running_loop().time(),
                }
                yield f"data: {json.dumps(end_data, ensure_ascii=False, default=json_serializer)}\n\n"

        except Exception as exc:
            # Catch-all: garante evento SSE de erro p/ frontend não travar.
            logger.exception(
                "Erro não tratado no stream_generator (fora dos handlers internos): "
                f"{type(exc).__name__} [trace_id={trace_id}]"
            )
            status_code = getattr(exc, "status_code", 500)
            detail = getattr(exc, "detail", None) or f"Erro interno: {exc}"
            error_data = {
                "type": "error",
                "status_code": status_code,
                "detail": detail,
                "timestamp": asyncio.get_running_loop().time(),
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False, default=json_serializer)}\n\n"
        finally:
            cleanup_arquivos_avulsos_temp_files(arquivos_avulsos_temp_files)
            reset_current_collector(benchmark_context_token)
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
