"""
Modulo de testes dos arquivos .env.

Este módulo permite validar a presença, ausência, duplicação e preenchimento de variáveis de ambiente
em arquivos `.env` com base em uma estrutura esperada.

Exemplo de uso:
variables_df = create_env_vars_df(env_vars)
env_df = consolidate_env_files(['security', 'prod', 'default'])
results, comparison_df = compare_env_variables(variables_df, env_df)
errors = report_env_issues(results)

Functions:
    - create_env_vars_df: Cria um DataFrame contendo as variáveis de ambiente organizadas por categoria.
    - load_env_file: Carrega as variáveis de ambiente de um arquivo `.env`, ignorando comentários e removendo 'export'.
    - consolidate_env_files: Consolida os dados de múltiplos arquivos `.env` em um único DataFrame.
    - compare_env_variables: Compara variáveis esperadas com as variáveis nos arquivos `.env`, identificando faltantes, sobrantes, duplicadas e vazias.
    - report_env_issues: Gera um relatório detalhado das variáveis faltantes, sobrantes, duplicadas e vazias.
    - validate_specific_variables: Valida variáveis específicas no DataFrame com base em expressões regulares ou condições.
    
"""

import re
import pandas as pd
import logging

env_vars = {
    "security": {
        "geral": ["ENVIRONMENT", "LOG_LEVEL", "GID_DOCKER"],
        "DB_SEI": [
            "DB_SEI_USER", "DB_SEI_PWD", "DB_SEI_HOST", "DB_SEI_DATABASE", 
            "DB_SEI_PORT", "DB_SEI_SCHEMA", "DATABASE_TYPE"
        ],
        "Solr_SEI": ["SEI_SOLR_ADDRESS", "SEI_SOLR_CORE"],
        "DB_INTERNO": ["POSTGRES_USER", "POSTGRES_PASSWORD"],
        "SEI_IA_WS": [
            "SEI_IAWS_URL", "SEI_IAWS_SISTEMA", "SEI_IAWS_KEY"
        ],
        "ASSISTENTE": [
            "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_ENDPOINT_GPT4o", "AZURE_OPENAI_KEY_GPT4o", "GPT_MODEL_4o_128k",
            "AZURE_OPENAI_ENDPOINT_GPT4o_mini", "AZURE_OPENAI_KEY_GPT4o_mini", "GPT_MODEL_4o_mini_128k",
            "OPENAI_API_VERSION", "ASSISTENTE_PGVECTOR_USER", "ASSISTENTE_PGVECTOR_PWD"
        ]
    },
    "prod": {
        "geral": ["ENVIRONMENT", "LOG_LEVEL"],
        "SEIWS": ["SEIWS_HOST", "SEIWS_PORT"],
        "Airflow_stack": [
            "AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG", "AIRFLOW__CELERY__WORKER_CONCURRENCY", "AIRFLOW_WORKERS_REPLICAS", 
            "AIRFLOW_WORKER_MEM_LIMIT", "AIRFLOW_WORKER_CPU_LIMIT", "AIRFLOW_POSTGRES_MEM_LIMIT", "AIRFLOW_POSTGRES_CPU_LIMIT",
            "RABBITMQ_MEM_LIMIT", "RABBITMQ_CPU_LIMIT", "AIRFLOW_WEBSERVER_MEM_LIMIT", "AIRFLOW_WEBSERVER_CPU_LIMIT",
            "AIRFLOW_SCHEDULER_MEM_LIMIT", "AIRFLOW_SCHEDULER_CPU_LIMIT", "AIRFLOW_SCHEDULER_CPU_SHARES", 
            "AIRFLOW_TRIGGERER_MEM_LIMIT", "AIRFLOW_TRIGGERER_CPU_LIMIT"
        ],
        "Api_sei": ["API_SEI_MEM_LIMIT", "API_SEI_CPU_LIMIT", "SOLR_MLT_PROCESS_CORE"],
        "App_api": ["APP_API_MEM_LIMIT", "APP_API_CPU_LIMIT"],
        "Solr": ["SOLR_JAVA_MEM", "SOLR_MEM_LIMIT", "SOLR_CPU_LIMIT"],
        "Pgvector": ["PGVECTOR_MEM_LIMIT", "PGVECTOR_CPU_LIMIT"],
        "Assistente": [
            "ASSISTENTE_MEM_LIMIT", "ASSISTENTE_CPU_LIMIT", "ASSISTENTE_NGINX_MEM_LIMIT", 
            "ASSISTENTE_NGINX_CPU_LIMIT", "ASSISTENTE_PGVECTOR_MEM_LIMIT", "ASSISTENTE_PGVECTOR_CPU_LIMIT", 
            "ASSISTENTE_LANGFUSE_MEM_LIMIT", "ASSISTENTE_LANGFUSE_CPU_LIMIT"
        ]
    },
    "default": {
        "geral": ["NB_USER", "AIRFLOW_UID", "NB_UID", "NB_GID"],
        "imagens": [
            "AIRFLOW_IMAGE_NAME", "API_SEI_IMAGE", "APP_API", "SOLR_CONTAINER", "POSTGRES_IMAGE",
            "API_ASSISTENTE_VERSION", "NGINX_ASSISTENTE_VERSION"
        ],
        "Solr": ["SOLR_ADDRESS", "SOLR_MLT_JURISPRUDENCE_CORE", "SOLR_MLT_PROCESS_CORE"],
        "EMBEDDINGS_CONFIG": [
            "EMBEDDINGS_TABLE_NAME", "PRE_TRAINED_SBERT_PATH", "EMBEDDING_STRATEGY", 
            "MIN_TOKENS_TO_SPLIT", "ALLOWED_EMBEDDING_FIELDS", "ALLOWED_EMBEDDING_TYPES"
        ],
        "deploy_externo": [
            "PROJECT_NAME", "STORAGE_PROJ_DIR", "USE_LANGFUSE", "EMBEDDER_PROJ_URL", "AIRFLOW_PROJ_DIR"
        ],
        "OpenTelemetry": [
            "OTEL_SERVICE_NAME", "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_PROTOCOL", "OTEL_EXPORTER_OTLP_INSECURE",
            "OTEL_METRICS_EXPORTER", "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL", "OTEL_TRACES_EXPORTER",
            "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "OTEL_PYTHON_REQUESTS_EXCLUDED_URLS", "OTEL_PYTHON_FASTAPI_EXCLUDED_URLS"
        ],
        "ASSISTENTE": [
            "ASSISTENTE_PGVECTOR_DB", "POSTGRES_DATABASE", "ASSISTENTE_PGVECTOR_HOST", 
            "ASSISTENTE_PGVECTOR_PORT", "POSTGRES_DB_ASSISTENTE_SCHEMA", "POSTGRES_DB", "POSTGRES_DB_SIMILARIDADE"
        ],
        "securities_openai": ["MAX_RETRIES", "TIMEOUT_API", "TOKEN_MAX"],
        "Git": ["GIT_TOKEN"]
    }
}


