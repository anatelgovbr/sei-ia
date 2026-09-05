import unittest

from api_sei.db_models.feedback import (
    FeedbackMLTDocumentRecommendation,
    FeedbackProcessWeightedMLTRecommendation,
)


class TestFeedbackMLTDocumentRecommendation(unittest.TestCase):
    def test_tablename(self):
        self.assertEqual(
            FeedbackMLTDocumentRecommendation.__tablename__, "feedback_jurisprudence"
        )

    def test_instantiation_sets_attributes(self):
        row = FeedbackMLTDocumentRecommendation(
            id_recommendation=1,
            id_recommended=2,
            like_flag=1,
            ranking_user=3,
            sugesty="melhor",
            racional="justificativa",
        )
        self.assertEqual(row.id_recommendation, 1)
        self.assertEqual(row.id_recommended, 2)
        self.assertEqual(row.like_flag, 1)
        self.assertEqual(row.ranking_user, 3)


class TestFeedbackProcessWeightedMLTRecommendation(unittest.TestCase):
    def test_tablename(self):
        self.assertEqual(
            FeedbackProcessWeightedMLTRecommendation.__tablename__,
            "feedback_process_weighted_mlt_recommendation",
        )

    def test_instantiation_sets_attributes(self):
        row = FeedbackProcessWeightedMLTRecommendation(
            id_recommendation=5,
            id_recommended=6,
            like_flag=0,
            ranking_user=1,
            sugesty="",
            racional="",
        )
        self.assertEqual(row.id_recommendation, 5)
        self.assertEqual(row.id_recommended, 6)
        self.assertEqual(row.like_flag, 0)
