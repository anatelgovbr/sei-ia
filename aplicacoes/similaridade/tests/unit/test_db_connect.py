# tests/test_db_connect.py

from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# from api_sei.db_models.db_connect import DBConnector
from db_connection.db_connection import DBConnector
from api_sei.envs import CONN_STRING_APP_DB


# Mocks
@pytest.fixture()
def mock_engine():
    with patch('api_sei.db_models.db_connect.create_engine') as mock_create_engine:
        mock_engine_instance = MagicMock()
        mock_create_engine.return_value = mock_engine_instance
        yield mock_engine_instance

@pytest.fixture()
def mock_session():
    with patch('api_sei.db_models.db_connect.sessionmaker') as mock_sessionmaker:
        mock_session_instance = MagicMock()
        mock_sessionmaker.return_value = MagicMock(return_value=mock_session_instance)
        yield mock_session_instance

@pytest.fixture()
def db_connector(mock_engine, mock_session):
    return DBConnector(CONN_STRING_APP_DB)

# Testes
def test_connection_success(db_connector, mock_session):
    db_connector.test_connection()
    assert any(call.args[0].text == 'SELECT 1' for call in mock_session.execute.mock_calls)
    assert mock_session.commit.call_count >= 1

def test_connection_failure(mock_engine, mock_session):
    mock_session.execute.side_effect = SQLAlchemyError("Connection Error")
    with pytest.raises(SQLAlchemyError):
        DBConnector(CONN_STRING_APP_DB)

def test_execute_query_success(db_connector, mock_session):
    mock_session.execute.return_value.fetchall.return_value = [('result',)]
    result = db_connector.execute_query("SELECT * FROM table")
    assert result == [('result',)]
    assert any(call.args[0].text == 'SELECT * FROM table' for call in mock_session.execute.mock_calls)

def test_execute_query_failure(db_connector, mock_session):
    mock_session.execute.side_effect = SQLAlchemyError("Query Error")
    with pytest.raises(SQLAlchemyError):
        db_connector.execute_query("SELECT * FROM table")

def test_execute_insert_success(db_connector, mock_session):
    result = db_connector.execute_insert("INSERT INTO table VALUES ('value')")
    assert result is True
    assert mock_session.commit.call_count >= 1

def test_execute_insert_failure(db_connector, mock_session):
    mock_session.execute.side_effect = SQLAlchemyError("Insert Error")
    with pytest.raises(SQLAlchemyError):
        db_connector.execute_insert("INSERT INTO table VALUES ('value')")

def test_add_object_success(db_connector, mock_session):
    mock_obj = MagicMock()
    result = db_connector.add(mock_obj)
    assert result is True
    mock_session.add.assert_called_once_with(mock_obj)
    assert mock_session.commit.call_count >= 1

def test_get_object_success(db_connector, mock_session):
    mock_model = MagicMock()
    mock_session.query.return_value.get.return_value = 'object'
    result = db_connector.get(mock_model, 1)
    assert result == 'object'
    mock_session.query.assert_called_once_with(mock_model)
    mock_session.query.return_value.get.assert_called_once_with(1)

def test_get_dataframe_success(db_connector, mock_session):
    mock_session.execute.return_value.fetchall.return_value = [MagicMock(_asdict=lambda: {'col': 'value'})]
    result = db_connector.get_dataframe("SELECT * FROM table")
    assert not result.empty
    assert 'col' in result.columns

def test_update_connection_counts(db_connector, mock_engine):
    db_connector.update_connection_counts()
    mock_engine.connect.assert_called_once()
    conn = mock_engine.connect.return_value.__enter__.return_value
    conn.execute.assert_called_once_with("SELECT 1")
