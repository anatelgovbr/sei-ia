from __future__ import annotations

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
        if len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1]
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


def test_apply_rejects_empty_searxng_secret(
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

    assert result.returncode != 0
    assert "SEARXNG_SECRET_KEY" in result.stderr


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


def test_prepare_upgrade_creates_private_minimal_backup(
    migration_fixture: dict[str, Path], tmp_path: Path
) -> None:
    backup = tmp_path / "backup-1.2"
    source_before = _tree_digest(migration_fixture["source"])

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

    assert result.returncode == 0, result.stderr
    assert "STATUS=prepared" in result.stdout
    assert _tree_digest(migration_fixture["source"]) == source_before
    for relative_path in (
        "docker-compose-prod.yaml",
        "docker-compose-ext.yaml",
        "airflow.env",
        ".env",
        "env_files/prod.env",
        "env_files/default.env",
        "env_files/security.env",
        ".env",
        "llm_config/litellm_config.yaml",
        "certificado/seiia.cert.pem",
        "certificado/seiia.cert.key",
        "migration-source.env",
        "migration-overrides.env",
    ):
        assert (backup / relative_path).is_file()
    for relative_path in (
        "env_files/security.env",
        "llm_config/litellm_config.yaml",
        "certificado/seiia.cert.key",
        "migration-source.env",
        "migration-overrides.env",
    ):
        assert os.stat(backup / relative_path).st_mode & 0o777 == 0o600
    assert {
        "LITELLM_NANO_MODEL",
        "LITELLM_NANO_API_BASE",
        "LITELLM_NANO_API_KEY",
        "LITELLM_NANO_API_VERSION",
    } <= set(_env_names(backup / "migration-overrides.env"))
    assert not any(path.name.startswith("pg_") for path in backup.rglob("*"))


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


@pytest.mark.parametrize("relative_path", ["airflow.env", ".env"])
def test_prepare_upgrade_requires_compose_env_files(
    migration_fixture: dict[str, Path], tmp_path: Path, relative_path: str
) -> None:
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
