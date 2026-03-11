#!/usr/bin/env python
"""Módulo para testar funcoes uteis de aspecto geral."""
from unittest.mock import MagicMock, patch

import pytest
from utils import ServicoNaoPermitidoError, execute_service_and_print_realtime, get_parameters


def test_execute_service_and_print_realtime_success() -> None:
    """Testa a execução de um serviço e a impressão de sua saída em tempo real."""
    with patch("utils.Popen") as mock_popen:
        process_mock = MagicMock()
        process_mock.stdout.readline.side_effect = [
            "output line 1\n",
            "output line 2\n",
            "",
        ]
        process_mock.poll.side_effect = [None, None, 0]
        mock_popen.return_value = process_mock

        assert mock_popen.call_count == 0 #noqa: S101


def test_execute_service_and_print_realtime_not_allowed() -> None:
    """Testa servico não permitido com print realtime."""
    service = "non_existent_service"
    with pytest.raises(ServicoNaoPermitidoError):
        execute_service_and_print_realtime(service)


@patch("utils.CONFIG")
def test_execute_service_not_allowed(mock_config: MagicMock) -> None:
    """Testa servico não permitido sem print realtime."""
    mock_config.__getitem__.return_value = {
        "repo_local_path": []
    }  # Nenhum serviço permitido
    service = "non_existent_service"
    with pytest.raises(ServicoNaoPermitidoError):
        execute_service_and_print_realtime(service)




@patch.dict("utils.CONFIG", {
    "alias_env": {
        "dev": "development",
        "prod": "production"
    },
    "rss_link_main_branch": {
        "service1": "https://example.com/rss/service1/main",
        "service2": "https://example.com/rss/service2/main"
    },
    "repo_local_path": {
        "service1": "/path/to/service1",
        "service2": "/path/to/service2"
    },
    "autodeploy_envs": {
        "service1": "dev,prod",
        "service2": "prod"
    }
}, clear=True)
def test_get_parameters() -> None:
    """Teste para obter os parâmetros de configuração."""
    params = get_parameters()

    expected = {
        "alias_env": {"dev": "development", "prod": "production"},
        "rss_link_main_branch": {
            "service1": "https://example.com/rss/service1/main",
            "service2": "https://example.com/rss/service2/main"
        },
        "repo_local_path": {
            "service1": "/path/to/service1",
            "service2": "/path/to/service2"
        },
        "autodeploy_envs": {
            "service1": ["dev", "prod"],
            "service2": ["prod"]
        }
    }

    assert params == expected #noqa: S101



@patch.dict("utils.CONFIG", {"repo_local_path": {"api_sei": "/path/to/api_sei"}}, clear=True)
def test_service_execution_process_stderr(mocker: MagicMock) -> None: #noqa: ARG001
    """Teste para verificar o tratamento de stderr."""
    service = "api_sei"
    with patch("utils.Popen") as mock_popen:
        # Configure mock for Popen with stderr
        process_mock = MagicMock()
        process_mock.stdout.readline.side_effect = ["", ""]
        process_mock.poll.side_effect = [None, 0]
        process_mock.stderr.read.return_value = "error message"
        mock_popen.return_value = process_mock

        # Execute function
        with patch("utils.print") as mock_print:
            execute_service_and_print_realtime(service)

            # Validate stderr handling
            mock_print.assert_called_with("error message", flush=True)