def create_env_vars_df(env_vars: dict) -> pd.DataFrame:
    """
    Cria um DataFrame contendo as variáveis de ambiente organizadas por categoria e subcategoria.

    Parameters:
    - env_vars (dict): Dicionário de variáveis de ambiente.

    Returns:
    - pd.DataFrame: DataFrame com colunas 'file', 'categoria', e 'variavel' para cada variável.
    """
    dfs = []
    for category, subcategories in env_vars.items():
        for subcategory, variables in subcategories.items():
            dfs.append(pd.DataFrame(data={
                "file": category,
                'categoria': subcategory,
                'variavel': variables
            }, index=range(len(variables))))
    return pd.concat(dfs, ignore_index=True)


def load_env_file(file_path:str) -> pd.DataFrame:
    """
    Carrega as variáveis de ambiente de um arquivo .env, ignorando comentários e removendo 'export'.

    Parameters:
    - file_path (str): Caminho do arquivo .env.

    Returns:
    - pd.DataFrame: DataFrame contendo as variáveis e seus valores do arquivo.
    """
    with open(file_path) as file:
        lines = file.readlines()

    processed_lines = []
    for line in lines:
        if line.strip().startswith("#") or not line.strip():
            continue
        if line.strip().startswith("export"):
            line = line.replace("export", "").split("#")[0].strip().replace('"', '')
            processed_lines.append(line)

    return pd.DataFrame([line.split('=', 1) for line in processed_lines], columns=['variavel', 'value'])


