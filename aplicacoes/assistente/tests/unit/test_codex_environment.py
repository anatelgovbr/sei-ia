import os
import stat
import subprocess
import tomllib
from pathlib import Path

WORKTREE_ROOT = Path(__file__).resolve().parents[4]


def test_setup_seleciona_worktree_legivel_nao_bare_sem_imprimir_segredos(tmp_path):
    current_root = tmp_path / "current"
    source_root = tmp_path / "source"
    bare_root = tmp_path / "gate.git"
    fake_bin = tmp_path / "bin"
    (current_root / "aplicacoes" / "assistente").mkdir(parents=True)
    (source_root / "aplicacoes" / "assistente").mkdir(parents=True)
    bare_root.mkdir()
    fake_bin.mkdir()
    (current_root / "default.env").write_text("DEFAULT=1\n", encoding="utf-8")
    (source_root / "security.env").write_text(
        "SECURITY_SECRET=source-only-secret\n", encoding="utf-8"
    )
    (source_root / "aplicacoes" / "assistente" / ".env").write_text(
        "APP_SECRET=another-source-secret\n", encoding="utf-8"
    )

    git_script = f"""#!/bin/sh
if [ "$1" = "fetch" ]; then
    exit 0
fi
if [ "$1" = "rev-parse" ] && [ "$2" = "--show-toplevel" ]; then
    pwd
    exit 0
fi
if [ "$1" = "worktree" ] && [ "$2" = "list" ]; then
    printf 'worktree {bare_root}\\n'
    printf 'bare\\n'
    printf 'worktree {current_root}\\n'
    printf 'HEAD abc\\n'
    printf 'worktree {source_root}\\n'
    printf 'HEAD def\\n'
    exit 0
fi
if [ "$1" = "-C" ]; then
    candidate="$2"
    shift 2
    if [ "$1" = "rev-parse" ] && [ "$2" = "--is-bare-repository" ]; then
        if [ "$candidate" = "{bare_root}" ]; then
            printf 'true\\n'
        else
            printf 'false\\n'
        fi
        exit 0
    fi
fi
exit 1
"""
    git_path = fake_bin / "git"
    git_path.write_text(git_script, encoding="utf-8")
    git_path.chmod(0o755)
    pre_commit_path = fake_bin / "pre-commit"
    pre_commit_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    pre_commit_path.chmod(0o755)

    setup_script = tomllib.loads(
        (WORKTREE_ROOT / ".codex" / "environments" / "environment.toml").read_text(
            encoding="utf-8"
        )
    )["setup"]["script"]
    result = subprocess.run(
        ["bash", "-c", setup_script],
        cwd=current_root,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (current_root / "security.env").read_text(encoding="utf-8") == (
        "SECURITY_SECRET=source-only-secret\n"
    )
    assert (current_root / "aplicacoes" / "assistente" / ".env").read_text(
        encoding="utf-8"
    ) == "APP_SECRET=another-source-secret\n"
    assert stat.S_IMODE((current_root / "security.env").stat().st_mode) == 0o600
    assert (
        stat.S_IMODE(
            (current_root / "aplicacoes" / "assistente" / ".env").stat().st_mode
        )
        == 0o600
    )
    assert "source-only-secret" not in result.stdout + result.stderr
    assert "another-source-secret" not in result.stdout + result.stderr
