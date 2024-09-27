#!/usr/bin/env python3
"""Este módulo gerencia a versão da aplicação com o repositório.

Atualizando um registro no banco de dados com informações de hash, branch, tag e URL do último commit.
"""
from pathlib import Path

from deploy_version_manager import update_version_on_db
from utils import root_path


def local_manager_version() -> None:
    """Atualiza a versão da aplicação com o repositório local.

    Itera sobre os subdiretórios do diretório base e atualiza a versão da aplicação com o repositório local.
    """
    tmp_path = root_path / Path("tmp")

    for folder in tmp_path.glob("*/"):
        update_version_on_db(folder)


if __name__ == "__main__":
    local_manager_version()  # pragma: no cover
