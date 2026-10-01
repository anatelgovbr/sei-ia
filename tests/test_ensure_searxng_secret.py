from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HELPER_SCRIPT = REPOSITORY_ROOT / "ops/scripts/ensure_searxng_secret.py"
HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _run_helper(
    target_path: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    exec_env = os.environ.copy()
    if env is not None:
        exec_env.update(env)
    return subprocess.run(
        [sys.executable, str(HELPER_SCRIPT), str(target_path)],
        capture_output=True,
        text=True,
        env=exec_env,
        check=False,
    )


def test_missing_file_fails_with_exit_2_and_no_creation(tmp_path: Path) -> None:
    missing_file = tmp_path / "security.env"
    result = _run_helper(missing_file)
    assert result.returncode == 2
    assert not missing_file.exists()
    assert "ERRO" in result.stderr


def test_symlink_target_rejected(tmp_path: Path) -> None:
    real_file = tmp_path / "real.env"
    real_file.write_text("SEARXNG_SECRET_KEY=\n", encoding="utf-8")
    symlink_file = tmp_path / "security.env"
    symlink_file.symlink_to(real_file)

    result = _run_helper(symlink_file)
    assert result.returncode == 2
    assert "link simbólico" in result.stderr
    assert real_file.read_text(encoding="utf-8") == "SEARXNG_SECRET_KEY=\n"


def test_directory_target_rejected(tmp_path: Path) -> None:
    dir_target = tmp_path / "security.env"
    dir_target.mkdir()

    result = _run_helper(dir_target)
    assert result.returncode == 2
    assert "arquivo regular" in result.stderr


def test_duplicate_searxng_secret_key_rejected(tmp_path: Path) -> None:
    target = tmp_path / "security.env"
    target.write_text(
        "SEARXNG_SECRET_KEY=first_val\nSEARXNG_SECRET_KEY=second_val\n",
        encoding="utf-8",
    )
    result = _run_helper(target)
    assert result.returncode == 2
    assert "duplicada" in result.stderr


def test_malformed_quoted_value_rejected(tmp_path: Path) -> None:
    target = tmp_path / "security.env"
    target.write_text(
        'SEARXNG_SECRET_KEY="invalid\\escape\\xzz"\n',
        encoding="utf-8",
    )
    result = _run_helper(target)
    assert result.returncode == 2
    assert "ERRO" in result.stderr or "inválid" in result.stderr


def test_generates_and_persists_64_hex_secret_when_key_missing(
    tmp_path: Path,
) -> None:
    target = tmp_path / "security.env"
    initial_content = (
        "# Comentário inicial com # símbolo e espaços\n"
        'DB_SEIIA_PWD="senha # com cerquilha"\n'
        "SOLR_USER=solr_admin\n"
    )
    target.write_text(initial_content, encoding="utf-8")
    target.chmod(0o644)

    env = {k: v for k, v in os.environ.items() if k != "SEARXNG_SECRET_KEY"}
    result = _run_helper(target, env=env)
    assert result.returncode == 0, result.stderr
    assert os.stat(target).st_mode & 0o777 == 0o600

    content = target.read_text(encoding="utf-8")
    assert initial_content in content
    match = re.search(r"^SEARXNG_SECRET_KEY=(.*)$", content, re.MULTILINE)
    assert match is not None
    generated_key = match.group(1).strip()
    assert HEX_64_PATTERN.match(generated_key)
    assert generated_key not in result.stdout
    assert generated_key not in result.stderr


@pytest.mark.parametrize(
    "empty_assignment",
    [
        "SEARXNG_SECRET_KEY=\n",
        "SEARXNG_SECRET_KEY=''\n",
        'SEARXNG_SECRET_KEY=""\n',
        "SEARXNG_SECRET_KEY=   \n",
    ],
)
def test_generates_and_persists_64_hex_secret_when_key_empty_or_empty_quotes(
    tmp_path: Path, empty_assignment: str
) -> None:
    target = tmp_path / "security.env"
    target.write_text(
        f"# Top comment\n{empty_assignment}# Bottom comment\n", encoding="utf-8"
    )

    env = {k: v for k, v in os.environ.items() if k != "SEARXNG_SECRET_KEY"}
    result = _run_helper(target, env=env)
    assert result.returncode == 0, result.stderr
    assert os.stat(target).st_mode & 0o777 == 0o600

    content = target.read_text(encoding="utf-8")
    assert "# Top comment" in content
    assert "# Bottom comment" in content
    match = re.search(r"^SEARXNG_SECRET_KEY=(.*)$", content, re.MULTILINE)
    assert match is not None
    generated_key = match.group(1).strip()
    assert HEX_64_PATTERN.match(generated_key)


def test_preserves_existing_filled_secret_without_modifying_file(
    tmp_path: Path,
) -> None:
    target = tmp_path / "security.env"
    original_bytes = (
        b"# Stable file\n"
        b"SEARXNG_SECRET_KEY=pre_existing_searxng_secret_abcdef1234567890\n"
        b"OTHER_SECRET=xyz\n"
    )
    target.write_bytes(original_bytes)
    target.chmod(0o600)

    env = {k: v for k, v in os.environ.items() if k != "SEARXNG_SECRET_KEY"}
    result = _run_helper(target, env=env)
    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == original_bytes


def test_empty_exported_env_does_not_shadow_file_or_generation(
    tmp_path: Path,
) -> None:
    target = tmp_path / "security.env"
    # Case 1: file already has a valid secret, env is empty string
    target.write_text("SEARXNG_SECRET_KEY=file_secret_abc123\n", encoding="utf-8")
    result = _run_helper(target, env={"SEARXNG_SECRET_KEY": ""})
    assert result.returncode == 0, result.stderr
    assert "SEARXNG_SECRET_KEY=file_secret_abc123\n" == target.read_text(
        encoding="utf-8"
    )

    # Case 2: file has empty secret, env is empty string -> generates key
    target.write_text("SEARXNG_SECRET_KEY=\n", encoding="utf-8")
    result = _run_helper(target, env={"SEARXNG_SECRET_KEY": ""})
    assert result.returncode == 0, result.stderr
    content = target.read_text(encoding="utf-8")
    match = re.search(r"^SEARXNG_SECRET_KEY=(.*)$", content, re.MULTILINE)
    assert match is not None
    assert HEX_64_PATTERN.match(match.group(1).strip())


def test_explicit_nonempty_env_persisted_when_file_is_empty(
    tmp_path: Path,
) -> None:
    target = tmp_path / "security.env"
    target.write_text("SEARXNG_SECRET_KEY=\n", encoding="utf-8")
    result = _run_helper(target, env={"SEARXNG_SECRET_KEY": "explicit_custom_key_456"})
    assert result.returncode == 0, result.stderr
    assert "SEARXNG_SECRET_KEY=explicit_custom_key_456\n" == target.read_text(
        encoding="utf-8"
    )


def test_explicit_nonempty_env_does_not_overwrite_already_filled_file(
    tmp_path: Path,
) -> None:
    target = tmp_path / "security.env"
    target.write_text("SEARXNG_SECRET_KEY=persisted_key_111\n", encoding="utf-8")
    # Operator provided a different non-empty key via env
    result = _run_helper(target, env={"SEARXNG_SECRET_KEY": "runtime_override_222"})
    assert result.returncode == 0, result.stderr
    assert "SEARXNG_SECRET_KEY=persisted_key_111\n" == target.read_text(
        encoding="utf-8"
    )


def test_explicit_env_with_quotes_and_dollar_persisted_losslessly_for_compose(
    tmp_path: Path,
) -> None:
    target = tmp_path / "security.env"
    target.write_text("SEARXNG_SECRET_KEY=\n", encoding="utf-8")

    test_key = "abc'def$TOKEN_VAL123"
    result = _run_helper(target, env={"SEARXNG_SECRET_KEY": test_key})
    assert result.returncode == 0, result.stderr

    # Test Compose actual interpolation without that environment variable set
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(
        """\
services:
  infra-searxng:
    image: searxng/searxng:test
    environment:
      SEARXNG_SECRET: ${SEARXNG_SECRET_KEY:?Defina SEARXNG_SECRET_KEY em security.env}
""",
        encoding="utf-8",
    )

    clean_env = {k: v for k, v in os.environ.items() if k != "SEARXNG_SECRET_KEY"}
    proc = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "--env-file",
            str(target),
            "config",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        env=clean_env,
        check=False,
    )
    assert proc.returncode == 0, f"docker compose config failed: {proc.stderr}"
    config = json.loads(proc.stdout)
    actual_secret = config["services"]["infra-searxng"]["environment"]["SEARXNG_SECRET"]
    assert actual_secret.replace("$$", "$") == test_key


