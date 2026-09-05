"""Middleware custom."""

import contextvars
from collections.abc import Callable

import anyio
from configs.settings_config import TIMEOUT_API
from fastapi import HTTPException, Request, Response, status
from fastapi.routing import APIRoute

cancel_scope_var = contextvars.ContextVar("cancel_scope_var", default=None)


class TimeoutMiddleware(APIRoute):
    """Middleware Timeout."""

    def get_route_handler(self) -> Callable:
        """Returns a custom route handler that wraps the original route handler with a timeout of 60 seconds.

        If the original route handler times out, it raises an HTTPException with a detail message of "Request timed out"
        and a status code of 504.
        Parameters:
            self (object): The instance of the class.

        Returns:
            Callable: The custom route handler.
        """
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            """An asynchronous route handler that wraps the original route handler with a timeout of 60 seconds.

            Parameters:
                request (Request): The incoming request object.

            Returns:
                Response: The response object returned by the original route handler.

            Raises:
                HTTPException: If the original route handler times out, an HTTPException with a detail message of
                "Request timed out by middleware" and a status code of 408 is raised.
            """

            async def task_wrapper() -> Response:
                return await original_route_handler(request)

            async def run_with_timeout() -> Response:
                with anyio.CancelScope() as cancel_scope:
                    cancel_scope_var.set(cancel_scope)
                    return await anyio.fail_after(TIMEOUT_API, task_wrapper)

            cancel_scope = anyio.CancelScope()
            cancel_scope_var.set(cancel_scope)

            try:
                return await run_with_timeout()
            except TimeoutError as err:
                raise HTTPException(
                    detail="Request timed out by middleware",
                    status_code=status.HTTP_408_REQUEST_TIMEOUT,
                ) from err

        return custom_route_handler
