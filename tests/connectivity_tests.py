"""Testes de conectividade do healthchecker local."""

from __future__ import annotations

import logging
import os
import socket
import ssl
import time
import warnings
from typing import Any
from urllib.parse import urlsplit

import pandas as pd
import requests
import urllib3
from requests.auth import HTTPBasicAuth

from tests.db_connect import DBConnector

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.simplefilter("ignore", category=urllib3.exceptions.InsecureRequestWarning)

assistente_tables = ["feedback", "ip_message", "messages", "models"]

similaridade_tables = [
    "document_mlt_recommendation",
    "log_consume",
    "log_update_mlt",
    "process_weighted_mlt_recommendation",
    "queue_update_mlt",
    "version_register",
]

GATEWAY_TLS_HOST = os.getenv("SEIIA_GATEWAY_HOST") or "seiia"
GATEWAY_CA_CERT = os.getenv("GATEWAY_CA_CERT") or ("/etc/ssl/certs/seiia.cert.pem")
EXPECTED_LITELLM_ALIASES = {
    "standard": ("agents:principal",),
    "mini": ("agents:classificador", "agents:busca_web"),
    "nano": ("agents:explorador", "agents:ocr", "agents:triagem_busca"),
    "embedding": ("agents:embedding",),
    "speech-to-text": ("agents:audio_transcription",),
}
EXPECTED_LITELLM_AGENT_TAGS = tuple(
    tag for tags in EXPECTED_LITELLM_ALIASES.values() for tag in tags
)


def test_gateway_certificate_sans(cert_path: str | None = None) -> dict:
    """Confirma validade temporal e todos os nomes usados no certificado do gateway."""
    cert_path = cert_path or GATEWAY_CA_CERT
    configured_dns = {
        name.strip()
        for name in os.getenv("SEIIA_CERT_DNS", "").split(",")
        if name.strip()
    }
    expected_dns = configured_dns | {GATEWAY_TLS_HOST}

    try:
        certificate = ssl._ssl._test_decode_cert(cert_path)  # type: ignore[attr-defined]
        san_dns = {
            value
            for kind, value in certificate.get("subjectAltName", ())
            if kind == "DNS"
        }
        now = time.time()
        not_before = ssl.cert_time_to_seconds(certificate["notBefore"])
        not_after = ssl.cert_time_to_seconds(certificate["notAfter"])
        missing = sorted(expected_dns - san_dns)
        return {
            "Reachable": not missing and not_before <= now <= not_after,
            "Host": ",".join(sorted(expected_dns)),
            "Port": "TLS",
            "Endpoint": cert_path,
            "MissingSAN": ",".join(missing),
        }
    except (OSError, KeyError, ValueError, ssl.SSLError) as exc:
        logging.error("Falha ao validar o certificado do gateway: %s", exc)
        return {
            "Reachable": False,
            "Host": ",".join(sorted(expected_dns)),
            "Port": "TLS",
            "Endpoint": cert_path,
            "MissingSAN": "certificado-invalido",
        }


def create_postgres_config(
    comparison_df: pd.DataFrame,
) -> tuple[dict, DBConnector | None, DBConnector | None]:
    try:
        postgres_user = comparison_df[comparison_df["variavel"] == "DB_SEIIA_USER"][
            "value"
        ].values[0]
        postgres_password = comparison_df[comparison_df["variavel"] == "DB_SEIIA_PWD"][
            "value"
        ].values[0]
        pgvector_host = comparison_df[comparison_df["variavel"] == "DB_SEIIA_HOST"][
            "value"
        ].values[0]
        pgvector_port = comparison_df[comparison_df["variavel"] == "DB_SEIIA_PORT"][
            "value"
        ].values[0]
        assistente_db_name = comparison_df[
            comparison_df["variavel"] == "DB_SEIIA_ASSISTENTE"
        ]["value"].values[0]
        similaridade_db_name = comparison_df[
            comparison_df["variavel"] == "DB_SEIIA_SIMILARIDADE"
        ]["value"].values[0]
    except IndexError:
        logging.error("Variaveis faltantes para configuracao do banco interno.")
        return {}, None, None

    assistente_conn_string = (
        f"postgresql+psycopg2://{postgres_user}:{postgres_password}"
        f"@{pgvector_host}:{pgvector_port}/{assistente_db_name}"
    )
    similaridade_conn_string = (
        f"postgresql+psycopg2://{postgres_user}:{postgres_password}"
        f"@{pgvector_host}:{pgvector_port}/{similaridade_db_name}"
    )

    try:
        assistente_db_instance = DBConnector(assistente_conn_string, schema="")
        similaridade_db_instance = DBConnector(similaridade_conn_string, schema="")
        return (
            {
                "ASSISTENTE": {"conn_string": assistente_conn_string},
                "SIMILARIDADE": {"conn_string": similaridade_conn_string},
            },
            assistente_db_instance,
            similaridade_db_instance,
        )
    except Exception:
        logging.exception("Erro ao conectar aos bancos internos.")
        return {}, None, None