def validate_specific_variables(comparison_df: pd.DataFrame) -> pd.DataFrame:
    """
    Valida variáveis específicas no DataFrame com base em expressões regulares ou condições.

    A função valida as seguintes variáveis:
        - SEI_SOLR_ADDRESS: Deve ter o formato 'http://<host>:<port>'.
        - AZURE_OPENAI_ENDPOINT e suas variações: Deve ter o formato 'http://<host>'.
        - ENVIRONMENT: Deve ser um dos valores 'prod', 'dev', 'homol'.
        - DATABASE_TYPE: Deve ser um dos valores 'mysql', 'mssql', 'oracle'.

    Args:
        comparison_df (pd.DataFrame): DataFrame contendo as variáveis a serem validadas. O DataFrame deve conter pelo menos duas colunas:
            - 'variavel': Nome da variável.
            - 'value': Valor da variável.

    Returns:
        pd.DataFrame: DataFrame original com uma nova coluna 'valid' que indica se o valor da variável é válido (True/False).
    """
    
    def validate_sei_solr_address(value: str) -> bool:
        """
        Valida o valor da variável SEI_SOLR_ADDRESS.

        Args:
            value (str): Valor a ser validado.

        Returns:
            bool: Retorna True se o valor corresponder ao formato 'http://<host>:<port>', caso contrário, False.
        """
        if bool(re.match(r'^(http|https)://\S+$', value)) and not value.endswith('/'):
            return True
        else:
            return False


    def validate_azure_endpoint(value: str) -> bool:
        """
        Valida o valor de endpoints Azure OpenAI.

        Args:
            value (str): Valor a ser validado.

        Returns:
            bool: Retorna True se o valor corresponder ao formato 'http://<host>', caso contrário, False.
        """
        if bool(re.match(r'^(http|https)://\S+$', value)) and not value.endswith('/'):
            return True
        else:
            return False


    def validate_environment(value: str) -> bool:
        """
        Valida o valor da variável ENVIRONMENT.

        Args:
            value (str): Valor a ser validado.

        Returns:
            bool: Retorna True se o valor for um dos seguintes: 'prod', 'dev', 'homol'.
        """
        return value in ['prod', 'dev', 'homol']


    def validate_database_type(value: str) -> bool:
        """
        Valida o valor da variável DATABASE_TYPE.

        Args:
            value (str): Valor a ser validado.

        Returns:
            bool: Retorna True se o valor for um dos seguintes: 'mysql', 'mssql', 'oracle'.
        """
        return value in ['mysql', 'mssql', 'oracle']
    
    def validate_postgres_password(value: str) -> bool:
        """
        Valida o valor da variável POSTGRES_PASSWORD.

        A senha não deve conter os seguintes caracteres:
        "'", '"', '\\', ' ', '$', '(', ')', ':', '@', ';', '`', '&', '*', '+', '-', '=', '/', '?', '!', '[', ']', '{', '}', '<', '>', '|', '%', '^', '~'.

        Args:
            value (str): Valor a ser validado.

        Returns:
            bool: Retorna True se o valor NÃO contiver os caracteres proibidos, caso contrário, False.
        """
        prohibited_chars = set("'\"\\ $():@;`&*+-=/?![]{}<>|%^~")
        return not any(char in prohibited_chars for char in value)

    validations = {
        'SEI_SOLR_ADDRESS': validate_sei_solr_address,
        'AZURE_OPENAI_ENDPOINT': validate_azure_endpoint,
        'AZURE_OPENAI_ENDPOINT_GPT4o': validate_azure_endpoint,
        'AZURE_OPENAI_ENDPOINT_GPT4o_mini': validate_azure_endpoint,
        'ENVIRONMENT': validate_environment,
        'DATABASE_TYPE': validate_database_type,
        'POSTGRES_PASSWORD': validate_postgres_password
    }
    for var, validation_func in validations.items():
        mask = comparison_df['variavel'] == var
        comparison_df.loc[mask, 'valid'] = comparison_df.loc[mask, 'value'].apply(validation_func)
    return comparison_df

