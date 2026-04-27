"""Limpa os logs do Airflow com base em um intervalo de tempo."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

from jobs.dags.logger import logger
from jobs.envs import dags_default_args


# Define a função para calcular a data 30 dias antes da execução
def timestamp_before_now(time_ago: timedelta) -> str:
    """Retorna o timestamp de um tempo atrás."""
    tz = ZoneInfo(
        "America/Sao_Paulo"
    )  # Usa o ZoneInfo para criar o objeto de fuso horário
    return (datetime.now(tz) - time_ago).strftime("%Y-%m-%dT%H:%M:%S")


with DAG(
    "system_clean_airflow_logs",
    start_date=pendulum.today("UTC").add(days=-1),
    default_args=dags_default_args,
    description="DAG para limpar logs do Airflow com mais de 30 dias",
    schedule="0 20 * * *",  # Executa todos os dias às 20h
) as dag:
    # Definir a tarefa BashOperator para executar o comando de limpeza do banco de dados
    logger.info("disparando comando shell via BashOperator")
    clean_db_task = BashOperator(
        task_id="clean_db",
        bash_command=f"airflow db clean --yes --skip-archive --clean-before-timestamp '{timestamp_before_now(timedelta(days=30))}'",
    )
