"""Modulo comum para as funcoes usadas nas rotas da API."""

import logging
from contextlib import contextmanager

import openai
from fastapi import Request
from httpx import ReadTimeout
from langfuse.langchain import CallbackHandler

from sei_ia.agents.chat_completion_graph import build_chat_completion_graph
from sei_ia.configs.langfuse_config import (
    get_configured_langfuse_client,
    truncate_large_fields,
)
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.database.db_instances import app_db_instance
from sei_ia.data.etl.extract.uploads import (
    AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION,
    EXT_AUDIO,
    process_uploads,
)
from sei_ia.data.pydantic_models import ChatRequest, ChatRequestWithModel, UserState
from sei_ia.routers.chat.model_response import ModelResponse, ModelResponseWithMetadata
from sei_ia.services.cache import get_cache
from sei_ia.services.cache.cache_cleanup_service import cleanup_non_cacheable_documents
from sei_ia.services.counter import token_counter
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException204,
    HTTPException403,
    HTTPException404,
    HTTPException406,
    HTTPException408,
    HTTPException411DocumentTimeout,
    HTTPException412SeiApiTimeout,
    HTTPException413,
    HTTPException415,
    HTTPException422,
    HTTPException429,
    HTTPException500,
)
from sei_ia.services.llm_models.get_model import get_model_config

setup_logging()
logger = logging.getLogger(__name__)
langfuse = get_configured_langfuse_client()


@contextmanager
def _langfuse_span(name: str):
    if langfuse is None:
        yield None
        return
    with langfuse.start_as_current_span(name=name) as span:  # type: ignore[attr-defined]
        yield span


def _flush_langfuse() -> None:
    if langfuse is None:
        return
    langfuse.flush()  # type: ignore[attr-defined]


def _update_langfuse_trace(span, **kwargs) -> None:
    if span is None:
        return
    # Aplica truncamento explícito nos campos input/output para garantir
    # que dados grandes não sejam enviados ao Langfuse
    if "input" in kwargs:
        kwargs["input"] = truncate_large_fields(kwargs["input"])
    if "output" in kwargs:
        kwargs["output"] = truncate_large_fields(kwargs["output"])
    span.update_trace(**kwargs)


def _build_langfuse_tags(state: UserState) -> list[str]:
    """Monta a lista de tags do Langfuse com base no user_state."""
    tags: list[str] = []
    try:
        intent = state.get("intent")
        if intent:
            tags.append(f"intent:{intent}")

        if state.get("use_websearch"):
            tags.append("websearch")

        if state.get("use_thinking"):
            tags.append("thinking")

        if state.get("doc_rag"):
            tags.append("rag")

        rag_method = state.get("rag_method")
        if rag_method:
            tags.append(f"rag_method:{rag_method}")
    except Exception:
        # Não bloquear o fluxo caso o state não esteja completo ainda
        pass

    return tags


