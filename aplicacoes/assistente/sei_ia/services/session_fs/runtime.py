"""Wiring de ciclo de vida do app para a sessão: singletons + sweeper.

Mantém `manager.py` puro (sem settings). Aqui amarramos o `SessionManager` ao
checkpointer singleton e às settings, e rodamos o sweeper periódico.
"""

from __future__ import annotations

import asyncio
import logging

from sei_ia.configs.settings_config import settings
from sei_ia.services.session_fs.checkpointer import get_session_checkpointer
from sei_ia.services.session_fs.manager import SessionManager

logger = logging.getLogger(__name__)

_manager: SessionManager | None = None


async def get_session_manager() -> SessionManager:
    """Manager singleton, ligado ao checkpointer já inicializado."""
    global _manager
    if _manager is None:
        checkpointer = await get_session_checkpointer()
        _manager = SessionManager(
            sessions_root=settings.SESSIONS_ROOT,
            ttl_seconds=settings.SESSION_TTL_SECONDS,
            checkpointer=checkpointer,
            max_fetch_concurrency=settings.SEI_API_SEMAPHORE,
            preview_chars=settings.SESSION_PREVIEW_CHARS,
        )
    return _manager


async def run_sweeper() -> None:
    """Loop periódico que apaga sessões expiradas. Iniciado no lifespan."""
    interval = settings.SESSION_SWEEPER_INTERVAL_SECONDS
    manager = await get_session_manager()
    logger.info("Sweeper de sessões iniciado (intervalo=%ds)", interval)
    while True:
        await asyncio.sleep(interval)
        try:
            await manager.sweep_once()
        except Exception:
            logger.warning("Falha no sweeper de sessões", exc_info=True)
