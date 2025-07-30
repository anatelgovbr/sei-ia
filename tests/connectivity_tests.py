"""
Modulo de testes de conexões.

Este módulo permite configurar e testar a conectividade com uma lista de serviços,
como bancos de dados, Solr, e APIs, conforme especificado nas variáveis de ambiente.
A configuração é derivada de um DataFrame de comparação (`comparison_df`), contendo
os dados de variáveis de ambiente.

Exemplo de uso:

1. Testando a conectividade com todos os serviços:

    ```python
    print("\n==================== TESTE DE CONECTIVIDADE ==================== \n ")
    config = create_connectivity_config(comparison_df)  # VEM DO TESTE DE ENV
    results = test_connectivity_all(config)
    print("\n==================== TESTE DE CONECTIVIDADE - RESUMO ==================== \n ")
    erros_conn = connectivity_report(results)
    ```
2. Testando a conectividade com o Solr:

```python
print("\n==================== TESTE DE CONEXÃO COM SOLR ==================== \n")
solr_config = create_solr_config(comparison_df)
solr_results = test_connectivity_all_solr(solr_config)
solr_erros = connectivity_report(solr_results)
```
    
3. Testando a conectividade com o Solr:

```python
print("\n==================== TESTE DE SAUDE DOS ENDPOINTS ==================== \n")
health_results = test_api_connectivity_and_response_all(health_testes_urls)
health_erros = connectivity_report(health_results)
```

4. Testando a conectividade com bancos de dados externos:
```python
print("================== EXTERNOS ==================")
DB_SEI_SCHEMA, db_instance = test_conn.create_external_sei_config(comparison_df)
print("============== TABELAS DO SEI ================")
if db_instance:
    db_sei_results = test_conn.verify_all_tables(db_instance, test_conn.sei_externo_tables, DB_SEI_SCHEMA,verbose=False)
    db_sei_erros = test_conn.connectivity_report(db_sei_results)
```

5. Testando a conectividade com bancos de dados internos (Postgres):

```python
postgres_config, assistente_db_instance, similaridade_db_instance = create_postgres_config(comparison_df)

if assistente_db_instance:
    assistente_results = verify_all_tables(assistente_db_instance, assistente_tables, verbose=True)
    print("\n==================== RESULTADO DE TABELAS DO ASSISTENTE ==================== \n")
    connectivity_report(assistente_results)

if similaridade_db_instance:
    similaridade_results = verify_all_tables(similaridade_db_instance, similaridade_tables, verbose=True)
    print("\n==================== RESULTADO DE TABELAS DE SIMILARIDADE ==================== \n")
    connectivity_report(similaridade_results)
```

Funções:
    - create_external_sei_config:     Configura e conecta-se ao banco de dados externo do SEI com base nas variáveis de ambiente.
    - create_postgres_config: Configura e conecta-se aos bancos de dados Postgres.
    - verify_table: Verifica se uma tabela específica existe no banco.
    - verify_all_tables: Verifica todas as tabelas especificadas em um banco.
    - create_connectivity_config: Cria uma configuração de conectividade a partir de um DataFrame de comparação.
    - create_solr_config: Cria uma configuração específica para os serviços Solr.
    - test_connectivity: Testa a conectividade com um serviço específico (geral).
    - test_connectivity_all: Testa a conectividade com todos os serviços especificados (geral).
    - test_connectivity_all_solr: Testa a conectividade com todos os cores Solr.
    - connectivity_report: Gera um resumo da conectividade com os serviços e retorna o número de falhas.
    - test_api_connectivity_and_response: Testa a conectividade e resposta de uma API específica, verificando se a API responde com o status esperado.
    - test_api_connectivity_and_response_all: Executa testes de conectividade e resposta para múltiplas URLs de serviços, gerando um relatório detalhado com o resultado.
"""

import socket
import os
import pandas as pd
import requests
import logging
from tests.db_connect import DBConnector
from requests.auth import HTTPBasicAuth
import urllib3
import warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.simplefilter("ignore", category=urllib3.exceptions.InsecureRequestWarning)

