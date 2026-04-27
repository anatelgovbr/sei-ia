"""Rota para o pipeline RLM em streaming (SSE)."""

import asyncio
import contextlib
import json
import logging
import re
import time

import httpx
import openai
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from sei_ia.agents.disclaimer import (
    classify_disclaimer_need,
    prepare_disclaimer_for_response,
)
from sei_ia.agents.intent_selector_agent import intent_selector_agent
from sei_ia.agents.prompts.web_search import WEB_SEARCH_PROMPT
from sei_ia.agents.rag.sources import transform_response_sources_enhanced
from sei_ia.agents.websearch.azure_web_search_tool import bing_grounding_search
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.etl.concatenate_documents import concatenate_documents
from sei_ia.data.etl.extract.uploads import (
    AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION,
    EXT_AUDIO,
    process_uploads,
)
from sei_ia.data.pydantic_models import ChatRequest
from sei_ia.routers.chat import (
    _build_langfuse_tags,
    _flush_langfuse,
    _langfuse_span,
    _update_langfuse_trace,
    create_user_state,
)
from sei_ia.routers.chat.model_response import ModelResponseWithMetadata
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
from sei_ia.services.llm_models.chat_workflow import ChatError, chat_gpt
from sei_ia.services.rlm.config import RLMConfig
from sei_ia.services.rlm.engine_repl import rlm_pipeline
from sei_ia.services.rlm.intent_prompts import INTENT_PROMPT_FRAGMENTS

setup_logging()
logger = logging.getLogger(__name__)

ENDPOINT_NAME = "/llm_lang/rlm_stream"

router = APIRouter()

_CHUNK_SIZE = 50


