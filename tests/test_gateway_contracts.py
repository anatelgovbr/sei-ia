"""Regression tests for the healthchecker's central gateway inventory."""

from __future__ import annotations

import re
import subprocess
import unittest
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call, patch

import pandas as pd

from tests import connectivity_tests, docker_tests, env_tests

ROOT = Path(__file__).resolve().parents[1]


def _compose_service_block(compose: str, service: str) -> str:
    match = re.search(
        rf"^  {re.escape(service)}:\n.*?(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        compose,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"serviço {service} ausente")
    return match.group(0)


def _nginx_listener_block(config: str, port: int) -> str:
    for block in config.split("server {")[1:]:
        if f"listen {port} ssl;" in block:
            return block.split("\n}", 1)[0]
    raise AssertionError(f"listener {port} ausente")


class GatewayInventoryTests(unittest.TestCase):
    def test_environment_templates_match_checker_inventory_exactly(self):
        expected = env_tests.create_env_vars_df(env_tests.env_vars)
        expected_by_file = {
            file_name: set(
                expected.loc[expected["file"] == file_name, "variavel"].tolist()
            )
            for file_name in ("default", "security")
        }
        actual_by_file = {
            "default": set(
                env_tests.load_env_file(str(ROOT / "default.env"))["variavel"].tolist()
            ),
            "security": set(
                env_tests.load_env_file(str(ROOT / "security_example.env"))[
                    "variavel"
                ].tolist()
            ),
        }

        self.assertEqual(actual_by_file, expected_by_file)
        for file_name, path in (
            ("default", ROOT / "default.env"),
            ("security", ROOT / "security_example.env"),
        ):
            names = env_tests.load_env_file(str(path))["variavel"].tolist()
            self.assertEqual(
                [name for name, count in Counter(names).items() if count > 1],
                [],
                f"variaveis repetidas em {file_name}",
            )
        self.assertEqual(env_tests.allowed_extra_vars, [])

    def test_compose_interpolation_uses_only_inventoried_variables(self):
        inventory = set(
            env_tests.load_env_file(str(ROOT / "default.env"))["variavel"]
        ) | set(env_tests.load_env_file(str(ROOT / "security_example.env"))["variavel"])
        compose = "\n".join(
            (ROOT / name).read_text(encoding="utf-8")
            for name in ("docker-compose.yml", "docker-compose.debug.yml")
        )
        interpolated = set(re.findall(r"\$\{([A-Z_][A-Z0-9_]*)", compose))

        self.assertEqual(interpolated - inventory, set())

    def test_embedding_routing_preserves_the_canonical_table_identity(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        airflow_common = compose.partition("x-airflow-common:")[2].partition(
            "\nservices:"
        )[0]
        jobs_api = _compose_service_block(compose, "etl-airflow-api")

        request_model = "LITELLM_EMBEDDING_MODEL_NAME: embedding"
        base_model = "EMBEDDING_BASE_MODEL: ${LITELLM_EMBEDDING_MODEL}"
        for service_environment in (airflow_common, jobs_api):
            self.assertIn(request_model, service_environment)
            self.assertIn(base_model, service_environment)

        envs = (ROOT / "aplicacoes/etl-airflow/jobs/envs.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'f"{EMBEDDING_BASE_MODEL}-{MAX_LENGTH_CHUNK_SIZE}-{CHUNK_OVERLAP}"',
            envs,
        )
        self.assertNotIn(
            'f"{LITELLM_EMBEDDING_MODEL_NAME}-{MAX_LENGTH_CHUNK_SIZE}-{CHUNK_OVERLAP}"',
            envs,
        )

    def test_environment_checker_rejects_uninventoried_variables(self):
        variables = pd.DataFrame(
            [
                {
                    "file": "security",
                    "categoria": "geral",
                    "variavel": "ENVIRONMENT",
                }
            ]
        )
        actual = pd.DataFrame(
            [
                {
                    "file": "security",
                    "variavel": "ENVIRONMENT",
                    "value": "prod",
                },
                {
                    "file": "security",
                    "variavel": "VARIAVEL_OBSOLETA",
                    "value": "valor",
                },
            ]
        )

        results, _ = env_tests.compare_env_variables(variables, actual)

        self.assertEqual(results["extra"]["variavel"].tolist(), ["VARIAVEL_OBSOLETA"])
        self.assertEqual(env_tests.report_env_issues(results), 1)

    def test_environment_checker_rejects_variable_in_both_files(self):
        variables = pd.DataFrame(
            [
                {
                    "file": "security",
                    "categoria": "geral",
                    "variavel": "ENVIRONMENT",
                }
            ]
        )
        actual = pd.DataFrame(
            [
                {"file": "security", "variavel": "ENVIRONMENT", "value": "prod"},
                {"file": "default", "variavel": "ENVIRONMENT", "value": "prod"},
            ]
        )

        results, _ = env_tests.compare_env_variables(variables, actual)

        self.assertEqual(len(results["duplicated"]), 2)
        self.assertFalse(results["extra"].empty)

    def test_missing_environment_variable_is_not_counted_as_empty_or_invalid(self):
        variables = pd.DataFrame(
            [
                {
                    "file": "security",
                    "categoria": "gateway_tls",
                    "variavel": "SEIIA_GATEWAY_HOST",
                }
            ]
        )
        actual = pd.DataFrame(columns=["file", "variavel", "value"])

        results, _ = env_tests.compare_env_variables(variables, actual)

        self.assertEqual(len(results["missing"]), 1)
        self.assertTrue(results["empty"].empty)
        self.assertTrue(results["invalid"].empty)

    def test_environment_parser_preserves_hash_inside_quoted_secret(self):
        with TemporaryDirectory() as output:
            env_file = Path(output) / "security.env"
            env_file.write_text('DB_SEIIA_PWD="senha # preservada" # comentario\n')

            loaded = env_tests.load_env_file(str(env_file))

        self.assertEqual(loaded.loc[0, "value"], "senha # preservada")

    def test_environment_checker_rejects_invalid_gateway_and_proxy_key(self):
        variables = pd.DataFrame(
            [
                {
                    "file": "security",
                    "categoria": "gateway_tls",
                    "variavel": "SEIIA_GATEWAY_HOST",
                },
                {
                    "file": "security",
                    "categoria": "litellm",
                    "variavel": "LITELLM_PROXY_API_KEY",
                },
                {
                    "file": "security",
                    "categoria": "litellm",
                    "variavel": "LITELLM_MINI_API_BASE",
                },
                {
                    "file": "security",
                    "categoria": "litellm",
                    "variavel": "LITELLM_NANO_API_BASE",
                },
            ]
        )
        actual = pd.DataFrame(
            [
                {
                    "file": "security",
                    "variavel": "SEIIA_GATEWAY_HOST",
                    "value": "nome_invalido",
                },
                {
                    "file": "security",
                    "variavel": "LITELLM_PROXY_API_KEY",
                    "value": "curta",
                },
                {
                    "file": "security",
                    "variavel": "LITELLM_MINI_API_BASE",
                    "value": "mini-sem-protocolo",
                },
                {
                    "file": "security",
                    "variavel": "LITELLM_NANO_API_BASE",
                    "value": "nano-sem-protocolo",
                },
            ]
        )

        results, _ = env_tests.compare_env_variables(variables, actual)

        self.assertEqual(
            set(results["invalid"]["variavel"]),
            {
                "SEIIA_GATEWAY_HOST",
                "LITELLM_PROXY_API_KEY",
                "LITELLM_MINI_API_BASE",
                "LITELLM_NANO_API_BASE",
            },
        )

    def test_environment_checker_rejects_malformed_dns_lists(self):
        variables = pd.DataFrame(
            [
                {
                    "file": "security",
                    "categoria": "gateway_tls",
                    "variavel": "SEIIA_CERT_DNS",
                }
            ]
        )
        for value in ("gateway..orgao.gov.br", "gateway.orgao.gov.br,"):
            with self.subTest(value=value):
                actual = pd.DataFrame(
                    [
                        {
                            "file": "security",
                            "variavel": "SEIIA_CERT_DNS",
                            "value": value,
                        }
                    ]
                )
                results, _ = env_tests.compare_env_variables(variables, actual)
                self.assertEqual(
                    results["invalid"]["variavel"].tolist(), ["SEIIA_CERT_DNS"]
                )

    def test_connectivity_inventory_has_three_gateway_listeners_and_internal_jobs(self):
        comparison = pd.DataFrame(
            [
                {"variavel": "DB_SEIIA_HOST", "value": "infra-postgres"},
                {"variavel": "DB_SEIIA_PORT", "value": "5432"},
                {"variavel": "SOLR_ADDRESS", "value": "http://infra-solr:8983"},
            ]
        )

        with patch.object(connectivity_tests, "GATEWAY_TLS_HOST", "seiia"):
            inventory = connectivity_tests.create_connectivity_config(comparison)

        self.assertEqual(
            {
                name: inventory[name]
                for name in (
                    "GATEWAY_ASSISTENTE",
                    "GATEWAY_SIMILARIDADE",
                    "GATEWAY_SIMILARIDADE_FEEDBACK",
                )
            },
            {
                "GATEWAY_ASSISTENTE": {"host": "seiia", "port": 8088},
                "GATEWAY_SIMILARIDADE": {"host": "seiia", "port": 8082},
                "GATEWAY_SIMILARIDADE_FEEDBACK": {
                    "host": "seiia",
                    "port": 8086,
                },
            },
        )
        self.assertEqual(
            inventory["API_JOBS_INTERNA"],
            {"host": "etl-airflow-api", "port": 8642},
        )
        self.assertNotIn("NGINX_ASSISTENTE", inventory)

    def test_http_contracts_disambiguate_overlapping_routes_by_listener(self):
        with patch.object(connectivity_tests, "GATEWAY_TLS_HOST", "seiia"):
            contracts = connectivity_tests.get_health_testes_urls()

        self.assertIn("https://seiia:8088", contracts["gateway_assistente"])
        self.assertIn("https://seiia:8082", contracts["gateway_similaridade"])
        self.assertIn(
            "https://seiia:8086",
            contracts["gateway_similaridade_feedback"],
        )
        self.assertEqual(
            contracts["gateway_assistente"]["https://seiia:8088"][1][
                "openapi_operations"
            ]["/llm_lang/session_stream"],
            {"post": {"request_body": True}},
        )
        self.assertEqual(
            contracts["gateway_similaridade"]["https://seiia:8082"][1][
                "openapi_operations"
            ]["/document-recommenders/mlt-recommender/recommendations"]["get"][
                "parameters"
            ],
            {"list_id_doc": "query", "text": "query", "rows": "query"},
        )

    def test_container_inventory_uses_gateway_name(self):
        self.assertIn("gateway-nginx", docker_tests.containers_names)
        self.assertNotIn("assistente-nginx", docker_tests.containers_names)

    def test_container_inventory_includes_official_web_search_profile(self):
        self.assertTrue(
            {
                "infra-searxng",
                "infra-lightpanda",
                "infra-chrome",
                "infra-fastcrw",
                "infra-byparr",
                "infra-marker",
            }
            <= set(docker_tests.containers_names)
        )

    def test_health_contract_reaches_searxng_on_the_compose_network(self):
        contracts = connectivity_tests.get_health_testes_urls()

        self.assertEqual(
            contracts["searxng"],
            {"http://infra-searxng:8080": [{"path": "/healthz"}]},
        )
        self.assertNotIn("SEARXNG_SECRET_KEY", env_tests.allowed_empty_vars)

    def test_searxng_healthcheck_uses_the_dedicated_endpoint(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        searxng = _compose_service_block(compose, "infra-searxng")

        self.assertIn("http://localhost:8080/healthz", searxng)
        self.assertIn(
            "SEARXNG_SECRET: ${SEARXNG_SECRET_KEY:?",
            searxng,
        )

    def test_searxng_engine_degradation_does_not_mask_service_errors(self):
        lines = [
            (
                "WARNING:searx.network.brave: HTTP Request failed: "
                "GET https://search.brave.com/search"
            ),
            "ERROR:searx.webapp: worker unavailable",
        ]

        filtered = docker_tests._filter_known_benign_lines(
            "sei-ia-infra-searxng-1", lines
        )

        self.assertEqual(filtered, ["ERROR:searx.webapp: worker unavailable"])

    def test_similarity_template_uses_canonical_internal_jobs_address(self):
        template = (ROOT / "aplicacoes/similaridade/template_export.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "JOBS_API_ADDRESS:-http://etl-airflow-api:8642",
            template,
        )
        self.assertNotIn("jobs_api:8642", template)

    def test_jobs_api_receives_airflow_metastore_connection(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        jobs_api = _compose_service_block(compose, "etl-airflow-api")

        self.assertIn(
            "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://",
            jobs_api,
        )
        self.assertIn(
            "${AIRFLOW_POSTGRES_PASSWORD:-airflow}",
            jobs_api,
        )

    def test_historical_password_defaults_remain_compatible(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        for interpolation in (
            "${DB_SEIIA_PWD:-postgres}",
            "${SOLR_PASSWORD:-solr}",
            "${AIRFLOW_POSTGRES_PASSWORD:-airflow}",
            "${AIRFLOW_AMQP_PASSWORD:-airflow}",
            "${_AIRFLOW_WWW_USER_PASSWORD:-admin}",
        ):
            self.assertIn(interpolation, compose)

    def test_environment_inventory_uses_gateway_resources_and_redacts_secrets(self):
        assistente_vars = env_tests.env_vars["default"]["assistente"]

        self.assertIn("GATEWAY_NGINX_MEM_LIMIT", assistente_vars)
        self.assertIn("GATEWAY_NGINX_CPU_LIMIT", assistente_vars)
        self.assertNotIn("ASSISTENTE_NGINX_MEM_LIMIT", assistente_vars)
        self.assertNotIn("ASSISTENTE_NGINX_CPU_LIMIT", assistente_vars)
        self.assertIn("LITELLM_STANDARD_API_KEY", env_tests.anon_variables)
        self.assertIn("LITELLM_MINI_API_KEY", env_tests.anon_variables)
        self.assertIn("LITELLM_NANO_API_KEY", env_tests.anon_variables)
        self.assertIn("LANGFUSE_SECRET_KEY", env_tests.anon_variables)
        self.assertIn("SEI_API_DB_IDENTIFIER_SERVICE", env_tests.anon_variables)

    def test_litellm_checker_inventory_matches_the_public_template(self):
        template = (ROOT / "litellm_config.template.yaml").read_text(encoding="utf-8")
        model_names = re.findall(
            r"^\s*- model_name:\s*([^\s#]+)", template, re.MULTILINE
        )
        template_tags = set(re.findall(r'"(agents:[^"]+)"', template))

        self.assertCountEqual(
            model_names, ["standard", "mini", "nano", "embedding", "speech-to-text"]
        )
        self.assertEqual(
            template_tags,
            set(connectivity_tests.EXPECTED_LITELLM_AGENT_TAGS),
        )
        self.assertNotIn("max_completion_tokens", template)

    def test_litellm_template_reads_provider_credentials_from_environment(self):
        template = (ROOT / "litellm_config.template.yaml").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        litellm = _compose_service_block(compose, "infra-litellm")
        referenced = set(re.findall(r"os\.environ/([A-Z0-9_]+)", template))
        security_names = set(
            env_tests.load_env_file(str(ROOT / "security_example.env"))["variavel"]
        )

        self.assertNotIn("${", template)
        self.assertTrue(referenced)
        self.assertTrue(referenced <= security_names)
        for variable in referenced:
            self.assertIn(f"{variable}: ${{{variable}", litellm)

    def test_text_model_tiers_use_separate_provider_credentials(self):
        template = (ROOT / "litellm_config.template.yaml").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        litellm = _compose_service_block(compose, "infra-litellm")
        security_names = set(
            env_tests.load_env_file(str(ROOT / "security_example.env"))["variavel"]
        )

        for tier in ("STANDARD", "MINI", "NANO"):
            model_variable = f"LITELLM_{tier}_MODEL"
            match = re.search(
                rf"^  - model_name: {tier.lower()}\n"
                rf"(?P<body>.*?)(?=^  - model_name:|\Z)",
                template,
                flags=re.MULTILINE | re.DOTALL,
            )
            self.assertIsNotNone(match, f"entrada {tier} ausente")
            entry = match.group("body")
            self.assertIn(f"model: os.environ/{model_variable}", entry)
            self.assertIn(f"base_model: os.environ/{model_variable}", entry)

            for suffix in ("API_BASE", "API_KEY", "API_VERSION"):
                variable = f"LITELLM_{tier}_{suffix}"
                self.assertIn(f"os.environ/{variable}", entry)
                self.assertIn(variable, security_names)
                self.assertIn(f"{variable}: ${{{variable}", litellm)

            for other_tier in {"STANDARD", "MINI", "NANO"} - {tier}:
                for suffix in ("API_BASE", "API_KEY", "API_VERSION"):
                    self.assertNotIn(f"os.environ/LITELLM_{other_tier}_{suffix}", entry)

    def test_litellm_consumers_wait_for_authenticated_proxy_health(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        airflow_common = compose.split("x-airflow-common:", 1)[1].split("services:", 1)[
            0
        ]

        for block in (
            airflow_common,
            _compose_service_block(compose, "assistente"),
            _compose_service_block(compose, "etl-airflow-api"),
        ):
            self.assertRegex(
                block,
                r"infra-litellm:\n\s+condition: service_healthy",
            )

    def test_redis_contract_has_no_unimplemented_password_toggle(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        redis = _compose_service_block(compose, "infra-redis")

        self.assertNotIn("REDIS_PASSWORD", redis)
        self.assertIn("redis-server --appendonly yes", redis)

    def test_gateway_certificate_checker_requires_configured_dns_names(self):
        with TemporaryDirectory() as output:
            cert = Path(output) / "gateway.pem"
            key = Path(output) / "gateway.key"
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-keyout",
                    str(key),
                    "-out",
                    str(cert),
                    "-subj",
                    "/CN=seiia",
                    "-addext",
                    "subjectAltName=DNS:seiia,DNS:gateway.exemplo.gov.br",
                ],
                check=True,
                capture_output=True,
            )

            with (
                patch.dict("os.environ", {"SEIIA_CERT_DNS": "gateway.exemplo.gov.br"}),
                patch.object(connectivity_tests, "GATEWAY_TLS_HOST", "seiia"),
            ):
                result = connectivity_tests.test_gateway_certificate_sans(str(cert))

        self.assertTrue(result["Reachable"])
        self.assertEqual(result["MissingSAN"], "")

    def test_gateway_certificate_checker_rejects_missing_configured_dns(self):
        with TemporaryDirectory() as output:
            cert = Path(output) / "gateway.pem"
            key = Path(output) / "gateway.key"
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-keyout",
                    str(key),
                    "-out",
                    str(cert),
                    "-subj",
                    "/CN=seiia",
                    "-addext",
                    "subjectAltName=DNS:seiia",
                ],
                check=True,
                capture_output=True,
            )

            with patch.dict("os.environ", {"SEIIA_CERT_DNS": "gateway.exemplo.gov.br"}):
                result = connectivity_tests.test_gateway_certificate_sans(str(cert))

        self.assertFalse(result["Reachable"])
        self.assertEqual(result["MissingSAN"], "gateway.exemplo.gov.br")

    def test_public_compose_does_not_autoload_debug_ports(self):
        self.assertFalse((ROOT / "docker-compose.override.yml").exists())
        self.assertTrue((ROOT / "docker-compose.debug.yml").is_file())

        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        defaults = (ROOT / "default.env").read_text(encoding="utf-8")
        self.assertNotIn("host.docker.internal", compose)
        self.assertNotIn("DOCKER_HOST_GATEWAY", defaults)

    def test_make_check_does_not_stop_the_running_stack(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

        self.assertIn("--profile checks run --build --rm --no-deps", makefile)
        self.assertNotIn("--abort-on-container-exit", makefile)

    def test_airflow_init_does_not_mask_migration_failure(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        airflow_init = _compose_service_block(compose, "etl-airflow-init")

        self.assertIn("airflow db migrate &&", airflow_init)
        self.assertNotIn("example.local || true", airflow_init)

    def test_rabbitmq_healthcheck_allows_cold_start(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        rabbitmq = _compose_service_block(compose, "infra-rabbitmq")

        self.assertIn(
            'test: ["CMD", "gosu", "rabbitmq", "rabbitmq-diagnostics", "-q", "ping"]',
            rabbitmq,
        )
        start_period = re.search(r"(?m)^\s+start_period:\s*(\d+)s\s*$", rabbitmq)
        assert start_period is not None
        self.assertGreaterEqual(int(start_period.group(1)), 60)

    def test_scheduler_healthcheck_checks_the_scheduler_job(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        script = (
            ROOT / "aplicacoes/etl-airflow/healthcheck/airflow_scheduler.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("airflow jobs check --job-type SchedulerJob", script)
        self.assertNotIn("etl-airflow-webserver", script)
        self.assertNotIn(
            '["CMD", "sh", "/home/airflow/app/healthcheck/airflow_', compose
        )

    def test_environment_checker_anonymizes_uninventoried_secrets(self):
        comparison = pd.DataFrame(
            [{"variavel": "FUTURE_PROVIDER_SECRET", "value": "must-not-leak"}]
        )

        with TemporaryDirectory() as output:
            env_tests.anonymize_and_save(comparison, output, [])
            saved = pd.read_csv(Path(output) / "comparison_df.csv")

        self.assertEqual(saved.loc[0, "value"], "ANONYMIZED")

    @patch("tests.connectivity_tests.requests.get")
    def test_http_checker_rejects_openapi_without_expected_operation(self, get: Mock):
        response = Mock(status_code=200)
        response.json.return_value = {"paths": {"/health": {"get": {}}}}
        get.return_value = response

        reachable = connectivity_tests.test_api_connectivity_and_response(
            "https://seiia:8088/openapi.json",
            {
                "path": "/openapi.json",
                "openapi_operations": {
                    "/llm_lang/session_stream": {"post": {"request_body": True}}
                },
            },
        )

        self.assertFalse(reachable)

    @patch("tests.connectivity_tests.requests.get")
    def test_gateway_https_uses_hostname_and_mounted_ca(self, get: Mock):
        response = Mock(status_code=200)
        response.json.return_value = {"status": "OK"}
        get.return_value = response

        reachable = connectivity_tests.test_api_connectivity_and_response(
            "https://seiia:8088/health",
            {
                "path": "/health",
                "expected_json": {"status": "OK"},
                "verify": "/etc/ssl/certs/seiia.cert.pem",
            },
        )

        self.assertTrue(reachable)
        get.assert_called_once_with(
            "https://seiia:8088/health",
            headers={"accept": "application/json"},
            verify="/etc/ssl/certs/seiia.cert.pem",
            timeout=15,
        )

    @patch("tests.connectivity_tests.requests.get")
    def test_litellm_health_uses_proxy_key(self, get: Mock):
        response = Mock(status_code=200)
        get.return_value = response

        reachable = connectivity_tests.test_api_connectivity_and_response(
            "http://infra-litellm:4000/health",
            {
                "path": "/health",
                "headers": {"Authorization": "Bearer sk-checker"},
            },
        )

        self.assertTrue(reachable)
        get.assert_called_once_with(
            "http://infra-litellm:4000/health",
            headers={
                "accept": "application/json",
                "Authorization": "Bearer sk-checker",
            },
            verify=False,
            timeout=15,
        )

    @patch.dict("os.environ", {"LITELLM_PROXY_API_KEY": "sk-checker"})
    @patch("tests.connectivity_tests.requests.get")
    def test_litellm_model_inventory_uses_readiness_probe(self, get: Mock):
        readiness_response = Mock(status_code=200)
        models_response = Mock(status_code=200)
        models_response.json.return_value = {
            "data": [
                {
                    "model_name": alias,
                    "litellm_params": {"tags": list(tags)},
                }
                for alias, tags in {
                    "standard": ["agents:principal"],
                    "mini": ["agents:classificador", "agents:busca_web"],
                    "nano": ["agents:explorador", "agents:ocr", "agents:triagem_busca"],
                    "embedding": ["agents:embedding"],
                    "speech-to-text": ["agents:audio_transcription"],
                }.items()
            ]
        }
        get.side_effect = [readiness_response, models_response]

        result = connectivity_tests.test_litellm_proxy_models(
            "http://infra-litellm:4000"
        )

        self.assertTrue(result["proxy_health"])
        self.assertIsNone(result["error"])
        self.assertTrue(all(model["available"] for model in result["models"].values()))
        self.assertEqual(
            get.call_args_list,
            [
                call(
                    "http://infra-litellm:4000/health/readiness",
                    headers={"Authorization": "Bearer sk-checker"},
                    timeout=15,
                ),
                call(
                    "http://infra-litellm:4000/model/info",
                    headers={"Authorization": "Bearer sk-checker"},
                    timeout=15,
                ),
            ],
        )

    @patch("tests.connectivity_tests.requests.get")
    def test_litellm_checker_rejects_physical_names_even_with_all_tags(self, get: Mock):
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": [
                {
                    "model_name": "openai/modelo-fisico",
                    "litellm_params": {
                        "tags": list(connectivity_tests.EXPECTED_LITELLM_AGENT_TAGS)
                    },
                }
            ]
        }
        get.return_value = response

        result = connectivity_tests.test_litellm_proxy_models("http://proxy.test")

        self.assertEqual(connectivity_tests.report_litellm_proxy_status(result), 5)
        self.assertFalse(result["models"]["embedding"]["available"])

    @patch("tests.connectivity_tests.requests.get")
    def test_litellm_checker_requires_tags_on_the_correct_alias(self, get: Mock):
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": [
                {"model_name": "embedding", "litellm_params": {"tags": []}},
                {
                    "model_name": "outro-modelo",
                    "litellm_params": {"tags": ["agents:embedding"]},
                },
            ]
        }
        get.return_value = response

        result = connectivity_tests.test_litellm_proxy_models("http://proxy.test")

        self.assertIn("embedding", result["models"])
        self.assertFalse(result["models"]["embedding"]["available"])

    def test_nginx_listeners_preserve_upstreams_and_streaming(self):
        config = (ROOT / "ops/gateway/nginx.conf").read_text(encoding="utf-8")
        listeners = {
            8088: ("$assistente_upstream", "http://assistente:8088"),
            8082: ("$similaridade_upstream", "http://similaridade:8082"),
            8086: ("$feedback_upstream", "http://similaridade-feedback:8086"),
        }

        for port, (variable, upstream) in listeners.items():
            block = _nginx_listener_block(config, port)
            self.assertIn(f"set {variable} {upstream};", block)
            self.assertIn(f"proxy_pass {variable};", block)
            self.assertNotIn(f"proxy_pass {variable}/", block)
            self.assertIn("proxy_set_header Host $http_host;", block)
            self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", block)

        assistente = _nginx_listener_block(config, 8088)
        self.assertIn("proxy_buffering off;", assistente)
        self.assertIn("proxy_cache off;", assistente)
        for timeout in (
            "proxy_connect_timeout 600s;",
            "proxy_send_timeout 600s;",
            "proxy_read_timeout 600s;",
            "send_timeout 600s;",
        ):
            self.assertIn(timeout, assistente)

        similaridade = _nginx_listener_block(config, 8082)
        self.assertIn("proxy_read_timeout 280s;", similaridade)

    def test_compose_keeps_tls_only_at_gateway_and_jobs_internal(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        gateway = _compose_service_block(compose, "gateway-nginx")
        checker = _compose_service_block(compose, "stack-config-checker")

        self.assertIn("${ASSISTENTE_PORT:-8088}:8088", gateway)
        self.assertIn('"8082:8082"', gateway)
        self.assertIn('"8086:8086"', gateway)
        self.assertIn(
            ".runtime/certs/seiia.cert.key:/etc/ssl/private/seiia.cert.key:ro",
            gateway,
        )
        self.assertNotIn("--keyfile", compose)
        self.assertNotIn("--certfile", compose)
        self.assertEqual(compose.count("/etc/ssl/private/seiia.cert.key"), 1)
        self.assertIn("tmpfs:\n      - /opt/healthchecker/.runtime", checker)
        self.assertNotIn("seiia.cert.key:/opt/healthchecker", checker)

        for service in ("assistente", "similaridade", "similaridade-feedback"):
            self.assertNotIn("\n    ports:", _compose_service_block(compose, service))
        for service in ("assistente", "similaridade", "similaridade-feedback"):
            self.assertIn(
                '--forwarded-allow-ips="*"',
                _compose_service_block(compose, service),
            )
        jobs = _compose_service_block(compose, "etl-airflow-api")
        self.assertNotIn("--forwarded-allow-ips", jobs)
        self.assertNotIn("\n    ports:", jobs)
        self.assertNotIn("8090", jobs)

        self.assertIn(
            ".runtime/certs/seiia.cert.pem:/etc/ssl/certs/seiia.cert.pem:ro",
            checker,
        )
        self.assertIn("/opt/healthchecker/.runtime", checker)
        self.assertNotIn("seiia.cert.key", checker)

        airflow_webserver = _compose_service_block(compose, "etl-airflow-webserver")
        self.assertIn('"127.0.0.1:8081:8080"', airflow_webserver)

        debug_compose = (ROOT / "docker-compose.debug.yml").read_text(encoding="utf-8")
        self.assertNotRegex(debug_compose, r'- "(?!127\.0\.0\.1:)')


if __name__ == "__main__":
    unittest.main()
