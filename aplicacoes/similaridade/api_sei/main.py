#!/usr/bin/env python
"""Módulo principal da API."""

import logging

from fastapi import FastAPI

from api_sei.db_models.solr_select import SolrRequests
from api_sei.envs import (
    ENABLE_OTEL_METRICS,
    SOLR_ADDRESS,
    SOLR_MLT_JURISPRUDENCE_CORE,
    SOLR_MLT_PROCESS_CORE,
    auth,
)
from api_sei.exception_handling.exception_handlers import (
    global_exception_handler,  # , exception_handlers
)
from api_sei.middleware.otel_middleware import MetricsMeddleware
from api_sei.routers.autotests import router as autoteste_router
from api_sei.routers.healthcheck import router as rerank_healthcheck
from api_sei.routers.jurisprudence_recommender import router as jurisprudence_router
from api_sei.routers.mlt_recommender import router as mlt_router
from api_sei.routers.n_embeddings_recommender import router as n_embd_router
from api_sei.routers.rerank_recommender import router as rerank_router

logger = logging.getLogger(__name__)

app = FastAPI(
    redoc_url="/",
    title="API de recomendação de processos SEI.",
    version="1.3.3",
)

if ENABLE_OTEL_METRICS:
    from api_sei.middleware.otel_middleware import MetricsMeddleware

    logger.info("Habilitando OTEL Metrics Middleware.")
    app.add_middleware(MetricsMeddleware)
else:
    logger.info("OTEL Metrics Middleware desabilitado.")

app.add_exception_handler(Exception, global_exception_handler)

# TEST DATABASE AND SOLR CONNECTION
if not SolrRequests().check_core_exists(
    SOLR_ADDRESS, SOLR_MLT_JURISPRUDENCE_CORE, auth=auth
):
    logger.warning(f"Core {SOLR_MLT_JURISPRUDENCE_CORE} nao encontrado")

if not SolrRequests().check_core_exists(SOLR_ADDRESS, SOLR_MLT_PROCESS_CORE, auth=auth):
    logger.warning(f"Core {SOLR_MLT_PROCESS_CORE} nao encontrado")

# ROUTERS
app.include_router(router=mlt_router)
app.include_router(router=rerank_router)
app.include_router(router=n_embd_router)
app.include_router(router=jurisprudence_router)
app.include_router(router=rerank_healthcheck)
app.include_router(router=autoteste_router)
