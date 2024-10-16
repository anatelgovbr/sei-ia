#!/usr/bin/env python3
"""Este módulo é responsável por monitorar merges para cada serviço configurado para auto-deploy.

Ele verifica novos merges em relação ao último merge detectado e, se positivo,
inicia o script de auto-deploy do serviço.
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

from deploy_version_manager import update_version_on_db
from dotenv import load_dotenv
from merge_checker import handle_merge_check
from utils import execute_service_and_print_realtime, get_parameters, root_path

load_dotenv()
GIT_TOKEN = os.environ.get("GIT_TOKEN", "git_token_not_found")
GIT_BASE_URL = os.environ.get("GIT_BASE_URL", "git_base_url_not_found")
ENVIRONMENT = os.getenv("ENVIRONMENT")


def load_env_file(env_file_path):
    """
    Carrega variáveis de ambiente de um arquivo .env para os.environ
    """
    if not os.path.exists(env_file_path):
        print(f"Erro: arquivo {env_file_path} não encontrado.")
        sys.exit(1)
    with open(env_file_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

def get_deploy():
    original_path = os.getcwd()
    if ENVIRONMENT not in ["dev", "homol", "prod"]:
        print("Erro: não foi possível identificar ambiente válido.")
        sys.exit(1)

    # Identifica branch conforme o ambiente
    if ENVIRONMENT == "dev":
        branch = "desenvolvimento"
    elif ENVIRONMENT == "homol":
        branch = "homologacao"
    elif ENVIRONMENT == "prod":
        branch = "master"

    print(f"Branch de ambiente definida: {branch}")

    # Ajusta diretório e paths
    os.chdir("/app/")

    # Remove o diretório tmp/api_deployer se ele existir
    tmp_dir = "tmp/api_deployer"
    if os.path.exists(tmp_dir):
        subprocess.run(["rm", "-rf", tmp_dir])

    # Clona o repositório
    repo_url = f"https://oauth2:{GIT_TOKEN}@{GIT_BASE_URL}/deploy.git"
    destination = str(Path().absolute() / "tmp/api_deployer/sei_similaridade_deploy")
    services_dir = "autodeployer/services"
    try:
        subprocess.run(
            [
                "git",
                "clone",
                "-b",
                branch,
                "--single-branch",
                "--depth",
                "1",
                repo_url,
                destination,
            ],
            check=True,
        )
        print(f"Repositório clonado com sucesso em {destination}")
    except subprocess.CalledProcessError as e:
        print(f"Erro ao clonar o repositório: {e}")
        sys.exit(1)

    default_env_path = os.path.join(destination, "env_files", "default.env")
    env_specific_env_path = os.path.join(destination, "env_files", f"{ENVIRONMENT}.env")
    services_path = os.path.join(destination, services_dir)
    security_env_path = "./security.env"
    combined_env_path = ".env"

    with open(combined_env_path, "w") as dest:
        # Copia default.env
        with open(default_env_path, "r") as src:
            shutil.copyfileobj(src, dest)
        dest.write("\n")
        # Anexa o arquivo ENVIRONMENT.env
        with open(env_specific_env_path, "r") as src:
            shutil.copyfileobj(src, dest)
        dest.write("\n")
        # Anexa o arquivo security.env
        with open(security_env_path, "r") as src:
            shutil.copyfileobj(src, dest)
    # Copia o arquivo .env para o diretório de destino
    shutil.copy(combined_env_path, os.path.join(destination, ".env"))
    load_env_file('.env')
    os.chdir(destination)

    target_services_dir = "/app/autodeployer/services"
    if not os.path.exists(target_services_dir):
        os.makedirs(target_services_dir)
    sh_files = [f for f in os.listdir(services_path) if f.endswith('.sh')]
    for file_name in sh_files:
        full_file_name = os.path.join(services_path, file_name)
        if os.path.isfile(full_file_name):
            shutil.copy(full_file_name, target_services_dir)

    os.chdir(original_path)
    print(f"Arquivos .sh copiados para {target_services_dir}")
    print("##################################################")
    print("##################################################")
    print("# Configuração do ambiente concluída com sucesso. #")
    print("##################################################")
    print("##################################################")



def setup_logging() -> None:
    """Configura os parâmetros básicos para o sistema de logging."""
    # Cria o logger raiz
    logger = logging.getLogger()
    logger.setLevel(os.environ.get("LOGLEVEL", logging.INFO))

    # Cria um handler para o console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)

    # Cria um handler para o arquivo
    file_handler = logging.FileHandler("/var/log/autodeployer/autodeployer.log", mode="a")
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s", 
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)

    # Adiciona os handlers ao logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

def validate_env_alias(params: Dict[str, Any], env_alias: str) -> None:
    """Valida o alias do ambiente contra as configurações disponíveis.

    :param params: Parâmetros de configuração.
    :param env_alias: Alias do ambiente para validar.
    :raises ValueError: Se o alias do ambiente não for válido.
    """
    if env_alias not in params["alias_env"].values():
        mensagem_erro = f"ENV_ALIAS '{env_alias}' não é válido."
        logging.error(mensagem_erro)
        raise ValueError(mensagem_erro)


def get_rss_url(service: str, env_alias: str, env: str, params: Dict[str, Any]) -> str:
    """Constrói a URL RSS para o serviço dado com base no ambiente.

    :param service: O serviço para o qual construir a URL RSS.
    :param env_alias: O alias do ambiente.
    :param env: O ambiente.
    :param params: Parâmetros de configuração.
    :return: A URL RSS construída.
    """
    url_rss = params["rss_link_main_branch"][service]
    base_url = GIT_BASE_URL.split("/")[0]  # "https://git.anatel.gov.br"
    auth_url = f"oauth2:{GIT_TOKEN}@{base_url}"

    if env_alias != "prod":
        url_rss_base = url_rss.split("&target_branch=")[0]
        url_rss = f"{url_rss_base}&target_branch={env}"
    return url_rss.replace(base_url, auth_url)


def auto_deploy_service(service: str, dict_details: Dict[str, Any], params: Dict[str, Any], env_alias: str) -> None:
    """Inicia o processo de auto-deploy se um novo merge for detectado.

    :param service: O serviço para auto-deploy.
    :param dict_details: Dicionário contendo detalhes do merge.
    :param params: Parâmetros de configuração.
    :param env_alias: O alias do ambiente.
    """
    tempo_inicio = time.time()
    run_sh = execute_service_and_print_realtime(service)
    exit_code = run_sh.wait()

    stdout, stderr = run_sh.communicate()
    logging.info(f"STDOUT SERVICE .sh : {stdout}")

    if exit_code == 0:
        dict_details["deployed"] = True
        details_path = root_path / Path(f"shared/{service}-{env_alias}-details.json")
        details_path.write_text(json.dumps(dict_details))
        update_version_on_db(
            Path().absolute()
            / Path(f"tmp/api_deployer/sei_similaridade_deploy/tmp/{params['repo_local_path'][service]}")
        )
        logging.info(f"Tempo total de deploy em segundos: {time.time() - tempo_inicio}")
    else:
        logging.error(f"{exit_code}\nERRO DURANTE AUTODEPLOY:\n{stderr}")
        logging.info(f"Tempo total de deploy em segundos: {time.time() - tempo_inicio}")


def main() -> None:
    """Função principal para orquestrar o processo de monitoramento de auto-deployment."""
    setup_logging()
    env_alias = os.getenv("ENVIRONMENT", "env_alias_vazia").lower()
    params = get_parameters()

    validate_env_alias(params, env_alias)
    logging.info(f"Ambiente atual: {env_alias}")

    try:
        while True:
            for env in params["alias_env"]:
                if params["alias_env"][env] == env_alias:
                    for service in params["autodeploy_envs"]:
                        if env_alias in params["autodeploy_envs"][service]:
                            url_rss = get_rss_url(service, env_alias, env, params)
                            new_merge, dict_details = handle_merge_check(service, env_alias, url_rss)
                            if new_merge:
                                get_deploy()
                                auto_deploy_service(service, dict_details, params, env_alias)

                            shared_path = Path("autodeployer/shared")
                            shared_path.mkdir(exist_ok=True)
                            shared_last_merge_json = shared_path / f"{service}-{env_alias}-details.json"
                            shared_last_merge_json.write_text(json.dumps(dict_details))
            time.sleep(30)
    except KeyboardInterrupt:  # pragma: no cover
        logging.info("O processo de monitoramento de auto-deploy foi interrompido.")


if __name__ == "__main__":  # pragma: no cover
    main()