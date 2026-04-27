from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status

from api_sei.resources.embed import get_similarity_embedding


# Mock do db_client
@pytest.fixture()
def mock_db_client() -> any:
    """Fixture that mocks the `db_client` object from `api_sei.resources.embed` module.

    Returns:
        MagicMock: A mock object that can be used to patch the `db_client` object.

    Yields:
        MagicMock: The mock object that was patched.

    Example:
        ```
        def test_my_function(mock_db_client):
            # Test code that uses mock_db_client
            ...
        ```
    """
    with patch("api_sei.resources.embed.db_client") as mock:
        yield mock

def test_get_similarity_embedding_valid_input(mock_db_client: MagicMock) -> None:
    """Test the `get_similarity_embedding` function with valid input.

    This function tests the `get_similarity_embedding` function with valid input.
    It mocks the `execute_query` method of the `mock_db_client` object to return
    a list of dictionaries representing the similarity scores. The function then
    calls the `get_similarity_embedding` function with the input parameters
    `1`, `[1, 2]`, and `2`. The expected result is a dictionary containing a
    list of dictionaries representing the similarity scores.

    Parameters:
        mock_db_client (MagicMock): The mock object for the `db_client` object.

    Returns:
        None

    Raises:
        AssertionError: If the result of the `get_similarity_embedding` function
        does not match the expected result.

    Example:
        ```
        def test_get_similarity_embedding_valid_input(mock_db_client):
            mock_db_client.execute_query.return_value = [
                {"id": 1, "score": 0.95},
                {"id": 2, "score": 0.90}
            ]

            result = get_similarity_embedding(1, [1, 2], 2)
            assert result == {
                "recommendation": [
                    {"id": 1, "score": 0.95},
                    {"id": 2, "score": 0.90}
                ]
            }
        ```
    """
    mock_db_client.execute_query.return_value = [
        {"id": 1, "score": 0.95},
        {"id": 2, "score": 0.90}
    ]

    result = get_similarity_embedding(1, [1, 2], 2)
    assert result == {
        "recommendation": [
            {"id": 1, "score": 0.95},
            {"id": 2, "score": 0.90}
        ]
    }

def test_get_similarity_embedding_no_list_id_processos(mock_db_client: MagicMock) -> None:
    """Test case for the `get_similarity_embedding` function when `list_id_processos` is an empty list.

    This test case verifies that the function returns the expected result when `list_id_processos` is an empty list.
    It mocks the `execute_query` method of the `mock_db_client` object to return a list of dictionaries representing
    the similarity scores. The function then calls the `get_similarity_embedding` function with the input parameters
    `1`, an empty list, and `2`. The expected result is a dictionary containing a list of dictionaries representing
    the similarity scores.

    Parameters:
        mock_db_client (MagicMock): The mock object for the `db_client` object.

    Returns:
        None

    Raises:
        AssertionError: If the result of the `get_similarity_embedding` function does not match the expected result.

    Example:
        ```
        def test_get_similarity_embedding_no_list_id_processos(mock_db_client):
            mock_db_client.execute_query.return_value = [
                {"id": 1, "score": 0.95},
                {"id": 2, "score": 0.90}
            ]

            result = get_similarity_embedding(1, [], 2)
            assert result == {
                "recommendation": [
                    {"id": 1, "score": 0.95},
                    {"id": 2, "score": 0.90}
                ]
            }
        ```
    """
    mock_db_client.execute_query.return_value = [
        {"id": 1, "score": 0.95},
        {"id": 2, "score": 0.90}
    ]

    result = get_similarity_embedding(1, [], 2)
    assert result == {  
        "recommendation": [
            {"id": 1, "score": 0.95},
            {"id": 2, "score": 0.90}
        ]
    }

def test_get_similarity_embedding_invalid_list_id_processos() -> None:
    """Test case for the `get_similarity_embedding` function when an invalid list of process IDs is provided.

    This test case verifies that the function raises a `ValueError` when the `list_id_processos` parameter is not a list.
    The expected error message is "list_id_processos nao pode ser vazio".

    Parameters:
        None

    Returns:
        None
    """
    with pytest.raises(ValueError) as excinfo:
        get_similarity_embedding(1, "not a list", 2)
    assert str(excinfo.value) == "list_id_processos nao pode ser vazio"

def test_get_similarity_embedding_invalid_id_processo() -> None:
    """Test case for the `get_similarity_embedding` function when an invalid `id_processo` is provided.

    This test case verifies that the function raises a `ValueError` when the `id_processo` parameter is not an integer.
    The expected error message is "id_processo deve ser um inteiro".

    Parameters:
        None

    Returns:
        None
    """
    with pytest.raises(ValueError) as excinfo:
        get_similarity_embedding("not an int", [1, 2], 2)
    assert str(excinfo.value) == "id_processo deve ser um inteiro"

def test_get_similarity_embedding_invalid_rows() -> None:
    """Test case for the `get_similarity_embedding` function when an invalid `rows` is provided.

    This test case verifies that the function raises a `ValueError` when the `rows` parameter is not an integer.
    The expected error message is "rows deve ser um inteiro positivo maior que zero".

    Parameters:
        None

    Returns:
        None
    """
    with pytest.raises(ValueError) as excinfo:
        get_similarity_embedding(1, [1, 2], "not an int")
    assert str(excinfo.value) == "rows deve ser um inteiro positivo maior que zero"

def test_get_similarity_embedding_db_exception(mock_db_client: MagicMock) -> None:
    """Test case for the `get_similarity_embedding` function when there is a database error.

    This test case verifies that the function raises an `HTTPException` with status code 500 and a specific error
    message when there is a database error.

    Parameters:
        mock_db_client (Mock): A mock object of the database client.

    Returns:
        None
    """
    mock_db_client.execute_query.side_effect = Exception("DB error")
    
    with pytest.raises(HTTPException) as excinfo:
        get_similarity_embedding(1, [1, 2], 2)
    assert excinfo.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert str(excinfo.value.detail) == "Erro de consulta no banco: DB error"
