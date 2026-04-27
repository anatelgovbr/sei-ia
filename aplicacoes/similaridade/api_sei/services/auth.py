# from datetime import datetime, timedelta

from fastapi.security import OAuth2PasswordBearer

# import jwt
from passlib.context import CryptContext

# from api_sei.envs import SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES
# from api_sei.pydantic_models.user import User
# from api_sei.repository.user import select_user

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


# def authenticate_user(id_usuario: str, senha: str):
#     user = select_user(id_usuario=id_usuario)
#     if not user:
#         return False
#     if not verify_password(senha, user.senha):
#         return False
#     return user


# def create_access_token(user: User):
#     token_data = {
#         "sub": user.id_usuario,  # Subject (the user to whom the token belongs)
#         "exp": datetime.utcnow()
#         + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),  # Expiration time
#     }
#     token = jwt.encode(token_data, SECRET_KEY, algorithm="HS256")
#     return {"token": token}