assistente_tables = [
    'feedback', 'ip_message', 
    'messages', 'models'
    ]

similaridade_tables = [
    'document_mlt_recommendation', 'log_consume', 'log_update_mlt',
    'process_weighted_mlt_recommendation', 'queue_update_mlt',
    'version_register'
    ]

sei_externo_tables = [
    'md_ia_adm_cfg_assi_ia_usu', 'md_ia_topico_chat', 
    'md_ia_adm_config_assist_ia', 'md_ia_adm_config_similar', 'md_ia_adm_doc_relev',
    'md_ia_adm_integ_funcion','md_ia_adm_integracao', 'md_ia_adm_meta_ods',
    'md_ia_adm_metadado', 'md_ia_adm_objetivo_ods', 'md_ia_adm_ods_onu',
    'md_ia_adm_perc_relev_met', 'md_ia_adm_pesq_doc', 'md_ia_adm_seg_doc_relev',
    'md_ia_adm_tp_doc_pesq', 'md_ia_adm_unidade_alerta', 'md_ia_class_meta_ods',
    'md_ia_classificacao_ods', 'md_ia_hist_class', 'md_ia_interacao_chat',
    ]


def create_postgres_config(comparison_df: pd.DataFrame) -> tuple[dict, DBConnector, DBConnector]:
    """
    Configura e conecta-se aos bancos de dados Postgres especificados no DataFrame.

    Args:
        comparison_df (pd.DataFrame): DataFrame contendo variáveis de ambiente.

    Returns:
        tuple:
            - dict: Configuração dos bancos de dados e instâncias conectadas.
            - DBConnector: Instância de conexão com o banco de dados assistente.
            - DBConnector: Instância de conexão com o banco de dados similaridade.
    """
    try:
        POSTGRES_USER = comparison_df[comparison_df['variavel'] == 'DB_SEIIA_USER']['value'].values[0]
        POSTGRES_PASSWORD = comparison_df[comparison_df['variavel'] == 'DB_SEIIA_PWD']['value'].values[0]
        ASSISTENTE_PGVECTOR_HOST = comparison_df[comparison_df['variavel'] == 'DB_SEIIA_HOST']['value'].values[0]
        ASSISTENTE_PGVECTOR_PORT = comparison_df[comparison_df['variavel'] == 'DB_SEIIA_PORT']['value'].values[0]
        ASSISTENTE_PGVECTOR_DB = comparison_df[comparison_df['variavel'] == 'DB_SEIIA_ASSISTENTE']['value'].values[0]
        POSTGRES_DATABASE = comparison_df[comparison_df['variavel'] == 'DB_SEIIA_SIMILARIDADE']['value'].values[0]
    except IndexError:
        logging.error("Variáveis faltantes para configuração do Banco de dados INTERNO.")
        return {}, None, None

    assistente_conn_string = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{ASSISTENTE_PGVECTOR_HOST}:{ASSISTENTE_PGVECTOR_PORT}/{ASSISTENTE_PGVECTOR_DB}"
    similaridade_conn_string = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{ASSISTENTE_PGVECTOR_HOST}:{ASSISTENTE_PGVECTOR_PORT}/{POSTGRES_DATABASE}"

    try:
        assistente_db_instance = DBConnector(assistente_conn_string, schema="")
        similaridade_db_instance = DBConnector(similaridade_conn_string, schema="")
        return {
            "ASSISTENTE": {"conn_string": assistente_conn_string},
            "SIMILARIDADE": {"conn_string": similaridade_conn_string}
        }, assistente_db_instance, similaridade_db_instance
    except Exception as e:
        logging.error("Erro ao conectar aos bancos de dados internos:", e)
        return {}, None, None

