"""Modulo comum para as funcoes usadas nas rotas da API."""

import asyncio
import logging
from contextlib import contextmanager

import openai
from fastapi import HTTPException as FastAPIHTTPException, Request
from httpx import ReadTimeout
from langfuse.langchain import CallbackHandler

from sei_ia.agents.chat_completion_graph import build_chat_completion_graph
from sei_ia.configs.langfuse_config import (
    get_configured_langfuse_client,
    mask_langfuse_payload,
)
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.database.db_instances import app_db_instance
from sei_ia.data.database.sei_client import sei_client
from sei_ia.data.etl.extract.uploads import (
    AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION,
    IMAGE_ATTACHMENT_SYSTEM_INSTRUCTION,
    ArquivoAvulsoProcessingError,
    cleanup_arquivos_avulsos_temp_files,
    process_arquivos_avulsos,
    process_uploads_tolerant,
)
from sei_ia.data.pydantic_models import ChatRequest, UserState
from sei_ia.routers.chat.model_response import ModelResponse
from sei_ia.services.cache import get_cache
from sei_ia.services.cache.cache_cleanup_service import cleanup_non_cacheable_documents
from sei_ia.services.cache.topic_attachments import persist_topic_attachments
from sei_ia.services.counter import token_counter
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException403,
    HTTPException408,
    HTTPException413,
    HTTPException429,
    HTTPException500,
)
from sei_ia.services.llm_models.chat_workflow import get_output_token_limit
from sei_ia.services.llm_models.get_model import get_model_config
from sei_ia.services.llm_models.model_catalog import (
    validate_model_override,
    validate_reasoning_effort,
)

setup_logging()
logger = logging.getLogger(__name__)
langfuse = get_configured_langfuse_client()


@contextmanager
def _langfuse_span(name: str, trace_id: str | None = None):
    if langfuse is None:
        yield None
        return
    if trace_id:
        with langfuse.start_as_current_span(  # type: ignore[attr-defined]
            name=name, trace_context={"trace_id": trace_id}
        ) as span:
            yield span
    else:
        with langfuse.start_as_current_span(name=name) as span:  # type: ignore[attr-defined]
            yield span


def _new_trace_id() -> str | None:
    """Trace_id criado antes dos spans para que o trace apareça na UI assim que
    o primeiro span (curto) fechar, em vez de esperar o request todo terminar."""
    if langfuse is None:
        return None
    return langfuse.create_trace_id()  # type: ignore[attr-defined]


def _flush_langfuse() -> None:
    if langfuse is None:
        return
    langfuse.flush()  # type: ignore[attr-defined]


def _update_langfuse_trace(span, **kwargs) -> None:
    if span is None:
        return
    span.update_trace(**kwargs)


def _trace_id_from_span(span) -> str | None:
    """ID do trace Langfuse associado ao span, para correlacionar logs de erro."""
    return getattr(span, "trace_id", None)


def _update_langfuse_observation(span, **kwargs) -> None:
    """Atualiza o span exibido na árvore do trace no Langfuse."""
    if span is None:
        return
    if "input" in kwargs:
        kwargs["input"] = mask_langfuse_payload(kwargs["input"])
    if "output" in kwargs:
        kwargs["output"] = mask_langfuse_payload(kwargs["output"])
    span.update(**kwargs)


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
        logger.debug("State incompleto ao coletar tags, ignorando")

    return tags


async def _validate_reasoning_effort_or_422(
    model_name: str, reasoning_effort: str | None
) -> None:
    """Valida `reasoning_effort` (se informado) contra o que `model_name`
    realmente aceita, e converte rejeição em HTTPException(422)."""
    if not reasoning_effort:
        return
    try:
        await validate_reasoning_effort(model_name, reasoning_effort)
    except ValueError as exc:
        raise FastAPIHTTPException(status_code=422, detail=str(exc)) from exc


async def _validate_model_override_or_422(model_override: str | None) -> None:
    """Valida `model` (override, se informado) contra o catálogo ao vivo do
    proxy LiteLLM, e converte rejeição em HTTPException(422)."""
    if not model_override:
        return
    try:
        await validate_model_override(model_override)
    except ValueError as exc:
        raise FastAPIHTTPException(status_code=422, detail=str(exc)) from exc


