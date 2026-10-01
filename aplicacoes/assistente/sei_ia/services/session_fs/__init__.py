"""Sessão escopada do endpoint Deep Agents (/llm_lang/session_stream).

A sessão é fechada por (id_usuario, id_topico): o filesystem do deepagents vive
em ``SESSIONS_ROOT/{session_key}/`` e o histórico multi-turn no checkpointer
Postgres com ``thread_id = session_key``. TTL deslizante apaga tudo na expiração.
"""

from sei_ia.services.session_fs.types import (
    SessionMeta,
    SessionPaths,
    build_session_key,
)

__all__ = ["SessionMeta", "SessionPaths", "build_session_key"]
