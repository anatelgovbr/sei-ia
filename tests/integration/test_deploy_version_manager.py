#!/usr/bin/env python3
"""Este módulo contém testes para o gerenciador de versões de deploy."""

from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
from deploy_version_manager import (
    DatabaseManager,
    get_params_of_repo,
    update_version_on_db,
)
from sqlalchemy.exc import SQLAlchemyError


@pytest.fixture(autouse=True)
def mock_create_engine() -> Generator[Any, None, None]:
    """Mock the database engine creation."""
    with patch("sqlalchemy.create_engine") as mock:
        yield mock


@pytest.fixture()
def mock_db_session() -> Generator[Any, None, None]:
    """Mock the database session."""
    with patch("deploy_version_manager.sessionmaker") as mock:
        mock_session = mock.return_value()
        mock_session.query().scalar.return_value = False
        yield mock_session


@pytest.fixture()
def mock_git_repo() -> Generator[Any, None, None]:
    """Mock a Git repository object."""
    with patch("git.Repo") as mock:
        repo_mock = mock.return_value
        repo_mock.head.commit.hexsha = "dummy_hash"
        repo_mock.active_branch.name = "main"
        repo_mock.tags = []
        repo_mock.remotes.origin.url = "http://example.com/repo.git"
        yield repo_mock


@pytest.fixture()
def mock_path_is_dir() -> Generator[Any, None, None]:
    """Mock Path.is_dir to always return True."""
    with patch("pathlib.Path.is_dir") as mock:
        mock.return_value = True
        yield mock


def test_add_or_update_record_new_record(mock_db_session: MagicMock) -> None:
    """Test adding a new record."""
    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    db_manager = DatabaseManager("sqlite:///:memory:")

    hash_value = "abc123"
    branch_value = "main"
    tag_value = "v0.9"
    url_value = "https://example.com/repo.git"

    db_manager.add_or_update_record(hash_value, branch_value, tag_value, url_value)


def test_add_or_update_record_existing_record(mock_db_session: MagicMock) -> None:
    """Test updating an existing record."""
    existing_record = MagicMock(hash="abc123", branch="main", tag="v0.9", url="https://example.com/repo.git")
    mock_db_session.query.return_value.filter.return_value.first.return_value = existing_record

    db_manager = DatabaseManager("sqlite:///:memory:")

    hash_value = "abc123"
    branch_value = "main"
    tag_value = "v0.9"  # Updated tag
    url_value = "https://example.com/repo.git"

    db_manager.add_or_update_record(hash_value, branch_value, tag_value, url_value)

    assert existing_record.tag == tag_value #noqa: S101


def test_get_params_of_repo(mock_git_repo: MagicMock) -> None: #noqa: ARG001
    """Test getting repository parameters."""
    params = get_params_of_repo(Path("/path/to/repo"))
    assert params["hash"] == "dummy_hash" #noqa: S101
    assert params["branch"] == "main" #noqa: S101
    assert params["url"] == "http://example.com/repo.git" #noqa: S101
    assert "tag" not in params or params["tag"] is None #noqa: S101


def test_update_version_on_db_not_found() -> None:
    """Test updating version in database when path is not found."""
    with pytest.raises(FileNotFoundError):
        update_version_on_db("/non/existent/path")


def test_update_version_on_db_db_error(
    mock_git_repo: MagicMock, mock_db_session: MagicMock, mock_path_is_dir: MagicMock #noqa: ARG001
) -> None:
    """Test database error during version update."""
    mock_db_session.commit.side_effect = SQLAlchemyError
    with pytest.raises(SQLAlchemyError):
        update_version_on_db("/path/to/repo")


@patch("git.Repo")
def test_get_params_of_repo_with_tag(mock_repo: MagicMock) -> None:
    """Testa a obtenção de parâmetros do repositório incluindo a tag correta."""
    # Configura o mock do repositório Git
    mock_commit = MagicMock()
    mock_commit.hexsha = "dummy_hash"

    mock_repo.return_value.head.commit = mock_commit
    mock_repo.return_value.active_branch.name = "main"
    mock_repo.return_value.remotes.origin.url = "http://example.com/repo.git"

    tag_mock = MagicMock()
    tag_mock.commit = mock_commit  # Usa o mesmo mock_commit para garantir a igualdade
    tag_mock.name = "v1.0"
    mock_repo.return_value.tags = [tag_mock]

    params = get_params_of_repo(Path("/path/to/repo"))

    # Verifica se a tag correta foi identificada
    assert params["tag"] == "v1.0" #noqa: S101

def test_update_version_on_db(mock_db_session: MagicMock,
                              mock_git_repo: MagicMock,
                              mock_path_is_dir: MagicMock) -> None:
    """Testa a atualização das informações de versão no banco de dados para diretórios."""
    # Configuração do ambiente de teste
    repo_path = "/path/to/repo"
    mock_path_is_dir.return_value = True  # Garante que o diretório é considerado existente

    # Configuração do retorno esperado da função get_params_of_repo
    mock_git_repo.head.commit.hexsha = "dummy_hash"
    mock_git_repo.active_branch.name = "main"
    mock_git_repo.tags = []
    mock_git_repo.remotes.origin.url = "http://example.com/repo.git"

    # Configuração do mock para simular a sessão do banco de dados
    db_url = "sqlite:///:memory:"
    db_manager = DatabaseManager(db_url)
    mock_db_session.add = MagicMock()
    mock_db_session.commit = MagicMock()

    with patch("deploy_version_manager.DatabaseManager", return_value=db_manager):
        update_version_on_db(Path(repo_path))

    assert mock_db_session.add.called #noqa: S101
    assert mock_db_session.commit.called #noqa: S101
