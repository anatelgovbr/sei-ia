"""
Modulo de gerenciamento de DAGs do Airflow em containers Docker.

Este módulo permite interagir com containers Docker executando o Airflow, coletando informações sobre 
DAGs, execuções de DAGs e estados de tarefas, além de capturar erros de importação de DAGs. Ele facilita o 
processo de execução de comandos no container e a conversão de saídas de texto em DataFrames para análise.

Exemplo de uso:

1. Obtendo informações sobre todos os DAGs no Airflow:

    ```python
    output_text = run_command(container, "airflow dags list")
    airflow_dags_df, error_airflow_lines = convert_docker_airflow_output_to_df(output_text)
    ```

2. Identificando erros de importação de DAGs:

    ```python
    dag_filename_error = get_airflow_dag_import_error(container, error_airflow_lines)
    ```

3. Coletando informações sobre execuções de DAGs e estados das tarefas associadas:

    ```python
    runs_df = get_dags_runs(container, airflow_dags_df, dag_filename_error)
    ```

4. Comparando as execuções de DAGs e identificando problemas de estado:

    ```python
    comparison_results = compare_dag_runs(runs_df)
    report_dag_run_issues(comparison_results, runs_df)
    ```

Funções:
    - run_command: Executa um comando em um container Docker e retorna a saída como uma string decodificada.
    - convert_docker_airflow_output_to_df: Converte a saída de listagem de DAGs do Airflow em um DataFrame e captura erros.
    - get_airflow_dag_import_error: Identifica e retorna arquivos de DAGs que falharam na importação.
    - get_dags_runs: Coleta informações sobre execuções de DAGs e estados das tarefas associadas em cada execução.
    - compare_dag_runs: Compara as execuções de DAGs com as informações do Airflow, identificando execuções com status inesperado e estado diferente de "success".
    - report_dag_run_issues: Gera um relatório para execuções com status inesperado e com estado diferente de "success", além de exibir o DataFrame completo das execuções de DAGs.
"""



import pandas as pd
import logging


def run_command(container, command: str) -> str:
    """
    Executa um comando em um container Docker e retorna a saída como uma string decodificada.

    Args:
        container: O objeto do container Docker no qual o comando será executado.
        command (str): O comando a ser executado no container.

    Returns:
        str: A saída do comando, decodificada em UTF-8.
    """
    result = container.exec_run(command)
    return result.output.decode('utf-8')


def convert_docker_airflow_output_to_df(text: str) -> tuple[pd.DataFrame, list[str]]:
    """
    Converte a saída do comando de listagem de DAGs do Airflow em um DataFrame pandas.

    Args:
        text (str): A saída de texto do comando Airflow, com linhas e colunas separadas por barras verticais.

    Returns:
        tuple[pd.DataFrame, list[str]]: Um DataFrame com os dados de DAGs e uma lista de linhas que contêm erros ou mensagens de aviso.
    """
    lines = text.splitlines()
    filtered_lines = []
    error_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("="):
            continue
        if "Error:" in line or "list-import-errors" in line:
            error_lines.append(line)
            continue
        filtered_lines.append(line)

    data = []
    for row in filtered_lines:
        cells = [cell.strip() for cell in row.split("|")]
        data.append(cells)

    if data:
        return pd.DataFrame(data[1:], columns=data[0]), error_lines
    else:
        return pd.DataFrame(), error_lines


def get_airflow_dag_import_error(container, error_airflow_lines: list[str]) -> list[str]:
    """
    Verifica e retorna uma lista de arquivos de DAG que falharam na importação.

    Args:
        container: O objeto do container Docker onde o comando será executado.
        error_airflow_lines (list[str]): Lista de linhas de erro identificadas na saída de listagem de DAGs do Airflow.

    Returns:
        list[str]: Lista de caminhos de arquivos de DAG que apresentaram erros de importação.
    """
    if len(error_airflow_lines) > 0:
        command = 'airflow dags list-import-errors'
        output_text_error = run_command(container, command)
        lines = output_text_error.splitlines()
        dag_filename_error = []

        for line in lines:
            if line.startswith('='):
                continue
            elif line.startswith('filepath'):
                continue
            else:
                line_splited = line.split("|")
                if line_splited[0].startswith(' '):
                    continue
                else:
                    dag_filename_error.append(line_splited[0])
        logging.error("Existem erros nas dags:")
        logging.error(f"{dag_filename_error!s}")
        return dag_filename_error
    else:
        return []