def verify_table(instance: DBConnector, table: str, schema: str = None,DATABASE_TYPE: str = None, verbose: bool = False) -> bool:
    """
    Verifica a existência de uma tabela em um banco de dados Postgres.

    Args:
        instance (DBConnector): Instância de conexão com o banco de dados.
        table (str): Nome da tabela a ser verificada.
        schema (str, optional): Nome do schema do banco de dados. Default é None.
        verbose (bool, optional): Indica se deve exibir mensagens de status. Default é False.

    Returns:
        bool: True se a tabela existir, False caso contrário.
    """
    if verbose:
        logging.debug(f"Verificando se a tabela {table} existe.")
    try:
        if schema:
            sql = f"SELECT * FROM {schema}.{table}"
        else:
            sql = f"SELECT * FROM {table}"
        if DATABASE_TYPE == "mysql":
            sql += ' LIMIT 1'
        elif DATABASE_TYPE == "oracle":
            sql += ' WHERE ROWNUM = 1'
        elif DATABASE_TYPE == "mssql":
            sql = f"SELECT TOP 1 * FROM {schema}.{table}" if schema else f"SELECT TOP 1 * FROM {table}"
        if verbose:
            logging.debug(sql)
        instance.execute_query(sql)
        if verbose:
            logging.debug(f"Tabela {table} existe.")
        return True
    except Exception as e:
        if verbose:
            logging.error(f"Tabela {table} não existe. Erro: {e}")
        return False

def verify_all_tables(instance: DBConnector, tables: list[str], schema: str = None, DATABASE_TYPE: str = None, verbose: bool = True) -> dict[str, dict]:
    """
    Verifica a existência de várias tabelas em um banco de dados Postgres.

    Args:
        instance (DBConnector): Instância de conexão com o banco de dados.
        tables (list[str]): Lista de nomes de tabelas a serem verificadas.
        schema (str, optional): Nome do schema do banco de dados. Default é None.
        verbose (bool, optional): Indica se deve exibir mensagens de status. Default é False.

    Returns:
        dict: Dicionário com o status de cada tabela, com True para tabelas existentes e False para ausentes.
    """
    result = {}
    for table in tables:
        result[table] = {"Reacheble": verify_table(instance, table, schema, DATABASE_TYPE, verbose)}
    return result

def create_solr_config(comparison_df: pd.DataFrame) -> dict:
    """
    Cria a configuração dos serviços Solr a partir de um DataFrame contendo as variáveis de ambiente.

    Args:
        comparison_df (pd.DataFrame): DataFrame contendo variáveis de ambiente.

    Returns:
        dict: Dicionário com a configuração dos serviços Solr.
    """
    return {
        "Solr_Interno_documento": {
            "host": comparison_df[comparison_df['variavel'] == 'SOLR_ADDRESS']['value'].values[0].split(":")[1].replace("//", ""),
            "port": int(comparison_df[comparison_df['variavel'] == 'SOLR_ADDRESS']['value'].values[0].split(":")[2]),
            "core": comparison_df[comparison_df['variavel'] == 'SOLR_MLT_JURISPRUDENCE_CORE']['value'].values[0],
            "interno": True
        },
        "Solr_Interno_processo": {
            "host": comparison_df[comparison_df['variavel'] == 'SOLR_ADDRESS']['value'].values[0].split(":")[1].replace("//", ""),
            "port": int(comparison_df[comparison_df['variavel'] == 'SOLR_ADDRESS']['value'].values[0].split(":")[2]),
            "core": comparison_df[comparison_df['variavel'] == 'SOLR_MLT_PROCESS_CORE']['value'].values[0],
            "interno": True
        }
    }

def verificar_status_solr(host:str, port:int, core:str, interno:bool, verbose:bool = False) -> dict:
    """
    Verifica o status de um core específico no Solr.

    Parameters:
    - host (str): Endereço do servidor Solr.
    - port (int): Porta do servidor Solr.
    - core (str): Nome do core Solr.
    - verbose (bool): verbose.

    Returns:
    - dict: Dicionário com o resultado da conexão e detalhes.
    """
        
    try:
        if interno:
            url = f"https://{host}:{port}/solr/{core}/admin/ping"
            response = requests.get(url, verify=False, auth=HTTPBasicAuth(os.getenv("SOLR_USER"), os.getenv("SOLR_PASSWORD")))
        else:
            url = f"http://{host}:{port}/solr/{core}/admin/ping"
            response = requests.get(url)
        response.raise_for_status()
        
        if response.status_code == 200:
            if verbose:
                logging.debug(f"Conexão ao core '{core}' bem-sucedida.")
            return {"Reacheble": True, "Host": host, "Port": port, "Core": core}
        else:
            if verbose:
                logging.error(f"Core '{core}' não encontrado ou inativo.")
            return {"Reacheble": False, "Host": host, "Port": port, "Core": core}
    
    except requests.exceptions.RequestException as e:
        if verbose:
            logging.error(f"Erro ao conectar ao Solr '{core}':", e)
        return {"Reacheble": False, "Host": host, "Port": port, "Core": core}

