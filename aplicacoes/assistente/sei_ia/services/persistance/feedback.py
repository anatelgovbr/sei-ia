"""Modulo de persistencia de feedbacks."""

import inspect
import logging

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.database.db_instances import app_db_instance
from sei_ia.data.database.db_models.feedback import Feedback

setup_logging()
logger = logging.getLogger(__name__)


async def persist_feedback(id_mensagem: int, stars: int, comment: str) -> int:
    """Persistencia de feedbacks.

    Args:
        id_mensagem (int): id da mensagem
        stars (int): estrelas must be between 1 and 5
        comment (str): comentario do feedback

    Returns:
        int: numero do feedback
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    feedback = Feedback(id_mensagem=id_mensagem, stars=stars, comment=comment)

    result = await app_db_instance.add_native_async(feedback, returns_obj=True)
    return result.id
