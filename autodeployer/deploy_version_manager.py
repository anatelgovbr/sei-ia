#!/usr/bin/env python3
"""Módulo gerencia a versionamento de repositórios rastreando seus status".

Ele lê as informações mais recentes de commit, branch e tag de um caminho de
repositório fornecido e atualiza o banco de dados.
"""

import argparse
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Union

import git
from dotenv import load_dotenv
from sqlalchemy import TIMESTAMP, Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import exists

load_dotenv("/app/security.env")

POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "pgvector_all")

logging.basicConfig(level=logging.INFO)

Base = declarative_base()


class VersionRegister(Base):
    """Define a estrutura da tabela version_register no banco de dados."""

    __tablename__ = "version_register"

    id = Column(Integer, primary_key=True)
    hash = Column(String(255))
    branch = Column(String(255))
    tag = Column(String(255))
    url = Column(String(255))
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)


class DatabaseManager:
    """Gerencia operações de banco de dados para rastrear o versionamento de implantações."""

    def __init__(self, db_url: str) -> None:
        """Inicializa o gerente de banco de dados com uma URL de banco de dados.

        :param db_url: A URL do banco de dados.
        """
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def add_or_update_record(self, hash_value: str, branch_value: str, tag_value: str, url_value: str) -> None:
        """Adiciona um novo registro ou atualiza um existente na tabela version_register.

        :param hash_value: O hash do commit.
        :param branch_value: O nome da branch.
        :param tag_value: O nome da tag.
        :param url_value: A URL do repositório.
        """
        session = self.Session()

        record_exists = session.query(
            exists().where((VersionRegister.hash == hash_value) & (VersionRegister.branch == branch_value))
        ).scalar()

        if record_exists:
            existing_record = (
                session.query(VersionRegister)
                .filter((VersionRegister.hash == hash_value) & (VersionRegister.branch == branch_value))
                .first()
            )
            existing_record.tag = tag_value
            existing_record.updated_at = datetime.now(timezone.utc)
        else:
            new_record = VersionRegister(
                hash=hash_value,
                branch=branch_value,
                tag=tag_value,
                url=url_value,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(new_record)

        session.commit()
        session.close()


def get_params_of_repo(path_dir: Path) -> Dict[str, Any]:
    """Recupera parâmetros do repositório no caminho fornecido.

    :param path_dir: O caminho do diretório do repositório.
    :return: Um dicionário com os parâmetros do repositório.
    """
    repo = git.Repo(path_dir)
    current_tag = None
    for tag in repo.tags:
        if tag.commit == repo.head.commit:
            current_tag = tag.name
            break

    return {
        "hash": repo.head.commit.hexsha,
        "branch": repo.active_branch.name,
        "tag": current_tag,
        "url": repo.remotes.origin.url,
    }


def update_version_on_db(absolute_path_repo_local_updated: Union[str, Path]) -> None:
    """Atualiza as informações de versão do repositório no banco de dados.

    :param absolute_path_repo_local_updated: O caminho absoluto do repositório local que foi atualizado.
    """
    path = Path(absolute_path_repo_local_updated)

    if not path.is_dir():
        error_message = f"Caminho não encontrado: {absolute_path_repo_local_updated}"
        logging.error(error_message)
        raise FileNotFoundError(error_message)

    directories = [path]
    db_url = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}/sei_similaridade"
    manager = DatabaseManager(db_url)

    for directory in directories:
        params = get_params_of_repo(directory)
        manager.add_or_update_record(
            params.get("hash"),
            params.get("branch"),
            params.get("tag"),
            params.get("url"),
        )
        logging.info(f"Versão atualizada no banco de dados para {directory}.")


if __name__ == "__main__":  # pragma: no cover
    parser = argparse.ArgumentParser(description="Atualiza as informações de versão do repositório no banco de dados.")
    parser.add_argument("--path", type=str, help="O caminho absoluto do repositório local que foi atualizado.")

    args = parser.parse_args()

    if args.path:
        update_version_on_db(args.path)
    else:
        logging.info("Você deve fornecer o caminho do repositório usando o argumento --path.")
