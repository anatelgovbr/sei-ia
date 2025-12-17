"""
Modulo de testes dos arquivos .env.

Este módulo permite validar a presença, ausência, duplicação e preenchimento de variáveis de ambiente
em arquivos `.env` com base em uma estrutura esperada.

Exemplo de uso:
variables_df = create_env_vars_df(env_vars)
env_df = consolidate_env_files(['security', 'prod', 'default'])
results, comparison_df = compare_env_variables(variables_df, env_df, allowed_empty_vars, allowed_extra_vars)
errors = report_env_issues(results)
"""

import re
import pandas as pd
import logging

env_vars = {
    "security": {
        "geral": [
            "ENVIRONMENT",
            "GID_DOCKER",
        ],
        "DB_INTERNO": [
            "DB_SEIIA_USER",
            "DB_SEIIA_PWD",
        ],
        "AIRFLOW": [
            "_AIRFLOW_WWW_USER_USERNAME",
            "_AIRFLOW_WWW_USER_PASSWORD",
            "AIRFLOW_POSTGRES_USER",
            "AIRFLOW_POSTGRES_PASSWORD",
            "AIRFLOW_AMQP_USER",
            "AIRFLOW_AMQP_PASSWORD"
        ],
        "SEI_API_DB": [
            "SEI_ADDRESS",
            "SEI_API_DB_IDENTIFIER_SERVICE",
            "SEI_API_DB_TIMEOUT",
            "SEI_API_DB_USER"
        ],
        "ASSISTENTE": [
            "OPENAI_API_VERSION",
            "ASSISTENTE_EMBEDDING_MODEL",
            "ASSISTENTE_EMBEDDING_API_KEY",
            "ASSISTENTE_EMBEDDING_ENDPOINT",
            "ASSISTENTE_DEFAULT_RESPONSE_MODEL",
            "ASSISTENTE_API_KEY_STANDARD_MODEL",
            "ASSISTENTE_ENDPOINT_STANDARD_MODEL",
            "ASSISTENTE_NAME_STANDARD_MODEL",
            "ASSISTENTE_OUTPUT_TOKENS_STANDARD_MODEL",
            "ASSISTENTE_CTX_LEN_STANDARD_MODEL",
            "ASSISTENTE_API_KEY_MINI_MODEL",
            "ASSISTENTE_ENDPOINT_MINI_MODEL",
            "ASSISTENTE_NAME_MINI_MODEL",
            "ASSISTENTE_OUTPUT_TOKENS_MINI_MODEL",
            "ASSISTENTE_CTX_LEN_MINI_MODEL",
            "ASSISTENTE_API_KEY_THINK_MODEL",
            "ASSISTENTE_ENDPOINT_THINK_MODEL",
            "ASSISTENTE_NAME_THINK_MODEL",
            "ASSISTENTE_OUTPUT_TOKENS_THINK_MODEL",
            "ASSISTENTE_CTX_LEN_THINK_MODEL",
            "ASSISTENTE_SUMMARIZE_MODEL",
            "ASSISTENTE_SUMMARIZE_CHUNK_SIZE",
            "ASSISTENTE_SUMMARIZE_CHUNK_MAX_OUTPUT"
        ],
        "Solr_interno": [
            "SOLR_USER",
            "SOLR_PASSWORD"
        ]
    },
    "prod": {
        "geral": [
            "LOG_LEVEL",
            "NODE_EXPORTER_MEM_LIMIT",
            "NODE_EXPORTER_CPU_LIMIT",
            "CADVISOR_MEM_LIMIT",
            "CADVISOR_CPU_LIMIT"
        ],
        "Airflow_stack": [
            "AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG",
            "AIRFLOW__CELERY__WORKER_CONCURRENCY",
            "AIRFLOW_WORKERS_REPLICAS",
            "AIRFLOW_WORKER_MEM_LIMIT",
            "AIRFLOW_WORKER_CPU_LIMIT",
            "AIRFLOW_POSTGRES_MEM_LIMIT",
            "AIRFLOW_POSTGRES_CPU_LIMIT",
            "RABBITMQ_MEM_LIMIT",
            "RABBITMQ_CPU_LIMIT",
            "AIRFLOW_WEBSERVER_MEM_LIMIT",
            "AIRFLOW_WEBSERVER_CPU_LIMIT",
            "AIRFLOW_SCHEDULER_MEM_LIMIT",
            "AIRFLOW_SCHEDULER_CPU_LIMIT",
            "AIRFLOW_SCHEDULER_CPU_SHARES",
            "AIRFLOW_TRIGGERER_MEM_LIMIT",
            "AIRFLOW_TRIGGERER_CPU_LIMIT"
        ],
        "Api_sei": [
            "API_SEI_MEM_LIMIT",
            "API_SEI_CPU_LIMIT",
        ],
        "App_api": [
            "APP_API_MEM_LIMIT",
            "APP_API_CPU_LIMIT"
        ],
        "Solr_interno": [
            "SOLR_JAVA_MEM",
            "SOLR_MEM_LIMIT",
            "SOLR_CPU_LIMIT"
        ],
        "DB_INTERNO": [
            "PGVECTOR_MEM_LIMIT",
            "PGVECTOR_CPU_LIMIT"
        ],
        "Assistente": [
            "ASSISTENTE_MEM_LIMIT",
            "ASSISTENTE_CPU_LIMIT",
            "ASSISTENTE_NGINX_MEM_LIMIT",
            "ASSISTENTE_NGINX_CPU_LIMIT",
            "ASSISTENTE_CONTEXT_MAX_TOKENS",
            "ASSISTENTE_FATOR_LIMITAR_RAG",
            "ASSISTENTE_FATOR_LIMITAR_RAG_FALSO"
        ],
        "LANGFUSE": [
            "LANGFUSE_MEM_LIMIT",
            "LANGFUSE_CPU_LIMIT"
        ]
    },
    "default": {
        "geral": [
            "NB_USER",
            "AIRFLOW_UID",
            "NB_UID",
            "NB_GID",
            "DOCKER_REGISTRY"
        ],
        "imagens": [
            "AIRFLOW_IMAGE_NAME",
            "API_SEI_IMAGE",
            "APP_API",
            "SOLR_CONTAINER",
            "POSTGRES_IMAGE",
            "API_ASSISTENTE_VERSION",
            "NGINX_ASSISTENTE_VERSION"
        ],
        "Solr": [
            "SOLR_HOST",
            "SOLR_ADDRESS",
            "SOLR_MLT_JURISPRUDENCE_CORE",
            "SOLR_MLT_PROCESS_CORE"
        ],
        "DEPLOY": [
            "PROJECT_NAME",
            "AIRFLOW_PROJ_DIR",
            "VOL_SEIIA_DIR"
        ],
        "OpenTelemetry": [
            "OTEL_SERVICE_NAME",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTEL_EXPORTER_OTLP_PROTOCOL",
            "OTEL_EXPORTER_OTLP_INSECURE",
            "OTEL_METRICS_EXPORTER",
            "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL",
            "OTEL_TRACES_EXPORTER",
            "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL",
            "ENABLE_OTEL_METRICS"
        ],
        "ASSISTENTE": [
            "ASSISTENTE_MAX_RETRIES",
            "ASSISTENTE_TIMEOUT_API",
            "ASSISTENTE_USE_LANGFUSE",
            "ASSISTENTE_TOKEN_MAX",
            "ASSISTENTE_TESTS_ID_DOC_INT",
            "ASSISTENTE_TESTS_ID_DOC_EXT",
            "ASSISTENTE_EMBEDDING_PROVIDER",
            "ASSISTENTE_MAX_LENGTH_CHUNK_SIZE",
            "ASSISTENTE_CHUNK_OVERLAP",
        ],
        "DB_INTERNO": [
            "DB_SEIIA_HOST",
            "DB_SEIIA_PORT",
            "DB_SEIIA_ASSISTENTE_SCHEMA",
            "LIB_CONNECTION",
            "DB_SEIIA_SIMILARIDADE",
            "DB_SEIIA_ASSISTENTE"
        ]
    }
}

