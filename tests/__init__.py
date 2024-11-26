"""
Módulo de Testes Automatizados para Ambiente, Conectividade e Docker

Este módulo executa uma série de testes automatizados para garantir que o ambiente, as conexões de rede, 
os bancos de dados, o Docker e o Airflow estão funcionando corretamente. Cada categoria de teste é realizada 
com o auxílio de funções específicas de teste, e os resultados são registrados em um arquivo de log com a 
data e hora atual.

Além disso, ao final dos testes, é gerado um resumo com a quantidade de erros encontrados em cada categoria.

"""

import logging
from datetime import datetime
import os
import shutil


def test_all():
    """
    Executa todos os testes automatizados em várias categorias (variáveis de ambiente, conectividade, bancos de dados externos e internos, Docker, e Airflow) e registra os resultados em um arquivo de log.

    O log é armazenado em um arquivo cujo nome é gerado com base na data e hora da execução do teste.
Durante a execução, os testes incluem:

    - Testes de variáveis de ambiente
    - Testes de conectividade de rede
    - Testes de conexão com o SOLR e bancos de dados externos e internos
    - Testes de status e logs do Docker
    - Testes de execução de DAGs do Airflow e problemas relacionados

Os resultados de cada categoria de teste são armazenados em um DataFrame, e um resumo final com 
a quantidade de erros é impresso no log.

Exceções que ocorrerem durante os testes são registradas no arquivo de log.

Returns:
    None: A função não retorna nada, mas gera um arquivo de log com o resumo dos testes.
    """
    print("LOGS")
    storage_proj_dir_base = os.getenv('STORAGE_PROJ_DIR', '/opt/sei-ia-storage').strip() 
    now = datetime.now().strftime('%Y%m%d')
    storage_proj_dir = os.path.join(storage_proj_dir_base, 'logs', datetime.now().strftime('%Y%m%d'))
    os.makedirs(storage_proj_dir, exist_ok=True)
    log_filename = os.path.join(storage_proj_dir, f'tests_{now}.log')
    
    logging.basicConfig(
        level=logging.INFO,  
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),  
            logging.FileHandler(log_filename)
        ]
    )
    
    def log_print(msg):
        # print(msg)
        logging.info(msg)

    log_print("\n==================== TESTES ==================\n")
    log_print("\n==================== ENVS ====================\n")
    
    import tests.env_tests as test_env
    import tests.connectivity_tests as test_conn
    import tests.docker_tests as test_docker
    import tests.airflow_tests as test_airflow
    import docker
    import pandas as pd
    
    errors_envs = 0
    errors_conn = 0
    errors_health = 0
    health_erros = 0
    solr_erros = 0
    db_sei_erros = 0
    assistente_erros = 0
    similaridade_erros = 0
    errors_docker = 0
    errors_log_docker = 0
    error_airflow_docker = 0

    try:
        variables_df = test_env.create_env_vars_df(test_env.env_vars)
        env_df = test_env.consolidate_env_files(['security', 'prod', 'default'])
        results_envs, comparison_df = test_env.compare_env_variables(variables_df, env_df)
        errors_envs = test_env.report_env_issues(results_envs)
        test_env.anom_and_save(comparison_df,storage_proj_dir,test_env.anon_variables)
    except Exception as e:
        errors_envs = 1
        log_print(f"Erro nos testes de variáveis de ambiente: {e}")

    log_print("\n============== CONECTIVIDADE =================\n")
    
    try:
        config = test_conn.create_connectivity_config(comparison_df)  # VEM DO TESTE DE ENV
        results_conn = test_conn.test_connectivity_all(config)
        log_print("\n====== TESTE DE CONECTIVIDADE - RESUMO =======\n")
        errors_conn, _ = test_conn.connectivity_report(results_conn, path = f"{storage_proj_dir}/conn_df.csv")
    except Exception as e:
        errors_conn = 1
        log_print(f"Erro nos testes de conectividade: {e}")
    
    log_print("\n====== TESTE DE SAUDE DOS ENDPOINTS ==========\n")
    try: 
        health_results = test_conn.test_api_connectivity_and_response_all(test_conn.health_testes_urls)
        health_erros, _ = test_conn.connectivity_report(health_results, path = f"{storage_proj_dir}/health_df.csv")
    except Exception as e:
        errors_health = 1
        log_print(f"Erro nos testes de conectividade: {e}")


    log_print("\n========= TESTE DE CONEXÃO COM SOLR ==========\n")
    
    try:
        solr_config = test_conn.create_solr_config(comparison_df)
        solr_results = test_conn.test_connectivity_all_solr(solr_config)
        solr_erros, _ = test_conn.connectivity_report(solr_results, path = f"{storage_proj_dir}/solr_df.csv")
    except Exception as e:
        solr_erros = 1
        log_print(f"Erro nos testes de conexão com o SOLR: {e}")
    
    log_print("\n===== TESTE DE CONEXÃO COM BANCO DE DADOS ====\n")
    log_print("\n================== EXTERNOS ==================\n")
    
    try:
        DB_SEI_SCHEMA, DATABASE_TYPE, db_instance = test_conn.create_external_sei_config(comparison_df)
        if db_instance:
            log_print("Sem erros de conexao com o BD do SEI")
        else:
            log_print("Não foi possível conectar com o BD do SEI")
        
        if db_instance:
            log_print("\n============== TABELAS DO SEI ================\n")
            log_print("\nVerificando a existencia das tabelas do sei:\n")
            db_sei_results = test_conn.verify_all_tables(db_instance, test_conn.sei_externo_tables, DB_SEI_SCHEMA, DATABASE_TYPE, verbose=False)
            db_sei_erros, _ = test_conn.connectivity_report(db_sei_results, path = f"{storage_proj_dir}/table_sei_df.csv")
    except Exception as e:
        db_sei_erros = 1
        log_print(f"Erro nos testes de conexão com o banco de dados SEI: {e}")
    
    log_print("\n================== INTERNOS ==================\n")
    
    try:
        postgres_config, assistente_db_instance, similaridade_db_instance = test_conn.create_postgres_config(comparison_df)
        if assistente_db_instance:
            log_print("Sem erros de conexao com o BD do Assistente")
        else:
            log_print("Não foi possível conectar com o BD do Assistente")
        
        if similaridade_db_instance:
            log_print("Sem erros de conexao com o BD do Sei-similaridade")
        else:
            log_print("Não foi possível conectar com o BD do Sei-similaridade")
        
        if assistente_db_instance:
            log_print("\n============= TABELAS DO ASSISTENTE ==========\n")
            log_print("\nVerificando a existencia das tabelas do assistente:\n")

            assistente_results = test_conn.verify_all_tables(assistente_db_instance, test_conn.assistente_tables, 'sei_llm','mysql' ,verbose=False)
            assistente_erros, _ = test_conn.connectivity_report(assistente_results, path = f"{storage_proj_dir}/table_assistente_df.csv")
        
        if similaridade_db_instance:
            log_print("\n============= TABELAS DE SIMILARIDADE =========\n")
            log_print("\nVerificando a existencia das tabelas de similaridade:\n")

            similaridade_results = test_conn.verify_all_tables(similaridade_db_instance, test_conn.similaridade_tables,None, 'mysql' ,verbose=False)
            similaridade_erros, _ = test_conn.connectivity_report(similaridade_results, path = f"{storage_proj_dir}/table_seisimilaridade_df.csv")
    except Exception as e:
        assistente_erros = 1
        similaridade_erros = 1
        log_print(f"Erro nos testes de bancos internos (Assistente e Similaridade): {e}")
    
    log_print("\n=================== DOCKER ====================\n")
    
    try:
        container_status = test_docker.get_docker_containers(verbose=False)
        container_status_df = test_docker.verify_status_docker(container_status, test_docker.containers_names, verbose=False)
        errors_docker, categorized_dfs = test_docker.report_container_status(container_status_df, return_dfs=True, verbose=True, path = f"{storage_proj_dir}/containers_status_df.csv")
        log_print("\n================ DOCKER - LOGS ================\n")
        logs_lines = test_docker.get_all_docker_logs(container_status, 1000, False)
        test_docker.save_logs_into_file(logs_lines,storage_proj_dir)
        errors_log_docker = test_docker.report_docker_logs(logs_lines, False)
    except Exception as e:
        errors_docker = 1
        errors_log_docker = 1
        log_print(f"Erro nos testes de Docker: {e}")
    
    log_print("\n=================== AIRFLOW ===================\n")
    
    try:
        client = docker.from_env()
        container_name = container_status_df[container_status_df['Nome'].str.contains("airflow-webserver")]['Nome'].values[0]
        container = client.containers.get(container_name)
        
        output_text = test_airflow.run_command(container, "airflow dags list")
        airflow_dags_df, error_airflow_lines = test_airflow.convert_docker_airflow_output_to_df(output_text)
        airflow_dags_df.to_csv(f"{storage_proj_dir}/airflow_dags_df.csv",index=False)
        dag_filename_error = test_airflow.get_airflow_dag_import_error(container, error_airflow_lines)
        # Comentado por estar levando muito tempo.
        # runs_df = test_airflow.get_dags_runs(container, airflow_dags_df, dag_filename_error)
        # airflow_results = test_airflow.compare_dag_runs(runs_df, storage_proj_dir)
        # airflow_errors = test_airflow.report_dag_run_issues(airflow_results, runs_df)
        
        # log_print("\n========== AIRFLOW - RESUMO DAG RUNS ==========\n")
        # log_print(runs_df.to_markdown(index=False))
    except Exception as e:
        error_airflow_docker = 1
        log_print(f"Erro no teste do Airflow: {e}")
    
    log_print("\n============== RESUMO - TESTES ================\n")
    
    data = {
        "Categoria": [
            "Env Variables", 
            "Conectividade", 
            "Health",
            "Conexão com SOLR", 
            "Banco de Dados Externo (SEI)", 
            "Banco de Dados Interno (Assistente)", 
            "Banco de Dados Interno (Similaridade)", 
            "Docker - Status", 
            "Docker - Logs", 
            "Airflow"
        ],
        "Quantidade de Erros": [
            errors_envs, 
            errors_conn, 
            health_erros,
            solr_erros, 
            db_sei_erros, 
            assistente_erros, 
            similaridade_erros, 
            errors_docker, 
            errors_log_docker, 
            error_airflow_docker
        ]
    }
    try:
        df_errors = pd.DataFrame(data)
        df_errors.to_csv(f"{storage_proj_dir}/resumo_df.csv",index=False)
        log_print(df_errors.to_markdown(index=False))
    except:
        log_print(data)
    log_print("\n=============== GERANDO O ZIP =================\n")
    try:
        zipfile = f"{storage_proj_dir_base}/logs/{now}"
        shutil.make_archive(zipfile, 'zip', storage_proj_dir)
        log_print(f"O arquivo {zipfile}.zip, foi gerado com sucesso")
    except Exception as e:
        logging.error(f"Não foi possivel gerar o zip.\n {e!s}")
