"""Tests for api_sei/services/autoteste.py."""

import json
from unittest.mock import patch

from fastapi import FastAPI

from api_sei.services.autoteste import TestesAutoteste


class TestReadEndpoints:
    def test_reads_json_list_from_config_path(self, tmp_path):
        config_file = tmp_path / "endpoints.json"
        payload = [{"test_description": "x", "path": "/x", "params": {}}]
        config_file.write_text(json.dumps(payload))

        ta = TestesAutoteste(FastAPI())
        with patch(
            "api_sei.services.autoteste.CONFIG_AUTO_TESTS_PATH", str(config_file)
        ):
            result = ta.read_endpoints()

        assert result == payload


class TestBuildUrl:
    def setup_method(self):
        self.ta = TestesAutoteste(FastAPI())

    def test_scalar_params_are_urlencoded(self):
        result = self.ta.build_url("/path", {"rows": 10, "text": "abc"})
        assert result == "/path?rows=10&text=abc"

    def test_list_params_become_repeated_query_params(self):
        result = self.ta.build_url("/path", {"list_type_id_doc": [7, 8, 94]})
        assert result == "/path?list_type_id_doc=7&list_type_id_doc=8&list_type_id_doc=94"

    def test_substitutes_id_recommendation_placeholder(self):
        result = self.ta.build_url(
            "/path/{id_recommendation}/x", {"id_recommendation": 123, "rows": 5}
        )
        assert result == "/path/123/x?rows=5"

    def test_prefixes_with_given_base_url(self):
        result = self.ta.build_url("/path", {"rows": 1}, base_url="http://host:8000")
        assert result == "http://host:8000/path?rows=1"

    def test_defaults_base_url_to_empty_string(self):
        result = self.ta.build_url("/path", {"rows": 1}, base_url=None)
        assert result.startswith("/path?")


class TestAutoteste:
    def test_marks_success_when_status_matches_expectation(self):
        app = FastAPI()

        @app.get("/health")
        def _health():
            return {"status": "OK"}

        ta = TestesAutoteste(app)
        endpoints = [
            {
                "test_description": "health ok",
                "path": "/health",
                "params": {},
                "result_expected": {"status_code": 200},
            }
        ]
        with patch.object(ta, "read_endpoints", return_value=endpoints):
            results = ta.autoteste()

        assert results == [
            {
                "test_description": "health ok",
                "url": "/health?",
                "test_success": "SUCCESS",
                "status_code": 200,
            }
        ]

    def test_marks_fail_when_status_does_not_match_expectation(self):
        app = FastAPI()

        @app.get("/health")
        def _health():
            return {"status": "OK"}

        ta = TestesAutoteste(app)
        endpoints = [
            {
                "test_description": "wrong expectation",
                "path": "/health",
                "params": {},
                "result_expected": {"status_code": 500},
            }
        ]
        with patch.object(ta, "read_endpoints", return_value=endpoints):
            results = ta.autoteste()

        assert results[0]["test_success"] == "FAIL"
        assert results[0]["status_code"] == 200
