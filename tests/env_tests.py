"""Validacoes de env adaptadas ao monorepo."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import pandas as pd

env_vars = {
    "security": {
        "geral": ["ENVIRONMENT", "GID_DOCKER"],
        "db_interno": ["DB_SEIIA_USER", "DB_SEIIA_PWD"],
        "airflow": [
            "AIRFLOW_POSTGRES_DB",
            "AIRFLOW_POSTGRES_USER",
            "AIRFLOW_AMQP_USER",
            "_AIRFLOW_WWW_USER_USERNAME",
            "_AIRFLOW_WWW_USER_PASSWORD",
            "AIRFLOW_POSTGRES_PASSWORD",
            "AIRFLOW_AMQP_PASSWORD",
            "AIRFLOW__WEBSERVER__SECRET_KEY",
        ],
        "solr": ["SOLR_USER", "SOLR_PASSWORD"],
        "litellm": ["OPENAI_API_VERSION"],
        "sei_api": ["SEI_ADDRESS", "SEI_API_DB_IDENTIFIER_SERVICE"],
        "azure_websearch": [
            "PROJECT_ENDPOINT",
            "MODEL_DEPLOYMENT_NAME",
            "AZURE_CLIENT_ID",
            "AZURE_CLIENT_SECRET",
            "AZURE_TENANT_ID",
            "AZURE_WEB_AGENT_ID",
            "BING_CONNECTION_NAME",
        ],
    },
    "default": {
        "deploy": ["COMPOSE_NETWORK_NAME"],
        "geral": ["PROJECT_NAME", "NB_USER", "NB_UID", "NB_GID", "VOL_SEIIA_DIR", "TZ", "LOG_LEVEL"],
        "airflow_base": ["AIRFLOW_UID"],
        "airflow_core": [
            "AIRFLOW__CORE__DEFAULT_TIMEZONE",
            "AIRFLOW__CORE__EXECUTOR",
            "AIRFLOW__CORE__PARALLELISM",
            "AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG",
            "AIRFLOW__CORE__ALLOWED_DESERIALIZATION_CLASSES",
            "AIRFLOW__CORE__DAGBAG_IMPORT_TIMEOUT",
            "AIRFLOW__CORE__DAG_FILE_PROCESSOR_TIMEOUT",
            "AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION",
            "AIRFLOW__CORE__TEST_CONNECTION",
            "AIRFLOW__CORE__MIN_SERIALIZED_DAG_UPDATE_INTERVAL",
            "AIRFLOW__CORE__MIN_SERIALIZED_DAG_FETCH_INTERVAL",
            "AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG",
        ],
        "airflow_webserver": [
            "AIRFLOW__WEBSERVER__DEFAULT_UI_TIMEZONE",
            "AIRFLOW__WEBSERVER__EXPOSE_CONFIG",
            "AIRFLOW__WEBSERVER__WEB_SERVER_MASTER_TIMEOUT",
            "AIRFLOW__WEBSERVER__WORKERS",
        ],
        "airflow_celery": [
            "AIRFLOW__CELERY__CELERY_APP_NAME",
            "AIRFLOW__CELERY__SYNC_PARALLELISM",
            "AIRFLOW__CELERY__OPERATION_TIMEOUT",
            "AIRFLOW__CELERY__TASK_TRACK_STARTED",
            "AIRFLOW__CELERY__TASK_PUBLISH_MAX_RETRIES",
            "AIRFLOW__CELERY__WORKER_PRECHECK",
            "AIRFLOW__CELERY__WORKER_TASK_LOG_READ_TIMEOUT",
            "AIRFLOW__CELERY__BROKER_CONNECTION_TIMEOUT",
            "AIRFLOW__CELERY__WORKER_CONCURRENCY",
            "AIRFLOW__CELERY_BROKER_TRANSPORT_OPTIONS__VISIBILITY_TIMEOUT",
        ],
        "airflow_scheduler": [
            "AIRFLOW__SCHEDULER__MAX_TIS_PER_QUERY",
            "AIRFLOW__SCHEDULER__PARSING_PROCESSES",
            "AIRFLOW__SCHEDULER__TASK_QUEUED_TIMEOUT",
            "AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK",
            "AIRFLOW__SCHEDULER__CATCHUP_BY_DEFAULT",
        ],
        "airflow_api": ["AIRFLOW__API__AUTH_BACKENDS"],
        "airflow_sensors": ["AIRFLOW__SENSORS__DEFAULT_TIMEOUT"],
        "airflow_resources": [
            "AIRFLOW_WORKERS_REPLICAS",
            "AIRFLOW_WORKER_MEM_LIMIT",
            "AIRFLOW_WORKER_CPU_LIMIT",
            "AIRFLOW_POSTGRES_MEM_LIMIT",
            "AIRFLOW_POSTGRES_CPU_LIMIT",
            "AIRFLOW_WEBSERVER_MEM_LIMIT",
            "AIRFLOW_WEBSERVER_CPU_LIMIT",
            "AIRFLOW_SCHEDULER_MEM_LIMIT",
            "AIRFLOW_SCHEDULER_CPU_LIMIT",
            "AIRFLOW_SCHEDULER_CPU_SHARES",
            "AIRFLOW_TRIGGERER_MEM_LIMIT",
            "AIRFLOW_TRIGGERER_CPU_LIMIT",
        ],
        "db_interno": [
            "DB_SEIIA_HOST",
            "DB_SEIIA_PORT",
            "DB_SEIIA_ASSISTENTE",
            "DB_SEIIA_SIMILARIDADE",
            "DB_SEIIA_ASSISTENTE_SCHEMA",
        ],
        "solr": [
            "SOLR_HOST",
            "SOLR_ADDRESS",
            "SOLR_MLT_JURISPRUDENCE_CORE",
            "SOLR_MLT_PROCESS_CORE",
            "SOLR_JAVA_MEM",
            "SOLR_MEM_LIMIT",
            "SOLR_CPU_LIMIT",
        ],
        "assistente": [
            "ASSISTENTE_MAX_RETRIES",
            "ASSISTENTE_TIMEOUT_API",
            "ASSISTENTE_MAX_LENGTH_CHUNK_SIZE",
            "ASSISTENTE_CHUNK_OVERLAP",
            "ASSISTENTE_DEFAULT_RESPONSE_MODEL",
            "ASSISTENTE_EMBEDDING_MODEL",
            "ASSISTENTE_EMBEDDING_ENCODING_NAME",
            "ASSISTENTE_OUTPUT_TOKENS_STANDARD_MODEL",
            "ASSISTENTE_OUTPUT_TOKENS_MINI_MODEL",
            "ASSISTENTE_OUTPUT_TOKENS_THINK_MODEL",
            "ASSISTENTE_CTX_LEN_STANDARD_MODEL",
            "ASSISTENTE_CTX_LEN_MINI_MODEL",
            "ASSISTENTE_CTX_LEN_THINK_MODEL",
            "ASSISTENTE_SUMMARIZE_MODEL",
            "ASSISTENTE_SUMMARIZE_CHUNK_SIZE",
            "ASSISTENTE_SUMMARIZE_CHUNK_MAX_OUTPUT",
            "ASSISTENTE_LITELLM_PROXY_URL",
            "ASSISTENTE_USE_LANGFUSE",
            "ASSISTENTE_MEM_LIMIT",
            "ASSISTENTE_CPU_LIMIT",
            "ASSISTENTE_NGINX_MEM_LIMIT",
            "ASSISTENTE_NGINX_CPU_LIMIT",
            "ASSISTENTE_CONTEXT_MAX_TOKENS",
            "ASSISTENTE_FATOR_LIMITAR_RAG",
            "ASSISTENTE_OCR_MAX_CONCURRENT_PAGES",
        ],
        "apps": [
            "API_SEI_MEM_LIMIT",
            "API_SEI_CPU_LIMIT",
            "APP_API_MEM_LIMIT",
            "APP_API_CPU_LIMIT",
            "EMBEDDING_MAX_ACTIVE_RUNS",
            "LITELLM_CPU_LIMIT",
            "LITELLM_MEM_LIMIT",
            "LITELLM_LOG_LEVEL",
            "PGVECTOR_CPU_LIMIT",
            "PGVECTOR_MEM_LIMIT",
            "RABBITMQ_CPU_LIMIT",
            "RABBITMQ_MEM_LIMIT",
            "SEI_API_DB_TIMEOUT",
            "SEI_API_DB_USER",
        ],
    },
}

allowed_empty_vars = [
    "COMPOSE_NETWORK_NAME",
    "ASSISTENTE_LITELLM_PROXY_API_KEY",
    "LANGFUSE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_SECRET_SALT",
    "LANGFUSE_NEXTAUTH_SECRET",
]
allowed_extra_vars = [
    "ASSISTENTE_LITELLM_PROXY_API_KEY",
    "LANGFUSE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_SECRET_SALT",
    "LANGFUSE_NEXTAUTH_SECRET",
]
anon_variables = []


def create_env_vars_df(env_vars: dict) -> pd.DataFrame:
    dfs = []
    for category, subcategories in env_vars.items():
        for subcategory, variables in subcategories.items():
            dfs.append(
                pd.DataFrame(
                    data={
                        "file": category,
                        "categoria": subcategory,
                        "variavel": variables,
                    },
                    index=range(len(variables)),
                )
            )
    return pd.concat(dfs, ignore_index=True)


def load_env_file(file_path: str) -> pd.DataFrame:
    with open(file_path, encoding="utf-8") as file:
        lines = file.readlines()

    parsed_lines = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.replace("export ", "", 1)
        if "=" not in line:
            continue
        var_name, var_value = line.split("=", 1)
        value = var_value.strip()
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        if value.startswith(("\"", "'")) and value.endswith(("\"", "'")):
            value = value[1:-1]
        parsed_lines.append([var_name.strip(), value])
    return pd.DataFrame(parsed_lines, columns=["variavel", "value"])


def validate_specific_variables(comparison_df: pd.DataFrame) -> pd.DataFrame:
    def validate_url(value: object) -> bool:
        return bool(isinstance(value, str) and re.match(r"^(http|https)://\S+$", value))

    def validate_environment(value: object) -> bool:
        return bool(isinstance(value, str) and value in ["prod", "dev", "homol"])

    validations = {
        "ASSISTENTE_LITELLM_PROXY_URL": validate_url,
        "SOLR_ADDRESS": validate_url,
        "ENVIRONMENT": validate_environment,
    }

    if "valid" not in comparison_df.columns:
        comparison_df["valid"] = True

    for var, validation_func in validations.items():
        mask = comparison_df["variavel"] == var
        if mask.any():
            comparison_df.loc[mask, "valid"] = comparison_df.loc[mask, "value"].apply(
                validation_func
            )
    return comparison_df


def consolidate_env_files(categories: list[str]) -> pd.DataFrame:
    env_df = pd.DataFrame()
    mapping = {"default": "default.env", "security": "security.env"}
    for category in categories:
        temp_df = load_env_file(mapping[category])
        temp_df["file"] = category
        env_df = pd.concat([env_df, temp_df], ignore_index=True)
    return env_df


def compare_env_variables(
    variables_df: pd.DataFrame,
    env_df: pd.DataFrame,
    allowed_empty_vars: list | None = None,
    allowed_extra_vars: list | None = None,
) -> tuple[dict, pd.DataFrame]:
    allowed_empty_vars = allowed_empty_vars or []
    allowed_extra_vars = allowed_extra_vars or []

    comparison_df = variables_df.merge(env_df, how="outer", indicator=True)
    comparison_df = validate_specific_variables(comparison_df)

    missing_vars = comparison_df[comparison_df["_merge"] == "left_only"]
    extra_vars = comparison_df[
        (comparison_df["_merge"] == "right_only")
        & (~comparison_df["variavel"].isin(allowed_extra_vars))
    ]
    empty_vars = comparison_df[
        (
            comparison_df["value"].isna()
            | comparison_df["value"].isin(["*****", "<VALOR>", "", "\"\""])
        )
        & (~comparison_df["variavel"].isin(allowed_empty_vars))
    ]
    duplicated_vars = env_df[env_df.duplicated(subset=["file", "variavel"], keep=False)]
    invalid_vars = comparison_df[comparison_df["valid"] == False]

    results = {
        "missing": missing_vars[["file", "categoria", "variavel", "value"]],
        "extra": extra_vars[["file", "categoria", "variavel", "value"]],
        "empty": empty_vars[["file", "categoria", "variavel", "value"]],
        "duplicated": duplicated_vars[["file", "variavel", "value"]],
        "invalid": invalid_vars[["file", "variavel", "value"]],
    }
    return results, comparison_df


def report_env_issues(results: dict) -> int:
    error = 0
    if not results["missing"].empty:
        logging.error("\nExistem variaveis faltando nos arquivos .env:\n")
        logging.error(results["missing"].to_markdown(index=False))
        error += len(results["missing"])
    if not results["extra"].empty:
        logging.warning("\nExistem variaveis sobrando nos arquivos .env:\n")
        logging.warning(results["extra"].to_markdown(index=False))
    if not results["duplicated"].empty:
        logging.warning("\nExistem variaveis duplicadas nos arquivos .env:\n")
        logging.warning(results["duplicated"].to_markdown(index=False))
        error += len(results["duplicated"])
    if not results["empty"].empty:
        logging.error("\nExistem variaveis vazias nos arquivos .env:\n")
        logging.error(results["empty"].to_markdown(index=False))
        error += len(results["empty"])
    if not results["invalid"].empty:
        logging.error("\nExistem variaveis com valores invalidos nos arquivos .env:\n")
        logging.error(results["invalid"].to_markdown(index=False))
        error += len(results["invalid"])
    if error == 0:
        logging.info("\nNao foram encontrados erros nos arquivos .env.\n")
    return error


def anonymize_and_save(comparison_df: pd.DataFrame, path: str, anonymize_variables: list[str]) -> None:
    df_anonymized = comparison_df.copy()
    df_anonymized.loc[
        df_anonymized["variavel"].isin(anonymize_variables), "value"
    ] = "ANONYMIZED"
    Path(path).mkdir(parents=True, exist_ok=True)
    df_anonymized.to_csv(f"{path}/comparison_df.csv", index=False)
    logging.info("Arquivo comparison_df salvo em: %s", path)


if __name__ == "__main__":
    variables_df = create_env_vars_df(env_vars)
    env_df = consolidate_env_files(["security", "default"])
    results, comparison_df = compare_env_variables(
        variables_df, env_df, allowed_empty_vars, allowed_extra_vars
    )
    errors = report_env_issues(results)
    anonymize_and_save(comparison_df, "output", anon_variables)
    sys.exit(errors)
