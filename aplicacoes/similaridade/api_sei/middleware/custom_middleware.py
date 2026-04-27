"""Middleware para armazenar os logs."""

from collections.abc import Callable

import jwt
from fastapi import Request, Response
from fastapi.routing import APIRoute

from api_sei.envs import SECRET_KEY
from api_sei.services.log_consume import create_log

list_ids = ["id_protocolo", "nr_processo", "list_id_doc"]


class MiddlewareCustom(APIRoute):
    """Middleware para armazenar os logs."""

    def validate_token(self, token: str) -> bool:
        """Verifica se o token valido.

        Parameters
        ----------
        token : str
            Token a ser verificado.

        Returns:
        -------
        bool
            True se o token   v lido, False caso contr rio.
        """
        try:
            jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            return True
        except jwt.ExpiredSignatureError:
            return False
        except jwt.InvalidTokenError:
            return False

    def get_user_from_token(token: str) -> str:
        """Obtains the user from the provided token.

        Parameters
        ----------
        token : str
            The token to decode and extract user information.

        Returns:
        -------
        str
            The user obtained from the token.
        """
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return decoded_token["sub"]

    def log_recommentation(self, request: Request, status_code: str) -> None:
        """Logs a recommendation.

        Parameters
        ----------
        request : Request
            The FastAPI Request object.
        status_code : str
            The HTTP status code of the response.

        """
        url = str(request.url)

        id_process = []

        for key in list_ids:
            if request.path_params.get(key):
                id_process.append(request.path_params.get(key))
            id_process.extend(request.query_params.getlist(key))

        id_process = list({int(value) for value in id_process})

        if id_process:
            id_user = request.query_params.get("id_user")
            create_log(
                status_code=status_code,
                id_protocol=id_process,
                id_user=id_user,
                api_recomend_url=url,
            )

    def get_route_handler(self) -> Callable:
        """Retorna o manipulador de rota com o registro de recomendação.

        O manipulador de rota do próximo middleware na cadeia é chamado, e
        a resposta é registrada com a função de registro de recomendação.

        Returns:
        -------
        Callable
            O manipulador de rotas com o registro de recomendações.
        """
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            response: Response = await original_route_handler(request)
            self.log_recommentation(request=request, status_code=response.status_code)
            return response

        return custom_route_handler


class LogRecommendationMiddleware(APIRoute):
    """Middleware para registrar os logs de recomendação."""

    def get_route_handler(self) -> Callable:
        """Retorna o manipulador de rota com o registro de recomenda o.

        O manipulador de rota do pr ximo middleware na cadeia   chamado, e
        a resposta   registrada com a fun o de registro de recomenda o.

        Returns:
        -------
        Callable
            O manipulador de rotas com o registro de recomenda es.
        """
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            response: Response = await original_route_handler(request)
            id_process = []
            for key in list_ids:
                id_process.extend(request.query_params.getlist(key))

            if id_process:
                create_log(
                    status_code=int(response.status_code),
                    id_protocol=id_process,
                    api_recomend_url=str(request.url),
                )
            return response

        return custom_route_handler
