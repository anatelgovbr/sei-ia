"""
Módulo de monitoramento de containers Docker.

Este módulo permite monitorar o status dos containers Docker e seus logs, incluindo a verificação
de execução, reinicialização, status de saúde e logs de erros. Ele facilita o diagnóstico rápido de problemas 
em containers Docker relevantes para o sistema.

Exemplo de uso:
container_status = get_docker_containers(verbose=True)
container_status_df = verify_status_docker(container_status, containers_names, verbose=True)
errors, categorized_dfs = report_container_status(container_status_df, return_dfs=True)
logs = get_all_docker_logs(container_status, tail=1000, verbose=True)
errors_in_logs = report_docker_logs(logs, show_logs=True)

Lista de containers para verificação:
containers_names = [
    'airflow-worker', 'airflow-scheduler', 'airflow-webserver', 'airflow-triggerer', 
    'nginx_assistente', 'solr_pd', 'pgvector_all', 'app-api-feedback', 'api_sei', 
    'api_assistente', 'airflow_postgres', 'jobs_api', 'rabbitmq'
]

Functions:
    - get_docker_containers: Obtém informações detalhadas dos containers Docker e calcula seu uptime.
    - verify_status_docker: Verifica o status dos containers de interesse, consolidando dados em um DataFrame.
    - report_container_status: Gera um relatório dos containers, destacando problemas de execução e saúde.
    - get_docker_logs: Coleta os logs de um container específico, permitindo especificar a quantidade de linhas desejada.
    - get_all_docker_logs: Coleta os logs de todos os containers monitorados, armazenando a contagem de linhas e o texto dos logs.
    - report_docker_logs: Analisa os logs de todos os containers, reportando possíveis erros e containers que não geram logs.
"""

import docker
from datetime import datetime
import pandas as pd
import logging
import os
containers_names = [
    'airflow-worker', 'airflow-scheduler', 'airflow-webserver', 'airflow-triggerer', 
    'nginx_assistente', 'solr_pd', 'pgvector_all', 'app-api-feedback', 'api_sei', 
    'api_assistente', 'airflow_postgres', 'jobs_api', 'rabbitmq'
]

def get_docker_logs(container_name: str, tail: int = None, verbose: bool = False) -> list:
    """
    Obtém os logs de um container Docker especificado.

    Args:
        container_name (str): Nome do container Docker do qual os logs serão obtidos.
        tail (int, opcional): Número de linhas finais do log para obter. Se não especificado, todos os logs serão retornados.
        verbose (bool, opcional): Se True, imprime informações adicionais sobre o status do container. Padrão é False.

    Returns:
        list: Uma lista de strings, cada uma representando uma linha de log do container.

    Raises:
        docker.errors.NotFound: Se o container especificado não for encontrado.
        docker.errors.APIError: Se houver um problema ao tentar acessar a API do Docker.
    """
    client = docker.from_env()
    container = client.containers.get(container_name)
    if tail:
        log_lines = container.logs(tail=tail).decode('utf-8').split('\n')

    else:
        log_lines = container.logs().decode('utf-8').split('\n')
    if len(log_lines) > 0:
        if verbose:
            logging.info(f"O container {container_name} está gerando logs")
    else:
        if verbose:
            logging.info(f"O container {container_name} nao está gerando logs")
    return log_lines

def get_all_docker_logs(container_status: dict, tail: int = 1000, verbose: bool = False) -> dict:
    """
    Obtém os logs de todos os containers especificados e os organiza em um dicionário.

    Args:
        container_status (dict): Dicionário com o status dos containers. As chaves representam os nomes dos containers.
        tail (int, opcional): Número de linhas finais dos logs para cada container. Padrão é 1000.
        verbose (bool, opcional): Se True, imprime informações adicionais sobre o status dos containers. Padrão é False.

    Returns:
        dict: Dicionário onde as chaves são os nomes dos containers e os valores são outro dicionário contendo:
            - 'Linhas': Quantidade de linhas de log do container.
            - 'log_text': Texto completo dos logs.

    Raises:
        docker.errors.NotFound: Se algum container especificado não for encontrado.
        docker.errors.APIError: Se houver um problema ao tentar acessar a API do Docker.
    """
    logs_lines = {}
    for container_name in container_status.keys():
        log_line = get_docker_logs(container_name,tail,verbose)
        logs_lines[container_name]={'Linhas': len(log_line), "log_text": '\n'.join(log_line)}
    return logs_lines

