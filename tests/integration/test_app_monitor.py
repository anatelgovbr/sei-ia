#!/usr/bin/env python
"""Testes unitários para o módulo app_monitor."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import app_monitor
import pytest
from app_monitor import get_rss_url, main, setup_logging, validate_env_alias


@pytest.fixture()
def mock_path() -> MagicMock:
    """Fixture para criar um mock de Path."""
    with patch("app_monitor.Path") as mock:
        yield mock

@pytest.fixture()
def mock_validate_env_alias() -> MagicMock:
    """Fixture para criar um mock de validate_env_alias."""
    with patch("app_monitor.validate_env_alias") as mock:
        yield mock

@pytest.fixture()
def mock_get_parameters() -> MagicMock:
    """Fixture para criar um mock de get_parameters."""
    with patch("app_monitor.get_parameters") as mock:
        yield mock

@pytest.fixture()
def mock_setup_logging() -> MagicMock:
    """Fixture para criar um mock de setup_logging."""
    with patch("app_monitor.setup_logging") as mock:
        yield mock

@pytest.fixture()
def _mock_time_sleep(monkeypatch: MagicMock) -> None:
    """Fixture para fazer o mock de time.sleep e lançar InterruptedError."""
    def _mock_sleep(sleep:int) -> None:
        """Mock de time.sleep."""
        interrupted_error = InterruptedError()
        interrupted_error.args = (f"{sleep} Interrompendo o sleep para fins de teste",)
        raise interrupted_error
    monkeypatch.setattr(app_monitor.time, "sleep", _mock_sleep)


@pytest.mark.usefixtures("_mock_time_sleep")
def test_main(
    mock_path: MagicMock,
    mock_validate_env_alias: MagicMock,
    mock_get_parameters: MagicMock,
    mock_setup_logging: MagicMock
) -> None:
    """Teste para a função main."""
    # Configura o mock_get_parameters para retornar um dicionário de configurações simulado
    mock_get_parameters.return_value = {
        "alias_env": {"dev": "development"},
        "autodeploy_envs": {"my_service": ["dev"]},
        "rss_link_main_branch": {"my_service": "https://example.com/rss?service=my_service&target_branch=main"},
        "repo_local_path": {"my_service": "/local/path/to/my_service"},
    }

    # Cria um Path mock para simular a criação de diretórios e escrita de arquivos
    mock_shared_path = MagicMock()
    mock_path.return_value = mock_shared_path

    # Executa a função main, esperando que ela termine com a exceção InterruptedError devido ao mock do time.sleep
    with pytest.raises(InterruptedError):
        app_monitor.main()

    # Verifica se as funções mockadas foram chamadas conforme esperado
    mock_setup_logging.assert_called_once()
    mock_get_parameters.assert_called_once()
    mock_validate_env_alias.assert_called()


def test_auto_deploy_service_success(tmp_path: str) -> None:
    """Teste para a função auto_deploy_service em caso de sucesso."""
    service = "test_service"
    env_alias = "dev"
    dict_details = {"merge_id": "1234"}
    params = {"repo_local_path": {service: "path/to/repo"}}

    # Simula o retorno de execute_service_and_print_realtime
    mock_run_sh = MagicMock()
    mock_run_sh.wait.return_value = 0
    mock_run_sh.communicate.return_value = ("stdout", "stderr")

    with patch("app_monitor.execute_service_and_print_realtime", return_value=mock_run_sh), \
         patch("app_monitor.update_version_on_db") as mock_update_version_on_db, \
         patch("app_monitor.root_path", tmp_path):

        # Certifique-se de que o diretório 'shared' exista
        shared_path = tmp_path / "shared"
        shared_path.mkdir(parents=True, exist_ok=True)

        app_monitor.auto_deploy_service(service, dict_details, params, env_alias)

        # Verifica se o arquivo de detalhes foi criado com o conteúdo esperado
        details_path = shared_path / f"{service}-{env_alias}-details.json"
        assert details_path.exists() #noqa: S101
        with details_path.open() as file:
            details_content = json.load(file)
            assert details_content["deployed"] #noqa: S101

        # Verifica se update_version_on_db foi chamado corretamente
        mock_update_version_on_db.assert_called_once()


def test_setup_logging() -> None:
    """Teste para a função setup_logging."""
    with patch("app_monitor.logging.basicConfig"):
        setup_logging()


def test_validate_env_alias_valid() -> None:
    """Teste para validar um alias de ambiente válido."""
    params = {"alias_env": {"dev": "desenvolvimento", "prod": "producao"}}
    env_alias = "desenvolvimento"
    # Este teste não deve lançar uma exceção
    validate_env_alias(params, env_alias)


def test_validate_env_alias_invalid() -> None:
    """Teste para validar um alias de ambiente inválido."""
    params = {"alias_env": {"dev": "desenvolvimento", "prod": "producao"}}
    env_alias = "inexistente"
    with pytest.raises(ValueError, match=f"ENV_ALIAS '{env_alias}' não é válido."):
        validate_env_alias(params, env_alias)


def test_get_rss_url() -> None:
    """Teste para obter a URL do RSS."""
    params = {
        "rss_link_main_branch": {
            "service1": "https://git.anatel.gov.br/rss?service=service1&target_branch=main"
        },
        "repo_local_path": {"service1": "/local/path/to/service1"},
    }
    service = "service1"
    env_alias = "dev"
    env = "development"
    expected_url = "https://oauth2:git_token_not_found@git.anatel.gov.br/rss?service=service1&target_branch=development"
    with patch("app_monitor.GIT_TOKEN", "git_token_not_found"), \
         patch("app_monitor.GIT_BASE_URL", "git.anatel.gov.br"):
        assert  get_rss_url(service, env_alias, env, params) == expected_url #noqa: S101


@pytest.fixture()
def mock_params() -> dict:
    """Fixture para fornecer parâmetros simulados."""
    return {
        "alias_env": {"dev": "dev", "prod": "production"},
        "autodeploy_envs": {
            "service1": ["dev"],
            "service2": ["prod", "dev"]
        },
        "rss_link_main_branch": {
            "service1": "https://example.com/rss/service1/main",
            "service2": "https://example.com/rss/service2/main"
        },
        "repo_local_path": {
            "service1": "/path/to/service1",
            "service2": "/path/to/service2"
        }
    }

def test_main_auto_deploy_logic(tmp_path: str, mock_params: dict) -> None:
    """Teste para a lógica de auto-deploy na função main."""
    with patch("app_monitor.get_parameters", return_value=mock_params), \
         patch("app_monitor.os.environ", {"ENVIRONMENT": "dev"}), \
         patch("app_monitor.handle_merge_check", side_effect=[(True, {"merge_id": "123"}), (False, {})]), \
         patch("app_monitor.auto_deploy_service") as mock_auto_deploy, \
         patch("app_monitor.time.sleep", side_effect=InterruptedError):

        shared_path = tmp_path / "shared"
        shared_path.mkdir(parents=True, exist_ok=True)

        with pytest.raises(InterruptedError):
            main()

        # Confirma que auto_deploy_service foi chamado para o novo merge
        mock_auto_deploy.assert_called_once()


def test_get_rss_url_replaces_base_url_for_prod_envs() -> None:
    """Teste para verificar se a URL base é substituída pela URL de autenticação."""
    params = {
        "rss_link_main_branch": {
            "service1": "https://git.anatel.gov.br/rss?service=service1&target_branch=main"
        },
        "repo_local_path": {"service1": "/local/path/to/service1"},
    }
    service = "service1"
    env_alias = "prod"
    env = "main"
    expected_url = "https://oauth2:git_token_not_found@git.anatel.gov.br/rss?service=service1&target_branch=main"

    with patch("app_monitor.GIT_TOKEN", "git_token_not_found"), \
         patch("app_monitor.GIT_BASE_URL", "git.anatel.gov.br"):
        assert  get_rss_url(service, env_alias, env, params) == expected_url #noqa: S101


def test_auto_deploy_service_failure(tmp_path: Path) -> None:
    """Teste para a função auto_deploy_service em caso de falha."""
    service = "test_service"
    env_alias = "dev"
    dict_details = {"merge_id": "1234"}
    params = {"repo_local_path": {service: str(tmp_path / "path/to/repo")}}

    # Simula o retorno de execute_service_and_print_realtime com falha (código de saída diferente de 0)
    mock_run_sh = MagicMock()
    mock_run_sh.wait.return_value = 1  # Código de saída indicando erro
    mock_run_sh.communicate.return_value = ("stdout", "stderr")

    with patch("app_monitor.execute_service_and_print_realtime", return_value=mock_run_sh), \
         patch("app_monitor.logging.error") as mock_logging_error, \
         patch("app_monitor.root_path", tmp_path):

        app_monitor.auto_deploy_service(service, dict_details, params, env_alias)

        # Verifica se o logging de erro foi chamado com a mensagem esperada
        error_call_args = mock_logging_error.call_args[0][0]
        assert "ERRO DURANTE AUTODEPLOY" in error_call_args  # noqa: S101