def verify_table(
    instance: DBConnector,
    table: str,
    schema: str | None = None,
    database_type: str | None = None,
    verbose: bool = False,
) -> bool:
    try:
        if schema:
            sql = f"SELECT * FROM {schema}.{table}"
        else:
            sql = f"SELECT * FROM {table}"
        if database_type == "postgres":
            sql += " LIMIT 1"
        instance.execute_query(sql)
        return True
    except Exception as exc:
        if verbose:
            logging.error("Tabela %s nao existe. Erro: %s", table, exc)
        return False


def verify_all_tables(
    instance: DBConnector,
    tables: list[str],
    schema: str | None = None,
    database_type: str | None = None,
    verbose: bool = True,
) -> dict[str, dict]:
    result = {}
    for table in tables:
        result[table] = {
            "Reachable": verify_table(instance, table, schema, database_type, verbose)
        }
    return result


def create_solr_config(comparison_df: pd.DataFrame) -> dict:
    solr_address = comparison_df[comparison_df["variavel"] == "SOLR_ADDRESS"][
        "value"
    ].values[0]
    solr_host = solr_address.split(":")[1].replace("//", "")
    solr_port = int(solr_address.split(":")[2])
    return {
        "Solr_documento": {
            "host": solr_host,
            "port": solr_port,
            "core": comparison_df[
                comparison_df["variavel"] == "SOLR_MLT_JURISPRUDENCE_CORE"
            ]["value"].values[0],
            "interno": True,
        },
        "Solr_processo": {
            "host": solr_host,
            "port": solr_port,
            "core": comparison_df[comparison_df["variavel"] == "SOLR_MLT_PROCESS_CORE"][
                "value"
            ].values[0],
            "interno": True,
        },
    }


def verify_solr_status(
    host: str, port: int, core: str, interno: bool, verbose: bool = False
) -> dict:
    try:
        url = f"https://{host}:{port}/solr/{core}/admin/ping"
        response = requests.get(
            url,
            verify=False,
            auth=HTTPBasicAuth(os.getenv("SOLR_USER"), os.getenv("SOLR_PASSWORD")),
            timeout=10,
        )
        response.raise_for_status()
        return {
            "Reachable": response.status_code == 200,
            "Host": host,
            "Port": port,
            "Core": core,
        }
    except requests.exceptions.RequestException as exc:
        if verbose:
            logging.error("Erro ao conectar ao Solr %s: %s", core, exc)
        return {"Reachable": False, "Host": host, "Port": port, "Core": core}


def test_connectivity_all_solr(solr_config: dict, verbose: bool = True) -> dict:
    results = {}
    for service_name, config in solr_config.items():
        results[service_name] = verify_solr_status(
            config["host"],
            config["port"],
            config["core"],
            config["interno"],
            verbose,
        )
    return results


