from unittest.mock import patch

import numpy as np
import pytest

from api_sei.services.hybrid import (
    hwmlt_process_recommendations_service,
    merge_recommenders,
    skipna_average,
)


class TestSkipnaAverage:
    def test_average_without_nan(self):
        result = skipna_average(np.array([[1.0, 2.0], [3.0, 4.0]]), [1, 1], axis=1)
        assert np.allclose(result, [1.5, 3.5])

    def test_average_ignores_nan(self):
        result = skipna_average(np.array([[1.0, np.nan], [3.0, 4.0]]), [1, 1], axis=1)
        assert np.allclose(result, [1.0, 3.5])

    def test_row_of_all_nan_returns_nan(self):
        result = skipna_average(np.array([[np.nan, np.nan]]), [1, 1], axis=1)
        assert np.isnan(result[0])


def _recommender(response):
    def _fn(id_value, fq, rows, normalized):  # noqa: ARG001
        return {"recommendation": response}

    return _fn


class TestMergeRecommenders:
    def test_outer_join_mean_aggregation(self):
        rec_a = _recommender([{"id": 1, "score": 1.0}, {"id": 2, "score": 3.0}])
        rec_b = _recommender([{"id": 1, "score": 5.0}, {"id": 3, "score": 1.0}])

        result = merge_recommenders(
            identifier=123,
            join_method="outer",
            rows=10,
            recommenders=[rec_a, rec_b],
            mean_weights=[1, 1],
            fq=None,
            depth=200,
        )

        by_id = {row["id"]: row["score"] for row in result["recommendation"]}
        assert by_id[1] == pytest.approx(3.0)
        assert by_id[2] == pytest.approx(3.0)
        assert by_id[3] == pytest.approx(1.0)

    def test_inner_join_keeps_only_intersection(self):
        rec_a = _recommender([{"id": 1, "score": 1.0}, {"id": 2, "score": 3.0}])
        rec_b = _recommender([{"id": 1, "score": 5.0}, {"id": 3, "score": 1.0}])

        result = merge_recommenders(
            identifier=123,
            join_method="inner",
            rows=10,
            recommenders=[rec_a, rec_b],
            mean_weights=[1, 1],
            fq=None,
            depth=200,
        )

        ids = [row["id"] for row in result["recommendation"]]
        assert ids == [1]

    def test_max_aggregation(self):
        rec_a = _recommender([{"id": 1, "score": 1.0}])
        rec_b = _recommender([{"id": 1, "score": 5.0}])

        result = merge_recommenders(
            identifier=123,
            join_method="outer",
            rows=10,
            recommenders=[rec_a, rec_b],
            mean_weights=[1, 1],
            fq=None,
            depth=200,
            agg_func="max",
        )

        assert result["recommendation"][0]["score"] == pytest.approx(5.0)

    def test_unknown_agg_func_raises(self):
        rec_a = _recommender([{"id": 1, "score": 1.0}])

        with pytest.raises(ValueError, match="Unknown agg_func"):
            merge_recommenders(
                identifier=123,
                join_method="outer",
                rows=10,
                recommenders=[rec_a],
                mean_weights=[1],
                fq=None,
                depth=200,
                agg_func="bogus",
            )

    def test_empty_recommender_response_is_skipped(self):
        rec_empty = _recommender([])
        rec_b = _recommender([{"id": 1, "score": 2.0}])

        result = merge_recommenders(
            identifier=123,
            join_method="outer",
            rows=10,
            recommenders=[rec_empty, rec_b],
            mean_weights=[1, 1],
            fq=None,
            depth=200,
        )

        assert result["recommendation"] == [{"id": 1, "score": 2.0}]

    def test_all_empty_recommender_responses_return_empty_recommendation(self):
        result = merge_recommenders(
            identifier=123,
            join_method="outer",
            rows=10,
            recommenders=[_recommender([]), _recommender([])],
            mean_weights=[1, 1],
            fq=None,
            depth=200,
        )

        assert result == {"recommendation": []}

    def test_vector_column_is_dropped(self):
        rec_a = _recommender([{"id": 1, "score": 1.0, "vector": [0.1, 0.2]}])

        result = merge_recommenders(
            identifier=123,
            join_method="outer",
            rows=10,
            recommenders=[rec_a],
            mean_weights=[1],
            fq=None,
            depth=200,
        )

        assert "vector" not in result["recommendation"][0]

    def test_fq_filters_results(self):
        rec_a = _recommender(
            [{"id": 1, "score": 1.0}, {"id": 2, "score": 3.0}, {"id": 3, "score": 2.0}]
        )

        result = merge_recommenders(
            identifier=123,
            join_method="outer",
            rows=10,
            recommenders=[rec_a],
            mean_weights=[1],
            fq=[1, 2],
            depth=200,
        )

        ids = {row["id"] for row in result["recommendation"]}
        assert ids == {1, 2}

    def test_inner_join_without_intersection_falls_back_to_outer(self):
        rec_a = _recommender([{"id": 1, "score": 1.0}])
        rec_b = _recommender([{"id": 2, "score": 5.0}])

        result = merge_recommenders(
            identifier=123,
            join_method="inner",
            rows=10,
            recommenders=[rec_a, rec_b],
            mean_weights=[1, 1],
            fq=None,
            depth=200,
        )

        ids = {row["id"] for row in result["recommendation"]}
        assert ids == {1, 2}

    def test_rows_limits_result_size(self):
        rec_a = _recommender([{"id": i, "score": float(i)} for i in range(5)])

        result = merge_recommenders(
            identifier=123,
            join_method="outer",
            rows=2,
            recommenders=[rec_a],
            mean_weights=[1],
            fq=None,
            depth=200,
        )

        assert len(result["recommendation"]) == 2


class TestHwmltProcessRecommendationsService:
    def test_calls_merge_recommenders_with_outer_join_and_max_agg(self):
        with patch("api_sei.services.hybrid.merge_recommenders") as mock_merge:
            mock_merge.return_value = {"recommendation": []}
            hwmlt_process_recommendations_service(id_value=422762, rows=10, fq=None)

        mock_merge.assert_called_once()
        _, kwargs = mock_merge.call_args
        args = mock_merge.call_args.args
        assert args[0] == 422762
        assert args[1] == "outer"
        assert args[2] == 10
        assert len(args[3]) == 2
        assert args[4] == [1, 1]
        assert kwargs["agg_func"] == "max"
