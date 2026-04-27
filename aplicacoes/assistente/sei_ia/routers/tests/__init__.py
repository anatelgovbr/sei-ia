"""Rotas do endpoint para realização de testes."""

import fastapi  # noqa: I001

# from sei_ia.routers.tests.tests import router as tests
from sei_ia.routers.tests.timeout_checker import router as timeout_test


api_router = fastapi.APIRouter()

# api_router.include_router(tests)
api_router.include_router(timeout_test)