def report_docker_logs(logs_lines: dict, show_logs: bool = False) -> int:
    """
    Gera um relatório dos logs dos containers e verifica a presença de erros.

    Args:
        logs_lines (dict): Dicionário com as linhas de log de cada container, no formato gerado por `get_all_docker_logs`.
        show_logs (bool, opcional): Se True, exibe os logs dos containers que contêm erros. Padrão é False.

    Returns:
        int: Número total de containers que apresentam problemas (não gerando logs ou contendo erros).

    Raises:
        KeyError: Se o formato de `logs_lines` estiver incorreto.
    """
    results_df = pd.DataFrame.from_dict(logs_lines, orient="index")
    results_df['contem_erro'] = results_df['log_text'].str.lower().str.count('\[error\]')
    notcontainslog = results_df[results_df['Linhas'] < 3]
    containserror = results_df[results_df['contem_erro'] != 0]
    errors = 0 
    if len(notcontainslog) > 0 :
        errors += len(notcontainslog)
        logging.info("\nexistem containers que nao estao gerando logs\n")
        logging.info(notcontainslog[['Linhas', 'contem_erro']].to_markdown())
    else:
        logging.info("\ntodos os containers estao gerando logs\n")
    if len(containserror) > 0 :
        errors += len(containserror)

        logging.info("\nexistem containers que podem possuir erros\n")
        logging.info(containserror[['Linhas', 'contem_erro']].to_markdown())
        if show_logs:
            for row, line in containserror.iterrows():
                logging.info(f"\n##### LOG do container {row} ####\n")
                logging.info(line['log_text'])
    else:
        logging.info("todos os containers estao gerando logs")
    return errors

def get_docker_containers(verbose: bool = False) -> dict:
    """
    Obtém o status e detalhes dos containers Docker que estão atualmente configurados, 
    filtrando apenas aqueles cujo nome inicia com 'sei_ia'. Calcula o uptime dos containers 
    com base no tempo de início e, quando aplicável, no tempo de término.

    Args:
        verbose (bool, opcional): Se True, imprime detalhes de cada container processado. 
            Padrão é False.

    Returns:
        dict: Um dicionário contendo o status e informações adicionais de cada container relevante,
        onde cada chave é o nome do container e o valor é um dicionário com detalhes como:
            - "ID": ID do container (str).
            - "Status": Status do container (str).
            - "uptime": Tempo de execução do container, se aplicável (datetime.timedelta ou str).
            - "network": Rede associada ao container (str).
            - Outros detalhes do estado do container.
    """
    client = docker.from_env()
    containers = client.containers.list(all=True)
    container_status = {}

    for container in containers:
        name = str(container.name)
        if name.startswith("sei"):
            start_time = container.attrs['State']['StartedAt']
            if start_time != '0001-01-01T00:00:00Z':
                start_time = datetime.fromisoformat(start_time[:23])
                if container.status == 'running':
                    uptime = datetime.now() - start_time
                else:
                    finished_time = container.attrs['State']['FinishedAt']
                    if finished_time != '0001-01-01T00:00:00Z':
                        finished_time = datetime.fromisoformat(finished_time[:23])
                        uptime = finished_time - start_time
                    else:
                        uptime = 'Indisponível'
            else:
                uptime = 'Indisponível'

            container_status[name] = {
                "ID": container.short_id,
                "Status": container.status,
                "uptime": uptime,
                "network": str(list(container.attrs['NetworkSettings']['Networks'].keys()))[1:-1]
            }
            container_status[name].update(container.attrs['State'])

            if verbose:
                logging.debug(f"ID: {container.short_id}, Nome: {container.name}, Status: {container.status}")

    return container_status

def verify_status_docker(container_status: dict, containers_names: list, verbose: bool = False) -> pd.DataFrame:
    """
    Verifica o status dos containers especificados na lista `containers_names` com base nas 
    informações contidas em `container_status`. Retorna um DataFrame com os dados de cada container solicitado,
    indicando sua existência e status.

    Args:
        container_status (dict): Dicionário com o status de cada container, conforme retornado por `get_docker_containers`.
        containers_names (list): Lista com os nomes dos containers para verificar.
        verbose (bool, opcional): Se True, imprime mensagens indicando se cada container existe ou não.

    Returns:
        pd.DataFrame: DataFrame com as informações de status e saúde de cada container especificado, incluindo:
            - Nome: Nome do container.
            - Status: Status do container.
            - Health: Status de saúde do container (ou 'Indisponível' se não disponível).
    """
    data_df = pd.DataFrame.from_dict(container_status, orient="index")
    dfs = []
    if len(data_df) == 0:
        for container_name in containers_names:
            dfs.append(pd.DataFrame(data={
                    'Nome': container_name,
                    'Status': 'Indisponível',
                    'Health': 'Indisponível',
                }, index=[0]))
    else:      
        data_df['Health'] = data_df['Health'].apply(lambda x: x.get('Status') if isinstance(x, dict) else "Indisponível")
        data_df.reset_index(inplace=True)
        data_df.rename(columns={'index': 'Nome'}, inplace=True)

        for container_name in containers_names:
            if data_df['Nome'].str.contains(container_name).sum() > 0:
                if verbose:
                    logging.debug(f"O container {container_name} existe\n")
                dfs.append(data_df[data_df['Nome'].str.contains(container_name)])
            else:
                if verbose:
                    logging.debug(f"O container {container_name} não existe\n")
                dfs.append(pd.DataFrame(data={
                    'Nome': container_name,
                    'Status': 'Indisponível',
                    'Health': 'Indisponível',
                }, index=[0]))

    return pd.concat(dfs, ignore_index=True).fillna(False)

