"""sync_config module."""

from airflow import DAG

from jobs.envs import LIST_RETRY_DELAYS_4t, dags_default_args
from jobs.scripts_airflow.operator import CustomPythonRetryOperator

with DAG(
    dag_id="system_create_mlt_weights_config",
    schedule="0 * * * *",  # Executar a cada hora
    tags=["config"],
    max_active_runs=1,
    default_args=dags_default_args,
) as dag2:
    from jobs.configs.parameters.conf_mlt_fields_weights import main

    build_config_task = CustomPythonRetryOperator(
        task_id="build_config",
        python_callable=main,
        retries=len(LIST_RETRY_DELAYS_4t),
        retry_delay=LIST_RETRY_DELAYS_4t[0],
    )
