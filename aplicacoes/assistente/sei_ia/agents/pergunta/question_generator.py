"""Gerador de múltiplas perguntas para RAG Enhanced."""

import inspect
import logging

from sei_ia.agents.prompts.question_generation import GENERATE_QUESTIONS_PROMPT
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.exceptions.http_exceptions import HTTPException500
from sei_ia.services.llm_models.get_model import get_llm_model

setup_logging()
logger = logging.getLogger(__name__)


def generate_multiple_questions(user_state: UserState) -> list[str]:
    """
    Gera N perguntas relevantes usando o modelo LLM já selecionado.

    Args:
        user_state: Estado com a pergunta original e configurações

    Returns:
        Lista com N+1 perguntas (original + N geradas)
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    logger.debug("Gerando múltiplas perguntas para RAG enhanced")
    try:
        model_type = user_state.get("model_type", "gpt-4.1")
        logger.debug(f"Usando modelo {model_type} para gerar perguntas")

        llm = get_llm_model(
            model_type=model_type, temperature=0.3
        )  # Baixa para gerar perguntas consistentes

        n_questions = getattr(settings, "N_QUESTIONS", 3)
        prompt = GENERATE_QUESTIONS_PROMPT.format(
            user_question=user_state["user_request"], n_questions=n_questions
        )

        response = llm.invoke(prompt).content

        # Parsear resposta (uma pergunta por linha)
        questions = [q.strip() for q in response.split("\n") if q.strip()]

        # Adicionar a pergunta original como primeira
        questions.insert(0, user_state["user_request"])

        return questions

    except Exception as e:
        raise HTTPException500(
            detail=f"Erro ao gerar perguntas: {e}", exc_info=True
        ) from e
