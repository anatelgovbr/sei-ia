"""Tests for api_sei/middleware/otel_middleware.py."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Match

from api_sei.middleware.otel_middleware import MetricsMeddleware


class TestGetPath:
    def test_returns_matched_route_path(self):
        app = FastAPI()

        @app.get("/items/{item_id}")
        async def endpoint(item_id: int) -> dict:
            return {"item_id": item_id}

        client = TestClient(app)
        middleware = MetricsMeddleware(app=app)

        captured = {}

        @app.middleware("http")
        async def capture_path(request, call_next):
            captured["path"] = middleware.get_path(request)
            return await call_next(request)

        client.get("/items/5")
        assert captured["path"] == "/items/{item_id}"

    def test_falls_back_to_url_path_when_no_route_matches(self):
        request = MagicMock()
        request.url.path = "/unmatched"
        fake_route = MagicMock()
        fake_route.path = "/other"
        fake_route.matches.return_value = (Match.NONE, {})
        request.app.routes = [fake_route]

        middleware = MetricsMeddleware(app=FastAPI())
        assert middleware.get_path(request) == "/unmatched"

    def test_skips_routes_without_path_attribute(self):
        request = MagicMock()
        request.url.path = "/unmatched"
        route_without_path = MagicMock(spec=[])
        request.app.routes = [route_without_path]

        middleware = MetricsMeddleware(app=FastAPI())
        assert middleware.get_path(request) == "/unmatched"


class TestDispatch:
    def test_records_request_count_on_success(self):
        app = FastAPI()

        @app.get("/ok")
        async def endpoint() -> dict:
            return {"ok": True}

        app.add_middleware(MetricsMeddleware)
        client = TestClient(app)

        response = client.get("/ok")
        assert response.status_code == 200

    def test_records_error_count_and_reraises_on_exception(self):
        app = FastAPI()

        @app.get("/boom")
        async def endpoint() -> dict:
            raise ValueError("boom")

        app.add_middleware(MetricsMeddleware)
        client = TestClient(app, raise_server_exceptions=True)

        with pytest.raises(ValueError, match="boom"):
            client.get("/boom")
