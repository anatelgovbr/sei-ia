"""Tests for api_sei/main.py (module-level app wiring)."""

import sys
from unittest.mock import patch

import pytest


def _fresh_import_main():
    sys.modules.pop("api_sei.main", None)
    import api_sei.main as main_module

    return main_module


@pytest.fixture(autouse=True)
def _cleanup_main_module():
    yield
    sys.modules.pop("api_sei.main", None)


class TestMainAppWiring:
    def test_builds_app_with_otel_enabled_and_cores_found(self):
        with patch(
            "api_sei.envs.ENABLE_OTEL_METRICS", True
        ), patch(
            "api_sei.db_models.solr_select.SolrRequests.check_core_exists",
            return_value=True,
        ):
            main_module = _fresh_import_main()

        assert main_module.app.title == "API de recomendação de processos SEI."
        assert main_module.app.url_path_for("autotests") == "/teste"
        assert any(
            middleware.cls.__name__ == "MetricsMeddleware"
            for middleware in main_module.app.user_middleware
        )

    def test_builds_app_with_otel_disabled_and_cores_missing(self):
        with patch(
            "api_sei.envs.ENABLE_OTEL_METRICS", False
        ), patch(
            "api_sei.db_models.solr_select.SolrRequests.check_core_exists",
            return_value=False,
        ):
            main_module = _fresh_import_main()

        assert main_module.app.title == "API de recomendação de processos SEI."
        assert not any(
            middleware.cls.__name__ == "MetricsMeddleware"
            for middleware in main_module.app.user_middleware
        )
