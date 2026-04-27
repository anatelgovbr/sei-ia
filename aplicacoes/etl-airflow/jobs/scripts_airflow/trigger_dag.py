"""Script para fazer trigger de DAGs do Airflow com configuração personalizada."""

import asyncio
import contextlib
from datetime import datetime
from typing import Any

import httpx

from jobs.envs import AIRFLOW_API_BASE_URL


class AirflowDagTrigger:
    """Classe para fazer trigger de DAGs do Airflow com configuração personalizada."""

    def __init__(
        self,
        base_url: str,
        username: str = "airflow",
        password: str = "airflow",  # noqa: S107 - Local dev default, not production secret
    ) -> None:
        """Inicializa o trigger de DAGs.

        Args:
            base_url: URL base da API do Airflow (ex: http://localhost:8080/api/v1)
            username: Usuário para autenticação (padrão: airflow)
            password: Senha para autenticação (padrão: airflow)
        """
        self.base_url = base_url
        self.auth = (username, password)

    async def trigger_dag(
        self,
        dag_id: str,
        conf: dict[str, Any] | None = None,
        dag_run_id: str | None = None,
    ) -> dict[str, Any]:
        """Faz trigger de uma DAG com configuração personalizada de forma assíncrona.

        Args:
            dag_id: ID da DAG a ser executada
            conf: Dicionário com configurações para a DAG run
            dag_run_id: ID personalizado para a DAG run (opcional)

        Returns:
            Dicionário com a resposta da API do Airflow

        Raises:
            Exception: Se houver erro na requisição
        """
        url = f"{self.base_url}/dags/{dag_id}/dagRuns"

        # Prepara o payload
        payload = {}

        if conf:
            payload["conf"] = conf

        if dag_run_id:
            payload["dag_run_id"] = dag_run_id
        else:
            # Gera um ID único baseado no timestamp com microsegundos
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            payload["dag_run_id"] = f"manual_trigger_{timestamp}"

        try:
            async with httpx.AsyncClient(auth=self.auth) as client:
                response = await client.post(
                    url=url, json=payload, headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    return response.json()
                error_msg = f"Erro ao fazer trigger da DAG '{dag_id}': {response.status_code} - {response.text}"
                raise Exception(error_msg)

        except httpx.RequestError as e:
            error_msg = f"Erro de conexão ao fazer trigger da DAG '{dag_id}': {e!s}"
            raise Exception(error_msg) from e

    async def trigger_dag_with_params(self, dag_id: str, **kwargs) -> dict[str, Any]:
        """Método conveniente para fazer trigger de uma DAG passando parâmetros como argumentos.

        Args:
            dag_id: ID da DAG a ser executada
            **kwargs: Parâmetros que serão passados como configuração para a DAG

        Returns:
            Dicionário com a resposta da API do Airflow
        """
        return await self.trigger_dag(dag_id=dag_id, conf=kwargs)

    async def get_dag_info(self, dag_id: str) -> dict[str, Any]:
        """Obtém informações sobre uma DAG de forma assíncrona.

        Args:
            dag_id: ID da DAG

        Returns:
            Dicionário com informações da DAG
        """
        url = f"{self.base_url}/dags/{dag_id}"

        try:
            async with httpx.AsyncClient(auth=self.auth) as client:
                response = await client.get(url=url)

                if response.status_code == 200:
                    return response.json()
                error_msg = f"Erro ao obter informações da DAG '{dag_id}': {response.status_code} - {response.text}"
                raise Exception(error_msg)

        except httpx.RequestError as e:
            error_msg = f"Erro de conexão ao obter informações da DAG '{dag_id}': {e!s}"
            raise Exception(error_msg) from e


async def trigger_dag_simple(
    dag_id: str,
    conf: dict[str, Any] | None = None,
    host: str = "localhost",
    port: int = 8080,
    username: str = "airflow",
    password: str = "airflow",  # noqa: S107 - Local dev default, not production secret
) -> dict[str, Any]:
    """Função simples para fazer trigger de uma DAG de forma assíncrona.

    Args:
        dag_id: ID da DAG a ser executada
        conf: Dicionário com configurações para a DAG run
        host: Host do Airflow (padrão: localhost)
        port: Porta do Airflow (padrão: 8080)
        username: Usuário para autenticação (padrão: airflow)
        password: Senha para autenticação (padrão: airflow)

    Returns:
        Dicionário com a resposta da API do Airflow
    """
    base_url = f"http://{host}:{port}/api/v1"
    trigger = AirflowDagTrigger(base_url=base_url, username=username, password=password)
    return await trigger.trigger_dag(dag_id=dag_id, conf=conf)


# Exemplo de uso
async def main() -> None:
    """Função principal para demonstrar o uso da classe."""
    trigger = AirflowDagTrigger(
        base_url=AIRFLOW_API_BASE_URL,
        username="seiia",
        password="seiia",  # noqa: S106 - Demo code, not production secret
    )

    config = {
        "id_process": f"exemplo_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "data_inicio": "2024-01-01",
        "parametro_custom": "valor_teste_async",
    }

    with contextlib.suppress(Exception):
        await trigger.trigger_dag("process_indexing", conf=config)


if __name__ == "__main__":
    asyncio.run(main())
