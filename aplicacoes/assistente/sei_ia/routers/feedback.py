"""Modulo de feedback."""

import inspect
import logging

from fastapi import APIRouter

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import FeedbackRequest
from sei_ia.services.persistance.feedback import persist_feedback

setup_logging()

router = APIRouter()

logger = logging.getLogger(__name__)


@router.post(
    "/feedback/feedback",
    tags=["feedback"],
    summary="feedback para resposta dos modelos.",
)
async def save_feedback(request: FeedbackRequest) -> int:
    """Salva o feedback do usuário sobre uma resposta do modelo.

    Esta função recebe um objeto FeedbackRequest contendo a avaliação do
    usuário e persiste essa informação no banco de dados para análise
    posterior.

    Args:
        request (FeedbackRequest): Objeto contendo os detalhes do feedback:
            - id_mensagem: Identificador único da mensagem avaliada
            - stars: Avaliação em estrelas (1-5)
            - comment: Comentário opcional do usuário

    Returns:
        int: ID do feedback salvo no banco de dados

    Raises:
        SQLAlchemyError: Em caso de falha na conexão com o banco de dados
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug(f">> {inspect.currentframe().f_code.co_name}: feedback: {request}")
    return await persist_feedback(
        id_mensagem=request.id_mensagem, stars=request.stars, comment=request.comment
    )
