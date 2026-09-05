"""Testes de quality local alinhados ao SonarQube."""

import subprocess
import sys
from pathlib import Path


def test_text_preprocess_respeita_limite_de_complexidade_cognitiva():
    """Evita reintroduzir violação Sonar python:S3776 no parser legado."""
    project_dir = Path(__file__).resolve().parents[2]
    target_file = project_dir / "sei_ia/data/etl/html_to_md/text_preprocess.py"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "flake8",
            "--select",
            "CCR",
            "--max-cognitive-complexity=15",
            str(target_file),
        ],
        cwd=project_dir,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
