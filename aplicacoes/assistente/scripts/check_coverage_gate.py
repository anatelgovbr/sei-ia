"""Executa testes com cobertura e aplica o limite mínimo do Quality Gate.

O SonarQube exige coverage >= 80%. Este script reproduz esse gate localmente
para evitar MR/promoção de branch com cobertura abaixo do limite.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

DEFAULT_MIN_COVERAGE = 80.0
DEFAULT_EXCLUSIONS = "sonar-project.properties"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Roda pytest com coverage e falha se a cobertura ficar abaixo do limite."
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=DEFAULT_MIN_COVERAGE,
        help="Percentual mínimo de cobertura exigido.",
    )
    parser.add_argument(
        "--coverage-exclusions-file",
        default=DEFAULT_EXCLUSIONS,
        help="Arquivo de propriedades com sonar.coverage.exclusions.",
    )
    parser.add_argument(
        "--new-code-base",
        help=(
            "Ref Git base para calcular cobertura apenas das linhas novas/alteradas, "
            "simulando o New Code Coverage do Sonar. Ex.: origin/homologacao."
        ),
    )
    parser.add_argument(
        "--new-code-head",
        default="WORKTREE",
        help=(
            "Ref Git final para o cálculo de New Code Coverage. "
            "Padrão: WORKTREE, incluindo mudanças ainda não commitadas."
        ),
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help=(
            "Argumentos opcionais repassados ao pytest após '--'. "
            "Quando omitido, usa tests/unit, que é a suíte que gera o "
            "coverage.xml consumido pelo Sonar no job unit_test:assistente."
        ),
    )
    return parser.parse_args()


def normalize_pytest_args(pytest_args: list[str]) -> list[str]:
    if pytest_args and pytest_args[0] == "--":
        return pytest_args[1:]
    return pytest_args


def run(command: list[str], *, cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def parse_sonar_coverage_exclusions(properties_path: Path) -> list[str]:
    if not properties_path.exists():
        return []

    logical_lines: list[str] = []
    current_line = ""
    for raw_line in properties_path.read_text(encoding="utf-8").splitlines():
        stripped_line = raw_line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if stripped_line.endswith("\\"):
            current_line += stripped_line[:-1].strip()
            continue
        logical_lines.append(current_line + stripped_line)
        current_line = ""
    if current_line:
        logical_lines.append(current_line)

    for line in logical_lines:
        if line.startswith("sonar.coverage.exclusions="):
            value = line.split("=", 1)[1]
            return [pattern.strip() for pattern in value.split(",") if pattern.strip()]
    return []


def is_excluded(filename: str, patterns: list[str]) -> bool:
    return any(fnmatch(filename, pattern) for pattern in patterns)


def read_quality_gate_coverage(
    project_dir: Path, exclusions_file: Path
) -> tuple[float, int, int]:
    coverage_path = project_dir / "coverage.json"
    with coverage_path.open(encoding="utf-8") as coverage_file:
        coverage_data = json.load(coverage_file)

    exclusions = parse_sonar_coverage_exclusions(exclusions_file)
    covered_lines = 0
    num_statements = 0

    for filename, file_data in coverage_data["files"].items():
        if is_excluded(filename, exclusions):
            continue
        summary = file_data["summary"]
        covered_lines += int(summary["covered_lines"])
        num_statements += int(summary["num_statements"])

    if num_statements == 0:
        return 100.0, covered_lines, num_statements
    return covered_lines / num_statements * 100, covered_lines, num_statements


def get_changed_lines_by_file(
    project_dir: Path, base_ref: str, head_ref: str
) -> dict[str, set[int]]:
    monorepo_dir = project_dir.parents[1]
    project_prefix = f"{project_dir.relative_to(monorepo_dir).as_posix()}/"
    command = ["git", "diff", "--unified=0", base_ref]
    if head_ref != "WORKTREE":
        command.append(head_ref)
    command.extend(["--", project_prefix])
    result = subprocess.run(
        command,
        cwd=monorepo_dir,
        check=True,
        capture_output=True,
        text=True,
    )

    changed_lines: dict[str, set[int]] = {}
    current_file: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith(f"+++ b/{project_prefix}"):
            current_file = line.removeprefix(f"+++ b/{project_prefix}")
            continue
        if line.startswith("+++ /dev/null"):
            current_file = None
            continue
        if not current_file or not line.startswith("@@"):
            continue

        match = re.search(r"\+(\d+)(?:,(\d+))?", line)
        if not match:
            continue
        start_line = int(match.group(1))
        line_count = int(match.group(2) or "1")
        if line_count == 0:
            continue
        changed_lines.setdefault(current_file, set()).update(
            range(start_line, start_line + line_count)
        )
    return changed_lines


def read_new_code_coverage(
    project_dir: Path, exclusions_file: Path, base_ref: str, head_ref: str
) -> tuple[float, int, int, int, int]:
    """Calcula New Code Coverage aproximando a fórmula do Sonar.

    Sonar usa uma cobertura combinada em new code:
    (linhas cobertas + condições cobertas) / (linhas a cobrir + condições a cobrir).
    O arquivo coverage.json do coverage.py expõe branches executados/faltantes; ao cruzar
    esses branches com as linhas adicionadas/alteradas no diff, conseguimos reproduzir
    melhor valores como 78.9% do Quality Gate.
    """
    coverage_path = project_dir / "coverage.json"
    with coverage_path.open(encoding="utf-8") as coverage_file:
        coverage_data = json.load(coverage_file)

    exclusions = parse_sonar_coverage_exclusions(exclusions_file)
    changed_lines = get_changed_lines_by_file(project_dir, base_ref, head_ref)
    covered_lines = 0
    lines_to_cover = 0
    covered_conditions = 0
    conditions_to_cover = 0

    for filename, added_lines in changed_lines.items():
        if is_excluded(filename, exclusions):
            continue
        file_data = coverage_data["files"].get(filename)
        if not file_data:
            continue

        executable_lines = set(file_data.get("executed_lines", [])) | set(
            file_data.get("missing_lines", [])
        )
        covered_file_lines = set(file_data.get("executed_lines", []))
        new_executable_lines = added_lines & executable_lines
        covered_lines += len(new_executable_lines & covered_file_lines)
        lines_to_cover += len(new_executable_lines)

        executed_branches = [
            branch
            for branch in file_data.get("executed_branches", [])
            if branch and branch[0] in added_lines
        ]
        missing_branches = [
            branch
            for branch in file_data.get("missing_branches", [])
            if branch and branch[0] in added_lines
        ]
        covered_conditions += len(executed_branches)
        conditions_to_cover += len(executed_branches) + len(missing_branches)

    total_to_cover = lines_to_cover + conditions_to_cover
    total_covered = covered_lines + covered_conditions
    if total_to_cover == 0:
        return (
            100.0,
            covered_lines,
            lines_to_cover,
            covered_conditions,
            conditions_to_cover,
        )
    return (
        total_covered / total_to_cover * 100,
        covered_lines,
        lines_to_cover,
        covered_conditions,
        conditions_to_cover,
    )


def main() -> None:
    args = parse_args()
    project_dir = Path(__file__).resolve().parents[1]
    pytest_args = normalize_pytest_args(args.pytest_args) or ["tests/unit"]
    exclusions_file = project_dir / args.coverage_exclusions_file

    run([sys.executable, "-m", "coverage", "erase"], cwd=project_dir)
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "--cov=sei_ia",
            "--cov-report=xml:coverage.xml",
            "--cov-report=json:coverage.json",
            *pytest_args,
        ],
        cwd=project_dir,
    )
    run(
        [sys.executable, "-m", "coverage", "report", "--show-missing"],
        cwd=project_dir,
    )

    total_coverage, total_covered, total_lines = read_quality_gate_coverage(
        project_dir, exclusions_file
    )
    print(
        "Cobertura total do Quality Gate: "
        f"{total_coverage:.2f}% ({total_covered}/{total_lines} linhas)"
    )

    coverage = total_coverage
    gate_name = "Coverage"
    if args.new_code_base:
        (
            coverage,
            covered_lines,
            lines_to_cover,
            covered_conditions,
            conditions_to_cover,
        ) = read_new_code_coverage(
            project_dir, exclusions_file, args.new_code_base, args.new_code_head
        )
        gate_name = "New Code Coverage"
        print(
            f"New Code Coverage ({args.new_code_base}..{args.new_code_head}): "
            f"{coverage:.2f}% "
            f"({covered_lines}/{lines_to_cover} linhas, "
            f"{covered_conditions}/{conditions_to_cover} condições)"
        )

    if coverage < args.min_coverage:
        raise SystemExit(
            f"{gate_name} {coverage:.2f}% abaixo do mínimo exigido "
            f"de {args.min_coverage:.2f}% pelo Quality Gate."
        )


if __name__ == "__main__":
    main()