def create_user_state(
    request: ChatRequest,
    request_starllete: Request,
    model_data: dict,
) -> UserState:
    """Função genérica para processar solicitações de chat completion.
    Args:
        request: O objeto de solicitação contendo os dados.
        request_starllete: O objeto de solicitação do starlette.
        model_data: Os dados do modelo a ser usado.
    Returns:
        dict: A resposta do modelo em formato de dicionário.
    """
    model_params = get_model_config(model_data["model_type"])
    general_max_ctx_len = model_params["max_ctx_len"] * settings.FACTOR_MAX_INPUT
    tokens_user_prompt = token_counter(request.text)
    tokens_system_prompt = token_counter(request.system_prompt)

    # Captura o body original da requisição
    original_request_body = ""
    if hasattr(request_starllete.state, "body"):
        try:
            original_request_body = request_starllete.state.body.decode("utf-8")
        except (AttributeError, UnicodeDecodeError):
            logger.warning("Não foi possível decodificar o body original da requisição")
            original_request_body = (
                str(request_starllete.state.body)
                if hasattr(request_starllete.state, "body")
                else ""
            )

    logger.debug(
        f"> entrou em process_chat_completion {model_data['model_type']}: Model: {model_params['model_name']}"
    )

    user_state = UserState(
        id_request=str(getattr(request_starllete.state, "id_request", "0")),
        id_usuario=str(request.id_usuario) if request.id_usuario is not None else "",
        ip=str(getattr(request_starllete.state, "ip", "127.0.0.1")),
        endpoint_name=str(request_starllete.scope.get("path", "")),
        id_topico=request.id_topico if hasattr(request, "id_topico") else None,
        id_procedimentos=request.id_procedimentos
        if hasattr(request, "id_procedimentos")
        else None,
        user_request="<user_request>" + request.text + "</user_request>"
        if hasattr(request, "text")
        else "",
        system_prompt=request.system_prompt
        if hasattr(request, "system_prompt")
        else "",
        original_request_body=original_request_body,
        all_procs=request.all_procs_allowed()
        if hasattr(request, "all_procs_allowed")
        else False,
        all_documents=request.all_documents_allowed()
        if hasattr(request, "all_documents_allowed")
        else False,
        use_websearch=bool(getattr(request, "use_websearch", False)),
        summarize_history=bool(getattr(request, "summarize_history", False)),
        use_thinking=bool(getattr(request, "use_thinking", False)),
        doc_paged=False,
        doc_summarized=False,
        doc_rag=False,
        doc_false_rag=False,
        all_tokens_counter=int(
            tokens_user_prompt
            + tokens_system_prompt
            + settings.MEMORY_ITERATION_TOKENS_LIMIT
        ),
        web_content="",
        model_type=str(model_data.get("model_type", "")),
        temperature=0.01,
        general_max_output_tokens=int(model_params.get("max_output_tokens", 0)),
        general_max_ctx_len=int(general_max_ctx_len),
        limit_rag=float(settings.FACTOR_LIMIT_RAG) * float(general_max_ctx_len),
        intent="",
        has_content=False,
        # Novos campos para pular o uso de memória
        skip_memory=bool(getattr(request, "skip_memory", False)),
        # Campos para RAG Enhanced
        rag_method=None,
        rag_documents_count=None,
        rag_chunks_count=None,
        response={},  # type: ignore[PGH003]
    )
    return user_state


