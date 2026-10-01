from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_SCRIPT = REPOSITORY_ROOT / "migracao/1.2_1.3/migracao_1.2_1.3.py"
WRAPPER_SCRIPT = REPOSITORY_ROOT / "migracao/1.2_1.3/deploy-migracao-1.2-1.3.sh"
PREPARE_SCRIPT = REPOSITORY_ROOT / "migracao/1.2_1.3/prepare-upgrade-1.3.sh"

RETIRED_TARGET_CONFIG = {
    "PROJECT_ENDPOINT",
    "MODEL_DEPLOYMENT_NAME",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "AZURE_TENANT_ID",
    "AZURE_WEB_AGENT_ID",
    "BING_CONNECTION_NAME",
    "LITELLM_THINK_MAX_TOKENS",
}


def _write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def _env_names(path: Path) -> list[str]:
    names: list[str] = []
    assignment = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = assignment.match(raw_line.strip())
        if match:
            names.append(match.group(1))
    return names


def _env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    assignment = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = assignment.match(raw_line.strip())
        if not match:
            continue
        name, value = match.groups()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            quote = value[0]
            if quote == '"':
                try:
                    value = ast.literal_eval(value.replace(r"\$", "$"))
                except Exception:
                    value = value[1:-1]
            else:
                value = value[1:-1].replace(r"\'", "'")
        values[name] = value
    return values


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.fixture
def migration_fixture(tmp_path: Path) -> dict[str, Path]:
    source = tmp_path / "server-1.2"
    target = tmp_path / "server-1.3"
    certs = tmp_path / "volumes-1.2/certificado"
    overrides = tmp_path / "migration-overrides.env"

    _write(
        source / "env_files/default.env",
        "\n".join(
            (
                'export VOL_SEIIA_DIR="/var/lib/seiia-1.2"',
                'export NB_USER="operator"',
                "export NB_UID=4100",
                "export NB_GID=4100",
                "TAG_ESCAPED='v1.2.4.1'",
                "",
            )
        ),
        0o644,
    )
    _write(source / "env_files/prod.env", "export LOG_LEVEL=WARNING\n", 0o644)
    _write(source / "airflow.env", "AIRFLOW_UID=50000\n", 0o644)
    _write(source / ".env", "AIRFLOW_UID=50000\n", 0o600)
    _write(source / "docker-compose-prod.yaml", "services: {}\n", 0o644)
    _write(source / "docker-compose-ext.yaml", "services: {}\n", 0o644)
    _write(
        source / "env_files/security.env",
        """\
export GID_DOCKER=998
export ENVIRONMENT=prod
export DB_SEIIA_USER=db_user
export DB_SEIIA_PWD=db_password
export SOLR_USER=solr_user
export SOLR_PASSWORD=solr_password
export _AIRFLOW_WWW_USER_USERNAME=airflow_admin
export _AIRFLOW_WWW_USER_PASSWORD=airflow_web_password
export AIRFLOW_POSTGRES_USER=airflow_user
export AIRFLOW_POSTGRES_PASSWORD=airflow_db_password
export AIRFLOW_AMQP_USER=airflow_amqp
export AIRFLOW_AMQP_PASSWORD=airflow_amqp_password
export AIRFLOW__WEBSERVER__SECRET_KEY=airflow_secret
export ASSISTENTE_LITELLM_PROXY_API_KEY=sk-proxy-old
export SEI_ADDRESS=https://sei.test
export SEI_API_DB_IDENTIFIER_SERVICE=sei_service_token
export PROJECT_ENDPOINT=
export MODEL_DEPLOYMENT_NAME=
export AZURE_CLIENT_ID=
export AZURE_CLIENT_SECRET=
export AZURE_TENANT_ID=
export AZURE_WEB_AGENT_ID=
export BING_CONNECTION_NAME=
export LANGFUSE_URL=
export LANGFUSE_PUBLIC_KEY=
export LANGFUSE_SECRET_KEY=
""",
    )
    _write(
        source / "llm_config/litellm_config.yaml",
        """\
model_list:
  - model_name: standard
    litellm_params:
      model: azure/standard-deployment
      api_base: https://models.test
      api_key: provider-standard-key
      api_version: "2025-03-01-preview"
      max_completion_tokens: 32768
  - model_name: mini
    litellm_params:
      model: azure/mini-deployment
      api_base: https://mini-models.test
      api_key: provider-mini-key
      api_version: "2025-04-01-preview"
      max_completion_tokens: 32768
  - model_name: think
    litellm_params:
      model: azure/standard-deployment
      api_base: https://models.test
      api_key: provider-standard-key
      api_version: "2025-03-01-preview"
      max_completion_tokens: 64000
  - model_name: embedding
    litellm_params:
      model: azure/embedding-deployment
      api_base: https://embeddings.test
      api_key: provider-embedding-key
      api_version: "2025-03-01-preview"
""",
    )
    _write(
        overrides,
        """\
LITELLM_NANO_MODEL=azure/nano-deployment
LITELLM_NANO_API_BASE=https://nano-models.test
LITELLM_NANO_API_KEY=provider-nano-key
LITELLM_NANO_API_VERSION=2025-05-01-preview
LITELLM_STT_MODEL=azure/stt-deployment
LITELLM_STT_API_BASE=https://speech.test
LITELLM_STT_API_KEY=provider-stt-key
LITELLM_STT_API_VERSION=2025-03-01-preview
SEIIA_GATEWAY_HOST=gateway.test
SEIIA_CERT_DNS=
SEARXNG_SECRET_KEY=searxng-secret-generated-for-test
""",
    )

    target.mkdir()
    (target / "security_example.env").write_bytes(
        (REPOSITORY_ROOT / "security_example.env").read_bytes()
    )
    (target / "litellm_config.template.yaml").write_bytes(
        (REPOSITORY_ROOT / "litellm_config.template.yaml").read_bytes()
    )
    _write(
        target / "default.env",
        """\
NB_USER="seiia"
NB_UID=4000
NB_GID=4000
VOL_SEIIA_DIR="/var/lib/seiia-1.2"
""",
        0o644,
    )
    _write(target / "docker-compose.yml", "name: sei-ia\nservices: {}\n", 0o644)
    _write(target / "Makefile", ".PHONY: config up check\n", 0o644)

    certs.mkdir(parents=True)
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-batch",
            "-days",
            "2",
            "-subj",
            "/CN=gateway.test",
            "-addext",
            "subjectAltName=DNS:gateway.test",
            "-out",
            str(certs / "seiia.cert.pem"),
            "-keyout",
            str(certs / "seiia.cert.key"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    (certs / "seiia.cert.pem").chmod(0o644)
    (certs / "seiia.cert.key").chmod(0o600)

    return {
        "source": source,
        "target": target,
        "certs": certs,
        "overrides": overrides,
    }


def _run_migration(
    fixture: dict[str, Path], *mode: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(MIGRATION_SCRIPT),
            "--source-dir",
            str(fixture["source"]),
            "--deploy-dir",
            str(fixture["target"]),
            "--overrides",
            str(fixture["overrides"]),
            "--old-certs-dir",
            str(fixture["certs"]),
            *mode,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_wrapper(
    fixture: dict[str, Path], mode: str, *, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(WRAPPER_SCRIPT),
            "--source-dir",
            str(fixture["source"]),
            "--deploy-dir",
            str(fixture["target"]),
            "--overrides",
            str(fixture["overrides"]),
            "--old-certs-dir",
            str(fixture["certs"]),
            mode,
        ],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def test_apply_builds_exact_target_contract_without_modifying_source(
    migration_fixture: dict[str, Path],
) -> None:
    source_before = _tree_digest(migration_fixture["source"])

    result = _run_migration(migration_fixture, "--apply")

    assert result.returncode == 0, result.stderr
    assert "MIGRATION_STATUS=applied" in result.stdout
    assert _tree_digest(migration_fixture["source"]) == source_before
    expected_fingerprint = (
        subprocess.run(
            [
                "openssl",
                "x509",
                "-in",
                str(migration_fixture["certs"] / "seiia.cert.pem"),
                "-noout",
                "-fingerprint",
                "-sha256",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
        .split("=", maxsplit=1)[1]
    )
    assert f"CERTIFICATE_SHA256={expected_fingerprint}" in result.stdout

    target = migration_fixture["target"]
    assert _env_names(target / "security.env") == _env_names(
        target / "security_example.env"
    )
    assert (target / "litellm_config.yaml").read_bytes() == (
        target / "litellm_config.template.yaml"
    ).read_bytes()
    target_values = _env_values(target / "security.env")
    source_values = _env_values(migration_fixture["source"] / "env_files/security.env")
    assert RETIRED_TARGET_CONFIG - {"LITELLM_THINK_MAX_TOKENS"} <= set(source_values)
    assert RETIRED_TARGET_CONFIG.isdisjoint(target_values)
    assert target_values["LITELLM_PROXY_API_KEY"] == "sk-proxy-old"
    assert target_values["LITELLM_STANDARD_MODEL"] == "azure/standard-deployment"
    assert target_values["LITELLM_MINI_MODEL"] == "azure/mini-deployment"
    assert target_values["LITELLM_NANO_MODEL"] == "azure/nano-deployment"
    assert target_values["LITELLM_STANDARD_API_BASE"] == "https://models.test"
    assert target_values["LITELLM_STANDARD_API_KEY"] == "provider-standard-key"
    assert target_values["LITELLM_STANDARD_API_VERSION"] == "2025-03-01-preview"
    assert target_values["LITELLM_MINI_API_BASE"] == "https://mini-models.test"
    assert target_values["LITELLM_MINI_API_KEY"] == "provider-mini-key"
    assert target_values["LITELLM_MINI_API_VERSION"] == "2025-04-01-preview"
    assert target_values["LITELLM_NANO_API_BASE"] == "https://nano-models.test"
    assert target_values["LITELLM_NANO_API_KEY"] == "provider-nano-key"
    assert target_values["LITELLM_NANO_API_VERSION"] == "2025-05-01-preview"
    assert target_values["LITELLM_EMBEDDING_API_KEY"] == "provider-embedding-key"
    assert target_values["LITELLM_STT_API_KEY"] == "provider-stt-key"
    assert target_values["LOG_LEVEL"] == "WARNING"
    assert target_values["ASSISTENTE_USE_LANGFUSE"] == "false"
    assert target_values["SEIIA_GATEWAY_HOST"] == "gateway.test"
    assert target_values["SEARXNG_SECRET_KEY"] == "searxng-secret-generated-for-test"
    assert (target / ".runtime/certs/seiia.cert.pem").read_bytes() == (
        migration_fixture["certs"] / "seiia.cert.pem"
    ).read_bytes()
    assert (target / ".runtime/certs/seiia.cert.key").read_bytes() == (
        migration_fixture["certs"] / "seiia.cert.key"
    ).read_bytes()
    assert os.stat(target / "security.env").st_mode & 0o777 == 0o600
    assert os.stat(target / "litellm_config.yaml").st_mode & 0o777 == 0o600
    assert os.stat(target / ".runtime/certs/seiia.cert.key").st_mode & 0o777 == 0o600
    target_default = _env_values(target / "default.env")
    assert target_default["VOL_SEIIA_DIR"] == "/var/lib/seiia-1.2"
    assert target_default["NB_USER"] == "operator"
    assert target_default["NB_UID"] == "4100"
    assert target_default["NB_GID"] == "4100"


def test_apply_auto_generates_empty_searxng_secret(
    migration_fixture: dict[str, Path],
) -> None:
    overrides = migration_fixture["overrides"]
    overrides.write_text(
        overrides.read_text(encoding="utf-8").replace(
            "SEARXNG_SECRET_KEY=searxng-secret-generated-for-test",
            "SEARXNG_SECRET_KEY=",
        ),
        encoding="utf-8",
    )

    result = _run_migration(migration_fixture, "--apply")

    assert result.returncode == 0, result.stderr
    target_security = _env_values(migration_fixture["target"] / "security.env")
    overrides_values = _env_values(overrides)
    generated = target_security["SEARXNG_SECRET_KEY"]
    assert re.fullmatch(r"[0-9a-f]{64}", generated)
    assert overrides_values["SEARXNG_SECRET_KEY"] == generated


def test_apply_auto_generates_missing_proxy_and_searxng_secrets(
    migration_fixture: dict[str, Path],
) -> None:
    source_sec = migration_fixture["source"] / "env_files/security.env"
    source_sec.write_text(
        source_sec.read_text(encoding="utf-8").replace(
            "export ASSISTENTE_LITELLM_PROXY_API_KEY=sk-proxy-old\n", ""
        ),
        encoding="utf-8",
    )
    overrides = migration_fixture["overrides"]
    overrides.write_text(
        overrides.read_text(encoding="utf-8").replace(
            "SEARXNG_SECRET_KEY=searxng-secret-generated-for-test", ""
        ),
        encoding="utf-8",
    )

    result = _run_migration(migration_fixture, "--apply")

    assert result.returncode == 0, result.stderr
    target_security = _env_values(migration_fixture["target"] / "security.env")
    overrides_values = _env_values(overrides)

    proxy_key = target_security["LITELLM_PROXY_API_KEY"]
    searxng_key = target_security["SEARXNG_SECRET_KEY"]
    assert re.fullmatch(r"sk-[0-9a-f]{64}", proxy_key)
    assert re.fullmatch(r"[0-9a-f]{64}", searxng_key)
    assert overrides_values["LITELLM_PROXY_API_KEY"] == proxy_key
    assert overrides_values["SEARXNG_SECRET_KEY"] == searxng_key


def test_migration_blank_override_preserves_source_alias(
    migration_fixture: dict[str, Path],
) -> None:
    overrides = migration_fixture["overrides"]
    # Blank override does not erase source alias
    overrides.write_text(
        overrides.read_text(encoding="utf-8") + "\nLITELLM_PROXY_API_KEY='   '\n",
        encoding="utf-8",
    )
    result = _run_migration(migration_fixture, "--apply")
    assert result.returncode == 0, result.stderr
    target_sec = _env_values(migration_fixture["target"] / "security.env")
    assert target_sec["LITELLM_PROXY_API_KEY"] == "sk-proxy-old"


def test_migration_canonical_blank_selects_alias(
    migration_fixture: dict[str, Path],
) -> None:
    source_sec = migration_fixture["source"] / "env_files/security.env"
    source_sec.write_text(
        source_sec.read_text(encoding="utf-8").replace(
            "export ASSISTENTE_LITELLM_PROXY_API_KEY=sk-proxy-old\n",
            "export LITELLM_PROXY_API_KEY=''\nexport ASSISTENTE_LITELLM_PROXY_API_KEY=sk-alias-key\n",
        ),
        encoding="utf-8",
    )
    result = _run_migration(migration_fixture, "--apply")
    assert result.returncode == 0, result.stderr
    target_sec = _env_values(migration_fixture["target"] / "security.env")
    assert target_sec["LITELLM_PROXY_API_KEY"] == "sk-alias-key"


def test_migration_rejects_invalid_proxy_key(
    migration_fixture: dict[str, Path],
) -> None:
    overrides = migration_fixture["overrides"]
    # Invalid in overrides (no sk- prefix)
    overrides.write_text(
        overrides.read_text(encoding="utf-8")
        + "\nLITELLM_PROXY_API_KEY=invalid-key-no-sk\n",
        encoding="utf-8",
    )
    result = _run_migration(migration_fixture, "--apply")
    assert result.returncode != 0
    assert "LITELLM_PROXY_API_KEY" in result.stderr
    assert "invalid-key-no-sk" not in result.stdout
    assert "invalid-key-no-sk" not in result.stderr
    assert not (migration_fixture["target"] / "security.env").exists()

    # Invalid in source canonical does not fallback to valid alias
    overrides.write_text(
        overrides.read_text(encoding="utf-8").replace(
            "LITELLM_PROXY_API_KEY=invalid-key-no-sk\n", ""
        ),
        encoding="utf-8",
    )
    source_sec = migration_fixture["source"] / "env_files/security.env"
    source_sec.write_text(
        source_sec.read_text(encoding="utf-8")
        + "export LITELLM_PROXY_API_KEY=bad-canonical\nexport ASSISTENTE_LITELLM_PROXY_API_KEY=sk-valid-alias\n",
        encoding="utf-8",
    )
    result2 = _run_migration(migration_fixture, "--apply")
    assert result2.returncode != 0
    assert "LITELLM_PROXY_API_KEY" in result2.stderr
    assert "bad-canonical" not in result2.stderr
    assert not (migration_fixture["target"] / "security.env").exists()


def test_migration_check_is_readonly_and_accepts_missing_managed_secrets(
    migration_fixture: dict[str, Path],
) -> None:
    source_sec = migration_fixture["source"] / "env_files/security.env"
    source_sec.write_text(
        source_sec.read_text(encoding="utf-8").replace(
            "export ASSISTENTE_LITELLM_PROXY_API_KEY=sk-proxy-old\n", ""
        ),
        encoding="utf-8",
    )
    overrides = migration_fixture["overrides"]
    overrides.write_text(
        overrides.read_text(encoding="utf-8").replace(
            "SEARXNG_SECRET_KEY=searxng-secret-generated-for-test", ""
        ),
        encoding="utf-8",
    )

    source_before = _tree_digest(migration_fixture["source"])
    overrides_before = overrides.read_bytes()

    result = _run_migration(migration_fixture, "--check")

    assert result.returncode == 0, result.stderr
    assert "MIGRATION_STATUS=ready" in result.stdout
    assert (
        "SECRETS_TO_GENERATE=LITELLM_PROXY_API_KEY,SEARXNG_SECRET_KEY" in result.stdout
        or (
            "LITELLM_PROXY_API_KEY" in result.stdout
            and "SEARXNG_SECRET_KEY" in result.stdout
        )
    )
    assert _tree_digest(migration_fixture["source"]) == source_before
    assert overrides.read_bytes() == overrides_before
    assert not (migration_fixture["target"] / "security.env").exists()


def test_migration_prepare_secrets_persists_managed_keys_0600_and_idempotent(
    migration_fixture: dict[str, Path],
) -> None:
    source_sec = migration_fixture["source"] / "env_files/security.env"
    source_sec.write_text(
        source_sec.read_text(encoding="utf-8").replace(
            "export ASSISTENTE_LITELLM_PROXY_API_KEY=sk-proxy-old\n", ""
        ),
        encoding="utf-8",
    )
    overrides = migration_fixture["overrides"]
    overrides.write_text(
        overrides.read_text(encoding="utf-8").replace(
            "SEARXNG_SECRET_KEY=searxng-secret-generated-for-test", ""
        ),
        encoding="utf-8",
    )

    result = _run_migration(migration_fixture, "--prepare-secrets")

    assert result.returncode == 0, result.stderr
    assert "MIGRATION_STATUS=secrets-prepared" in result.stdout
    assert not (migration_fixture["target"] / "security.env").exists()
    assert os.stat(overrides).st_mode & 0o777 == 0o600

    overrides_after_first = overrides.read_text(encoding="utf-8")
    values_first = _env_values(overrides)
    assert re.fullmatch(r"sk-[0-9a-f]{64}", values_first["LITELLM_PROXY_API_KEY"])
    assert re.fullmatch(r"[0-9a-f]{64}", values_first["SEARXNG_SECRET_KEY"])

    # Idempotent second run
    result2 = _run_migration(migration_fixture, "--prepare-secrets")
    assert result2.returncode == 0, result2.stderr
    assert overrides.read_text(encoding="utf-8") == overrides_after_first


def test_migration_prepare_secrets_rejects_symlink_overrides(
    migration_fixture: dict[str, Path],
) -> None:
    overrides = migration_fixture["overrides"]
    symlink_overrides = overrides.parent / "symlink-overrides.env"
    symlink_overrides.symlink_to(overrides)
    bad_fixture = {**migration_fixture, "overrides": symlink_overrides}
    result_symlink = _run_migration(bad_fixture, "--prepare-secrets")
    assert result_symlink.returncode != 0
    assert (
        "link simbólico" in result_symlink.stderr or "inválid" in result_symlink.stderr
    )


def test_apply_rejects_unmappable_standard_and_think_models_without_writing(
    migration_fixture: dict[str, Path],
) -> None:
    source_yaml = migration_fixture["source"] / "llm_config/litellm_config.yaml"
    source_yaml.write_text(
        source_yaml.read_text(encoding="utf-8").replace(
            "model: azure/standard-deployment\n"
            "      api_base: https://models.test\n"
            "      api_key: provider-standard-key\n"
            '      api_version: "2025-03-01-preview"\n'
            "      max_completion_tokens: 64000",
            "model: azure/distinct-think-deployment\n"
            "      api_base: https://models.test\n"
            "      api_key: provider-standard-key\n"
            '      api_version: "2025-03-01-preview"\n'
            "      max_completion_tokens: 64000",
        ),
        encoding="utf-8",
    )

    result = _run_migration(migration_fixture, "--apply")

    assert result.returncode != 0
    assert "conflito não migrável" in result.stderr
    assert not (migration_fixture["target"] / "security.env").exists()
    assert not (migration_fixture["target"] / "litellm_config.yaml").exists()
    assert not (migration_fixture["target"] / ".runtime").exists()


def test_wrapper_check_is_read_only_and_does_not_call_docker_or_make(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"
    for command in ("docker", "make"):
        _write(
            fake_bin / command,
            f"#!/bin/sh\nprintf '%s\\n' '{command}' >> \"$MIGRATION_TEST_LOG\"\n",
            0o755,
        )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "MIGRATION_TEST_LOG": str(command_log),
    }

    result = _run_wrapper(migration_fixture, "--check", environment=environment)

    assert result.returncode == 0, result.stderr
    assert "MIGRATION_STATUS=ready" in result.stdout
    assert not command_log.exists()
    assert not (migration_fixture["target"] / "security.env").exists()
    assert not (migration_fixture["target"] / ".runtime").exists()


def test_check_rejects_non_v12_source_without_writing(
    migration_fixture: dict[str, Path],
) -> None:
    default_env = migration_fixture["source"] / "env_files/default.env"
    default_env.write_text("TAG_ESCAPED='v1.1.9'\n", encoding="utf-8")

    result = _run_migration(migration_fixture, "--check")

    assert result.returncode != 0
    assert "origem não identificada" in result.stderr
    assert not (migration_fixture["target"] / "security.env").exists()
    assert not (migration_fixture["target"] / ".runtime").exists()


def test_check_rejects_missing_required_file_without_writing(
    migration_fixture: dict[str, Path],
) -> None:
    (migration_fixture["source"] / "llm_config/litellm_config.yaml").unlink()

    result = _run_migration(migration_fixture, "--check")

    assert result.returncode != 0
    assert "arquivo obrigatório ausente" in result.stderr
    assert not (migration_fixture["target"] / "security.env").exists()
    assert not (migration_fixture["target"] / ".runtime").exists()


def test_check_accepts_source_key_with_group_read_only(
    migration_fixture: dict[str, Path],
) -> None:
    source_key = migration_fixture["certs"] / "seiia.cert.key"
    source_key.chmod(0o640)

    result = _run_migration(migration_fixture, "--check")

    assert result.returncode == 0, result.stderr
    assert "MIGRATION_STATUS=ready" in result.stdout
    assert not (migration_fixture["target"] / "security.env").exists()
    assert not (migration_fixture["target"] / ".runtime").exists()


@pytest.mark.parametrize("unsafe_mode", [0o620, 0o604, 0o641])
def test_check_rejects_source_key_with_unsafe_permissions(
    migration_fixture: dict[str, Path], unsafe_mode: int
) -> None:
    source_key = migration_fixture["certs"] / "seiia.cert.key"
    source_key.chmod(unsafe_mode)

    result = _run_migration(migration_fixture, "--check")

    assert result.returncode != 0
    assert "chave TLS" in result.stderr
    assert not (migration_fixture["target"] / "security.env").exists()
    assert not (migration_fixture["target"] / ".runtime").exists()


def test_check_plans_a_different_target_volume_root_without_writing(
    migration_fixture: dict[str, Path],
) -> None:
    target_default = migration_fixture["target"] / "default.env"
    target_default.write_text(
        target_default.read_text(encoding="utf-8").replace(
            "/var/lib/seiia-1.2", "/var/lib/another-installation"
        ),
        encoding="utf-8",
    )

    result = _run_migration(migration_fixture, "--check")

    assert result.returncode == 0, result.stderr
    assert "MIGRATION_STATUS=ready" in result.stdout
    assert _env_values(target_default)["VOL_SEIIA_DIR"].strip('"') == (
        "/var/lib/another-installation"
    )
    assert not (migration_fixture["target"] / "security.env").exists()
    assert not (migration_fixture["target"] / ".runtime").exists()


def test_apply_rejects_divergent_target_without_overwriting_it(
    migration_fixture: dict[str, Path],
) -> None:
    target_security = migration_fixture["target"] / "security.env"
    _write(target_security, "OPERATOR_VALUE=preserve-me\n")
    before = target_security.read_bytes()

    result = _run_migration(migration_fixture, "--apply")

    assert result.returncode != 0
    assert "arquivo de destino divergente" in result.stderr
    assert target_security.read_bytes() == before
    assert not (migration_fixture["target"] / "litellm_config.yaml").exists()
    assert not (migration_fixture["target"] / ".runtime").exists()


def test_second_apply_is_a_noop_with_clear_status(
    migration_fixture: dict[str, Path],
) -> None:
    first = _run_migration(migration_fixture, "--apply")
    target_before = _tree_digest(migration_fixture["target"])

    second = _run_migration(migration_fixture, "--apply")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "MIGRATION_STATUS=already-migrated" in second.stdout
    assert _tree_digest(migration_fixture["target"]) == target_before


def test_wrapper_propagates_make_check_failure(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"
    _write(
        fake_bin / "docker",
        '#!/bin/sh\nprintf \'docker %s\\n\' "$*" >> "$MIGRATION_TEST_LOG"\n',
        0o755,
    )
    _write(
        fake_bin / "make",
        """\
#!/bin/sh
printf 'make %s\n' "$*" >> "$MIGRATION_TEST_LOG"
last=''
for argument in "$@"; do last="$argument"; done
if [ "$last" = 'check' ]; then exit 9; fi
""",
        0o755,
    )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "MIGRATION_TEST_LOG": str(command_log),
    }

    result = _run_wrapper(migration_fixture, "--apply", environment=environment)

    assert result.returncode == 9
    assert "Migração concluída" not in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "docker compose" in commands
    assert "make --directory" in commands
    docker_command = next(
        line for line in commands.splitlines() if line.startswith("docker ")
    )
    assert "docker compose --profile *" in docker_command
    assert "down --remove-orphans" in docker_command
    assert " -v" not in docker_command
    assert " config\n" not in commands
    assert " up\n" in commands
    assert commands.rstrip().endswith("check")
    assert not (
        migration_fixture["target"] / ".runtime/migration-1.2-1.3.complete"
    ).exists()


def test_wrapper_apply_fails_and_preserves_old_stack_if_preflight_fails(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"
    _write(
        fake_bin / "docker",
        '#!/bin/sh\nprintf \'docker %s\\n\' "$*" >> "$MIGRATION_TEST_LOG"\n',
        0o755,
    )
    _write(
        fake_bin / "make",
        '#!/bin/sh\nprintf \'make %s\\n\' "$*" >> "$MIGRATION_TEST_LOG"\n',
        0o755,
    )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "MIGRATION_TEST_LOG": str(command_log),
    }
    overrides = migration_fixture["overrides"]
    overrides.write_text(
        overrides.read_text(encoding="utf-8")
        + "\nLITELLM_PROXY_API_KEY=invalid-key-no-sk\n",
        encoding="utf-8",
    )

    result = _run_wrapper(migration_fixture, "--apply", environment=environment)

    assert result.returncode != 0
    assert not command_log.exists()
    assert not (migration_fixture["target"] / "security.env").exists()


def test_wrapper_resumes_activation_then_second_apply_is_a_noop(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    first = _run_migration(migration_fixture, "--apply")
    assert first.returncode == 0, first.stderr
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"
    for command in ("docker", "make"):
        _write(
            fake_bin / command,
            f"#!/bin/sh\nprintf '%s\\n' '{command}' >> \"$MIGRATION_TEST_LOG\"\n",
            0o755,
        )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "MIGRATION_TEST_LOG": str(command_log),
    }

    resumed = _run_wrapper(migration_fixture, "--apply", environment=environment)

    assert resumed.returncode == 0, resumed.stderr
    assert "MIGRATION_STATUS=already-migrated" in resumed.stdout
    assert "ativação não concluída" in resumed.stdout
    assert command_log.read_text(encoding="utf-8").splitlines() == [
        "docker",
        "make",
        "make",
    ]
    marker = migration_fixture["target"] / ".runtime/migration-1.2-1.3.complete"
    assert marker.stat().st_mode & 0o777 == 0o600

    command_log.unlink()
    second = _run_wrapper(migration_fixture, "--apply", environment=environment)

    assert second.returncode == 0, second.stderr
    assert "MIGRATION_STATUS=already-migrated" in second.stdout
    assert "já migrado e ativado; nenhuma ação executada" in second.stdout
    assert not command_log.exists()


def test_wrapper_direct_source_without_root_env_check_is_readonly(
    migration_fixture: dict[str, Path],
) -> None:
    source = migration_fixture["source"]
    (source / ".env").unlink()
    source_before = _tree_digest(source)

    result = _run_wrapper(migration_fixture, "--check")

    assert result.returncode == 0, result.stderr
    assert _tree_digest(source) == source_before
    assert not (source / ".env").exists()


def test_wrapper_direct_source_without_root_env_apply_succeeds(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    source = migration_fixture["source"]
    (source / ".env").unlink()

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"
    for command in ("docker", "make"):
        _write(
            fake_bin / command,
            f"#!/bin/sh\nprintf '%s %s\\n' '{command}' \"$*\" >> \"$MIGRATION_TEST_LOG\"\n",
            0o755,
        )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "MIGRATION_TEST_LOG": str(command_log),
    }

    result = _run_wrapper(migration_fixture, "--apply", environment=environment)

    assert result.returncode == 0, result.stderr
    assert not (source / ".env").exists()
    commands = command_log.read_text(encoding="utf-8")
    assert "docker compose" in commands
    assert "down --remove-orphans" in commands
    marker = migration_fixture["target"] / ".runtime/migration-1.2-1.3.complete"
    assert marker.is_file()


def test_prepare_upgrade_without_root_env_creates_private_minimal_backup(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    source = migration_fixture["source"]
    backup = tmp_path / "backup-1.2"
    (source / ".env").unlink()
    expected_compose_env = b"".join(
        (source / relative_path).read_bytes()
        for relative_path in (
            "env_files/prod.env",
            "env_files/default.env",
            "env_files/security.env",
        )
    )
    source_before = _tree_digest(source)

    result = subprocess.run(
        [
            "bash",
            str(PREPARE_SCRIPT),
            "--source-dir",
            str(source),
            "--backup-dir",
            str(backup),
            "--certs-dir",
            str(migration_fixture["certs"]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "STATUS=prepared" in result.stdout
    assert not (source / ".env").exists()
    assert _tree_digest(source) == source_before
    for relative_path in (
        "docker-compose-prod.yaml",
        "docker-compose-ext.yaml",
        "airflow.env",
        ".env",
        "env_files/prod.env",
        "env_files/default.env",
        "env_files/security.env",
        "llm_config/litellm_config.yaml",
        "certificado/seiia.cert.pem",
        "certificado/seiia.cert.key",
        "migration-source.env",
        "migration-overrides.env",
    ):
        assert (backup / relative_path).is_file()
    for relative_path in (
        ".env",
        "env_files/security.env",
        "llm_config/litellm_config.yaml",
        "certificado/seiia.cert.key",
        "migration-source.env",
        "migration-overrides.env",
    ):
        assert os.stat(backup / relative_path).st_mode & 0o777 == 0o600
    backup_compose_env = (backup / ".env").read_bytes()
    assert backup_compose_env == expected_compose_env
    assert b"airflow_web_password" in backup_compose_env
    assert "airflow_web_password" not in result.stdout
    assert "airflow_web_password" not in result.stderr
    assert {
        "LITELLM_NANO_MODEL",
        "LITELLM_NANO_API_BASE",
        "LITELLM_NANO_API_KEY",
        "LITELLM_NANO_API_VERSION",
        "LITELLM_PROXY_API_KEY",
        "SEARXNG_SECRET_KEY",
    } <= set(_env_names(backup / "migration-overrides.env"))
    overrides_values = _env_values(backup / "migration-overrides.env")
    assert overrides_values["LITELLM_PROXY_API_KEY"] == "sk-proxy-old"
    assert re.fullmatch(r"[0-9a-f]{64}", overrides_values["SEARXNG_SECRET_KEY"])


def test_prepare_upgrade_generates_proxy_when_missing_in_source(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    source = migration_fixture["source"]
    backup = tmp_path / "backup-1.2-no-proxy"
    sec = source / "env_files/security.env"
    sec.write_text(
        sec.read_text(encoding="utf-8").replace(
            "export ASSISTENTE_LITELLM_PROXY_API_KEY=sk-proxy-old\n", ""
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "bash",
            str(PREPARE_SCRIPT),
            "--source-dir",
            str(source),
            "--backup-dir",
            str(backup),
            "--certs-dir",
            str(migration_fixture["certs"]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    overrides_values = _env_values(backup / "migration-overrides.env")
    assert re.fullmatch(r"sk-[0-9a-f]{64}", overrides_values["LITELLM_PROXY_API_KEY"])
    assert re.fullmatch(r"[0-9a-f]{64}", overrides_values["SEARXNG_SECRET_KEY"])
    assert not any(path.name.startswith("pg_") for path in backup.rglob("*"))


def test_prepare_upgrade_preserves_secrets_from_prod_env_and_respects_precedence(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    source = migration_fixture["source"]
    backup = tmp_path / "backup-1.2-prod-secrets"

    sec = source / "env_files/security.env"
    sec.write_text(
        sec.read_text(encoding="utf-8").replace(
            "export ASSISTENTE_LITELLM_PROXY_API_KEY=sk-proxy-old\n", ""
        ),
        encoding="utf-8",
    )
    prod = source / "env_files/prod.env"
    prod.write_text(
        "export LOG_LEVEL=WARNING\n"
        "export LITELLM_PROXY_API_KEY=sk-proxy-from-prod-1234567890\n"
        "export SEARXNG_SECRET_KEY=searxng-from-prod-abcdef1234567890\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "bash",
            str(PREPARE_SCRIPT),
            "--source-dir",
            str(source),
            "--backup-dir",
            str(backup),
            "--certs-dir",
            str(migration_fixture["certs"]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    overrides_values = _env_values(backup / "migration-overrides.env")
    assert overrides_values["LITELLM_PROXY_API_KEY"] == "sk-proxy-from-prod-1234567890"
    assert (
        overrides_values["SEARXNG_SECRET_KEY"] == "searxng-from-prod-abcdef1234567890"
    )

    # Test precedence: default -> prod -> security
    backup_precedence = tmp_path / "backup-1.2-precedence"
    sec.write_text(
        sec.read_text(encoding="utf-8")
        + "export SEARXNG_SECRET_KEY=searxng-from-security\n",
        encoding="utf-8",
    )
    result_prec = subprocess.run(
        [
            "bash",
            str(PREPARE_SCRIPT),
            "--source-dir",
            str(source),
            "--backup-dir",
            str(backup_precedence),
            "--certs-dir",
            str(migration_fixture["certs"]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result_prec.returncode == 0, result_prec.stderr
    prec_values = _env_values(backup_precedence / "migration-overrides.env")
    assert prec_values["SEARXNG_SECRET_KEY"] == "searxng-from-security"


def test_prepare_upgrade_preserves_invalid_proxy_in_prod_and_check_rejects(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    source = migration_fixture["source"]
    backup = tmp_path / "backup-1.2-invalid-prod"

    sec = source / "env_files/security.env"
    sec.write_text(
        sec.read_text(encoding="utf-8").replace(
            "export ASSISTENTE_LITELLM_PROXY_API_KEY=sk-proxy-old\n", ""
        ),
        encoding="utf-8",
    )
    prod = source / "env_files/prod.env"
    prod.write_text(
        "export LOG_LEVEL=WARNING\nexport LITELLM_PROXY_API_KEY=invalid-proxy-without-sk\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "bash",
            str(PREPARE_SCRIPT),
            "--source-dir",
            str(source),
            "--backup-dir",
            str(backup),
            "--certs-dir",
            str(migration_fixture["certs"]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    overrides_values = _env_values(backup / "migration-overrides.env")
    # Preserves the invalid literal, does NOT silently mask with a generated key
    assert overrides_values["LITELLM_PROXY_API_KEY"] == "invalid-proxy-without-sk"

    # Preflight check on the prepared backup rejects the invalid proxy key before writes
    check_fixture = {
        "source": backup,
        "target": migration_fixture["target"],
        "overrides": backup / "migration-overrides.env",
        "certs": backup / "certificado",
    }
    check_result = _run_migration(check_fixture, "--check")
    assert check_result.returncode != 0
    assert "LITELLM_PROXY_API_KEY" in check_result.stderr
    assert "invalid-proxy-without-sk" not in check_result.stderr
    assert not (migration_fixture["target"] / "security.env").exists()


def test_prepare_upgrade_preserves_quoted_secrets_with_inline_comment_hash_and_check_succeeds(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    source = migration_fixture["source"]
    backup = tmp_path / "backup-1.2-hash-comment"

    sec = source / "env_files/security.env"
    sec.write_text(
        sec.read_text(encoding="utf-8").replace(
            "export ASSISTENTE_LITELLM_PROXY_API_KEY=sk-proxy-old\n",
            "export ASSISTENTE_LITELLM_PROXY_API_KEY='sk-proxy # with # hash'\n",
        )
        + 'export SEARXNG_SECRET_KEY="session # key # preserved"\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "bash",
            str(PREPARE_SCRIPT),
            "--source-dir",
            str(source),
            "--backup-dir",
            str(backup),
            "--certs-dir",
            str(migration_fixture["certs"]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    overrides_values = _env_values(backup / "migration-overrides.env")
    assert overrides_values["LITELLM_PROXY_API_KEY"] == "sk-proxy # with # hash"
    assert overrides_values["SEARXNG_SECRET_KEY"] == "session # key # preserved"
    backup_overrides = backup / "migration-overrides.env"
    overrides_text = backup_overrides.read_text(encoding="utf-8")
    for key, val in [
        ("LITELLM_NANO_MODEL", "azure/nano-deployment"),
        ("LITELLM_NANO_API_BASE", "https://models.test"),
        ("LITELLM_NANO_API_KEY", "provider-nano-key"),
        ("LITELLM_NANO_API_VERSION", "2025-03-01-preview"),
        ("LITELLM_STT_MODEL", "azure/stt-deployment"),
        ("LITELLM_STT_API_BASE", "https://models.test"),
        ("LITELLM_STT_API_KEY", "provider-stt-key"),
        ("LITELLM_STT_API_VERSION", "2025-03-01-preview"),
        ("SEIIA_GATEWAY_HOST", "gateway.test"),
    ]:
        overrides_text = re.sub(
            rf"^{key}=.*$", f"{key}={val}", overrides_text, flags=re.MULTILINE
        )
    backup_overrides.write_text(overrides_text, encoding="utf-8")

    check_fixture = {
        "source": backup,
        "target": migration_fixture["target"],
        "overrides": backup / "migration-overrides.env",
        "certs": backup / "certificado",
    }
    check_result = _run_migration(check_fixture, "--check")
    assert check_result.returncode == 0, check_result.stderr
    assert "MIGRATION_STATUS=ready" in check_result.stdout


@pytest.mark.parametrize(
    ("proxy_val", "searx_val"),
    [
        ("sk-proxy'with'apostrophe", "searx'key'with'apostrophe"),
        (r"sk-proxy\'with\trailing\\", r"searx\'with\trailing\\"),
        (r"sk-proxy\nwith\nliteral", r"searx\nwith\nliteral"),
    ],
)
def test_migration_preserves_special_characters_end_to_end(
    migration_fixture: dict[str, Path], proxy_val: str, searx_val: str
) -> None:
    def _quote_val(v: str) -> str:
        escaped = v.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")
        return f'"{escaped}"'

    source_sec = migration_fixture["source"] / "env_files/security.env"
    source_sec.write_text(
        source_sec.read_text(encoding="utf-8").replace(
            "export ASSISTENTE_LITELLM_PROXY_API_KEY=sk-proxy-old\n",
            f"export ASSISTENTE_LITELLM_PROXY_API_KEY={_quote_val(proxy_val)}\n",
        ),
        encoding="utf-8",
    )
    overrides = migration_fixture["overrides"]
    overrides_text = overrides.read_text(encoding="utf-8")
    overrides_text = re.sub(
        r"^SEARXNG_SECRET_KEY=.*$",
        lambda _: f"SEARXNG_SECRET_KEY={_quote_val(searx_val)}",
        overrides_text,
        flags=re.MULTILINE,
    )
    if "LITELLM_PROXY_API_KEY=" in overrides_text:
        overrides_text = re.sub(
            r"^LITELLM_PROXY_API_KEY=.*$",
            lambda _: f"LITELLM_PROXY_API_KEY={_quote_val(proxy_val)}",
            overrides_text,
            flags=re.MULTILINE,
        )
    else:
        overrides_text += f"\nLITELLM_PROXY_API_KEY={_quote_val(proxy_val)}\n"
    overrides.write_text(overrides_text, encoding="utf-8")

    result_check = _run_migration(migration_fixture, "--check")
    assert result_check.returncode == 0, result_check.stderr

    result_apply = _run_migration(migration_fixture, "--apply")
    assert result_apply.returncode == 0, result_apply.stderr

    # Test effective Compose environment parsed directly from the target
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("LITELLM_PROXY_API_KEY", "SEARXNG_SECRET_KEY")
    }
    proc_env = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "--env-file",
            "default.env",
            "--env-file",
            "security.env",
            "config",
            "--environment",
        ],
        cwd=migration_fixture["target"],
        capture_output=True,
        text=True,
        env=clean_env,
        check=False,
    )
    assert proc_env.returncode == 0, f"compose --environment failed: {proc_env.stderr}"
    lines = proc_env.stdout.splitlines()
    assert f"LITELLM_PROXY_API_KEY={proxy_val}" in lines
    assert f"SEARXNG_SECRET_KEY={searx_val}" in lines


def test_migration_preserves_single_quoted_escaped_apostrophe_with_inline_comment(
    migration_fixture: dict[str, Path],
) -> None:
    source_sec = migration_fixture["source"] / "env_files/security.env"
    source_sec.write_text(
        source_sec.read_text(encoding="utf-8").replace(
            "export ASSISTENTE_LITELLM_PROXY_API_KEY=sk-proxy-old\n",
            "export ASSISTENTE_LITELLM_PROXY_API_KEY='sk-proxy\\'apostrophe # preserved'\n",
        ),
        encoding="utf-8",
    )
    overrides = migration_fixture["overrides"]
    overrides_text = overrides.read_text(encoding="utf-8")
    overrides_text = re.sub(
        r"^SEARXNG_SECRET_KEY=.*$",
        lambda _: "SEARXNG_SECRET_KEY='session\\'secret # preserved'",
        overrides_text,
        flags=re.MULTILINE,
    )
    overrides.write_text(overrides_text, encoding="utf-8")

    result_check = _run_migration(migration_fixture, "--check")
    assert result_check.returncode == 0, result_check.stderr

    result_apply = _run_migration(migration_fixture, "--apply")
    assert result_apply.returncode == 0, result_apply.stderr

    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("LITELLM_PROXY_API_KEY", "SEARXNG_SECRET_KEY")
    }
    proc_env = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "--env-file",
            "default.env",
            "--env-file",
            "security.env",
            "config",
            "--environment",
        ],
        cwd=migration_fixture["target"],
        capture_output=True,
        text=True,
        env=clean_env,
        check=False,
    )
    assert proc_env.returncode == 0, f"compose --environment failed: {proc_env.stderr}"
    lines = proc_env.stdout.splitlines()
    assert "LITELLM_PROXY_API_KEY=sk-proxy'apostrophe # preserved" in lines
    assert "SEARXNG_SECRET_KEY=session'secret # preserved" in lines


def test_prepare_upgrade_refuses_to_replace_an_existing_backup(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    backup = tmp_path / "backup-1.2"
    backup.mkdir()
    marker = backup / "preserve.txt"
    marker.write_text("preserve", encoding="utf-8")

    result = subprocess.run(
        [
            "bash",
            str(PREPARE_SCRIPT),
            "--source-dir",
            str(migration_fixture["source"]),
            "--backup-dir",
            str(backup),
            "--certs-dir",
            str(migration_fixture["certs"]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "backup já existe" in result.stderr
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_prepare_upgrade_requires_airflow_env(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    relative_path = "airflow.env"
    (migration_fixture["source"] / relative_path).unlink()

    result = subprocess.run(
        [
            "bash",
            str(PREPARE_SCRIPT),
            "--source-dir",
            str(migration_fixture["source"]),
            "--backup-dir",
            str(tmp_path / "backup-1.2"),
            "--certs-dir",
            str(migration_fixture["certs"]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert relative_path in result.stderr


def test_wrapper_accepts_prepared_backup_shortcut(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    backup = tmp_path / "backup-1.2"
    backup.mkdir()
    for relative_path in (
        "docker-compose-prod.yaml",
        "docker-compose-ext.yaml",
        "airflow.env",
        ".env",
        "env_files/prod.env",
        "env_files/default.env",
        "env_files/security.env",
        "llm_config/litellm_config.yaml",
    ):
        source = migration_fixture["source"] / relative_path
        destination = backup / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        destination.chmod(source.stat().st_mode & 0o777)
    (backup / "certificado").mkdir()
    for filename in ("seiia.cert.pem", "seiia.cert.key"):
        source = migration_fixture["certs"] / filename
        destination = backup / "certificado" / filename
        destination.write_bytes(source.read_bytes())
        destination.chmod(source.stat().st_mode & 0o777)
    (backup / "migration-overrides.env").write_bytes(
        migration_fixture["overrides"].read_bytes()
    )
    (backup / "migration-overrides.env").chmod(0o600)

    result = subprocess.run(
        [
            "bash",
            str(WRAPPER_SCRIPT),
            "--from-backup",
            str(backup),
            "--deploy-dir",
            str(migration_fixture["target"]),
            "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "MIGRATION_STATUS=ready" in result.stdout
