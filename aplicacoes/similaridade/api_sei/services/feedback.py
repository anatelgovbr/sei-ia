"""Service layer for feedback persistence inside similaridade."""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from api_sei.db_models.db_instances import app_db
from api_sei.db_models.feedback import (
    FeedbackMLTDocumentRecommendation,
    FeedbackProcessWeightedMLTRecommendation,
)
from api_sei.pydantic_models.feedback import Feedback

logger = logging.getLogger(__name__)

feedback_example_process = [
    {
        "id_recommendation": 1,
        "result": [
            {
                "id_recommended": 456,
                "like_flag": 1,
                "ranking_user": 1,
                "sugesty": "Sugestao 1",
                "racional": "Racional 1",
            },
            {
                "id_recommended": 789,
                "like_flag": 0,
                "ranking_user": 2,
                "sugesty": "Sugestao 2",
                "racional": "Racional 2",
            },
        ],
    }
]

feedback_example_jurisprudence = [
    {
        "id_recommendation": 1,
        "result": [
            {
                "id_recommended": 456,
                "like_flag": 1,
                "ranking_user": 1,
                "sugesty": "Sugestao 1",
                "racional": "Racional 1",
            },
            {
                "id_recommended": 789,
                "like_flag": 0,
                "ranking_user": 2,
                "sugesty": "Sugestao 2",
                "racional": "Racional 2",
            },
        ],
    }
]


class FeedbackStorage:
    """Persist legacy feedback payloads in the similarity database."""

    def save_feedback_db(
        self, feedback: Feedback, table_feedback: Any
    ) -> dict[str, Any]:
        """Persist one feedback payload into the given ORM table."""
        session = app_db.get_session()
        try:
            added_ids: list[int] = []
            for feedback_item in feedback.result:
                row = table_feedback(
                    id_recommendation=feedback.id_recommendation,
                    id_recommended=feedback_item.id_recommended,
                    like_flag=feedback_item.like_flag,
                    ranking_user=feedback_item.ranking_user,
                    sugesty=feedback_item.sugesty,
                    racional=feedback_item.racional,
                )
                session.add(row)
                session.flush()
                added_ids.append(row.id)

            session.commit()
            logger.info("Feedback salvo com sucesso.")
            return {"status_code": status.HTTP_200_OK, "added_ids": added_ids}
        except AttributeError as exc:
            session.rollback()
            logger.exception("Erro de atributo ao salvar feedback.")
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except IntegrityError as exc:
            session.rollback()
            match = re.search(r"Key \((\w+)\)=\((\d+)\)", str(exc))
            detail = "Erro de integridade. Confira se o campo id_recommendation existe."
            if match:
                detail = (
                    f"{detail} O campo {match.group(1)} possui valor invalido: "
                    f"{match.group(2)}."
                )
            logger.exception("Erro de integridade ao salvar feedback.")
            raise HTTPException(status_code=400, detail=detail) from exc
        except SQLAlchemyError as exc:
            session.rollback()
            logger.exception("Erro interno ao salvar feedback.")
            raise HTTPException(
                status_code=500,
                detail=f"Erro interno no servidor. Detail: {exc}",
            ) from exc
        finally:
            session.close()


__all__ = [
    "FeedbackMLTDocumentRecommendation",
    "FeedbackProcessWeightedMLTRecommendation",
    "FeedbackStorage",
    "feedback_example_jurisprudence",
    "feedback_example_process",
]