async def process_chat_completion(
    request: ChatRequest,
    request_starllete: Request,
    model_data: dict,
) -> dict:
    """Função genérica para processar solicitações de chat completion.
    Args:
        request: O objeto de solicitação contendo os dados.
        request_starllete: O objeto de solicitação do starlette.
        model_data: Os dados do modelo a ser usado.
        use_websearch: Indica se deve usar WebSearch.
    Returns:
        dict: A resposta do modelo em formato de dicionário.
    """
    model_params = get_model_config(model_data["model_type"])
    user_state: UserState = create_user_state(request, request_starllete, model_data)

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

    graph_workflow = await build_chat_completion_graph()

    try:
        # Run the workflow graph usando o runnable configurado
        with _langfuse_span("LangGraph") as span:
            # Constrói tags e só adiciona se houver alguma
            initial_tags = _build_langfuse_tags(user_state)
            if initial_tags:
                _update_langfuse_trace(
                    span,
                    session_id=str(user_state["id_topico"]),
                    input=user_state,
                    tags=initial_tags,
                )
            else:
                _update_langfuse_trace(
                    span,
                    session_id=str(user_state["id_topico"]),
                    input=user_state,
                )

            final_state = await graph_workflow.ainvoke(
                user_state,
                config={"callbacks": [CallbackHandler()]},
            )

            # Constrói tags finais e só adiciona se houver alguma
            final_tags = _build_langfuse_tags(final_state)
            if final_tags:
                _update_langfuse_trace(span, output=final_state, tags=final_tags)
            else:
                _update_langfuse_trace(span, output=final_state)
        _flush_langfuse()
        # Generate model response
        model_response = ModelResponse(user_state=final_state)
        # Log para Solr removido - persist_log_api() desabilitado
        model_response_dict = model_response.to_dict()

        logger.debug(
            f">> saindo de process_chat_completion para {model_params['model_name']}"
        )
    except (
        HTTPException204,
        HTTPException404,
        HTTPException406,
        HTTPException411DocumentTimeout,
        HTTPException412SeiApiTimeout,
        HTTPException413,
        HTTPException415,
        HTTPException422,
        HTTPException429,
    ) as exc:
        logger.exception("Erro ao processar a requisição")
        raise exc from exc
    except (ReadTimeout, openai.APITimeoutError) as exc:
        logger.exception("Timeout error")
        raise HTTPException408 from exc
    except openai.BadRequestError as exc:
        logger.exception("BadRequestError capturada")
        error_json = None
        if hasattr(exc, "response") and hasattr(exc.response, "json"):
            try:
                error_json = exc.response.json()
            except (ValueError, TypeError, AttributeError):
                error_json = None
        if error_json:
            error_code = error_json.get("error", {}).get("code")
            inner_code = error_json.get("error", {}).get("innererror", {}).get("code")
            if (
                error_code == "content_filter"
                and inner_code == "ResponsibleAIPolicyViolation"
            ):
                msg = (
                    "Seu prompt foi bloqueado pela política de uso da OpenAI/Azure. "
                    "Por favor, revise o conteúdo e tente novamente."
                )
                raise HTTPException403(detail=msg) from exc
        msg = (
            f"Tamanho do contexto excedido ({user_state['all_tokens_counter']} tokens)."
        )
        raise HTTPException413(detail=msg) from exc
    except openai.RateLimitError as exc:
        logger.exception("Rate limit error")
        raise HTTPException429 from exc
    except openai.InternalServerError as exc:
        logger.exception(f"Erro interno no LiteLLM Proxy: {exc}")
        from fastapi import HTTPException as FastAPIHTTPException

        raise FastAPIHTTPException(
            status_code=502,
            detail="Erro no serviço de LLM. O servidor de modelos retornou um erro interno. Tente novamente.",
        ) from exc
    except openai.APIConnectionError as exc:
        logger.exception(f"Erro de conexão com LLM Proxy: {exc}")
        from fastapi import HTTPException as FastAPIHTTPException

        raise FastAPIHTTPException(
            status_code=503,
            detail="Serviço de LLM indisponível. Não foi possível conectar ao servidor de modelos.",
        ) from exc
    except Exception as ex:
        logger.exception("Erro inesperado")
        logger.info(f"Exception type: {type(ex)}, Exception: {ex}")
        raise HTTPException500 from ex
    else:
        return model_response_dict
    finally:
        # === LIMPEZA PÓS-RESPOSTA: Deletar cache/embeddings após processamento ===
        # Só executa se final_state existir (processamento foi bem-sucedido)
        # Se falhou antes, a limpeza em concatenate_documents.py não foi executada,
        # então não há necessidade de tentar limpar novamente
        if "final_state" in locals() and user_state.get("id_procedimentos"):
            try:
                redis_cache = get_cache()
                db_engine = app_db_instance.async_engine

                cleanup_result = await cleanup_non_cacheable_documents(
                    user_state=final_state,
                    redis_client=redis_cache,
                    db_pool=db_engine,
                )

                # Log apenas se houver algo deletado
                if (
                    cleanup_result["deleted_from_redis"]
                    or cleanup_result["deleted_from_postgres"]
                ):
                    logger.debug(
                        f"Pós-limpeza request {user_state['id_request']}: "
                        f"Redis={len(cleanup_result['deleted_from_redis'])}, "
                        f"Postgres={len(cleanup_result['deleted_from_postgres'])}"
                    )
            except Exception as e:
                # Não propagar erro - limpeza é auxiliar
                logger.warning(f"Erro na limpeza pós-resposta: {e}", exc_info=True)


