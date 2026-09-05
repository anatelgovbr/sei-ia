"""Tests for FeedbackStorage (session persistence + error mapping)."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from api_sei.db_models.feedback import FeedbackProcessWeightedMLTRecommendation
from api_sei.pydantic_models.feedback import Feedback, FeedbackItem
from api_sei.services.feedback import FeedbackStorage


class FakeSession:
    """Stub SQLAlchemy session: assigns incrementing ids on flush, tracks calls."""

    def __init__(self, flush_error=None):
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self._next_id = 1
        self._flush_error = flush_error

    def add(self, row):
        self.added.append(row)

    def flush(self):
        if self._flush_error is not None:
            raise self._flush_error
        self.added[-1].id = self._next_id
        self._next_id += 1

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _feedback() -> Feedback:
    return Feedback(
        id_recommendation=1,
        result=[
            FeedbackItem(
                id_recommended=456,
                like_flag=1,
                sugesty="Sugestao 1",
                racional="Racional 1",
                ranking_user=1,
            ),
            FeedbackItem(
                id_recommended=789,
                like_flag=0,
                sugesty="Sugestao 2",
                racional="Racional 2",
                ranking_user=2,
            ),
        ],
    )


class TestSaveFeedbackDb:
    def test_persists_all_items_and_returns_added_ids(self):
        session = FakeSession()
        with patch("api_sei.services.feedback.app_db") as mock_app_db:
            mock_app_db.get_session.return_value = session
            result = FeedbackStorage().save_feedback_db(
                _feedback(), FeedbackProcessWeightedMLTRecommendation
            )

        assert result == {"status_code": 200, "added_ids": [1, 2]}
        assert session.committed is True
        assert session.closed is True
        assert len(session.added) == 2

    def test_attribute_error_rolls_back_and_raises_400(self):
        session = FakeSession(flush_error=AttributeError("missing attr"))
        with patch("api_sei.services.feedback.app_db") as mock_app_db:
            mock_app_db.get_session.return_value = session
            with pytest.raises(HTTPException) as excinfo:
                FeedbackStorage().save_feedback_db(
                    _feedback(), FeedbackProcessWeightedMLTRecommendation
                )

        assert excinfo.value.status_code == 400
        assert session.rolled_back is True
        assert session.closed is True

    def test_integrity_error_with_key_detail_rolls_back_and_raises_400(self):
        exc = IntegrityError(
            "stmt",
            {},
            Exception(
                'Key (id_recommendation)=(999) is not present in table '
                '"process_weighted_mlt_recommendation".'
            ),
        )
        session = FakeSession(flush_error=exc)
        with patch("api_sei.services.feedback.app_db") as mock_app_db:
            mock_app_db.get_session.return_value = session
            with pytest.raises(HTTPException) as excinfo:
                FeedbackStorage().save_feedback_db(
                    _feedback(), FeedbackProcessWeightedMLTRecommendation
                )

        assert excinfo.value.status_code == 400
        assert "id_recommendation" in excinfo.value.detail
        assert "999" in excinfo.value.detail
        assert session.rolled_back is True

    def test_integrity_error_without_match_uses_generic_detail(self):
        exc = IntegrityError("stmt", {}, Exception("some other integrity issue"))
        session = FakeSession(flush_error=exc)
        with patch("api_sei.services.feedback.app_db") as mock_app_db:
            mock_app_db.get_session.return_value = session
            with pytest.raises(HTTPException) as excinfo:
                FeedbackStorage().save_feedback_db(
                    _feedback(), FeedbackProcessWeightedMLTRecommendation
                )

        assert excinfo.value.status_code == 400
        assert "Erro de integridade" in excinfo.value.detail

    def test_sqlalchemy_error_rolls_back_and_raises_500(self):
        session = FakeSession(flush_error=SQLAlchemyError("db down"))
        with patch("api_sei.services.feedback.app_db") as mock_app_db:
            mock_app_db.get_session.return_value = session
            with pytest.raises(HTTPException) as excinfo:
                FeedbackStorage().save_feedback_db(
                    _feedback(), FeedbackProcessWeightedMLTRecommendation
                )

        assert excinfo.value.status_code == 500
        assert session.rolled_back is True
        assert session.closed is True