@router.post(
    ENDPOINT_NAME,
    tags=["llm_lang"],
    summary="Pipeline RLM em streaming (SSE)",
    responses=fast_api_responses,
)
async def rlm_stream(request: ChatRequest, request_starllete: Request):
    logger.debug(f">> entrou em rlm_stream, endpoint={ENDPOINT_NAME}")

    async def stream_generator():
        with _langfuse_span("RLM") as span:
            try:
                # ------------------------------------------------------------------
                # Step 1: Inicializa UserState
                # ------------------------------------------------------------------
                model_data = {
                    "model_type": settings.DEFAULT_RESPONSE_MODEL
                    if not request.use_thinking
                    else "think",
                    "endpoint_name": ENDPOINT_NAME,
                    "temperature": 0.0,
                }
                user_state = create_user_state(request, request_starllete, model_data)

                # Registra trace inicial no Langfuse
                try:
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
                except Exception:
                    logger.debug(
                        "Langfuse trace inicial falhou — ignorando", exc_info=True
                    )

                # ------------------------------------------------------------------
                # Step 2: Processa uploads (se houver)
                # ------------------------------------------------------------------
                if getattr(request, "uploads", None):
                    has_audio = any(
                        u.extensao.lower().strip(".") in EXT_AUDIO
                        for u in request.uploads
                    )
                    uploads_content = await process_uploads(request.uploads)
                    if uploads_content:
                        user_state["user_request"] += f"\n\n{uploads_content}"
                        user_state["all_tokens_counter"] += token_counter(
                            uploads_content
                        )
                    if has_audio and user_state.get("system_prompt"):
                        user_state["system_prompt"] += (
                            AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION
                        )

                # ------------------------------------------------------------------
                # Step 3: Carrega documentos (se houver)
                # ------------------------------------------------------------------
                if len(user_state.get("all_documents", [])) > 0:
                    user_state = await concatenate_documents(user_state)

                # ------------------------------------------------------------------
                # Step 4: Detecta intent (somente quando há documentos)
                # ------------------------------------------------------------------
                if user_state.get("has_content"):
                    user_state = await intent_selector_agent(user_state)

                # ------------------------------------------------------------------
                # Step 5: Disclaimer em paralelo com o pipeline principal
                # ------------------------------------------------------------------
                disclaimer_task: asyncio.Task | None = asyncio.create_task(
                    classify_disclaimer_need(user_state)
                )

                try:
                    # ------------------------------------------------------------------
                    # Step 6: Caminhos de execução
                    # ------------------------------------------------------------------
                    has_content = user_state.get("has_content", False)
                    intent = user_state.get("intent", "")

                    if has_content:
                        # Prepend intent-specific instruction
                        intent_instruction = INTENT_PROMPT_FRAGMENTS.get(intent, "")
                        if intent_instruction:
                            user_state["user_request"] = (
                                f"{intent_instruction}\n\n{user_state['user_request']}"
                            )

                        config = RLMConfig()
                        total_tokens = user_state.get("all_tokens_counter", 0)

                        _reporter_cls = None
                        if settings.RLM_REPORTER:
                            from sei_ia.services.rlm.reporter import RLMReporter

                            _reporter_cls = RLMReporter

                        if total_tokens < config.direct_llm_token_threshold:
                            # Path: Contexto pequeno — LLM direto (com prompt injetado)
                            logger.info(
                                f"RLM bypass: {total_tokens} tokens < "
                                f"{config.direct_llm_token_threshold} threshold — LLM direto"
                            )
                            _rlm_reporter = _reporter_cls() if _reporter_cls else None
                            response_dict = await chat_gpt(user_state)
                            if _rlm_reporter is not None:
                                _rlm_reporter.print_report(
                                    user_state,
                                    threshold=config.direct_llm_token_threshold,
                                    path="direto",
                                )
                        else:
                            # Path: Contexto grande — pipeline RLM
                            logger.info(
                                f"RLM ativado: {total_tokens} tokens >= "
                                f"{config.direct_llm_token_threshold} threshold"
                            )
                            user_state["limit_rag"] = 0
                            _rlm_reporter = _reporter_cls() if _reporter_cls else None
                            user_state = await rlm_pipeline(
                                user_state,
                                config=config,
                                on_step=_rlm_reporter,
                            )
                            if _rlm_reporter is not None:
                                _rlm_reporter.print_report(
                                    user_state,
                                    threshold=config.direct_llm_token_threshold,
                                    path="rlm",
                                )
                            response_dict = await chat_gpt(user_state)

                        # Aplica transformação de fontes/citações quando aplicável
                        if response_dict.get("response", "").find(
                            "<doc_"
                        ) != -1 or user_state.get("doc_rag"):
                            response_dict = transform_response_sources_enhanced(
                                response_dict, user_state
                            )

                        user_state["response"] = response_dict
                        answer = response_dict.get("response", "")

                    else:
                        # Path: Sem documentos
                        if user_state.get("use_websearch"):
                            # Pre-search: busca web ANTES do agente final
                            raw_result = await asyncio.to_thread(
                                bing_grounding_search.invoke,
                                {"query": user_state["user_request"]},
                            )
                            try:
                                parsed = json.loads(raw_result)
                            except (json.JSONDecodeError, TypeError):
                                parsed = {
                                    "text": raw_result
                                    if isinstance(raw_result, str)
                                    else "",
                                    "references": [],
                                }

                            web_text = parsed.get("text", "")
                            web_refs = parsed.get("references", [])

                            # Normalizar <web_N></web_N> → <web_N>
                            web_text = re.sub(
                                r"<web_(\d+)></web_\1>", r"<web_\1>", web_text
                            )

                            if web_refs:
                                user_state["tool_web_search"] = [
                                    {"references": web_refs}
                                ]

                            # Injetar texto web como contexto no prompt
                            user_state["last_prompt"] = (
                                f'<busca_web query="{user_state["user_request"]}">'
                                f"{web_text}</busca_web>"
                                f"\n\n{user_state['user_request']}"
                            )

                            # Instrucoes de citacao web no system prompt
                            user_state["system_prompt"] = (
                                f"{user_state['system_prompt']}\n\n{WEB_SEARCH_PROMPT}"
                            )

                            # Desabilitar websearch no chat_gpt p/ evitar busca duplicada
                            user_state["use_websearch"] = False

                        response_dict = await chat_gpt(user_state)

                        # Resolver <web_N> → HTML tooltips
                        if user_state.get("tool_web_search"):
                            response_dict = transform_response_sources_enhanced(
                                response_dict, user_state
                            )

                        user_state["response"] = response_dict
                        answer = response_dict.get("response", "")

                    # ------------------------------------------------------------------
                    # Step 7: Aguarda disclaimer e prepend se necessário
                    # ------------------------------------------------------------------
                    try:
                        disclaimer_result = await disclaimer_task
                        disclaimer_task = None
                        user_state.update(disclaimer_result)
                        disclaimer_prepared = await prepare_disclaimer_for_response(
                            user_state
                        )
                        user_state.update(disclaimer_prepared)
                        disclaimer_text = user_state.get("disclaimer_text")
                        if disclaimer_text:
                            answer = disclaimer_text + answer
                    except Exception:
                        logger.warning(
                            "Erro ao processar disclaimer — ignorando", exc_info=True
                        )

                finally:
                    # Cancela a task de disclaimer se ainda estiver pendente
                    if disclaimer_task is not None and not disclaimer_task.done():
                        disclaimer_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await disclaimer_task

                # ------------------------------------------------------------------
                # Step 8: Emite conteúdo em chunks
                # ------------------------------------------------------------------
                for i in range(0, len(answer), _CHUNK_SIZE):
                    chunk = answer[i : i + _CHUNK_SIZE]
                    yield f"data: {json.dumps({'type': 'content', 'data': chunk, 'timestamp': time.time()}, ensure_ascii=False, default=str)}\n\n"

                # ------------------------------------------------------------------
                # Step 9: Emite metadata
                # ------------------------------------------------------------------
                response_obj = ModelResponseWithMetadata(user_state=user_state)
                metadata = response_obj.to_dict()
                yield f"data: {json.dumps({'type': 'metadata', 'data': metadata, 'timestamp': time.time()}, ensure_ascii=False, default=str)}\n\n"

                # ------------------------------------------------------------------
                # Step 10: Emite fim do stream
                # ------------------------------------------------------------------
                yield f"data: {json.dumps({'type': 'end', 'data': 'Stream completed', 'timestamp': time.time()}, default=str)}\n\n"

                # Atualiza trace final no Langfuse
                try:
                    final_tags = _build_langfuse_tags(user_state)
                    if final_tags:
                        _update_langfuse_trace(span, output=user_state, tags=final_tags)
                    else:
                        _update_langfuse_trace(span, output=user_state)
                except Exception:
                    logger.debug(
                        "Langfuse trace final falhou — ignorando", exc_info=True
                    )

            except HTTPException as exc:
                error_data = handle_http_exception(exc, span)
                yield f"data: {json.dumps(error_data, ensure_ascii=False, default=str)}\n\n"
                return
            except openai.BadRequestError as exc:
                error_data = handle_openai_bad_request(exc, span)
                yield f"data: {json.dumps(error_data, ensure_ascii=False, default=str)}\n\n"
                return
            except openai.InternalServerError as exc:
                error_data = handle_openai_internal_server_error(exc, span)
                yield f"data: {json.dumps(error_data, ensure_ascii=False, default=str)}\n\n"
                return
            except openai.RateLimitError as exc:
                error_data = handle_rate_limit(exc, span)
                yield f"data: {json.dumps(error_data, ensure_ascii=False, default=str)}\n\n"
                return
            except (openai.APIConnectionError, httpx.ConnectError) as exc:
                error_data = handle_connection_error(exc, span)
                yield f"data: {json.dumps(error_data, ensure_ascii=False, default=str)}\n\n"
                return
            except (openai.APITimeoutError, httpx.TimeoutException) as exc:
                error_data = handle_timeout(exc, span)
                yield f"data: {json.dumps(error_data, ensure_ascii=False, default=str)}\n\n"
                return
            except ChatError as exc:
                error_data = handle_chat_error(exc, span)
                yield f"data: {json.dumps(error_data, ensure_ascii=False, default=str)}\n\n"
                return
            except (httpx.ReadError, httpx.RemoteProtocolError) as exc:
                error_data = handle_protocol_error(exc, span)
                yield f"data: {json.dumps(error_data, ensure_ascii=False, default=str)}\n\n"
                return
            except Exception as exc:
                error_data = handle_unhandled_exception(exc, span)
                # Sanitiza detail para nao vazar informacoes internas
                error_data["detail"] = "Erro interno inesperado. Tente novamente."
                yield f"data: {json.dumps(error_data, ensure_ascii=False, default=str)}\n\n"
                return

        _flush_langfuse()

        logger.debug(f">> saindo de rlm_stream, endpoint={ENDPOINT_NAME}")

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )
