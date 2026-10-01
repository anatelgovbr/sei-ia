import unittest

from pydantic import ValidationError

from api_sei.pydantic_models.feedback import Feedback, FeedbackItem, FeedbackResponse


class TestFeedbackItem(unittest.TestCase):
    def test_valid_feedback_item(self):
        item = FeedbackItem(
            id_recommended=1,
            like_flag=1,
            sugesty="melhorar busca",
            racional="pouco relevante",
            ranking_user=2,
        )
        self.assertEqual(item.id_recommended, 1)
        self.assertEqual(item.ranking_user, 2)

    def test_missing_required_field_raises(self):
        with self.assertRaises(ValidationError):
            FeedbackItem(id_recommended=1, like_flag=1, sugesty="x", racional="y")


class TestFeedback(unittest.TestCase):
    def test_feedback_with_multiple_items(self):
        feedback = Feedback(
            id_recommendation=10,
            result=[
                {
                    "id_recommended": 1,
                    "like_flag": 1,
                    "sugesty": "",
                    "racional": "",
                    "ranking_user": 1,
                },
                {
                    "id_recommended": 2,
                    "like_flag": 0,
                    "sugesty": "",
                    "racional": "",
                    "ranking_user": 2,
                },
            ],
        )
        self.assertEqual(feedback.id_recommendation, 10)
        self.assertEqual(len(feedback.result), 2)
        self.assertIsInstance(feedback.result[0], FeedbackItem)


class TestFeedbackResponse(unittest.TestCase):
    def test_default_timestamp_is_generated(self):
        response = FeedbackResponse(message="ok", ids=[1, 2, 3])
        self.assertEqual(response.message, "ok")
        self.assertEqual(response.ids, [1, 2, 3])
        # formato "YYYY-MM-DD HH:MM:SS"
        self.assertRegex(response.timestamp, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    def test_explicit_timestamp_is_kept(self):
        response = FeedbackResponse(message="ok", ids=[], timestamp="2024-01-01 00:00:00")
        self.assertEqual(response.timestamp, "2024-01-01 00:00:00")
