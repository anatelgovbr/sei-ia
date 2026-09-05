"""Validacoes de env adaptadas ao monorepo."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import pandas as pd

env_vars = {
    "security": {
        "geral": ["ENVIRONMENT"],
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
        "litellm": [
            "LITELLM_EMBEDDING_API_BASE",
            "LITELLM_EMBEDDING_API_KEY",
            "LITELLM_EMBEDDING_API_VERSION",
            "LITELLM_EMBEDDING_MODEL",
            "LITELLM_MINI_API_BASE",
            "LITELLM_MINI_API_KEY",
            "LITELLM_MINI_API_VERSION",
            "LITELLM_MINI_MODEL",
            "LITELLM_NANO_API_BASE",
            "LITELLM_NANO_API_KEY",
            "LITELLM_NANO_API_VERSION",
            "LITELLM_NANO_MODEL",
            "LITELLM_PROXY_API_KEY",
            "LITELLM_STANDARD_API_BASE",
            "LITELLM_STANDARD_API_KEY",
            "LITELLM_STANDARD_API_VERSION",
            "LITELLM_STANDARD_MODEL",
            "LITELLM_STT_API_BASE",
            "LITELLM_STT_API_KEY",
            "LITELLM_STT_API_VERSION",
            "LITELLM_STT_MODEL",
        ],
        "gateway_tls": [
            "SEIIA_GATEWAY_HOST",
            "SEIIA_CERT_DNS",
        ],
        "observabilidade": [
            "LANGFUSE_URL",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
        ],
        "sei_api": ["SEI_ADDRESS", "SEI_API_DB_IDENTIFIER_SERVICE"],
        "searxng": ["SEARXNG_SECRET_KEY"],
    },
    "default": {
        "deploy": ["COMPOSE_NETWORK_NAME"],
        "geral": [
            "NB_USER",
            "NB_UID",
            "NB_GID",
            "VOL_SEIIA_DIR",
            "TZ",
            "LOG_LEVEL",
        ],
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
            "AIRFLOW_INIT_MEM_LIMIT",
            "AIRFLOW_INIT_CPU_LIMIT",
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
            "SOLR_READ_TIMEOUT_SECONDS",
            "SOLR_JAVA_MEM",
            "SOLR_MEM_LIMIT",
            "SOLR_CPU_LIMIT",
        ],
        "assistente": [
            "ASSISTENTE_MAX_RETRIES",
            "ASSISTENTE_SEI_API_MAX_RETRIES",
            "ASSISTENTE_TIMEOUT_API",
            "ASSISTENTE_STREAMING_HEARTBEAT_INTERVAL",
            "ASSISTENTE_MAX_LENGTH_CHUNK_SIZE",
            "ASSISTENTE_CHUNK_OVERLAP",
            "ASSISTENTE_DEFAULT_RESPONSE_MODEL",
            "EMBEDDING_MODEL",
            "EMBEDDING_DIM",
            "ASSISTENTE_EMBEDDING_ENCODING_NAME",
            "ASSISTENTE_OUTPUT_TOKENS_STANDARD_MODEL",
            "ASSISTENTE_OUTPUT_TOKENS_MINI_MODEL",
            "ASSISTENTE_CTX_LEN_STANDARD_MODEL",
            "ASSISTENTE_CTX_LEN_MINI_MODEL",
            "ASSISTENTE_SUMMARIZE_MODEL",
            "ASSISTENTE_SUMMARIZE_CHUNK_SIZE",
            "ASSISTENTE_SUMMARIZE_CHUNK_MAX_OUTPUT",
            "LITELLM_PORT",
            "ASSISTENTE_LITELLM_PROXY_URL",
            "ASSISTENTE_PORT",
            "REDIS_URI",
            "ASSISTENTE_CACHE_TTL_SECONDS",
            "ASSISTENTE_CACHE_MAX_CONNECTIONS",
            "ASSISTENTE_CACHE_POOL_WAIT_TIMEOUT",
            "ASSISTENTE_SESSIONS_ROOT",
            "ASSISTENTE_SESSION_TTL_SECONDS",
            "ASSISTENTE_SESSION_MAX_FILE_SIZE_MB",
            "ASSISTENTE_SESSION_SWEEPER_INTERVAL_SECONDS",
            "ASSISTENTE_SESSION_MAIN_MODEL",
            "ASSISTENTE_SESSION_EXPLORER_MODEL",
            "ASSISTENTE_SESSION_CLASSIFIER_MODEL",
            "ASSISTENTE_SESSION_CHECKPOINTER_SCHEMA",
            "ASSISTENTE_SESSION_PREPARATION_HEARTBEAT_INTERVAL_SECONDS",
            "ASSISTENTE_SESSION_AGENT_HEARTBEAT_INTERVAL_SECONDS",
            "ASSISTENTE_USE_LANGFUSE",
            "ASSISTENTE_LANGFUSE_TRUNCATE_PAYLOADS",
            "ASSISTENTE_MEM_LIMIT",
            "ASSISTENTE_CPU_LIMIT",
            "GATEWAY_NGINX_MEM_LIMIT",
            "GATEWAY_NGINX_CPU_LIMIT",
            "ASSISTENTE_FATOR_LIMITAR_RAG",
            "OCR_MAX_CONCURRENT_PAGES",
        ],
        "apps": [
            "API_SEI_MEM_LIMIT",
            "API_SEI_CPU_LIMIT",
            "APP_API_MEM_LIMIT",
            "APP_API_CPU_LIMIT",
            "EMBEDDING_MAX_ACTIVE_RUNS",
            "ETL_AIRFLOW_API_CPU_LIMIT",
            "ETL_AIRFLOW_API_MEM_LIMIT",
            "LITELLM_CPU_LIMIT",
            "LITELLM_MEM_LIMIT",
            "PGVECTOR_CPU_LIMIT",
            "PGVECTOR_MEM_LIMIT",
            "RABBITMQ_CPU_LIMIT",
            "RABBITMQ_MEM_LIMIT",
            "REDIS_CPU_LIMIT",
            "REDIS_MEM_LIMIT",
            "SEI_API_DB_TIMEOUT",
            "SEI_API_DB_USER",
            "STACK_CONFIG_CHECKER_CPU_LIMIT",
            "STACK_CONFIG_CHECKER_MEM_LIMIT",
        ],
        "web_search": [
            "SEARX_BASE_URL",
            "SEARXNG_MEM_LIMIT",
            "SEARXNG_CPU_LIMIT",
            "FASTCRW_BASE_URL",
            "FASTCRW_MEM_LIMIT",
            "FASTCRW_CPU_LIMIT",
            "BYPARR_BASE_URL",
            "BYPARR_MEM_LIMIT",
            "BYPARR_CPU_LIMIT",
            "MARKER_BASE_URL",
            "MARKER_MEM_LIMIT",
            "MARKER_CPU_LIMIT",
            "CHROME_MEM_LIMIT",
            "CHROME_CPU_LIMIT",
            "LIGHTPANDA_MEM_LIMIT",
            "LIGHTPANDA_CPU_LIMIT",
        ],
    },
}

allowed_empty_vars = [
    "LANGFUSE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LITELLM_EMBEDDING_API_VERSION",
    "LITELLM_MINI_API_VERSION",
    "LITELLM_NANO_API_VERSION",
    "LITELLM_STANDARD_API_VERSION",
    "LITELLM_STT_API_VERSION",
    "SEIIA_CERT_DNS",
]
allowed_extra_vars: list[str] = []


def is_sensitive_variable(variable: str) -> bool:
    return bool(
        re.search(
            r"(?:KEY|SECRET|PASSWORD|PWD|TOKEN|IDENTIFIER_SERVICE)$",
            variable,
        )
    )


ALL_ENV_VARIABLES = {
    variable
    for file_vars in env_vars.values()
    for category_vars in file_vars.values()
    for variable in category_vars
}
anon_variables = sorted(
    variable for variable in ALL_ENV_VARIABLES if is_sensitive_variable(variable)
)


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
        if value.startswith(('"', "'")):
            quote = value[0]
            closing = value.find(quote, 1)
            if closing >= 0:
                value = value[1:closing]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        parsed_lines.append([var_name.strip(), value])
    return pd.DataFrame(parsed_lines, columns=["variavel", "value"])


def validate_specific_variables(comparison_df: pd.DataFrame) -> pd.DataFrame:
    def validate_url(value: object) -> bool:
        return bool(isinstance(value, str) and re.match(r"^(http|https)://\S+$", value))

    def validate_environment(value: object) -> bool:
        return bool(isinstance(value, str) and value in ["prod", "dev", "homol"])

    def validate_dns_name(value: object) -> bool:
        if not isinstance(value, str) or not value or len(value) > 253:
            return False
        labels = value.split(".")
        return all(
            len(label) <= 63
            and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
            for label in labels
        )

    def validate_optional_url(value: object) -> bool:
        return value == "" or validate_url(value)

    def validate_optional_dns_list(value: object) -> bool:
        if not isinstance(value, str) or value == "":
            return value == ""
        names = [name.strip() for name in value.split(",")]
        return all(names) and all(validate_dns_name(name) for name in names)

    def validate_positive_integer(value: object) -> bool:
        return bool(isinstance(value, str) and value.isdigit() and int(value) > 0)

    def validate_proxy_key(value: object) -> bool:
        return bool(
            isinstance(value, str) and value.startswith("sk-") and len(value) > 8
        )

    def validate_absolute_data_path(value: object) -> bool:
        return bool(isinstance(value, str) and value.startswith("/") and value != "/")

    validations = {
        "ASSISTENTE_LITELLM_PROXY_URL": validate_url,
        "LITELLM_MINI_API_BASE": validate_url,
        "LITELLM_NANO_API_BASE": validate_url,
        "LITELLM_STANDARD_API_BASE": validate_url,
        "LITELLM_EMBEDDING_API_BASE": validate_url,
        "LITELLM_STT_API_BASE": validate_url,
        "SOLR_ADDRESS": validate_url,
        "SEI_ADDRESS": validate_url,
        "ENVIRONMENT": validate_environment,
        "SEIIA_GATEWAY_HOST": validate_dns_name,
        "SEIIA_CERT_DNS": validate_optional_dns_list,
        "LANGFUSE_URL": validate_optional_url,
        "LITELLM_PROXY_API_KEY": validate_proxy_key,
        "NB_UID": validate_positive_integer,
        "NB_GID": validate_positive_integer,
        "AIRFLOW_WORKERS_REPLICAS": validate_positive_integer,
        "VOL_SEIIA_DIR": validate_absolute_data_path,
    }

    if "valid" not in comparison_df.columns:
        comparison_df["valid"] = True

    for var, validation_func in validations.items():
        mask = (comparison_df["variavel"] == var) & (comparison_df["_merge"] == "both")
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
        (comparison_df["_merge"] == "both")
        & (
            comparison_df["value"].isna()
            | comparison_df["value"].isin(["*****", "<VALOR>", "", '""'])
        )
        & (~comparison_df["variavel"].isin(allowed_empty_vars))
    ]
    duplicated_vars = env_df[env_df.duplicated(subset=["variavel"], keep=False)]
    invalid_vars = comparison_df[~comparison_df["valid"]]

    results = {
        "missing": missing_vars[["file", "categoria", "variavel", "value"]],
        "extra": extra_vars[["file", "categoria", "variavel", "value"]],
        "empty": empty_vars[["file", "categoria", "variavel", "value"]],
        "duplicated": duplicated_vars[["file", "variavel", "value"]],
        "invalid": invalid_vars[["file", "variavel", "value"]],
    }
    return results, comparison_df


def report_env_issues(results: dict) -> int:
    def safe_markdown(frame: pd.DataFrame) -> str:
        redacted = frame.copy()
        if "value" in redacted.columns:
            sensitive = redacted["variavel"].astype(str).map(is_sensitive_variable)
            if "file" in redacted.columns:
                sensitive |= redacted["file"].eq("security")
            redacted.loc[sensitive, "value"] = "ANONYMIZED"
        return redacted.to_markdown(index=False)

    error = 0
    if not results["missing"].empty:
        logging.error("\nExistem variaveis faltando nos arquivos .env:\n")
        logging.error(safe_markdown(results["missing"]))
        error += len(results["missing"])
    if not results["extra"].empty:
        logging.error("\nExistem variaveis sobrando nos arquivos .env:\n")
        logging.error(safe_markdown(results["extra"]))
        error += len(results["extra"])
    if not results["duplicated"].empty:
        logging.error("\nExistem variaveis duplicadas nos arquivos .env:\n")
        logging.error(safe_markdown(results["duplicated"]))
        error += len(results["duplicated"])
    if not results["empty"].empty:
        logging.error("\nExistem variaveis vazias nos arquivos .env:\n")
        logging.error(safe_markdown(results["empty"]))
        error += len(results["empty"])
    if not results["invalid"].empty:
        logging.error("\nExistem variaveis com valores invalidos nos arquivos .env:\n")
        logging.error(safe_markdown(results["invalid"]))
        error += len(results["invalid"])
    if error == 0:
        logging.info("\nNao foram encontrados erros nos arquivos .env.\n")
    return error


def anonymize_and_save(
    comparison_df: pd.DataFrame, path: str, anonymize_variables: list[str]
) -> None:
    df_anonymized = comparison_df.copy()
    sensitive = df_anonymized["variavel"].astype(str).map(is_sensitive_variable)
    sensitive |= df_anonymized["variavel"].isin(anonymize_variables)
    if "file" in df_anonymized.columns:
        sensitive |= df_anonymized["file"].eq("security")
    df_anonymized.loc[sensitive, "value"] = "ANONYMIZED"
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