def test_connectivity_all_solr(solr_config:dict, verbose:bool = True) -> dict:
    """
    Testa a conectividade com todos os serviços Solr especificados.

    Parameters:
    - solr_config (dict): Configuração dos serviços Solr.
    - verbose (bool): verbose.

    Returns:
    - dict: Resultados dos testes de conectividade com cada serviço Solr.
    """
    results = {}
    for service_name, config in solr_config.items():
        result = verificar_status_solr(config["host"], config["port"], config["core"],config["interno"], verbose)
        results[service_name] = result
    return results

def connectivity_report(results:dict , return_df:bool=False, path:str = None)->tuple[int,pd.DataFrame]:
    """
    Gera um relatório da conectividade com os serviços e retorna o número de falhas.

    Parameters:
    - results (dict): Dicionário contendo o resultado de conectividade para cada serviço.
    - return_df (bool): Se True, retorna o DataFrame dos resultados junto com o número de falhas.
    - path (str) : caminho para salvar o report
    
    Returns:
    - int: Número de serviços que falharam na conexão.
    - pd.DataFrame (opcional): DataFrame contendo os resultados detalhados se return_df for True.
    """
    try:
        results_df = pd.DataFrame.from_dict(results, orient="index")
    except:
        results_df = pd.DataFrame.from_dict(results)
    error_count = len(results_df[results_df["Reacheble"] == False])

    if error_count > 0:
        logging.error("\nHouve falha nos testes abaixo:\n")
        # logging.info(results_df[results_df["Reacheble"] == False][["Host", "Port", "Core", "Reacheble"]].to_markdown())
        logging.error(results_df[results_df["Reacheble"] == False].to_markdown())
    else:
        logging.info("\nTodos os testes passaram.\n")

    if path:
        results_df.to_csv(path,index=False)
    if return_df:
        return error_count, results_df
    return error_count, None

def create_connectivity_config(comparison_df: pd.DataFrame) -> dict:
    """
    Cria uma configuração de conectividade a partir de um DataFrame de variáveis de ambiente.

    Parameters:
    - comparison_df (pd.DataFrame): DataFrame contendo variáveis de ambiente com colunas 
      'variavel' e 'value', onde 'variavel' identifica o serviço e 'value' armazena o valor.

    Returns:
    - dict: Dicionário com a configuração de conectividade, contendo hosts e portas dos serviços.
    """
    return {
        "DB_INTERNO": {
            "host": comparison_df[comparison_df['variavel'] == 'DB_SEIIA_HOST']['value'].values[0],
            "port": int(comparison_df[comparison_df['variavel'] == 'DB_SEIIA_PORT']['value'].values[0])
        },
        "Solr_Interno": {
            "host": comparison_df[comparison_df['variavel'] == 'SOLR_ADDRESS']['value'].values[0].split(":")[1].replace("//", ""),
            "port": int(comparison_df[comparison_df['variavel'] == 'SOLR_ADDRESS']['value'].values[0].split(":")[2].replace("//", ""))  
        },
        "API_SEI": {
            "host": "api_sei",
            "port": 8082
        },
        "API_JOBS": {
            "host": "jobs_api",
            "port": 8642
        },
        "API_SEI_FEEDBACK": {
            "host": "app-api-feedback",
            "port": 8086
        },
        "API_ASSISTENTE": {
            "host": "nginx_assistente",
            "port": 80
        },
        "AIRFLOW": {
            "host": "airflow-webserver-pd",
            "port": 8080
        }
    }


