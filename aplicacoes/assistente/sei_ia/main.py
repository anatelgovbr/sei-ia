"""API - Assistente ."""

import logging
import warnings
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from sei_ia.configs.langfuse_config import initialize_langfuse_singleton
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings

# from sei_ia.data.database.solr_handlers import CoreCreationExceptionError, create_solr_core  # REMOVIDO - não usado mais
from sei_ia.middleware.middleware_exception_handlers import (
    http_exception_handler,
    sqlalchemy_exception_handler,
)
from sei_ia.middleware.middleware_request import RequestMiddleware
from sei_ia.middleware.middleware_timeout import TimeoutMiddleware
from sei_ia.routers.chat.gpt_4o_128k import router as chat_2_doc_gpt_4o_128k_router
from sei_ia.routers.chat.gpt_4o_mini_128k import (
    router as chat_2_doc_gpt_4o_mini_128k_router,
)
from sei_ia.routers.chat.gpt_endpoint import router as gpt_endpoint
from sei_ia.routers.chat.rlm_stream import router as rlm_stream_router
from sei_ia.routers.feedback import router as feedback_router
from sei_ia.routers.healthcheck import api_router as healthcheck
from sei_ia.routers.tests import api_router as tests_router

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


@asynccontextmanager
async def initialize_database_tables(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan event handler for FastAPI application."""
    # Startup
    try:
        # Import models to ensure they are registered on BasePgvector.metadata
        from sqlalchemy import exc as sa_exc, text

        from sei_ia.data.database.db_instances import BasePgvector, app_db_instance
        from sei_ia.data.database.table_manager import TableManager

        with app_db_instance.engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE SCHEMA IF NOT EXISTS {settings.DB_SEIIA_ASSISTENTE_SCHEMA}"
                )
            )
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        logger.info(
            f"Schema {settings.DB_SEIIA_ASSISTENTE_SCHEMA} and pgvector extension ensured"
        )

        BasePgvector.metadata.create_all(app_db_instance.engine, checkfirst=True)
        logger.info("Database tables ensured at startup (BasePgvector)")

        # Initialize embeddings table and other custom tables
        table_manager = TableManager(app_db_instance)
        if table_manager.initialize_all_tables():
            logger.info("All custom tables initialized successfully")
        else:
            logger.warning(
                "Some custom tables initialization failed, but continuing..."
            )

    except sa_exc.ProgrammingError as e:  # Possible race across workers
        err_str = str(e.orig) if hasattr(e, "orig") else str(e)
        if "already exists" in err_str or "DuplicateTable" in err_str:
            logger.warning("Some tables already exist; proceeding")
        else:
            logger.exception("ProgrammingError ensuring database tables at startup")
            masked_conn = app_db_instance.hide_password(app_db_instance.conn_str)
            raise RuntimeError(
                f"Falha ao inicializar tabelas. DB: {masked_conn}"
            ) from e
    except sa_exc.SQLAlchemyError as e:
        logger.exception("Failed to ensure database tables at startup")
        masked_conn = app_db_instance.hide_password(app_db_instance.conn_str)
        raise RuntimeError(f"Falha ao inicializar tabelas. DB: {masked_conn}") from e

    yield

    # Shutdown
    logger.info("Application shutdown - closing database connections...")
    try:
        await app_db_instance.close()
        logger.info("Database connections closed successfully")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}", exc_info=True)


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if enable_timeout_middleware:
        app.add_middleware(TimeoutMiddleware)
        logging.info("TimeoutMiddleware habilitado.")
    if enable_request_middleware:
        app.add_middleware(RequestMiddleware)
        logging.info("RequestMiddleware habilitado.")

    # Adiciona os exception handlers
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(Exception, http_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)

    # Rotas
    app.include_router(tests_router)
    app.include_router(healthcheck)
    app.include_router(chat_2_doc_gpt_4o_128k_router)
    app.include_router(chat_2_doc_gpt_4o_mini_128k_router)
    app.include_router(gpt_endpoint)
    app.include_router(rlm_stream_router)
    app.include_router(feedback_router)

    return app


app = get_app()