async def process_chat_completion_with_model(
    request: ChatRequestWithModel,
    request_starllete: Request,
    model_data: dict,
) -> dict:
    """Função genérica para processar solicitações de chat completion.
    Args:
        request: O objeto de solicitação contendo os dados.
        request_starllete: O objeto de solicitação do starlette.
        model_data: Os dados do modelo a ser usado.
        use_websearch: Indica se deve usar WebSearch.
    Returns:
        dict: A resposta do modelo em formato de dicionário.
    """

    model_params = get_model_config(model_data["model_type"])
    user_state: UserState = create_user_state(request, request_starllete, model_data)

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

    graph_workflow = await build_chat_completion_graph()

    try:
        # Run the workflow graph usando o runnable configurado
        with _langfuse_span("LangGraph") as span:
            # Constrói tags e só adiciona se houver alguma
            initial_tags = _build_langfuse_tags(user_state)
            if initial_tags:
                _update_langfuse_trace(
                    span,
                    session_id=str(user_state["id_topico"]),
                    input=user_state,
                    tags=initial_tags,
                )
            else:
                _update_langfuse_trace(
                    span,
                    session_id=str(user_state["id_topico"]),
                    input=user_state,
                )

            final_state = await graph_workflow.ainvoke(
                user_state,
                config={"callbacks": [CallbackHandler()]},
            )

            # Constrói tags finais e só adiciona se houver alguma
            final_tags = _build_langfuse_tags(final_state)
            if final_tags:
                _update_langfuse_trace(span, output=final_state, tags=final_tags)
            else:
                _update_langfuse_trace(span, output=final_state)
        _flush_langfuse()
        # Generate model response
        model_response = ModelResponseWithMetadata(user_state=final_state)
        # Log para Solr removido - persist_log_api() desabilitado
        model_response_dict = model_response.to_dict()

        logger.debug(
            f">> saindo de process_chat_completion para {model_params['model_name']}"
        )
    except (
        HTTPException204,
        HTTPException404,
        HTTPException406,
        HTTPException411DocumentTimeout,
        HTTPException412SeiApiTimeout,
        HTTPException413,
        HTTPException415,
        HTTPException422,
        HTTPException429,
    ) as exc:
        logger.exception("Erro ao processar a requisição")
        raise exc from exc
    except (ReadTimeout, openai.APITimeoutError) as exc:
        logger.exception("Timeout error")
        raise HTTPException408 from exc
    except openai.BadRequestError as exc:
        logger.exception("BadRequestError capturada")
        error_json = None
        if hasattr(exc, "response") and hasattr(exc.response, "json"):
            try:
                error_json = exc.response.json()
            except (ValueError, TypeError, AttributeError):
                error_json = None
        if error_json:
            error_code = error_json.get("error", {}).get("code")
            inner_code = error_json.get("error", {}).get("innererror", {}).get("code")
            if (
                error_code == "content_filter"
                and inner_code == "ResponsibleAIPolicyViolation"
            ):
                msg = (
                    "Seu prompt foi bloqueado pela política de uso da OpenAI/Azure. "
                    "Por favor, revise o conteúdo e tente novamente."
                )
                raise HTTPException403(detail=msg) from exc
        msg = (
            f"Tamanho do contexto excedido ({user_state['all_tokens_counter']} tokens)."
        )
        raise HTTPException413(detail=msg) from exc
    except openai.RateLimitError as exc:
        logger.exception("Rate limit error")
        raise HTTPException429 from exc
    except openai.InternalServerError as exc:
        logger.exception(f"Erro interno no LiteLLM Proxy: {exc}")
        from fastapi import HTTPException as FastAPIHTTPException

        raise FastAPIHTTPException(
            status_code=502,
            detail="Erro no serviço de LLM. O servidor de modelos retornou um erro interno. Tente novamente.",
        ) from exc
    except openai.APIConnectionError as exc:
        logger.exception(f"Erro de conexão com LLM Proxy: {exc}")
        from fastapi import HTTPException as FastAPIHTTPException

        raise FastAPIHTTPException(
            status_code=503,
            detail="Serviço de LLM indisponível. Não foi possível conectar ao servidor de modelos.",
        ) from exc
    except Exception as ex:
        logger.exception("Erro inesperado")
        logger.info(f"Exception type: {type(ex)}, Exception: {ex}")
        raise HTTPException500 from ex
    else:
        return model_response_dict
    finally:
        # === LIMPEZA PÓS-RESPOSTA: Deletar cache/embeddings após processamento ===
        # Só executa se final_state existir (processamento foi bem-sucedido)
        # Se falhou antes, a limpeza em concatenate_documents.py não foi executada,
        # então não há necessidade de tentar limpar novamente
        if "final_state" in locals() and user_state.get("id_procedimentos"):
            try:
                redis_cache = get_cache()
                db_engine = app_db_instance.async_engine

                cleanup_result = await cleanup_non_cacheable_documents(
                    user_state=final_state,
                    redis_client=redis_cache,
                    db_pool=db_engine,
                )

                # Log apenas se houver algo deletado
                if (
                    cleanup_result["deleted_from_redis"]
                    or cleanup_result["deleted_from_postgres"]
                ):
                    logger.debug(
                        f"Pós-limpeza request {user_state['id_request']}: "
                        f"Redis={len(cleanup_result['deleted_from_redis'])}, "
                        f"Postgres={len(cleanup_result['deleted_from_postgres'])}"
                    )
            except Exception as e:
                # Não propagar erro - limpeza é auxiliar
                logger.warning(f"Erro na limpeza pós-resposta: {e}", exc_info=True)