def test_connectivity(host: str, port: int, service_name: str, verbose: bool = True) -> bool:
    """
    Testa a conectividade com um serviço específico.

    Parameters:
    - host (str): Endereço do host do serviço.
    - port (int): Porta do serviço.
    - service_name (str): Nome do serviço para identificação no relatório.

    Returns:
    - bool: Retorna True se a conexão for bem-sucedida, False caso contrário.
    """
    if verbose:
        logging.debug(f"Testando a conexao {service_name}({host}:{port})...")
    try:
        with socket.create_connection((host, port), timeout=5):
            if verbose:
                logging.debug(f"Conexao {service_name} bem sucedida!")
            return True
    except (socket.timeout, socket.error) as e:
        if verbose:
            logging.error(f"Falha ao conectar ao {service_name}. Erro: {e}")
        return False

def test_connectivity_all(config: dict, verbose: bool = False) -> dict:
    """
    Testa a conectividade com todos os serviços especificados na configuração.

    Parameters:
    - config (dict): Dicionário com a configuração de conectividade contendo 
      hosts e portas dos serviços a serem testados.

    Returns:
    - dict: Dicionário contendo o resultado de cada teste, com True para conexões bem-sucedidas 
      e False para falhas.
    """
    results = {}
    for service_name, settings in config.items():
        host = settings["host"]
        port = settings["port"]
        result = test_connectivity(host, port, service_name, verbose)
        results[service_name] = {"Reacheble": result, "Host": host, "Port": port}
    return results


health_testes_urls = {
    "api_recomendacao": {"https://api_sei:8082":[
        "/health",
        "/health/database",
        # "/health/process-recommendation",
        # "/health/document-recommendation"
    ]},
    "api_feedback": {"https://app-api-feedback:8086":["/health"]},
    "api_assistente": {"http://api_assistente:8088":["/health"]}
}


def test_api_connectivity_and_response(api_url: str, expected_status: int = 200) -> bool:
    """
    Testa a conectividade e resposta de uma API específica, verificando se a API responde com o status esperado.

    Parâmetros:
        api_url (str): A URL da API a ser testada.
        expected_status (int, opcional): Código de status HTTP esperado para a resposta (padrão é 200).

    Retorna:
        bool: Retorna `True` se a API responder com o status esperado; caso contrário, retorna `False`.

    Exceções:
        - Em caso de falha na conexão ou qualquer erro de requisição, a função registra o erro no log e retorna `False`.
    """
    try:
        response = requests.get(api_url, headers={'accept': 'application/json'}, verify=False)
        if response.status_code == expected_status:
            logging.debug(f"API {api_url} respondeu com o status esperado: {expected_status}")
            return True
        else:
            logging.error(f"API {api_url} respondeu com status inesperado: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logging.error(f"Falha ao conectar à API {api_url}. Erro: {e}")
        return False

def test_api_connectivity_and_response_all(health_tests_urls: dict, expected_status: int = 200) -> list:
    """
    Executa testes de conectividade e resposta para múltiplas URLs de serviços, gerando um relatório detalhado com o resultado.

    Parâmetros:
        health_tests_urls (dict): Dicionário contendo URLs e endpoints para diferentes serviços.
                                  Estrutura esperada: { "servico": { "url": ["endpoint1", "endpoint2", ...] } }
        expected_status (int, opcional): Código de status HTTP esperado para cada resposta (padrão é 200).

    Retorna:
        list: Uma lista de dicionários contendo o relatório de cada teste, incluindo serviço, status de conectividade, 
              host, porta e endpoint.
    """
    report = []
    for servico in health_tests_urls.keys():
        for url in health_tests_urls[servico]:
            for check in health_tests_urls[servico][url]:
                report.append({
                    "Servico": servico,
                    "Reacheble": test_api_connectivity_and_response(f'{url}{check}', expected_status),
                    "Host": url.split(":")[1].replace("//", ""),
                    "Port": url.split(":")[2],
                    "Endpoint": check
                })
    return report