def connectivity_report(
    results: dict, return_df: bool = False, path: str | None = None
) -> tuple[int, pd.DataFrame | None]:
    try:
        results_df = pd.DataFrame.from_dict(results, orient="index")
    except Exception:
        results_df = pd.DataFrame.from_dict(results)

    error_count = len(results_df[~results_df["Reachable"]])
    if error_count > 0:
        logging.error("\nHouve falha nos testes abaixo:\n")
        logging.error(results_df[~results_df["Reachable"]].to_markdown())
    else:
        logging.info("\nTodos os testes passaram.\n")

    if path:
        results_df.to_csv(path, index=False)
    if return_df:
        return error_count, results_df
    return error_count, None


def create_connectivity_config(comparison_df: pd.DataFrame) -> dict:
    litellm_proxy_url = os.getenv("LITELLM_PROXY_URL") or "http://infra-litellm:4000"
    try:
        litellm_url_parts = litellm_proxy_url.replace("http://", "").replace(
            "https://", ""
        )
        if ":" in litellm_url_parts:
            litellm_host, litellm_port = litellm_url_parts.split(":")
            litellm_port = int(litellm_port)
        else:
            litellm_host = litellm_url_parts
            litellm_port = 80
    except Exception:
        litellm_host = "infra-litellm"
        litellm_port = 4000

    solr_address = comparison_df[comparison_df["variavel"] == "SOLR_ADDRESS"][
        "value"
    ].values[0]
    return {
        "DB_INTERNO": {
            "host": comparison_df[comparison_df["variavel"] == "DB_SEIIA_HOST"][
                "value"
            ].values[0],
            "port": int(
                comparison_df[comparison_df["variavel"] == "DB_SEIIA_PORT"][
                    "value"
                ].values[0]
            ),
        },
        "Solr_Interno": {
            "host": solr_address.split(":")[1].replace("//", ""),
            "port": int(solr_address.split(":")[2]),
        },
        "API_SIMILARIDADE": {"host": "similaridade", "port": 8082},
        "API_SIMILARIDADE_FEEDBACK": {"host": "similaridade-feedback", "port": 8086},
        "API_JOBS_INTERNA": {"host": "etl-airflow-api", "port": 8642},
        "API_ASSISTENTE": {"host": "assistente", "port": 8088},
        "GATEWAY_ASSISTENTE": {"host": GATEWAY_TLS_HOST, "port": 8088},
        "GATEWAY_SIMILARIDADE": {"host": GATEWAY_TLS_HOST, "port": 8082},
        "GATEWAY_SIMILARIDADE_FEEDBACK": {
            "host": GATEWAY_TLS_HOST,
            "port": 8086,
        },
        "AIRFLOW": {"host": "etl-airflow-webserver", "port": 8080},
        "LITELLM_PROXY": {"host": litellm_host, "port": litellm_port},
    }


def test_connectivity(
    host: str, port: int, service_name: str, verbose: bool = True
) -> bool:
    if verbose:
        logging.debug("Testando conexao %s(%s:%s)", service_name, host, port)
    try:
        with socket.create_connection((host, port), timeout=5):
            return True
    except (socket.timeout, socket.error) as exc:
        if verbose:
            logging.error("Falha ao conectar ao %s: %s", service_name, exc)
        return False


def test_connectivity_all(config: dict, verbose: bool = False) -> dict:
    results = {}
    for service_name, settings in config.items():
        host = settings["host"]
        port = settings["port"]
        results[service_name] = {
            "Reachable": test_connectivity(host, port, service_name, verbose),
            "Host": host,
            "Port": port,
        }
    return results


