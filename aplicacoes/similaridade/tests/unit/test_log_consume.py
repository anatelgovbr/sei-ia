import pytest
from unittest.mock import patch, MagicMock
from api_sei.services.log_consume import create_log
from api_sei.pydantic_models.log_consume import LogConsumeCreate
from api_sei.repository.log_consume import insert_log_consume

@pytest.fixture
def log_data():
    return {
        "status_code": 200,
        "id_protocol": [123, 456],
        "id_user": 1,
        "api_recomend_url": "http://example.com/recommend"
    }

@patch("api_sei.services.log_consume.insert_log_consume")
def test_create_log(mock_insert_log_consume, log_data):
    create_log(
        status_code=log_data["status_code"],
        id_protocol=log_data["id_protocol"],
        id_user=log_data["id_user"],
        api_recomend_url=log_data["api_recomend_url"]
    )
    
    log_consume_create = LogConsumeCreate(
        id_protocol=log_data["id_protocol"],
        id_user=log_data["id_user"],
        api_recomend_url=log_data["api_recomend_url"],
        status_code=log_data["status_code"]
    )
    
    mock_insert_log_consume.assert_called_once_with(log_consume=log_consume_create)

@patch("api_sei.repository.log_consume.db_client")
def test_insert_log_consume(mock_db_client, log_data):
    from api_sei.repository.log_consume import insert_log_consume
    from api_sei.db_models.models import LogConsume

    mock_db_client.add = MagicMock()

    log_consume = LogConsumeCreate(
        id_protocol=log_data["id_protocol"],
        id_user=log_data["id_user"],
        api_recomend_url=log_data["api_recomend_url"],
        status_code=log_data["status_code"]
    )

    insert_log_consume(log_consume=log_consume)

    new_log_consume = LogConsume(
        api_recomend_url=log_consume.api_recomend_url,
        status_code=log_consume.status_code,
        id_protocol=log_consume.id_protocol,
        id_user=log_consume.id_user
    )

    # Verifique se os atributos do objeto são iguais
    added_log = mock_db_client.add.call_args[0][0]
    assert added_log.api_recomend_url == new_log_consume.api_recomend_url
    assert added_log.status_code == new_log_consume.status_code
    assert added_log.id_protocol == new_log_consume.id_protocol
    assert added_log.id_user == new_log_consume.id_user

@patch("api_sei.repository.log_consume.db_client", None)
def test_insert_log_consume_no_db_client(log_data):
    from api_sei.repository.log_consume import insert_log_consume

    log_consume = LogConsumeCreate(
        id_protocol=log_data["id_protocol"],
        id_user=log_data["id_user"],
        api_recomend_url=log_data["api_recomend_url"],
        status_code=log_data["status_code"]
    )

    result = insert_log_consume(log_consume=log_consume)
    
    assert result is None

@patch("api_sei.repository.log_consume.logger")
@patch("api_sei.repository.log_consume.db_client")
def test_insert_log_consume_exception(mock_db_client, mock_logger, log_data):
    from api_sei.repository.log_consume import insert_log_consume
    from api_sei.db_models.models import LogConsume

    mock_db_client.add = MagicMock(side_effect=Exception("DB error"))

    log_consume = LogConsumeCreate(
        id_protocol=log_data["id_protocol"],
        id_user=log_data["id_user"],
        api_recomend_url=log_data["api_recomend_url"],
        status_code=log_data["status_code"]
    )

    with pytest.raises(Exception, match="DB error"):
        insert_log_consume(log_consume=log_consume)

    mock_logger.error.assert_called_once()
