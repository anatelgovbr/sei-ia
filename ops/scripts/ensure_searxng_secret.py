#!/usr/bin/env python3
"""Garante que SEARXNG_SECRET_KEY esteja configurada em security.env."""

from __future__ import annotations

import ast
import os
import re
import secrets
import sys
from pathlib import Path

ENV_ASSIGNMENT = re.compile(
    r"^(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$"
)
SAFE_ENV_VALUE = re.compile(r"^[A-Za-z0-9_./:@+,-]*$")


def _strip_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if char == "#" and quote is None:
            if index > 0 and value[index - 1] in {" ", "\t"}:
                return value[:index].rstrip()
    return value.strip()


def _parse_scalar(raw_value: str, *, location: str = "") -> str:
    value = _strip_inline_comment(raw_value).strip()
    if not value:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        quote = value[0]
        try:
            if quote == '"':
                parsed = ast.literal_eval(value.replace("\\$", "\\u0024"))
            else:
                parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError) as error:
            raise ValueError(f"valor de string malformado em {location}") from error
        if not isinstance(parsed, str):
            raise ValueError(f"valor não textual em {location}")
        return parsed
    return value


def _format_env_value(value: str, *, name: str) -> str:
    if "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"valor multilinha não suportado: {name}")
    if SAFE_ENV_VALUE.match(value) and value != "":
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")
    return f'"{escaped}"'


def ensure_searxng_secret(path: Path) -> int:
    if not path.exists():
        sys.stderr.write(f"ERRO: arquivo não encontrado: {path}\n")
        return 2

    if path.is_symlink():
        sys.stderr.write(f"ERRO: link simbólico não permitido: {path}\n")
        return 2

    if not path.is_file():
        sys.stderr.write(f"ERRO: arquivo regular obrigatório: {path}\n")
        return 2

    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as error:
        sys.stderr.write(f"ERRO: falha ao ler {path}: {error}\n")
        return 2

    count = 0
    file_val: str | None = None
    for line_idx, line in enumerate(raw_lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENV_ASSIGNMENT.match(stripped)
        if match and match.group("name") == "SEARXNG_SECRET_KEY":
            count += 1
            if count > 1:
                sys.stderr.write(
                    f"ERRO: variável duplicada em {path}: SEARXNG_SECRET_KEY\n"
                )
                return 2
            try:
                file_val = _parse_scalar(
                    match.group("value"), location=f"{path}:{line_idx}"
                )
            except ValueError as error:
                sys.stderr.write(f"ERRO: {error}\n")
                return 2

    env_val = os.environ.get("SEARXNG_SECRET_KEY")

    # Caso já preenchido no arquivo:
    if file_val is not None and file_val != "":
        return 0

    # Determinar valor a persistir:
    if env_val is not None and env_val != "":
        secret_to_write = env_val
    else:
        secret_to_write = secrets.token_hex(32)
    formatted_assignment = f"SEARXNG_SECRET_KEY={_format_env_value(secret_to_write, name='SEARXNG_SECRET_KEY')}"

    new_lines: list[str] = []
    replaced = False
    for line in raw_lines:
        stripped = line.strip()
        match = ENV_ASSIGNMENT.match(stripped)
        if match and match.group("name") == "SEARXNG_SECRET_KEY":
            new_lines.append(formatted_assignment)
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        new_lines.append(formatted_assignment)

    content = ("\n".join(new_lines) + "\n").encode("utf-8")
    temp_path = path.parent / f".{path.name}.tmp.{os.getpid()}"
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(temp_path, flags, 0o600)
        with open(fd, "wb") as file:
            file.write(content)
        os.replace(temp_path, path)
        path.chmod(0o600)
    except Exception as error:
        temp_path.unlink(missing_ok=True)
        sys.stderr.write(f"ERRO: falha ao gravar {path}: {error}\n")
        return 2

    return 0


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("security.env")
    return ensure_searxng_secret(target)


if __name__ == "__main__":
    sys.exit(main())
