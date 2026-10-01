"""Router do endpoint Deep Agents com sessão escopada (/llm_lang/session_stream).

Pacote próprio (fora de `routers/chat/`) para não herdar o import do LangGraph
antigo feito em `routers/chat/__init__.py`. Mantém o endpoint isolado do fluxo atual.
"""

from fastapi import APIRouter

from sei_ia.routers.session.benchmark import router as benchmark_router
from sei_ia.routers.session.stream import router as stream_router

router = APIRouter()
router.include_router(stream_router)
router.include_router(benchmark_router)

__all__ = ["router"]