# Lista de variáveis que podem estar vazias e não devem ser reportadas como erros
allowed_empty_vars = [
    "LANGFUSE_NEXTAUTH_SECRET",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_SECRET_SALT",
    "LANGFUSE_URL",
    # OpenTelemetry - relevante apenas para deploy interno (podem ficar vazias em deploy externo)
    "OTEL_SERVICE_NAME",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_INSECURE",
    "OTEL_METRICS_EXPORTER",
    "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL",
    "OTEL_TRACES_EXPORTER",
    "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"
]

# Lista de variáveis que podem estar presentes nos arquivos .env sem serem consideradas erros
allowed_extra_vars = [
    "AZURE_OPENAI_ENDPOINT_GPT4o",
    # Variáveis do Azure AI Foundry presentes em security.env
    "AGENT_ID",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "AZURE_SUBSCRIPTION_ID",
    "AZURE_TENANT_ID",
    "AZURE_WEB_AGENT_ID",
    "BING_CONNECTION_NAME",
    "MODEL_DEPLOYMENT_NAME",
    "PROJECT_ENDPOINT",
    # Outras variáveis de configuração
    "EMBEDDING_MAX_ACTIVE_RUNS"
]

def create_env_vars_df(env_vars: dict) -> pd.DataFrame:
    dfs = []
    for category, subcategories in env_vars.items():
        for subcategory, variables in subcategories.items():
            dfs.append(pd.DataFrame(data={
                "file": category,
                'categoria': subcategory,
                'variavel': variables
            }, index=range(len(variables))))
    return pd.concat(dfs, ignore_index=True)

