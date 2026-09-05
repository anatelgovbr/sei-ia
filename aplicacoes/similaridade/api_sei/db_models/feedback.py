"""ORM models for recommendation feedback."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from api_sei.db_models.models import Base


class FeedbackMLTDocumentRecommendation(Base):
    """Feedback rows associated with document recommendations."""

    __tablename__ = "feedback_jurisprudence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_recommendation = Column(
        BigInteger,
        ForeignKey("document_mlt_recommendation.id_recommendation"),
        nullable=False,
    )
    id_recommended = Column(Integer, nullable=False)
    like_flag = Column(Integer, nullable=False)
    ranking_user = Column(Integer, nullable=False)
    sugesty = Column(String)
    racional = Column(String)
    created_at = Column(DateTime(timezone=True), default=func.now())


class FeedbackProcessWeightedMLTRecommendation(Base):
    """Feedback rows associated with process recommendations."""

    __tablename__ = "feedback_process_weighted_mlt_recommendation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_recommendation = Column(
        Integer,
        ForeignKey("process_weighted_mlt_recommendation.id_recommendation"),
        nullable=False,
    )
    id_recommended = Column(Integer, nullable=False)
    like_flag = Column(Integer, nullable=False)
    ranking_user = Column(Integer, nullable=False)
    sugesty = Column(String)
    racional = Column(String)
    created_at = Column(DateTime(timezone=True), default=func.now())
