# from datetime import datetime, timedelta
# from unittest.mock import Mock

# import jwt
# import pytest
# from passlib.hash import bcrypt

# from api_sei.envs import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY
# from api_sei.services.auth import (
#     authenticate_user,
#     create_access_token,
#     get_password_hash,
#     verify_password,
# )


# # Mock data and functions
# class MockUser:
#     def __init__(self, id_usuario, senha):
#         self.id_usuario = id_usuario
#         self.senha = senha

# mock_user = MockUser(id_usuario="testuser", senha=bcrypt.hash("testpassword"))  # hashed password for "testpassword"

# def mock_select_user(id_usuario: str):
#     if id_usuario == "testuser":
#         return mock_user
#     return None

# # Mocking select_user function from api_sei.repository.user
# @pytest.fixture(autouse=True)
# def mock_select_user_fixture(monkeypatch):
#     monkeypatch.setattr("api_sei.repository.user.select_user", mock_select_user)

# # Mocking db_client
# @pytest.fixture(autouse=True)
# def mock_db_client(monkeypatch):
#     mock_db_client = Mock()
#     mock_db_client.get = Mock(side_effect=lambda model, id: mock_user if id == "testuser" else None)
#     monkeypatch.setattr("api_sei.repository.user.db_client", mock_db_client)

# # Tests
# def test_verify_password():
#     plain_password = "testpassword"
#     hashed_password = mock_user.senha
#     assert verify_password(plain_password, hashed_password) is True

# def test_verify_password_incorrect():
#     plain_password = "wrongpassword"
#     hashed_password = mock_user.senha
#     assert verify_password(plain_password, hashed_password) is False

# def test_get_password_hash():
#     password = "newpassword"
#     hashed_password = get_password_hash(password)
#     assert bcrypt.verify(password, hashed_password) is True

# def test_authenticate_user():
#     id_usuario = "testuser"
#     senha = "testpassword"
#     user = authenticate_user(id_usuario, senha)
#     assert user is not False
#     assert user.id_usuario == "testuser"

# def test_authenticate_user_invalid_id():
#     id_usuario = "invaliduser"
#     senha = "testpassword"
#     user = authenticate_user(id_usuario, senha)
#     assert user is False

# def test_authenticate_user_invalid_password():
#     id_usuario = "testuser"
#     senha = "wrongpassword"
#     user = authenticate_user(id_usuario, senha)
#     assert user is False

# def test_create_access_token():
#     user = mock_user
#     token_data = {
#         "sub": user.id_usuario,
#         "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
#     }
#     token = jwt.encode(token_data, SECRET_KEY, algorithm="HS256")
#     access_token = create_access_token(user)
#     assert access_token["token"] == token