def load_env_file(file_path: str) -> pd.DataFrame:
    with open(file_path) as file:
        lines = file.readlines()
    processed_lines = []
    for line in lines:
        if line.strip().startswith("#") or not line.strip():
            continue
        if line.strip().startswith("export"):
            line = line.replace("export", "").split("#")[0].strip().replace('"', '')
            # Ensure line contains an equals sign
            if '=' in line:
                processed_lines.append(line)
    
    # Parse the lines and handle potential issues
    parsed_lines = []
    for line in processed_lines:
        parts = line.split('=', 1)
        if len(parts) == 2:
            var_name = parts[0].strip()
            var_value = parts[1].strip()
            # Ensure both parts are non-empty strings
            if var_name and isinstance(var_name, str):
                parsed_lines.append([var_name, var_value])
    
    return pd.DataFrame(parsed_lines, columns=['variavel', 'value'])

def validate_specific_variables(comparison_df: pd.DataFrame) -> pd.DataFrame:
   
    def validate_azure_endpoint(value) -> bool:
        try:
            if pd.isna(value) or not isinstance(value, str):
                return False
            return bool(re.match(r'^(http|https)://\S+$', value)) and not value.endswith('/')
        except (TypeError, AttributeError):
            return False

    def validate_environment(value) -> bool:
        try:
            if pd.isna(value) or not isinstance(value, str):
                return False
            return value in ['prod', 'dev', 'homol']
        except (TypeError, AttributeError):
            return False

    validations = {
        'AZURE_OPENAI_ENDPOINT_GPT4o': validate_azure_endpoint,
        'AZURE_OPENAI_ENDPOINT_GPT4o_mini': validate_azure_endpoint,
        'ENVIRONMENT': validate_environment,
    }
    
    # Initialize 'valid' column if it doesn't exist
    if 'valid' not in comparison_df.columns:
        comparison_df['valid'] = True
    
    for var, validation_func in validations.items():
        mask = comparison_df['variavel'] == var
        if mask.any():
            comparison_df.loc[mask, 'valid'] = comparison_df.loc[mask, 'value'].apply(validation_func)
    return comparison_df