def get_health_testes_urls() -> dict:
    litellm_proxy_url = os.getenv("LITELLM_PROXY_URL") or "http://infra-litellm:4000"
    searx_base_url = os.getenv("SEARX_BASE_URL") or "http://infra-searxng:8080"
    gateway_url = f"https://{GATEWAY_TLS_HOST}"
    assistente_contract = [
        {"path": "/health", "expected_json": {"status": "OK"}},
        {
            "path": "/openapi.json",
            "openapi_operations": {
                "/llm_lang/session_stream": {"post": {"request_body": True}},
                "/feedback/feedback": {"post": {"request_body": True}},
            },
        },
    ]
    similaridade_contract = [
        {"path": "/health", "expected_json": {"status": "OK"}},
        {
            "path": "/openapi.json",
            "openapi_operations": {
                (
                    "/process-recommenders/weighted-mlt-recommender/"
                    "recommendations/{id_protocolo}"
                ): {
                    "get": {
                        "parameters": {
                            "id_protocolo": "path",
                            "id_user": "query",
                            "rows": "query",
                        }
                    }
                },
                (
                    "/process-recommenders/weighted-mlt-recommender/"
                    "indexed-ids/{id_protocolo}"
                ): {"get": {}},
                "/document-recommenders/mlt-recommender/recommendations": {
                    "get": {
                        "parameters": {
                            "list_id_doc": "query",
                            "text": "query",
                            "rows": "query",
                        }
                    }
                },
            },
        },
    ]
    feedback_contract = [
        {"path": "/health", "expected_json": {"status": "OK"}},
        {
            "path": "/openapi.json",
            "openapi_operations": {
                "/process-recommenders/feedbacks": {"post": {"request_body": True}},
                "/document-recommenders/feedbacks": {"post": {"request_body": True}},
            },
        },
    ]
    return {
        "similaridade": {
            "http://similaridade:8082": [
                *similaridade_contract,
                {"path": "/health/database"},
                {"path": "/health/solr"},
            ]
        },
        "similaridade_feedback": {
            "http://similaridade-feedback:8086": feedback_contract
        },
        "jobs_interna": {"http://etl-airflow-api:8642": [{"path": "/health"}]},
        "assistente": {"http://assistente:8088": assistente_contract},
        "gateway_assistente": {
            f"{gateway_url}:8088": [
                {**check, "verify": GATEWAY_CA_CERT} for check in assistente_contract
            ]
        },
        "gateway_similaridade": {
            f"{gateway_url}:8082": [
                {**check, "verify": GATEWAY_CA_CERT} for check in similaridade_contract
            ]
        },
        "gateway_similaridade_feedback": {
            f"{gateway_url}:8086": [
                {**check, "verify": GATEWAY_CA_CERT} for check in feedback_contract
            ]
        },
        "litellm_proxy": {
            litellm_proxy_url: [
                {
                    "path": "/health",
                    "headers": {
                        "Authorization": (
                            "Bearer " + (os.getenv("LITELLM_PROXY_API_KEY") or "")
                        )
                    },
                }
            ]
        },
        "searxng": {searx_base_url: [{"path": "/healthz"}]},
    }


health_testes_urls = get_health_testes_urls()


def _matches_openapi_operation(operation: Any, constraints: dict[str, Any]) -> bool:
    if not isinstance(operation, dict):
        return False
    request_body = constraints.get("request_body")
    if (
        request_body is not None
        and bool(operation.get("requestBody")) is not request_body
    ):
        return False
    actual_parameters = {
        parameter.get("name"): parameter.get("in")
        for parameter in operation.get("parameters") or []
        if isinstance(parameter, dict)
    }
    return all(
        actual_parameters.get(name) == location
        for name, location in (constraints.get("parameters") or {}).items()
    )


def _matches_http_contract(response: requests.Response, check: dict[str, Any]) -> bool:
    if response.status_code != check.get("expected_status", 200):
        return False
    expected_json = check.get("expected_json")
    openapi_operations = check.get("openapi_operations")
    if not expected_json and not openapi_operations:
        return True
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError:
        return False
    if expected_json and any(
        payload.get(key) != value for key, value in expected_json.items()
    ):
        return False
    paths = payload.get("paths") or {}
    return all(
        _matches_openapi_operation((paths.get(path) or {}).get(method), constraints)
        for path, expected_methods in (openapi_operations or {}).items()
        for method, constraints in expected_methods.items()
    )


def test_api_connectivity_and_response(api_url: str, check: dict[str, Any]) -> bool:
    try:
        headers = {"accept": "application/json", **check.get("headers", {})}
        response = requests.get(
            api_url,
            headers=headers,
            verify=check.get("verify", False),
            timeout=15,
        )
        return _matches_http_contract(response, check)
    except requests.exceptions.RequestException as exc:
        logging.error("Falha ao conectar a API %s: %s", api_url, exc)
        return False