@pytest.mark.parametrize(
    "explicit_val",
    [
        "secret_trailing_backslash\\",
        "secret_backslash_and_apostrophe\\'abc",
    ],
)
def test_explicit_env_with_trailing_backslash_and_apostrophe_lossless(
    tmp_path: Path, explicit_val: str
) -> None:
    target = tmp_path / "security.env"
    target.write_text("SEARXNG_SECRET_KEY=\n", encoding="utf-8")

    # 1. First write from env
    res1 = _run_helper(target, env={"SEARXNG_SECRET_KEY": explicit_val})
    assert res1.returncode == 0, res1.stderr
    content_after_first = target.read_bytes()

    # 2. Reload: run helper again without env (verifying parser parses it back without error)
    clean_env = {k: v for k, v in os.environ.items() if k != "SEARXNG_SECRET_KEY"}
    res2 = _run_helper(target, env=clean_env)
    assert res2.returncode == 0, res2.stderr
    assert target.read_bytes() == content_after_first

    # Also reload with same env:
    res3 = _run_helper(target, env={"SEARXNG_SECRET_KEY": explicit_val})
    assert res3.returncode == 0, res3.stderr
    assert target.read_bytes() == content_after_first

    # 3. Docker Compose config --environment receives the exact original string
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(
        """\
services:
  infra-searxng:
    image: searxng/searxng:test
    environment:
      SEARXNG_SECRET: ${SEARXNG_SECRET_KEY}
""",
        encoding="utf-8",
    )
    proc_env = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "--env-file",
            str(target),
            "config",
            "--environment",
        ],
        capture_output=True,
        text=True,
        env=clean_env,
        check=False,
    )
    assert proc_env.returncode == 0, f"compose --environment failed: {proc_env.stderr}"
    assert f"SEARXNG_SECRET_KEY={explicit_val}" in proc_env.stdout.splitlines()


def test_no_secret_leaked_to_stdout_or_stderr(tmp_path: Path) -> None:
    target = tmp_path / "security.env"
    target.write_text("SEARXNG_SECRET_KEY=\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "SEARXNG_SECRET_KEY"}
    result = _run_helper(target, env=env)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_write_failure_cleans_up_and_exits_2(tmp_path: Path) -> None:
    protected_dir = tmp_path / "readonly_dir"
    protected_dir.mkdir()
    target = protected_dir / "security.env"
    target.write_text("SEARXNG_SECRET_KEY=\n", encoding="utf-8")
    protected_dir.chmod(0o500)

    try:
        result = _run_helper(target)
        assert result.returncode == 2
        assert (
            "falha ao gravar" in result.stderr or "Permission denied" in result.stderr
        )
        remaining = list(protected_dir.iterdir())
        assert remaining == [target]
    finally:
        protected_dir.chmod(0o700)