def consolidate_env_files(categories: list[str]) -> pd.DataFrame:
    env_df = pd.DataFrame()
    for category in categories:
        temp_df = load_env_file(f'env_files/{category}.env')
        temp_df['file'] = category
        env_df = pd.concat([env_df, temp_df], ignore_index=True)
    return env_df

def compare_env_variables(variables_df: pd.DataFrame, env_df: pd.DataFrame, allowed_empty_vars: list = [], allowed_extra_vars: list = []) -> tuple[dict, pd.DataFrame]:
    comparison_df = variables_df.merge(env_df, how="outer", indicator=True)
    comparison_df = validate_specific_variables(comparison_df)

    missing_vars = comparison_df[comparison_df['_merge'] == 'left_only']
    extra_vars = comparison_df[
        (comparison_df['_merge'] == 'right_only') & 
        (~comparison_df['variavel'].isin(allowed_extra_vars))
    ]
    empty_vars = comparison_df[
        ((comparison_df['value'].isna()) | 
         (comparison_df['value'].isin(["*****", "<VALOR>"]))) & 
        (~comparison_df['variavel'].isin(allowed_empty_vars))
    ]
    duplicated_vars = env_df[env_df.duplicated(subset=['variavel'], keep=False)]
    invalid_vars = comparison_df[comparison_df['valid'] == False]
    
    results = {
        'missing': missing_vars[['file', 'categoria', 'variavel', 'value']],
        'extra': extra_vars[['file', 'categoria', 'variavel', 'value']],
        'empty': empty_vars[['file', 'categoria', 'variavel', 'value']],
        'duplicated': duplicated_vars[['file', 'variavel', 'value']],
        'invalid': invalid_vars[['file', 'variavel', 'value']]
    }
    return results, comparison_df

def report_env_issues(results: dict) -> int:
    error = 0
    if not results['missing'].empty:
        logging.error("\nExistem variáveis faltando nos arquivos .env:\n")
        logging.error(results['missing'].to_markdown(index=False))
        error += len(results['missing'])
    if not results['extra'].empty:
        logging.warning("\nExistem variáveis sobrando nos arquivos .env:\n")
        logging.warning(results['extra'].to_markdown(index=False))
        error += len(results['extra'])
    if not results['duplicated'].empty:
        logging.warning("\nExistem variáveis duplicadas nos arquivos .env:\n")
        logging.warning(results['duplicated'].to_markdown(index=False))
        error += len(results['duplicated'])
    if not results['empty'].empty:
        logging.error("\nExistem variáveis vazias nos arquivos .env:\n")
        logging.error(results['empty'].to_markdown(index=False))
        error += len(results['empty'])
    if not results['invalid'].empty:
        logging.error("\nExistem variáveis com valores inválidos nos arquivos .env:\n")
        logging.error(results['invalid'].to_markdown(index=False))
        error += len(results['invalid'])
    if error == 0:
        logging.info("\nNão foram encontrados erros nos arquivos .env.\n")
    return error

anon_variables = ["GIT_TOKEN"] # anonimizar env

def anom_and_save(comparison_df: pd.DataFrame, path: str, anom_variables: list):
    df_anonymized = comparison_df.copy()
    df_anonymized.loc[df_anonymized['variavel'].isin(anom_variables), 'value'] = 'ANONIMIZED'
    df_anonymized.to_csv(f"{path}/comparison_df.csv", index=False)
    logging.info(f"Arquivo comparison_df anonimizado salvo em: {path}")

if __name__ == "__main__":
    variables_df = create_env_vars_df(env_vars)
    env_df = consolidate_env_files(['security', 'prod', 'default'])
    results, comparison_df = compare_env_variables(variables_df, env_df, allowed_empty_vars, allowed_extra_vars)
    errors = report_env_issues(results)
    anom_and_save(comparison_df, "output", anon_variables)