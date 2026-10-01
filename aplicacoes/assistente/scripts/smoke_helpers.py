"""Helpers para scripts de smoke e diagnósticos locais sem containers."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import types
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv


def find_repo_root(start: Path) -> Path:
    """Sobe a árvore até encontrar o root do worktree Git."""
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError(f"Não foi possível encontrar root Git a partir de {start}")


def iter_json_objects(text: str) -> list[dict[str, Any]]:
    """Aceita JSON array, arrays concatenados ou objetos JSON por linha."""
    stripped = text.strip()
    if not stripped:
        return []
    decoder = json.JSONDecoder()
    items: list[dict[str, Any]] = []
    idx = 0
    while idx < len(stripped):
        while idx < len(stripped) and stripped[idx].isspace():
            idx += 1
        if idx >= len(stripped):
            break
        try:
            obj, end = decoder.raw_decode(stripped, idx)
        except json.JSONDecodeError:
            # Fallback linha-a-linha para saídas parcialmente textuais.
            for line in stripped[idx:].splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    line_obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(line_obj, dict):
                    items.append(line_obj)
                elif isinstance(line_obj, list):
                    items.extend(x for x in line_obj if isinstance(x, dict))
            break
        if isinstance(obj, dict):
            items.append(obj)
        elif isinstance(obj, list):
            items.extend(x for x in obj if isinstance(x, dict))
        idx = end
    return items


def import_hm_litellm_from_gitlab_if_needed() -> bool:
    """Preenche proxy/key do LiteLLM a partir de variáveis GitLab HM se faltarem.

    Não imprime valores. Retorna True quando conseguiu aplicar pelo menos URL ou key.
    Requer `glab` autenticado e acesso ao projeto atual.
    """
    current_key = os.getenv("LITELLM_PROXY_API_KEY") or ""
    current_url = os.getenv("LITELLM_PROXY_URL") or ""
    parsed = urlparse(current_url)

    needs_key = not current_key.strip()
    needs_url = not current_url.strip() or parsed.hostname in {
        None,
        "",
        "infra-litellm",
    }
    if not (needs_key or needs_url):
        return False

    try:
        project_proc = subprocess.run(
            ["glab", "api", "projects/:id"],
            check=False,
            cwd=find_repo_root(Path.cwd()),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        project_id = (
            str(json.loads(project_proc.stdout).get("id"))
            if project_proc.returncode == 0
            else ""
        )
    except Exception:
        project_id = ""
    if not project_id:
        return False

    try:
        proc = subprocess.run(
            ["glab", "api", f"projects/{project_id}/variables", "--paginate"],
            check=False,
            cwd=find_repo_root(Path.cwd()),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
    except Exception:
        return False
    if proc.returncode != 0:
        return False

    wanted = {
        "LITELLM_STANDARD_API_BASE": "LITELLM_PROXY_URL",
        "LITELLM_STANDARD_API_KEY": "LITELLM_PROXY_API_KEY",
        "LITELLM_STANDARD_MODEL": "_LITELLM_STANDARD_MODEL",
        "LITELLM_MINI_MODEL": "_LITELLM_MINI_MODEL",
        "LITELLM_NANO_MODEL": "_LITELLM_NANO_MODEL",
        "LITELLM_PROXY_URL": "LITELLM_PROXY_URL",
        "LITELLM_PROXY_API_KEY": "LITELLM_PROXY_API_KEY",
    }
    applied = False
    for item in iter_json_objects(proc.stdout):
        if item.get("environment_scope") not in {"homologacao", "*"}:
            continue
        gitlab_key = str(item.get("key") or "")
        env_key = wanted.get(gitlab_key)
        value = str(item.get("value") or "")
        if not env_key or not value:
            continue
        if env_key.startswith("_LITELLM_"):
            os.environ[env_key.removeprefix("_")] = value
            applied = True
            continue
        if env_key == "LITELLM_PROXY_URL" and not needs_url:
            continue
        if env_key == "LITELLM_PROXY_API_KEY" and not needs_key:
            continue
        os.environ[env_key] = value
        applied = True
    return applied


def load_worktree_envs(app_dir: Path, *, import_gitlab_hm: bool = True) -> list[Path]:
    """Carrega envs do root do worktree e do diretório da app."""
    repo_root = find_repo_root(app_dir)
    candidates = [
        repo_root / "default.env",
        repo_root / "security.env",
        repo_root / ".env",
        app_dir / ".env",
        app_dir / "security.env",
    ]
    loaded: list[Path] = []
    for env_file in candidates:
        if env_file.exists():
            load_dotenv(env_file, override=True)
            loaded.append(env_file)

    if not os.getenv("SEI_API_DB_ADDRESS") and os.getenv("SEI_ADDRESS"):
        os.environ["SEI_API_DB_ADDRESS"] = os.environ["SEI_ADDRESS"]

    local_required_defaults = {
        "SOLR_USER": "local-smoke-solr-user",
        "SOLR_PASSWORD": "local-smoke-solr-password",
        "DB_SEIIA_USER": "local-smoke-db-user",
        "DB_SEIIA_PWD": "local-smoke-db-password",
        "SEI_API_DB_ADDRESS": "http://local-smoke-sei-api",
        "SEI_API_DB_IDENTIFIER_SERVICE": "local-smoke-service",
    }
    for key, value in local_required_defaults.items():
        os.environ.setdefault(key, value)

    for key in (
        "LITELLM_PROXY_URL",
        "DB_SEIIA_HOST",
        "DB_SEIIA_PORT",
        "DB_SEIIA_ASSISTENTE",
        "SEI_API_DB_IDENTIFIER_SERVICE",
    ):
        value = os.getenv(key)
        if value and "${" in value:
            os.environ[key] = os.path.expandvars(value)

    if import_gitlab_hm:
        import_hm_litellm_from_gitlab_if_needed()

    if urlparse(os.getenv("LITELLM_PROXY_URL") or "").hostname == "rhgicdpdin02":
        standard_model = os.getenv("LITELLM_STANDARD_MODEL", "openai/seiia-hm")
        mini_model = os.getenv("LITELLM_MINI_MODEL", "openai/seiia-hm-mini")
        nano_model = os.getenv("LITELLM_NANO_MODEL", "openai/seiia-hm-nano")
        for key, value in {
            "LITELLM_STANDARD_MODEL_NAME": standard_model,
            "LITELLM_MINI_MODEL_NAME": mini_model,
            "LITELLM_NANO_MODEL_NAME": nano_model,
        }.items():
            os.environ[key] = value.removeprefix("openai/")

    return loaded


def install_local_smoke_stubs() -> None:  # noqa: C901  # NOSONAR
    """Neutraliza side-effects de Postgres/Redis no smoke local.

    Mantém isolamento do probe de embeddings e outros side-effects de DB/Redis.
    """

    class DummyMetaData:
        def create_all(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
            return None

    class DummyBasePgvector:
        metadata = DummyMetaData()

    class DummyEngine:
        def connect(self):
            return self

        def execute(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
            return None

        def commit(self) -> None:
            return None

        def dispose(self) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, ARG002
            return False

    class DummyAsyncDbInstance:
        engine = DummyEngine()
        async_engine = None
        conn_str = "postgresql://stub:***@local-smoke/stub"

        async def connect(self):
            return self

        @staticmethod
        def hide_password(connection_string: str) -> str:
            return connection_string

        async def close(self) -> None:
            return None

    db_instances = types.ModuleType("sei_ia.data.database.db_instances")
    db_instances.BasePgvector = DummyBasePgvector
    db_instances.app_db_instance = DummyAsyncDbInstance()
    sys.modules["sei_ia.data.database.db_instances"] = db_instances

    table_manager = types.ModuleType("sei_ia.data.database.table_manager")

    class DummyTableManager:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
            pass

        def initialize_all_tables(self) -> bool:
            return True

    table_manager.TableManager = DummyTableManager
    sys.modules["sei_ia.data.database.table_manager"] = table_manager

    runtime_bootstrap = types.ModuleType("sei_ia.data.database.runtime_bootstrap")

    async def initialize_runtime_database(
        _db: Any,
        _metadata: Any,
    ) -> None:
        return None

    runtime_bootstrap.initialize_runtime_database = initialize_runtime_database
    sys.modules["sei_ia.data.database.runtime_bootstrap"] = runtime_bootstrap

    session_checkpointer = types.ModuleType("sei_ia.services.session_fs.checkpointer")
    dummy_checkpointer = object()

    async def get_session_checkpointer() -> object:
        return dummy_checkpointer

    async def close_session_checkpointer() -> None:
        return None

    session_checkpointer.get_session_checkpointer = get_session_checkpointer
    session_checkpointer.close_session_checkpointer = close_session_checkpointer
    sys.modules["sei_ia.services.session_fs.checkpointer"] = session_checkpointer

    session_runtime = types.ModuleType("sei_ia.services.session_fs.runtime")

    async def get_session_manager() -> object:
        return object()

    async def run_sweeper() -> None:
        await asyncio.Event().wait()

    session_runtime.get_session_manager = get_session_manager
    session_runtime.run_sweeper = run_sweeper
    sys.modules["sei_ia.services.session_fs.runtime"] = session_runtime


def make_app(use_local_stubs: bool = True):
    """Import tardio para garantir env carregado antes de settings_config."""
    if use_local_stubs:
        install_local_smoke_stubs()

    from sei_ia import main as main_module

    main_module.embedding_generator.provider.test_connection = lambda: True

    # Desliga timeout middleware no smoke para simplificar diagnóstico local.
    # Mantém RequestMiddleware para preencher request.state.body/id/ip como no fluxo real.
    return main_module.get_app(
        enable_timeout_middleware=False,
        enable_request_middleware=True,
    )
