"""Testes de conectividade do healthchecker local."""

from __future__ import annotations

import logging
import os
import socket
import warnings

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


def create_postgres_config(
    comparison_df: pd.DataFrame,
) -> tuple[dict, DBConnector | None, DBConnector | None]:
    try:
        postgres_user = comparison_df[
            comparison_df["variavel"] == "DB_SEIIA_USER"
        ]["value"].values[0]
        postgres_password = comparison_df[
            comparison_df["variavel"] == "DB_SEIIA_PWD"
        ]["value"].values[0]
        pgvector_host = comparison_df[
            comparison_df["variavel"] == "DB_SEIIA_HOST"
        ]["value"].values[0]
        pgvector_port = comparison_df[
            comparison_df["variavel"] == "DB_SEIIA_PORT"
        ]["value"].values[0]
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
            "core": comparison_df[
                comparison_df["variavel"] == "SOLR_MLT_PROCESS_CORE"
            ]["value"].values[0],
            "interno": True,
        },
    }


def verify_solr_status(host: str, port: int, core: str, interno: bool, verbose: bool = False) -> dict:
    try:
        url = f"https://{host}:{port}/solr/{core}/admin/ping"
        response = requests.get(
            url,
            verify=False,
            auth=HTTPBasicAuth(os.getenv("SOLR_USER"), os.getenv("SOLR_PASSWORD")),
            timeout=10,
        )
        response.raise_for_status()
        return {"Reachable": response.status_code == 200, "Host": host, "Port": port, "Core": core}
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


def connectivity_report(results: dict, return_df: bool = False, path: str | None = None) -> tuple[int, pd.DataFrame | None]:
    try:
        results_df = pd.DataFrame.from_dict(results, orient="index")
    except Exception:
        results_df = pd.DataFrame.from_dict(results)

    error_count = len(results_df[results_df["Reachable"] == False])
    if error_count > 0:
        logging.error("\nHouve falha nos testes abaixo:\n")
        logging.error(results_df[results_df["Reachable"] == False].to_markdown())
    else:
        logging.info("\nTodos os testes passaram.\n")

    if path:
        results_df.to_csv(path, index=False)
    if return_df:
        return error_count, results_df
    return error_count, None


def create_connectivity_config(comparison_df: pd.DataFrame) -> dict:
    litellm_proxy_url = (
        os.getenv("LITELLM_PROXY_URL")
        or os.getenv("ASSISTENTE_LITELLM_PROXY_URL")
        or "http://infra-litellm:4000"
    )
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
        "API_AIRFLOW": {"host": "etl-airflow-api", "port": 8642},
        "API_ASSISTENTE": {"host": "assistente", "port": 8088},
        "NGINX_ASSISTENTE": {"host": "assistente-nginx", "port": 443},
        "AIRFLOW": {"host": "etl-airflow-webserver", "port": 8080},
        "LITELLM_PROXY": {"host": litellm_host, "port": litellm_port},
    }


def test_connectivity(host: str, port: int, service_name: str, verbose: bool = True) -> bool:
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
    litellm_proxy_url = (
        os.getenv("LITELLM_PROXY_URL")
        or os.getenv("ASSISTENTE_LITELLM_PROXY_URL")
        or "http://infra-litellm:4000"
    )
    return {
        "similaridade": {
            "http://similaridade:8082": ["/health", "/health/database", "/health/solr"]
        },
        "similaridade_feedback": {"http://similaridade-feedback:8086": ["/health"]},
        "etl_airflow_api": {"http://etl-airflow-api:8642": ["/health"]},
        "assistente": {"http://assistente:8088": ["/health"]},
        "assistente_nginx": {"https://assistente-nginx:443": ["/health"]},
        "litellm_proxy": {litellm_proxy_url: ["/health"]},
    }


health_testes_urls = get_health_testes_urls()


def test_api_connectivity_and_response(api_url: str, expected_status: int = 200) -> bool:
    try:
        response = requests.get(
            api_url,
            headers={"accept": "application/json"},
            verify=False,
            timeout=15,
        )
        return response.status_code == expected_status
    except requests.exceptions.RequestException as exc:
        logging.error("Falha ao conectar a API %s: %s", api_url, exc)
        return False


def test_api_connectivity_and_response_all(
    health_tests_urls: dict, expected_status: int = 200
) -> list[dict]:
    report = []
    for servico in health_tests_urls.keys():
        for url in health_tests_urls[servico]:
            for check in health_tests_urls[servico][url]:
                report.append(
                    {
                        "Servico": servico,
                        "Reachable": test_api_connectivity_and_response(
                            f"{url}{check}", expected_status
                        ),
                        "Host": url.split(":")[1].replace("//", ""),
                        "Port": url.split(":")[2],
                        "Endpoint": check,
                    }
                )
    return report


def test_litellm_proxy_models(proxy_url: str | None = None) -> dict:
    expected_models = ["standard", "mini", "think", "embedding"]
    if proxy_url is None:
        proxy_url = (
            os.getenv("LITELLM_PROXY_URL")
            or os.getenv("ASSISTENTE_LITELLM_PROXY_URL")
            or "http://infra-litellm:4000"
        )

    result = {
        "proxy_health": False,
        "proxy_url": proxy_url,
        "models": {},
        "error": None,
    }

    try:
        health_response = requests.get(f"{proxy_url}/health", timeout=10)
        result["proxy_health"] = health_response.status_code == 200
        if not result["proxy_health"]:
            result["error"] = f"Proxy health check falhou com status {health_response.status_code}"
            return result

        models_response = requests.get(f"{proxy_url}/model/info", timeout=15)
        models_response.raise_for_status()
        models_data = models_response.json()
        available_models = {
            model.get("model_name"): model for model in models_data.get("data", [])
        }

        for model_name in expected_models:
            result["models"][model_name] = {
                "available": model_name in available_models,
                "details": available_models.get(model_name, {}),
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
    for model_name, model_info in test_result["models"].items():
        if model_info["available"]:
            logging.info("Modelo '%s' esta disponivel.", model_name)
        else:
            logging.error("Modelo '%s' NAO esta disponivel.", model_name)
            missing_models.append(model_name)

    if test_result["error"]:
        logging.error("Erro durante o teste: %s", test_result["error"])
        return 1
    if missing_models:
        logging.error("Modelos faltando no LiteLLM Proxy: %s", ", ".join(missing_models))
        return len(missing_models)

    logging.info("Todos os modelos esperados estao disponiveis no LiteLLM Proxy.")
    return 0
