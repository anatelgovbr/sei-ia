"""Legacy app-api compatibility entrypoint backed by similaridade internals."""

from __future__ import annotations

import logging

from fastapi import Body, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api_sei.db_models.feedback import (
    FeedbackMLTDocumentRecommendation,
    FeedbackProcessWeightedMLTRecommendation,
)
from api_sei.pydantic_models.feedback import (
    Feedback,
    FeedbackResponse,
    current_timestamp,
)
from api_sei.services.feedback import (
    FeedbackStorage,
    feedback_example_jurisprudence,
    feedback_example_process,
)

logger = logging.getLogger(__name__)


class HealthCheck(BaseModel):
    """Legacy app-api health response."""

    status: str = "OK"
    timestamp: str = Field(default_factory=current_timestamp)


app = FastAPI(
    title="API de Feedback - SEI Similaridade",
    version="0.1.1",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return the legacy validation payload for feedback requests."""
    errors: list[str] = []
    for error in exc.errors():
        loc = error["loc"]
        if "body" in loc and "result" in loc:
            inner_index = loc[loc.index("result") + 1]
            field = loc[-1]
            errors.append(
                f"Erro no feedback: {inner_index + 1}. Campo faltante ou invalido: {field}"
            )

    logger.error("Validation error on request to %s: %s", request.url, errors)
    return JSONResponse(
        status_code=422,
        content={"detail": errors, "timestamp": current_timestamp()},
    )


@app.post("/process-recommenders/feedbacks", response_model=FeedbackResponse)
async def insert_feedback_process(
    feedbacks: list[Feedback] = Body(..., example=feedback_example_process),
) -> FeedbackResponse:
    """Persist process recommendation feedback using the legacy contract."""
    ids: list[int] = []
    storage = FeedbackStorage()
    for feedback in feedbacks:
        response = storage.save_feedback_db(
            feedback,
            FeedbackProcessWeightedMLTRecommendation,
        )
        ids.extend(response["added_ids"])

    return FeedbackResponse(message="Feedbacks salvos com sucesso.", ids=ids)


@app.post("/document-recommenders/feedbacks", response_model=FeedbackResponse)
async def insert_feedback_document(
    feedbacks: list[Feedback] = Body(..., example=feedback_example_jurisprudence),
) -> FeedbackResponse:
    """Persist document recommendation feedback using the legacy contract."""
    ids: list[int] = []
    storage = FeedbackStorage()
    for feedback in feedbacks:
        response = storage.save_feedback_db(
            feedback,
            FeedbackMLTDocumentRecommendation,
        )
        ids.extend(response["added_ids"])

    return FeedbackResponse(message="Feedbacks salvos com sucesso.", ids=ids)


@app.get(
    "/health",
    tags=["healthcheck"],
    summary="Perform a Health Check",
    response_description="Return HTTP Status Code 200 (OK)",
    status_code=status.HTTP_200_OK,
    response_model=HealthCheck,
)
def get_health() -> HealthCheck:
    """Legacy app-api health endpoint."""
    return HealthCheck(status="OK")
