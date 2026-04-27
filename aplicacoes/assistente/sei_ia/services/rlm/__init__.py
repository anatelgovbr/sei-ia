"""RLM (Recursive Language Model) para extensao de contexto do assistente SEI-IA.

Este pacote implementa a estrategia RLM v2 (Plan-Execute-Synthesize via
LangGraph Tools) para permitir ao assistente interagir com contextos de
ate 4M tokens.

Uso basico::

    from rlm import rlm_pipeline, should_use_rlm, RLMConfig

    if should_use_rlm(user_state):
        user_state = await rlm_pipeline(user_state)
"""

from sei_ia.services.rlm.config import RLMConfig
from sei_ia.services.rlm.engine_repl import rlm_pipeline, should_use_rlm

__all__ = [
    "RLMConfig",
    "rlm_pipeline",
    "should_use_rlm",
]
