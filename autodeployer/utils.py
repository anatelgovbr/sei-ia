#!/usr/bin/env python3
"""Módulo com funções utilitárias para o autodeployer."""

import configparser
from pathlib import Path
from subprocess import PIPE, Popen
from typing import Any, Dict

CONFIG = configparser.ConfigParser()
CONFIG.read("autodeployer/setup.cfg")
root_path = Path().absolute() / Path(CONFIG["repo_local_path"]["root_path"])


class ServicoNaoPermitidoError(Exception):
    """Exceção para serviços não permitidos no autodeployer."""

    def __init__(self, service: str) -> None:
        """Inicializa a exceção."""
        super().__init__(f"Serviço não permitido: {service}")


def get_parameters() -> Dict[str, Any]:
    """Lê e retorna os parâmetros de configuração do autodeployer a partir do arquivo 'setup.cfg'.

    Returns:
    -------
        dict: Dicionário contendo os parâmetros de configuração.

    """
    alias_env = dict(CONFIG["alias_env"])
    rss_link_main_branch = dict(CONFIG["rss_link_main_branch"])
    repo_local_path = dict(CONFIG["repo_local_path"])

    autodeploy_envs = {service: value.split(",") for service, value in CONFIG["autodeploy_envs"].items()}

    return {
        "alias_env": alias_env,
        "rss_link_main_branch": rss_link_main_branch,
        "repo_local_path": repo_local_path,
        "autodeploy_envs": autodeploy_envs,
    }


def execute_service_and_print_realtime(service: str) -> Popen:
    """Executa um comando shell e imprime o resultado em tempo real.

    Args:
    ----
        service (str): Nome do serviço a ser executado.

    Returns:
    -------
        Popen: Objeto Popen representando o processo executado.

    """
    allowed_services = list(CONFIG["repo_local_path"])

    if service in allowed_services:
        script_path = root_path / Path(f"services/{service}.sh")

        process = Popen(["sh", script_path], stdin=PIPE, stdout=PIPE, text=True)  # noqa: S603,S607

    else:
        raise ServicoNaoPermitidoError(service)

    while True:
        output = process.stdout.readline()
        if output == "" and process.poll() is not None:
            break
        if output:
            print(output.strip(), end="\n", flush=True)  # noqa: T201 # pragma: no cover

    if process.stderr:  # pragma: no cover
        print(process.stderr.read(), flush=True)  # noqa: T201

    return process
