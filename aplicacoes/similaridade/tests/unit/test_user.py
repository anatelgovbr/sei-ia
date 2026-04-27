# import pytest
# from unittest.mock import patch, MagicMock
# from api_sei.services.user import create_user, get_user
# from api_sei.exception_handling.exceptions import SQLAlchemyInsertError
# from api_sei.pydantic_models.user import UserNotFoundException
# from fastapi import HTTPException

# # Testes para create_user
# @patch('api_sei.services.user.insert_user')
# @patch('api_sei.services.user.get_password_hash')
# def test_create_user_success(mock_get_password_hash, mock_insert_user):
#     # Configurar os mocks
#     mock_get_password_hash.return_value = 'hashed_password'
#     mock_insert_user.return_value = 'user_inserted'

#     # Chamar a função
#     result = create_user(nome='Test User', id_usuario='user123', senha='password123')

#     # Verificar resultados
#     assert result == 'user_inserted'
#     mock_get_password_hash.assert_called_once_with('password123')
#     mock_insert_user.assert_called_once()

# @patch('api_sei.services.user.insert_user')
# @patch('api_sei.services.user.get_password_hash')
# def test_create_user_sqlalchemy_error(mock_get_password_hash, mock_insert_user):
#     # Configurar os mocks
#     mock_get_password_hash.return_value = 'hashed_password'
#     mock_insert_user.side_effect = SQLAlchemyInsertError('Insert failed')

#     # Chamar a função e verificar a exceção
#     with pytest.raises(HTTPException) as exc_info:
#         create_user(nome='Test User', id_usuario='user123', senha='password123')

#     assert exc_info.value.status_code == 422
#     assert str(exc_info.value.detail) == 'Insert failed'
#     mock_get_password_hash.assert_called_once_with('password123')
#     mock_insert_user.assert_called_once()

# # Testes para get_user
# @patch('api_sei.services.user.select_user')
# def test_get_user_success(mock_select_user):
#     # Configurar o mock
#     mock_select_user.return_value = MagicMock()

#     # Chamar a função
#     result = get_user(id_usuario='user123')

#     # Verificar resultados
#     assert result == mock_select_user.return_value
#     mock_select_user.assert_called_once_with(id_usuario='user123')

# @patch('api_sei.services.user.select_user')
# def test_get_user_not_found(mock_select_user):
#     # Configurar o mock
#     mock_select_user.return_value = None

#     # Chamar a função e verificar a exceção
#     with pytest.raises(UserNotFoundException):
#         get_user(id_usuario='user123')

#     mock_select_user.assert_called_once_with(id_usuario='user123')
