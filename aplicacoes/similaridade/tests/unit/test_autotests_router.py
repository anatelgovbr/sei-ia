"""Tests for api_sei/routers/autotests.py."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from api_sei.routers.autotests import autotests


class TestAutotests:
    @pytest.mark.asyncio
    async def test_delegates_to_testesautoteste_with_request_app(self):
        app = FastAPI()
        request = MagicMock()
        request.app = app

        expected = [
            {
                "test_description": "health",
                "url": "/health?",
                "test_success": "SUCCESS",
                "status_code": 200,
            }
        ]
        with patch(
            "api_sei.routers.autotests.TestesAutoteste"
        ) as mock_cls:
            mock_cls.return_value.autoteste.return_value = expected
            result = await autotests(request)

        assert result == expected
        mock_cls.assert_called_once_with(app=app)
