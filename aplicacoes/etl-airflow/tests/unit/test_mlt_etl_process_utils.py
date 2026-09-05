"""Tests for jobs/dags/dag_objects/mlt_etl_process/utils.py."""

from jobs.dags.dag_objects.mlt_etl_process.utils import split_set


def test_distributes_round_robin():
    result = split_set([1, 2, 3, 4, 5], 2)
    assert len(result) == 2
    assert sorted(result[0] + result[1]) == [1, 2, 3, 4, 5]


def test_more_slots_than_items():
    assert split_set([1], 3) == [[1], [], []]


def test_zero_slots_returns_empty_list():
    assert split_set([1, 2], 0) == []
