"""Tests for the legacy feedback router endpoints."""

from unittest.mock import patch

import pytest

from api_sei.db_models.feedback import FeedbackMLTDocumentRecommendation
from api_sei.pydantic_models.feedback import Feedback, FeedbackItem
from api_sei.routers.feedback import insert_feedback_document, insert_feedback_process


def _feedback(id_recommendation: int) -> Feedback:
    return Feedback(
        id_recommendation=id_recommendation,
        result=[
            FeedbackItem(
                id_recommended=456,
                like_flag=1,
                sugesty="Sugestao 1",
                racional="Racional 1",
                ranking_user=1,
            )
        ],
    )


class TestInsertFeedbackProcess:
    @pytest.mark.asyncio
    async def test_persists_each_feedback_and_aggregates_ids(self):
        feedbacks = [_feedback(1), _feedback(2)]
        with patch(
            "api_sei.routers.feedback.FeedbackStorage"
        ) as mock_storage_cls:
            mock_storage_cls.return_value.save_feedback_db.side_effect = [
                {"status_code": 200, "added_ids": [10]},
                {"status_code": 200, "added_ids": [11]},
            ]
            response = await insert_feedback_process(feedbacks)

        assert response.ids == [10, 11]
        assert response.message == "Feedbacks salvos com sucesso."
        assert mock_storage_cls.return_value.save_feedback_db.call_count == 2


class TestInsertFeedbackDocument:
    @pytest.mark.asyncio
    async def test_persists_each_feedback_and_aggregates_ids(self):
        feedbacks = [_feedback(1)]
        with patch(
            "api_sei.routers.feedback.FeedbackStorage"
        ) as mock_storage_cls:
            mock_storage_cls.return_value.save_feedback_db.return_value = {
                "status_code": 200,
                "added_ids": [42],
            }
            response = await insert_feedback_document(feedbacks)

        assert response.ids == [42]
        assert response.message == "Feedbacks salvos com sucesso."
        args, _kwargs = mock_storage_cls.return_value.save_feedback_db.call_args
        assert args[1] is FeedbackMLTDocumentRecommendation
