"""Legacy feedback endpoints now hosted inside similaridade."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body

from api_sei.db_models.feedback import (
    FeedbackMLTDocumentRecommendation,
    FeedbackProcessWeightedMLTRecommendation,
)
from api_sei.pydantic_models.feedback import Feedback, FeedbackResponse
from api_sei.services.feedback import (
    FeedbackStorage,
    feedback_example_jurisprudence,
    feedback_example_process,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/process-recommenders/feedbacks",
    tags=["feedback"],
    response_model=FeedbackResponse,
    summary="Persist process recommendation feedback",
)
async def insert_feedback_process(
    feedbacks: list[Feedback] = Body(..., example=feedback_example_process),
) -> FeedbackResponse:
    """Persist process recommendation feedback keeping the legacy route."""
    ids: list[int] = []
    storage = FeedbackStorage()
    for feedback in feedbacks:
        response = storage.save_feedback_db(
            feedback,
            FeedbackProcessWeightedMLTRecommendation,
        )
        ids.extend(response["added_ids"])

    logger.info("Feedback de processo salvo. ids=%s", ids)
    return FeedbackResponse(message="Feedbacks salvos com sucesso.", ids=ids)


@router.post(
    "/document-recommenders/feedbacks",
    tags=["feedback"],
    response_model=FeedbackResponse,
    summary="Persist document recommendation feedback",
)
async def insert_feedback_document(
    feedbacks: list[Feedback] = Body(..., example=feedback_example_jurisprudence),
) -> FeedbackResponse:
    """Persist document recommendation feedback keeping the legacy route."""
    ids: list[int] = []
    storage = FeedbackStorage()
    for feedback in feedbacks:
        response = storage.save_feedback_db(
            feedback,
            FeedbackMLTDocumentRecommendation,
        )
        ids.extend(response["added_ids"])

    logger.info("Feedback de documento salvo. ids=%s", ids)
    return FeedbackResponse(message="Feedbacks salvos com sucesso.", ids=ids)
