"""Tests for api_sei/middleware/custom_middleware.py."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from starlette.datastructures import QueryParams

from api_sei.envs import SECRET_KEY
from api_sei.middleware.custom_middleware import (
    LogRecommendationMiddleware,
    MiddlewareCustom,
)


def _token(exp_delta_minutes: int) -> str:
    return jwt.encode(
        {
            "sub": "user1",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=exp_delta_minutes),
        },
        SECRET_KEY,
        algorithm="HS256",
    )


class TestValidateToken:
    def setup_method(self):
        self.middleware = MiddlewareCustom(path="/x", endpoint=lambda: None)

    def test_valid_token_returns_true(self):
        assert self.middleware.validate_token(_token(5)) is True

    def test_expired_token_returns_false(self):
        assert self.middleware.validate_token(_token(-5)) is False

    def test_invalid_token_returns_false(self):
        assert self.middleware.validate_token("not-a-jwt") is False


class TestGetUserFromToken:
    def test_returns_sub_claim(self):
        middleware = MiddlewareCustom(path="/x", endpoint=lambda: None)
        assert middleware.get_user_from_token(_token(5)) == "user1"


class TestLogRecommentation:
    def setup_method(self):
        self.middleware = MiddlewareCustom(path="/x", endpoint=lambda: None)

    def test_logs_when_path_param_id_present(self):
        request = MagicMock()
        request.url = "http://test/x/123"
        request.path_params = {"id_protocolo": "123"}
        request.query_params = QueryParams("")

        with patch("api_sei.middleware.custom_middleware.create_log") as mock_log:
            self.middleware.log_recommentation(request, status_code=200)

        mock_log.assert_called_once_with(
            status_code=200,
            id_protocol=[123],
            id_user=None,
            api_recomend_url="http://test/x/123",
        )

    def test_logs_when_query_param_list_present_and_deduplicates(self):
        request = MagicMock()
        request.url = "http://test/x"
        request.path_params = {}
        request.query_params = QueryParams(
            "list_id_doc=1&list_id_doc=2&list_id_doc=1&id_user=9"
        )

        with patch("api_sei.middleware.custom_middleware.create_log") as mock_log:
            self.middleware.log_recommentation(request, status_code=200)

        kwargs = mock_log.call_args.kwargs
        assert sorted(kwargs["id_protocol"]) == [1, 2]
        assert kwargs["id_user"] == "9"

    def test_does_not_log_when_no_ids_found(self):
        request = MagicMock()
        request.url = "http://test/x"
        request.path_params = {}
        request.query_params = QueryParams("")

        with patch("api_sei.middleware.custom_middleware.create_log") as mock_log:
            self.middleware.log_recommentation(request, status_code=200)

        mock_log.assert_not_called()


class TestMiddlewareCustomRouteHandler:
    def test_calls_log_recommentation_after_response(self):
        app = FastAPI()
        router = APIRouter(route_class=MiddlewareCustom)

        @router.get("/process/{id_protocolo}")
        async def endpoint() -> dict:
            return {"ok": True}

        app.include_router(router)
        client = TestClient(app)

        with patch("api_sei.middleware.custom_middleware.create_log") as mock_log:
            response = client.get("/process/123")

        assert response.status_code == 200
        mock_log.assert_called_once()
        assert mock_log.call_args.kwargs["id_protocol"] == [123]


class TestLogRecommendationMiddlewareRouteHandler:
    def test_logs_when_list_id_doc_query_param_present(self):
        app = FastAPI()
        router = APIRouter(route_class=LogRecommendationMiddleware)

        @router.get("/documents")
        async def endpoint() -> dict:
            return {"ok": True}

        app.include_router(router)
        client = TestClient(app)

        with patch("api_sei.middleware.custom_middleware.create_log") as mock_log:
            response = client.get("/documents", params={"list_id_doc": [1, 2]})

        assert response.status_code == 200
        mock_log.assert_called_once()
        assert mock_log.call_args.kwargs["id_protocol"] == ["1", "2"]

    def test_does_not_log_when_no_list_ids_in_query(self):
        app = FastAPI()
        router = APIRouter(route_class=LogRecommendationMiddleware)

        @router.get("/documents")
        async def endpoint() -> dict:
            return {"ok": True}

        app.include_router(router)
        client = TestClient(app)

        with patch("api_sei.middleware.custom_middleware.create_log") as mock_log:
            response = client.get("/documents")

        assert response.status_code == 200
        mock_log.assert_not_called()
