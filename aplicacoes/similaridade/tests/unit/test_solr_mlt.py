"""tests solr mlt."""
from unittest.mock import Mock

import pytest

from api_sei.db_models.solr_mlt import SolrMlt, process_mlt_qf
from api_sei.pydantic_models.solr_mlt import SolrMltConfigModel


@pytest.fixture()
def mock_config() -> SolrMltConfigModel:
    """Creates a mock instance of the SolrMltConfigModel class with predefined values for the id_field, extra_fields.

    Returns:
        Mock: A mock instance of the SolrMltConfigModel class.
    """
    config = Mock(spec=SolrMltConfigModel)
    config.id_field = "doc_id"
    config.extra_fields = ["author", "title"]
    config.fields = ["text", "content"]
    config.url = "http://example.com/solr"

    return config

@pytest.fixture()
def solr_mlt(mock_config: SolrMltConfigModel) -> SolrMlt:
    """Fixture that creates an instance of the SolrMlt class with the provided mock_config.

    :param mock_config: A mock instance of the SolrMltConfigModel class.
    :type mock_config: SolrMltConfigModel
    :return: An instance of the SolrMlt class.
    :rtype: SolrMlt
    """
    return SolrMlt(config=mock_config)

def test_build_fl(solr_mlt: SolrMlt) -> None:
    """Test the _build_fl method of the SolrMlt class.

    This test verifies that the _build_fl method correctly builds the field list
    for the Solr More Like This (MLT) query. It checks if the result matches the
    expected field list.

    Parameters:
    - solr_mlt (SolrMlt): An instance of the SolrMlt class.

    Returns:
    - None

    Raises:
    - AssertionError: If the result does not match the expected field list.
    """
    result = solr_mlt._build_fl()
    expected_result = "doc_id,score,author,title"
    assert result == expected_result, "The _build_fl method should return the correct field list"  # noqa: S101

def test_build_initial_query(solr_mlt: SolrMlt) -> None:
    """Test the _build_initial_query method of the SolrMlt class.

    This test verifies that the _build_initial_query method correctly builds the initial query URL
    for retrieving more like this (MLT) documents from Solr. It checks if the built URL matches the
    expected result.

    Parameters:
    - solr_mlt (SolrMlt): An instance of the SolrMlt class.

    Returns:
    - None

    Raises:
    - AssertionError: If the built URL does not match the expected result.

    Note:
    - The test assumes that the SolrMlt class has the following attributes:
        - config (SolrMltConfigModel): The configuration object for the SolrMlt class.
        - _build_fl (function): A private method that builds the field list for the MLT query.

    - The test assumes that the SolrMltConfigModel class has the following attributes:
        - id_field (str): The name of the field used as the document ID in Solr.
        - fields (List[str]): The list of fields to retrieve in the MLT query.
        - url (str): The base URL of the Solr server.

    - The test assumes that the SolrMlt class has the following methods:
        - _build_fl (function): A private method that builds the field list for the MLT query.

    - The test assumes that the expected result is a string representing the URL of the MLT query.
    """
    solr_doc_id = "123"
    result = solr_mlt._build_initial_query(solr_doc_id)
    expected_result = "http://example.com/solr/mlt?q=doc_id:123&fl=doc_id,score,author,title&mlt.fl=text,content"
    assert result == expected_result, "The _build_initial_query should build the correct query URL"  # noqa: S101


@pytest.mark.parametrize(("input_str", "expected_output"), [
    ("title(text)", "titletext"),
    ("(content)", "content"),
    ("title+content", "title content"),
    ("name+^content+age", "name ^content age"),
    ("+title(^content)", " title^content"),
    ("^name+(content)", "^name content"),
    ("^+", "^"),
    ("()", ""),
    ("+()", " "),
])
def test_process_mlt_qf(input_str: str, expected_output: str) -> None:
    """Test the `process_mlt_qf` function with different input strings and expected output.

    Parameters:
        input_str (str): The input string to be processed.
        expected_output (str): The expected output of the `process_mlt_qf` function.

    Returns:
        None

    This function uses the `pytest.mark.parametrize` decorator to run the test multiple times with different input
    and expected output values. It asserts that the output of the `process_mlt_qf` function matches the expected output.
    """
    assert process_mlt_qf(input_str) == expected_output,f"Expected {expected_output}, but {process_mlt_qf(input_str)}"  # noqa: S101