async def create_user_state(
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
    model_override = getattr(request, "model", None)
    await _validate_model_override_or_422(model_override)
    model_params = get_model_config(
        model_data["agent_tag"], model_override=model_override
    )

    # Valida contra o modelo físico que será de fato usado (já resolvido acima
    # com o override aplicado, se houver) — não assume um tier fixo, já que
    # este helper serve tanto o endpoint principal quanto outros agent_tags
    # (ex.: /chat_gpt_4o_mini_128k usa "classificador").
    reasoning_effort = getattr(request, "reasoning_effort", None)
    await _validate_reasoning_effort_or_422(model_params["model"], reasoning_effort)
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
        f"> entrou em process_chat_completion {model_data['agent_tag']}: Model: {model_params['model_name']}"
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
        agent_tag=str(model_data.get("agent_tag", "")),
        model_override=model_override,
        reasoning_effort=reasoning_effort,
        # Contrato legado do /stream: reserva local, sem limitar o provider.
        general_max_output_tokens=get_output_token_limit(model_data["agent_tag"]),
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


async def _remove_arquivos_avulsos_no_sei(
    arquivos_avulsos, *, eligible_ids: set[int] | None = None
) -> None:
    """Sinaliza ao SEI que os arquivos avulsos processados podem ser removidos.

    Esta função só deve ser chamada depois de ``process_arquivos_avulsos``
    concluir o lote inteiro. A API do SEI aceita um ID por chamada; por isso,
    não há remoção durante o processamento individual de cada upload.
    """
    loop = asyncio.get_running_loop()
    for arquivo_avulso in arquivos_avulsos:
        if (
            eligible_ids is not None
            and arquivo_avulso.id_arquivo_avulso not in eligible_ids
        ):
            continue
        try:
            await loop.run_in_executor(
                None,
                sei_client.md_ia_remove_arquivos_avulsos,
                [arquivo_avulso.id_arquivo_avulso],
            )
        except Exception:
            logger.warning(
                "Falha ao sinalizar remoção do arquivo avulso %s no SEI",
                arquivo_avulso.id_arquivo_avulso,
                exc_info=True,
            )
            continue
        logger.debug(
            "Arquivo avulso %s sinalizado para remoção no SEI",
            arquivo_avulso.id_arquivo_avulso,
        )


async def _apply_arquivos_avulsos_to_state(
    request,
    user_state: UserState,
    *,
    remove_from_sei: bool = True,
    tolerant_uploads: bool = False,
) -> set[str]:
    """Processa os arquivos avulsos do request e injeta no `user_state`.

    Retorna o conjunto de paths em /tmp/ que o caller deve apagar no `finally`
    do handler (incluindo paths já baixados quando um upload subsequente falhou).
    ``remove_from_sei=False`` permite que endpoints streaming só confirmem a
    remoção depois que o restante do request concluir com sucesso.

    Raises:
        FastAPIHTTPException(422): quando algum upload falha. Body inclui
            `{error, filename, extensao, message}` para o cliente identificar
            qual arquivo deu erro.
    """
    arquivos_avulsos = getattr(request, "arquivos_avulsos", None)
    if not arquivos_avulsos:
        return set()

    try:
        outcome = await (
            process_uploads_tolerant(arquivos_avulsos)
            if tolerant_uploads
            else process_arquivos_avulsos(arquivos_avulsos)
        )
    except ArquivoAvulsoProcessingError as exc:
        error = FastAPIHTTPException(
            status_code=422,
            detail={
                "error": "arquivo_avulso_failed",
                "legacy_error": "upload_failed",
                "filename": exc.filename,
                "extensao": exc.extensao,
                "message": exc.message,
            },
        )
        error.cleanup_paths = getattr(exc, "cleanup_paths", set())
        raise error from exc

    if outcome.text_block:
        user_state["user_request"] += f"\n\n{outcome.text_block}"
        user_state["all_tokens_counter"] += token_counter(outcome.text_block)
    if outcome.image_attachments:
        user_state["image_attachments"] = outcome.image_attachments
    user_state["upload_removal_ids"] = sorted(outcome.removal_ids)
    has_audio = any(
        attachment.tipo == "audio" and attachment.content_state != "unavailable"
        for attachment in outcome.attachments
    )
    if has_audio and user_state.get("system_prompt"):
        user_state["system_prompt"] += AUDIO_TRANSCRIPTION_SYSTEM_INSTRUCTION
    if outcome.image_attachments and user_state.get("system_prompt"):
        user_state["system_prompt"] += IMAGE_ATTACHMENT_SYSTEM_INSTRUCTION

    # Persiste anexos no Redis ANTES da remoção no SEI: se persistência
    # falhar (fail-open), o anexo ainda está no prompt corrente; se a
    # remoção falhar, o anexo já está disponível para consulta posterior.
    id_topico = user_state.get("id_topico")
    if id_topico is not None and outcome.attachments:
        try:
            await persist_topic_attachments(
                id_topico=int(id_topico),
                attachments=outcome.attachments,
            )
        except Exception:
            logger.warning(
                "Falha ao persistir anexos do tópico %s no Redis (fail-open)",
                id_topico,
                exc_info=True,
            )

    if remove_from_sei:
        # Só chegamos aqui depois de todos os uploads terem sido processados e, se
        # houver, persistidos. O cleanup de /tmp é independente e nunca significa
        # que o arquivo-fonte foi removido do SEI.
        await _remove_arquivos_avulsos_no_sei(
            arquivos_avulsos,
            eligible_ids=outcome.removal_ids,
        )

    return outcome.temp_files


async def process_chat_completion(  # noqa: C901, PLR0912, PLR0915  # NOSONAR
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
    model_params = get_model_config(
        model_data["agent_tag"], model_override=getattr(request, "model", None)
    )
    user_state: UserState = await create_user_state(
        request, request_starllete, model_data
    )
    arquivos_avulsos_temp_files: set[str] = set()

    trace_id = _new_trace_id()
    request_starllete.state.trace_id = trace_id

    try:
        with _langfuse_span("setup", trace_id=trace_id) as span:
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
            arquivos_avulsos_temp_files = await _apply_arquivos_avulsos_to_state(
                request, user_state
            )
            graph_workflow = await build_chat_completion_graph()

        # Span ativo no OTel context para o CallbackHandler herdar.
        with _langfuse_span("langgraph", trace_id=trace_id):
            final_state = await graph_workflow.ainvoke(
                user_state,
                config={"callbacks": [CallbackHandler()]},
            )

        with _langfuse_span("finalize", trace_id=trace_id) as span:
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
    except FastAPIHTTPException:
        # Erros já modelados com status_code (ex.: 422 de upload, 502 de
        # LLM proxy) precisam atravessar o handler de Exception genérico
        # abaixo sem virar 500.
        raise
    except (ReadTimeout, openai.APITimeoutError) as exc:
        logger.exception(f"Timeout error [trace_id={trace_id}]")
        raise HTTPException408 from exc
    except openai.BadRequestError as exc:
        logger.exception(f"BadRequestError capturada [trace_id={trace_id}]")
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
        logger.exception(f"Rate limit error [trace_id={trace_id}]")
        raise HTTPException429 from exc
    except openai.InternalServerError as exc:
        logger.exception(
            f"Erro interno no LiteLLM Proxy: {exc} [trace_id={trace_id}]"  # noqa: TRY401
        )
        raise FastAPIHTTPException(
            status_code=502,
            detail="Erro no serviço de LLM. O servidor de modelos retornou um erro interno. Tente novamente.",
        ) from exc
    except openai.APIConnectionError as exc:
        logger.exception(
            f"Erro de conexão com LLM Proxy: {exc} [trace_id={trace_id}]"  # noqa: TRY401
        )
        raise FastAPIHTTPException(
            status_code=503,
            detail="Serviço de LLM indisponível. Não foi possível conectar ao servidor de modelos.",
        ) from exc
    except Exception as ex:
        logger.exception(f"Erro inesperado [trace_id={trace_id}]")
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

        # Apaga arquivos avulsos baixados em /tmp/ depois da resposta ter
        # sido enviada (sucesso ou erro). Best-effort, não pode interromper
        # o fluxo de resposta ao usuário.
        cleanup_arquivos_avulsos_temp_files(arquivos_avulsos_temp_files)


# Aliases legados para testes/patches existentes durante a migração.
_apply_uploads_to_state = _apply_arquivos_avulsos_to_state
process_uploads = process_arquivos_avulsos
cleanup_upload_temp_files = cleanup_arquivos_avulsos_temp_files
UploadProcessingError = ArquivoAvulsoProcessingError
