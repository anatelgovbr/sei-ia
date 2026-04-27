# from api_sei.exception_handling.exceptions import SQLAlchemyInsertError
# from api_sei.pydantic_models.user import User, UserNotFoundException
# from api_sei.repository.user import insert_user, select_user
# from api_sei.services.auth import get_password_hash
# from fastapi import HTTPException

# def create_user(nome, id_usuario, senha):
#     try:
#         user = User(id_usuario=id_usuario, senha=get_password_hash(senha), nome=nome)
#         return insert_user(user)

#     except SQLAlchemyInsertError as exc:
#         raise HTTPException(status_code=422, detail=str(exc))


# def get_user(id_usuario: str):
#     user = select_user(id_usuario=id_usuario)
#     if not user:
#         raise UserNotFoundException("User not found")

#     return user
