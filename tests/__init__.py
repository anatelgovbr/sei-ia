"""Orquestrador do healthchecker local do monorepo."""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime


def test_all() -> None:
    """Executa a suite principal do healthchecker."""
    storage_proj_dir_base = "/opt/sei-ia-storage"
    now = datetime.now().strftime("%Y%m%d")
    storage_proj_dir = os.path.join(storage_proj_dir_base, "logs", now)
    os.makedirs(storage_proj_dir, exist_ok=True)
    log_filename = os.path.join(
        storage_proj_dir, f"tests_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_filename)],
        force=True,
    )

    def log_print(msg: str) -> None:
        logging.info(msg)

    log_print("\n==================== TESTES ==================\n")

    import tests.airflow_tests as test_airflow
    import tests.connectivity_tests as test_conn
    import tests.docker_tests as test_docker
    import tests.env_tests as test_env
    import docker

    errors_envs = 0
    errors_conn = 0
    health_errors = 0
    solr_errors = 0
    assistente_errors = 0
    similaridade_errors = 0
    errors_docker = 0
    error_airflow_docker = 0
    error_litellm = 0
    comparison_df = None

    log_print("\n==================== ENVS ====================\n")
    try:
        variables_df = test_env.create_env_vars_df(test_env.env_vars)
        env_df = test_env.consolidate_env_files(["security", "default"])
        results_envs, comparison_df = test_env.compare_env_variables(
            variables_df,
            env_df,
            allowed_empty_vars=test_env.allowed_empty_vars,
            allowed_extra_vars=test_env.allowed_extra_vars,
        )
        errors_envs = test_env.report_env_issues(results_envs)
        test_env.anonymize_and_save(
            comparison_df, storage_proj_dir, test_env.anon_variables
        )
    except Exception as exc:
        errors_envs = 1
        log_print(f"Erro nos testes de variaveis de ambiente: {exc}")

    log_print("\n============== CONECTIVIDADE =================\n")
    try:
        if comparison_df is not None:
            config = test_conn.create_connectivity_config(comparison_df)
            results_conn = test_conn.test_connectivity_all(config)
            errors_conn, _ = test_conn.connectivity_report(
                results_conn, path=f"{storage_proj_dir}/conn_df.csv"
            )
        else:
            errors_conn = 1
            log_print(
                "Erro nos testes de conectividade: comparison_df nao foi inicializado."
            )
    except Exception as exc:
        errors_conn = 1
        log_print(f"Erro nos testes de conectividade: {exc}")

    log_print("\n====== TESTE DE SAUDE DOS ENDPOINTS ==========\n")
    try:
        health_results = test_conn.test_api_connectivity_and_response_all(
            test_conn.health_testes_urls
        )
        health_errors, _ = test_conn.connectivity_report(
            health_results, path=f"{storage_proj_dir}/health_df.csv"
        )
    except Exception as exc:
        health_errors = 1
        log_print(f"Erro nos testes de health endpoints: {exc}")

    log_print("\n====== TESTE DO LITELLM PROXY ================\n")
    try:
        litellm_result = test_conn.test_litellm_proxy_models()
        error_litellm = test_conn.report_litellm_proxy_status(litellm_result)
    except Exception as exc:
        error_litellm = 1
        log_print(f"Erro no teste do LiteLLM Proxy: {exc}")

    log_print("\n========= TESTE DE CONEXAO COM SOLR ==========\n")
    try:
        if comparison_df is not None:
            solr_config = test_conn.create_solr_config(comparison_df)
            solr_results = test_conn.test_connectivity_all_solr(solr_config)
            solr_errors, _ = test_conn.connectivity_report(
                solr_results, path=f"{storage_proj_dir}/solr_df.csv"
            )
        else:
            solr_errors = 1
            log_print("Erro nos testes de Solr: comparison_df nao foi inicializado.")
    except Exception as exc:
        solr_errors = 1
        log_print(f"Erro nos testes de Solr: {exc}")

    log_print("\n===== TESTE DE CONEXAO COM BANCOS INTERNOS ===\n")
    try:
        if comparison_df is not None:
            _, assistente_db, similaridade_db = test_conn.create_postgres_config(
                comparison_df
            )
            if assistente_db:
                assistente_results = test_conn.verify_all_tables(
                    assistente_db,
                    test_conn.assistente_tables,
                    None,
                    "postgres",
                    verbose=False,
                )
                assistente_errors, _ = test_conn.connectivity_report(
                    assistente_results,
                    path=f"{storage_proj_dir}/table_assistente_df.csv",
                )
            else:
                assistente_errors = 1
                log_print("Nao foi possivel conectar ao banco do assistente.")

            if similaridade_db:
                similaridade_results = test_conn.verify_all_tables(
                    similaridade_db,
                    test_conn.similaridade_tables,
                    None,
                    "postgres",
                    verbose=False,
                )
                similaridade_errors, _ = test_conn.connectivity_report(
                    similaridade_results,
                    path=f"{storage_proj_dir}/table_similaridade_df.csv",
                )
            else:
                similaridade_errors = 1
                log_print("Nao foi possivel conectar ao banco da similaridade.")
        else:
            assistente_errors = 1
            similaridade_errors = 1
            log_print("Erro nos testes de banco: comparison_df nao foi inicializado.")
    except Exception as exc:
        assistente_errors = 1
        similaridade_errors = 1
        log_print(f"Erro nos testes de bancos internos: {exc}")

    log_print("\n=================== DOCKER ===================\n")
    try:
        container_status = test_docker.get_docker_containers(verbose=False)
        container_status_df = test_docker.verify_status_docker(
            container_status, test_docker.containers_names, verbose=False
        )
        errors_docker, _ = test_docker.report_container_status(
            container_status_df,
            return_dfs=True,
            verbose=True,
            path=f"{storage_proj_dir}/containers_status_df.csv",
        )
        logs_lines = test_docker.get_all_docker_logs(container_status, 300, False)
        test_docker.save_logs_into_file(logs_lines, storage_proj_dir)
        test_docker.report_docker_logs(logs_lines, False)
    except Exception as exc:
        errors_docker = 1
        log_print(f"Erro nos testes de Docker: {exc}")

    log_print("\n=================== AIRFLOW ==================\n")
    try:
        client = docker.from_env()
        container_name = container_status_df[
            container_status_df["Nome"].str.contains("etl-airflow-webserver")
        ]["Nome"].values[0]
        container = client.containers.get(container_name)

        output_text = test_airflow.run_command(container, "airflow dags list")
        airflow_dags_df, error_airflow_lines = (
            test_airflow.convert_docker_airflow_output_to_df(output_text)
        )
        airflow_dags_df.to_csv(f"{storage_proj_dir}/airflow_dags_df.csv", index=False)
        test_airflow.get_airflow_dag_import_error(container, error_airflow_lines)
    except Exception as exc:
        error_airflow_docker = 1
        log_print(f"Erro no teste do Airflow: {exc}")

    log_print("\n============== RESUMO - TESTES ===============\n")
    summary = {
        "envs": errors_envs,
        "connectivity": errors_conn,
        "health": health_errors,
        "litellm": error_litellm,
        "solr": solr_errors,
        "db_assistente": assistente_errors,
        "db_similaridade": similaridade_errors,
        "docker": errors_docker,
        "airflow": error_airflow_docker,
    }
    for key, value in summary.items():
        status = "OK" if value == 0 else f"ERROS={value}"
        log_print(f"{key}: {status}")

    shutil.make_archive(storage_proj_dir, "zip", storage_proj_dir)
    total_errors = sum(summary.values())
    if total_errors:
        raise SystemExit(1)