def test_api_connectivity_and_response_all(
    health_tests_urls: dict, expected_status: int = 200
) -> list[dict]:
    report = []
    for servico in health_tests_urls:
        for url in health_tests_urls[servico]:
            for raw_check in health_tests_urls[servico][url]:
                check = (
                    {"path": raw_check, "expected_status": expected_status}
                    if isinstance(raw_check, str)
                    else {"expected_status": expected_status, **raw_check}
                )
                parsed_url = urlsplit(url)
                report.append(
                    {
                        "Servico": servico,
                        "Reachable": test_api_connectivity_and_response(
                            f"{url}{check['path']}", check
                        ),
                        "Host": parsed_url.hostname,
                        "Port": parsed_url.port,
                        "Endpoint": check["path"],
                    }
                )
    return report


def test_litellm_proxy_models(proxy_url: str | None = None) -> dict:
    # Cada alias fixo precisa existir com seus próprios papéis. Uma entrada extra
    # com a mesma tag não substitui o contrato chamado pelos clientes.
    if proxy_url is None:
        proxy_url = os.getenv("LITELLM_PROXY_URL") or "http://infra-litellm:4000"
    proxy_key = os.getenv("LITELLM_PROXY_API_KEY") or ""
    headers = {"Authorization": f"Bearer {proxy_key}"}

    result = {
        "proxy_health": False,
        "proxy_url": proxy_url,
        "models": {},
        "error": None,
    }

    try:
        health_response = requests.get(
            f"{proxy_url}/health/readiness", headers=headers, timeout=15
        )
        result["proxy_health"] = health_response.status_code == 200
        if not result["proxy_health"]:
            result["error"] = (
                f"Proxy health check falhou com status {health_response.status_code}"
            )
            return result

        models_response = requests.get(
            f"{proxy_url}/model/info", headers=headers, timeout=15
        )
        models_response.raise_for_status()
        models_data = models_response.json()
        entries = models_data.get("data", [])
        tags_by_alias: dict[str, set[str]] = {}
        for entry in entries:
            alias = entry.get("model_name")
            tags_by_alias.setdefault(alias, set()).update(
                entry.get("litellm_params", {}).get("tags") or []
            )

        for alias, required_tags in EXPECTED_LITELLM_ALIASES.items():
            tags = tags_by_alias.get(alias, set())
            missing_tags = sorted(set(required_tags) - tags)
            result["models"][alias] = {
                "available": alias in tags_by_alias and not missing_tags,
                "details": {"tags": sorted(tags), "missing_tags": missing_tags},
            }
        return result
    except requests.exceptions.RequestException as exc:
        result["error"] = f"Erro ao conectar ao LiteLLM Proxy: {exc}"
        return result
    except Exception as exc:
        result["error"] = f"Erro inesperado no teste do LiteLLM Proxy: {exc}"
        return result


def report_litellm_proxy_status(test_result: dict) -> int:
    logging.info("\n========== STATUS DO LITELLM PROXY ===========")
    logging.info("URL do Proxy: %s", test_result["proxy_url"])

    if not test_result["proxy_health"]:
        logging.error("LiteLLM Proxy nao esta saudavel.")
        if test_result["error"]:
            logging.error("Erro: %s", test_result["error"])
        return 1

    logging.info("LiteLLM Proxy esta saudavel.")
    missing_models = []
    for alias, model_info in test_result["models"].items():
        if model_info["available"]:
            logging.info(
                "Alias '%s' esta disponivel (%s).",
                alias,
                model_info["details"]["tags"],
            )
        else:
            logging.error("Alias '%s' ausente ou com papeis incompletos.", alias)
            missing_models.append(alias)

    if test_result["error"]:
        logging.error("Erro durante o teste: %s", test_result["error"])
        return 1
    if missing_models:
        logging.error(
            "Aliases invalidos no LiteLLM Proxy: %s", ", ".join(missing_models)
        )
        return len(missing_models)

    logging.info("Todos os modelos esperados estao disponiveis no LiteLLM Proxy.")
    return 0
