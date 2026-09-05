"""API - Assistente ."""

import asyncio
import logging
import warnings
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from sei_ia.configs.langfuse_config import initialize_langfuse_singleton
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.middleware.middleware_exception_handlers import (
    http_exception_handler,
    sqlalchemy_exception_handler,
)
from sei_ia.middleware.middleware_request import RequestMiddleware
from sei_ia.middleware.middleware_timeout import TimeoutMiddleware
from sei_ia.routers.chat.gpt_4o_mini_128k import (
    router as chat_2_doc_gpt_4o_mini_128k_router,
)
from sei_ia.routers.feedback import router as feedback_router
from sei_ia.routers.healthcheck import api_router as healthcheck
from sei_ia.routers.llm_models import api_router as llm_models_router
from sei_ia.routers.session import router as session_stream_router
from sei_ia.routers.tests import api_router as tests_router
from sei_ia.services.embedder.pipeline import embedding_generator

# Suprime warnings do Pydantic sobre conflitos de namespace com a biblioteca docling
# Colocado após os imports para evitar E402 do Ruff
warnings.filterwarnings(
    "ignore",
    message=".*has conflict with protected namespace.*model_.*",
    category=UserWarning,
    module="pydantic._internal._fields",
)

setup_logging()
load_dotenv()

logger = logging.getLogger(__name__)

# IMPORTANTE: Inicializa o singleton GLOBAL do Langfuse ANTES de qualquer outra coisa
# Isso garante que quando CallbackHandler() chamar get_client() internamente,
# ele pegará o cliente já configurado com blocked_instrumentation_scopes.
# Ref: https://github.com/orgs/langfuse/discussions/8492


initialize_langfuse_singleton()


async def _start_session_runtime() -> asyncio.Task:
    """Initialize the session checkpointer and sweeper or propagate failure."""
    from sei_ia.services.session_fs.checkpointer import get_session_checkpointer
    from sei_ia.services.session_fs.runtime import run_sweeper

    await get_session_checkpointer()
    task = asyncio.create_task(run_sweeper())
    logger.info("Sessão Deep Agents inicializada (checkpointer + sweeper)")
    return task


async def _stop_session_runtime(sweeper_task: "asyncio.Task | None") -> None:
    if sweeper_task is not None:
        sweeper_task.cancel()
        with suppress(asyncio.CancelledError):
            await sweeper_task
    from sei_ia.services.session_fs.checkpointer import close_session_checkpointer

    await close_session_checkpointer()


@asynccontextmanager
async def initialize_database_tables(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001  # NOSONAR
    """Lifespan event handler for FastAPI application."""
    from sei_ia.data.database.db_instances import BasePgvector, app_db_instance
    from sei_ia.data.database.runtime_bootstrap import initialize_runtime_database

    sweeper_task: asyncio.Task | None = None
    await app_db_instance.connect()
    try:
        try:
            await initialize_runtime_database(app_db_instance, BasePgvector.metadata)
        except SQLAlchemyError as e:
            logger.exception("Failed to ensure database tables at startup")
            masked_conn = app_db_instance.hide_password(app_db_instance.conn_str)
            raise RuntimeError(
                f"Falha ao inicializar tabelas. DB: {masked_conn}"
            ) from e

        logger.info("Runtime database bootstrap completed")
        if not embedding_generator.provider.test_connection():
            logger.warning(
                "LiteLLM Proxy inalcançável no startup; pipeline pode falhar"
            )

        sweeper_task = await _start_session_runtime()
        yield
    finally:
        logger.info("Application shutdown - closing database connections...")
        shutdown_errors: list[Exception] = []
        try:
            await _stop_session_runtime(sweeper_task)
        except Exception as e:
            shutdown_errors.append(e)
        try:
            await app_db_instance.close()
        except Exception as e:
            shutdown_errors.append(e)
        if shutdown_errors:
            raise ExceptionGroup(
                "Failed to close application database resources.", shutdown_errors
            )
        logger.info("Database connections closed successfully")


def get_app(
    enable_timeout_middleware: bool = True,
    enable_request_middleware: bool = True,
) -> FastAPI:
    """Função para criar uma instância do FastAPI com middlewares opcionais.
    Args:
        enable_timeout_middleware (bool): Habilita TimeoutMiddleware se True.
        enable_request_middleware (bool): Habilita RequestMiddleware se True.
    Returns:
        FastAPI: Instância do FastAPI com os middlewares especificados.
    """
    app = FastAPI(
        title=settings.APP_NAME,
        redoc_url="/",
        version=settings.VERSION,
        description=settings.APP_NAME,
        lifespan=initialize_database_tables,
    )
    if enable_timeout_middleware:
        app.add_middleware(TimeoutMiddleware)
        logging.info("TimeoutMiddleware habilitado.")
    if enable_request_middleware:
        app.add_middleware(RequestMiddleware)
        logging.info("RequestMiddleware habilitado.")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Adiciona os exception handlers
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(Exception, http_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)

    # Rotas
    app.include_router(tests_router)
    app.include_router(healthcheck)
    app.include_router(chat_2_doc_gpt_4o_mini_128k_router)
    app.include_router(session_stream_router)
    app.include_router(feedback_router)
    app.include_router(llm_models_router)

    return app


app = get_app()