def get_dags_runs(container, airflow_dags_df: pd.DataFrame, dag_filename_error: list[str]) -> pd.DataFrame:
    """
    Coleta informações de execuções de DAGs e estados de tarefas associadas.

    Args:
        container: O objeto do container Docker onde os comandos do Airflow serão executados.
        airflow_dags_df (pd.DataFrame): DataFrame contendo informações dos DAGs listados.
        dag_filename_error (list[str]): Lista de caminhos de arquivos de DAG que apresentaram erros de importação.

    Returns:
        pd.DataFrame: DataFrame contendo informações agregadas sobre execuções de DAGs e estados de tarefas.
    """
    runs_data = []
    tasks_dfs = []

    for _, dag in airflow_dags_df.iterrows():
        dag_id = dag["dag_id"]
        
        runs_output = run_command(container, f"airflow dags list-runs -d {dag_id}")
        runs_df, error = convert_docker_airflow_output_to_df(runs_output)
        
        for idx_runs, run_row in runs_df.iterrows():
            run_id = run_row['run_id']
            execution_date = run_row['execution_date']
            state = run_row['state']
            
            tasks_output = run_command(container, f"airflow tasks states-for-dag-run {dag_id} {run_id}")
            tasks_df, errors = convert_docker_airflow_output_to_df(tasks_output)
            tasks_dfs.append(tasks_df)
            
            success = (tasks_df['state'] == 'success').sum()
            failed = (tasks_df['state'] == 'failed').sum()
            running = (tasks_df['state'] == 'running').sum()
            up_for_retry = (tasks_df['state'] == 'up_for_retry').sum()
            
            runs_data.append([
                dag_id, dag['fileloc'], dag["is_paused"], state,
                success, failed, running, up_for_retry
            ])

    for file in dag_filename_error:
        runs_data.append(["no_name", file, True, "Indisponivel", 0, 0, 0, 0])

    runs_columns = [
        "dag_id", "file_loc", "is_paused", "status",
        "success", "failed", "running", "up_for_retry"
    ]

    return pd.DataFrame(runs_data, columns=runs_columns)


def compare_dag_runs(runs_df: pd.DataFrame, path: str = None) -> dict:
    """
    Compara as execuções de DAGs com as informações dos DAGs do Airflow, identificando execuções faltantes,
    sobrantes, com status inesperado e com estado diferente de "success".

    Parameters:
    - runs_df (pd.DataFrame): DataFrame com informações sobre as execuções de DAGs.

    Returns:
    - dict: Dicionário contendo DataFrames para execuções faltantes, sobrantes, status inesperados,
                e DAGs com estado diferente de "success".
    """

    unexpected_status = runs_df[~runs_df['status'].isin(['success', 'failed', 'running', 'up_for_retry'])]

    non_success_runs = runs_df[runs_df['status'] != 'success']

    results = {
        'unexpected_status': unexpected_status[['dag_id', 'file_loc', 'status']],
        'non_success_runs': non_success_runs[['dag_id', 'file_loc', 'status']]
    }
    if path:
        unexpected_status.to_csv(os.path.join(path,f"airflow_unexpected_status.csv", index = False))
        non_success_runs.to_csv(os.path.join(path,f"airflow_non_success_runs.csv", index = False)) 


    return results


def report_dag_run_issues(results: dict, runs_df: pd.DataFrame) -> int:
    """
    Gera um relatório para as execuções faltantes, sobrantes, com status inesperado e com estado diferente de "success".

    Parameters:
    - results (dict): Dicionário contendo DataFrames para execuções faltantes, sobrantes, status inesperado e 
                      execuções com estado diferente de "success".

    Returns:
    - int: Número total de problemas encontrados.
    """
    error = 0
    if not results['unexpected_status'].empty:
        logging.error("\nExistem execuções com status inesperado nos seguintes DAGs:\n")
        logging.error(results['unexpected_status'].to_markdown(index=False))
        error += len(results['unexpected_status'])

    if not results['non_success_runs'].empty:
        logging.warning("\nExistem execuções com estado diferente de 'success' nos seguintes DAGs:\n")
        logging.warning(results['non_success_runs'].to_markdown(index=False))
        error += len(results['non_success_runs'])
    
    if error == 0:
        logging.info("\nNão foram encontrados erros nas execuções dos DAGs.\n")

    return error
