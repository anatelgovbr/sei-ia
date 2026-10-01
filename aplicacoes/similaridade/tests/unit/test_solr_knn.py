import pytest

from api_sei.db_models.solr_knn import build_filter


@pytest.mark.parametrize(("id_field", "pfq", "nfq", "expected"), [
    ("doc_id", ["1", "2"], ["3"], "doc_id:( 1 2 ) AND -doc_id:( 3 )"),
    ("doc_id", ["1", "2"], None, "doc_id:( 1 2 )"),
    ("doc_id", None, ["3"], "doc_id:* AND -doc_id:( 3 )"),
    ("doc_id", None, None, "doc_id:*"),
])
def test_build_filter(id_field: str, pfq: list, nfq: list, expected: str) -> None:
    """Test the build_filter function with different parameter combinations.

    This function uses pytest.mark.parametrize to test the build_filter function with different combinations of input parameters.
    It verifies that the function returns the correct filter string based on the input parameters.

    Args:
        id_field (str): The field name for the document IDs.
        pfq (list): A list of positive filter queries.
        nfq (list): A list of negative filter queries.
        expected (str): The expected filter string.

    Returns:
        None

    Raises:
        AssertionError: If the filter string returned by build_filter does not match the expected filter string.
    """
    assert build_filter(id_field, pfq, nfq) == expected, "The build_filter function should return the correct string"  # noqa: S101