def report_container_status(container_status_df: pd.DataFrame, return_dfs: bool = False, verbose: bool = False, path:str = None) -> tuple:
    """
    Gera um relatório sobre o status dos containers, incluindo aqueles que não estão rodando, 
    estão em reinicialização ou apresentam problemas de saúde.

    Args:
        container_status_df (pd.DataFrame): DataFrame com o status de cada container, conforme retornado por `verify_status_docker`.
        return_dfs (bool, opcional): Se True, retorna um dicionário com DataFrames categorizados por status dos containers. Padrão é False.
        verbose (bool, opcional): Se True, imprime informações adicionais para containers saudáveis.

    Returns:
        tuple: Uma tupla contendo:
            - int: Número total de containers com erros (não rodando, em reinicialização, com saúde comprometida, ou sem status de saúde).
            - dict (opcional): Dicionário com DataFrames categorizados por status de containers (se `return_dfs` for True), com chaves:
                - "not_running": Containers que não estão com estado 'running'.
                - "restarting": Containers em estado de reinicialização.
                - "unhealth": Containers com status de saúde 'unhealthy'.
                - "health_unavailable": Containers sem informações de saúde.
    """
    if path:
        container_status_df.to_csv(path,index=False)

    not_running = container_status_df[container_status_df['Status'] != 'running']
    restarting = container_status_df[container_status_df['Restarting'] == True]
    unhealth = container_status_df[container_status_df['Health'] == 'unhealthy']
    health_unavailable = container_status_df[container_status_df['Health'] == 'Indisponível']

    errors = 0

    if len(not_running) > 0:
        errors += len(not_running)
        logging.error("\nExistem containers que não estão com estado running.\n")
        logging.error(not_running.to_markdown())
    else:
        logging.info("\nTodos os containers estão com estado running.\n")

    if len(restarting) > 0:
        errors += len(restarting)
        logging.error("\nExistem containers que estão reiniciando.\n")
        logging.error(restarting.to_markdown())
    else:
        logging.info("\nNenhum container está reiniciando.\n")

    if len(unhealth) > 0:
        errors += len(unhealth)
        logging.warning("\nExistem containers que estão com a saúde comprometida.\n")
        logging.warning(unhealth.to_markdown())
    else:
        logging.info("\nTodos os containers estão com saúde OK.\n")

    if len(health_unavailable) > 0:
        errors += len(health_unavailable)
        logging.warning("\nExistem containers cuja informação de saúde está indisponível.\n")
        logging.warning(health_unavailable.to_markdown())
    elif verbose:
        logging.info("\nTodos os containers estão com saúde OK")

    if errors == 0:
        logging.info("\nTodos os containers estão rodando e com a saúde OK.\n")

    if return_dfs:
        return errors, {
            "not_running": not_running,
            "restarting": restarting,
            "unhealth": unhealth,
            "health_unavailable": health_unavailable,
        }

    return errors, {}

def save_logs_into_file(logs_lines:dict, path:str):
    """
    Salva os logs de cada container em arquivos separados dentro de um diretório especificado.

    Args:
        logs_lines (dict): Dicionário contendo os logs de cada container, no formato gerado por `get_all_docker_logs`.
        path (str): Caminho para o diretório onde os arquivos de log serão salvos.

    Raises:
        ValueError: Se o caminho especificado não for válido.
    """
    for container_name, log_data in logs_lines.items():
        log_file_path = os.path.join(path, f"{container_name}.log")
        try:
            with open(log_file_path, 'w', encoding='utf-8') as log_file:
                log_file.write(log_data.get("log_text", ""))
            logging.info(f"Logs do container '{container_name}' salvos em: {log_file_path}")
        except Exception as e:
            logging.error(f"Erro ao salvar logs do container '{container_name}': {e}")    