def consolidate_env_files(categories:list[str])->pd.DataFrame:
    """
    Consolida os dados de múltiplos arquivos .env em um único DataFrame.

    Parameters:
    - categories (list): Lista de categorias de arquivos para processar.

    Returns:
    - pd.DataFrame: DataFrame consolidado com variáveis e valores de todos os arquivos .env.
    """
    env_df = pd.DataFrame()
    for category in categories:
        temp_df = load_env_file(f'env_files/{category}.env')
        temp_df['file'] = category
        env_df = pd.concat([temp_df, env_df], ignore_index=True)
    return env_df


def compare_env_variables(variables_df: pd.DataFrame, env_df: pd.DataFrame) -> tuple[dict,pd.DataFrame]:
    """
    Compara variáveis de ambiente do dicionário com os arquivos .env, identificando faltantes, sobrantes e vazias.

    Parameters:
    - variables_df (pd.DataFrame): DataFrame com variáveis esperadas.
    - env_df (pd.DataFrame): DataFrame com variáveis presentes nos arquivos .env.

    Returns:
    - tuple: contendo 
        - dict: Dicionário contendo DataFrames para variáveis faltantes, sobrantes e vazias.
        - pd.DataFrame: DataFrame completo.
    """
    comparison_df = variables_df.merge(env_df, how="outer", indicator=True)
    comparison_df = validate_specific_variables(comparison_df)

    missing_vars = comparison_df[comparison_df['_merge'] == 'left_only']
    extra_vars = comparison_df[comparison_df['_merge'] == 'right_only']
    empty_vars = comparison_df[(comparison_df['value'].isna()) | (comparison_df['value'].isin(["****","*****", "<VALOR>"]))]
    duplicated_vars = env_df[env_df.duplicated(subset=['variavel'], keep=False)]
    invalid_vars = comparison_df[comparison_df['valid'] == False]
    
    results = {
        'missing': missing_vars[['file','categoria', 'variavel', 'value']],
        'extra': extra_vars[['file','categoria', 'variavel', 'value']],
        'empty': empty_vars[['file','categoria', 'variavel', 'value']],
        'duplicated': duplicated_vars[['file', 'variavel', 'value']],
        'invalid': invalid_vars[['file', 'variavel', 'value']]
    }

    return results, comparison_df


def report_env_issues(results:dict) -> int:
    """
    Gera um relatório para as variáveis faltantes, sobrantes e vazias.

    Parameters:
    - results (dict): Dicionário contendo DataFrames para variáveis faltantes, sobrantes e vazias.

    Returns:
    - None
    """
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

anon_variables = ["GIT_TOKEN", "ASSISTENTE_PGVECTOR_PWD", "POSTGRES_PASSWORD",
                  "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_ENDPOINT_GPT4o",
                  "AZURE_OPENAI_ENDPOINT_GPT4o_mini", "AZURE_OPENAI_KEY_GPT4o",
                  "AZURE_OPENAI_KEY_GPT4o_mini", "DB_SEI_PWD", "DB_SEI_USER",
                  "SEI_IAWS_KEY"]

def anom_and_save(comparison_df: pd.DataFrame, path: str, anom_variables: list):
    """
    Anonimiza valores de variáveis sensíveis no DataFrame e salva em um arquivo.

    Parameters:
    - comparison_df (pd.DataFrame): DataFrame contendo as variáveis a serem processadas.
    - path (str): Caminho do arquivo para salvar o DataFrame anonimizado.
    - anom_variables (list): Lista de nomes de variáveis que devem ser anonimizadas.

    Returns:
    - None
    """
    df_anonymized = comparison_df.copy()
    df_anonymized.loc[df_anonymized['variavel'].isin(anom_variables), 'value'] = 'ANONIMIZED'
    df_anonymized.to_csv(f"{path}/comparison_df.csv", index=False)
    logging.info(f"Arquivo comparison_df anonimizado salvo em: {path}")
