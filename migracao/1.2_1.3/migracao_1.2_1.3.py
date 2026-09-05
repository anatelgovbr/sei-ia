#!/usr/bin/env python3
"""Migra a configuração privada do Servidor SEI IA 1.2 para o contrato 1.3."""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class MigrationError(RuntimeError):
    """Erro de contrato que impede uma migração segura."""


ENV_ASSIGNMENT = re.compile(
    r"^(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$"
)
SAFE_ENV_VALUE = re.compile(r"^[A-Za-z0-9_./:@+,-]*$")
SOURCE_VERSION = re.compile(r"^v?1\.2(?:\.|$)")

OPTIONAL_EMPTY = {
    "LANGFUSE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LITELLM_EMBEDDING_API_VERSION",
    "LITELLM_MINI_API_VERSION",
    "LITELLM_NANO_API_VERSION",
    "LITELLM_STANDARD_API_VERSION",
    "LITELLM_STT_API_VERSION",
    "SEIIA_CERT_DNS",
}

DIRECT_KEYS = {
    "ENVIRONMENT",
    "DB_SEIIA_USER",
    "DB_SEIIA_PWD",
    "SOLR_USER",
    "SOLR_PASSWORD",
    "AIRFLOW_POSTGRES_DB",
    "AIRFLOW_POSTGRES_USER",
    "AIRFLOW_AMQP_USER",
    "_AIRFLOW_WWW_USER_USERNAME",
    "_AIRFLOW_WWW_USER_PASSWORD",
    "AIRFLOW_POSTGRES_PASSWORD",
    "AIRFLOW_AMQP_PASSWORD",
    "AIRFLOW__WEBSERVER__SECRET_KEY",
    "SEI_API_DB_IDENTIFIER_SERVICE",
    "SEI_ADDRESS",
    "LANGFUSE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
}

LOCAL_DEFAULT_KEYS = (
    "NB_USER",
    "NB_UID",
    "NB_GID",
    "VOL_SEIIA_DIR",
    "TZ",
    "COMPOSE_NETWORK_NAME",
)


@dataclass(frozen=True)
class PlannedFile:
    path: Path
    content: bytes
    mode: int
    allow_existing_update: bool = False


@dataclass(frozen=True)
class MigrationPlan:
    files: tuple[PlannedFile, ...]
    certificate_fingerprint: str
    status: str


def _strip_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.strip()


def _parse_scalar(raw_value: str, *, location: str) -> str:
    value = _strip_inline_comment(raw_value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError) as error:
            raise MigrationError(f"valor inválido em {location}") from error
        if not isinstance(parsed, str):
            raise MigrationError(f"valor não textual em {location}")
        return parsed
    return value


def read_env_file(path: Path, *, strict: bool = True) -> dict[str, str]:
    """Lê assignments dotenv sem executar o conteúdo."""
    if not path.is_file():
        raise MigrationError(f"arquivo obrigatório ausente: {path}")

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_ASSIGNMENT.match(line)
        if not match:
            if strict:
                raise MigrationError(f"linha inválida em {path}:{line_number}")
            continue
        name = match.group("name")
        if name in values:
            raise MigrationError(f"variável duplicada em {path}: {name}")
        values[name] = _parse_scalar(
            match.group("value"), location=f"{path}:{line_number}"
        )
    return values


def _format_env_value(value: str, *, name: str) -> str:
    if "\n" in value or "\r" in value or "\x00" in value:
        raise MigrationError(f"valor multilinha não suportado: {name}")
    if SAFE_ENV_VALUE.fullmatch(value):
        return value
    if "'" in value:
        raise MigrationError(
            f"{name} contém aspas simples e não pode ser migrada sem alteração"
        )
    return f"'{value}'"


def render_security_template(template: Path, values: dict[str, str]) -> bytes:
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in template.read_text(encoding="utf-8").splitlines():
        match = ENV_ASSIGNMENT.match(raw_line.strip())
        if not match:
            lines.append(raw_line)
            continue
        name = match.group("name")
        if name in seen:
            raise MigrationError(f"variável duplicada no contrato 1.3: {name}")
        seen.add(name)
        lines.append(f"{name}={_format_env_value(values[name], name=name)}")
    if seen != set(values):
        difference = sorted(seen ^ set(values))
        raise MigrationError(
            "inventário divergente ao renderizar security.env: " + ", ".join(difference)
        )
    return ("\n".join(lines) + "\n").encode()


def render_target_default(
    target_default: Path,
    old_default: dict[str, str],
    old_environment: dict[str, str],
) -> bytes:
    """Preserva no contrato 1.3 os parâmetros locais efetivos da instalação 1.2."""
    source_values = {**old_environment, **old_default}
    mapped = {
        name: source_values[name]
        for name in LOCAL_DEFAULT_KEYS
        if source_values.get(name)
    }
    if "VOL_SEIIA_DIR" not in mapped:
        raise MigrationError("VOL_SEIIA_DIR ausente na origem 1.2")

    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in target_default.read_text(encoding="utf-8").splitlines():
        match = ENV_ASSIGNMENT.match(raw_line.strip())
        if match and match.group("name") in mapped:
            name = match.group("name")
            lines.append(f"{name}={_format_env_value(mapped[name], name=name)}")
            seen.add(name)
        else:
            lines.append(raw_line)

    missing = sorted(set(mapped) - seen)
    if missing:
        raise MigrationError(
            "parâmetros locais ausentes no default.env 1.3: " + ", ".join(missing)
        )
    return ("\n".join(lines) + "\n").encode()


def parse_litellm_models(path: Path) -> dict[str, dict[str, str]]:
    """Lê o subconjunto do YAML 1.2 necessário à migração, sem executá-lo."""
    if not path.is_file():
        raise MigrationError(f"arquivo obrigatório ausente: {path}")

    models: dict[str, dict[str, str]] = {}
    current: str | None = None
    params_indent: int | None = None
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        content = raw_line.strip()
        model_match = re.fullmatch(r"-\s*model_name:\s*(.+)", content)
        if model_match:
            current = _parse_scalar(
                model_match.group(1), location=f"{path}:{line_number}"
            )
            if current in models:
                raise MigrationError(f"alias LiteLLM duplicado: {current}")
            models[current] = {}
            params_indent = None
            continue
        if current is None:
            continue
        if content == "litellm_params:":
            params_indent = indent
            continue
        if params_indent is None or indent <= params_indent:
            continue
        parameter_match = re.fullmatch(
            r"(model|api_base|api_key|api_version|max_completion_tokens):\s*(.*)",
            content,
        )
        if parameter_match:
            name, raw_value = parameter_match.groups()
            models[current][name] = _parse_scalar(
                raw_value, location=f"{path}:{line_number}"
            )

    required_aliases = {"standard", "mini", "think", "embedding"}
    missing_aliases = sorted(required_aliases - set(models))
    if missing_aliases:
        raise MigrationError(
            "aliases obrigatórios ausentes no LiteLLM 1.2: "
            + ", ".join(missing_aliases)
        )
    for alias in required_aliases:
        missing_params = sorted({"model", "api_base", "api_key"} - set(models[alias]))
        if missing_params:
            raise MigrationError(
                f"parâmetros ausentes no alias {alias}: {', '.join(missing_params)}"
            )
    return models


def _provider_value(
    models: dict[str, dict[str, str]],
    source_alias: str | None,
    parameter: str,
    target_name: str,
    overrides: dict[str, str],
) -> str:
    if target_name in overrides:
        return overrides[target_name]
    if source_alias is None:
        return ""
    return models[source_alias].get(parameter, "")


def build_target_values(
    contract_names: list[str],
    old_security: dict[str, str],
    models: dict[str, dict[str, str]],
    overrides: dict[str, str],
) -> dict[str, str]:
    contract = set(contract_names)
    extra_overrides = sorted(set(overrides) - contract)
    if extra_overrides:
        raise MigrationError(
            "variáveis extras no arquivo de overrides: " + ", ".join(extra_overrides)
        )
    standard_source_alias: str | None = "standard"
    if models["standard"]["model"] != models["think"]["model"]:
        selected_standard = overrides.get("LITELLM_STANDARD_MODEL")
        if not selected_standard:
            raise MigrationError(
                "conflito não migrável entre os modelos standard e think da 1.2; "
                "informe LITELLM_STANDARD_MODEL no arquivo de overrides"
            )
        if selected_standard == models["standard"]["model"]:
            standard_source_alias = "standard"
        elif selected_standard == models["think"]["model"]:
            standard_source_alias = "think"
        else:
            standard_source_alias = None

    values = {name: old_security.get(name, "") for name in DIRECT_KEYS & contract}
    values["AIRFLOW_POSTGRES_DB"] = old_security.get("AIRFLOW_POSTGRES_DB", "airflow")
    values["LITELLM_PROXY_API_KEY"] = old_security.get(
        "LITELLM_PROXY_API_KEY",
        old_security.get("ASSISTENTE_LITELLM_PROXY_API_KEY", ""),
    )
    values.update(
        {
            "LITELLM_STANDARD_MODEL": overrides.get(
                "LITELLM_STANDARD_MODEL", models["standard"]["model"]
            ),
            "LITELLM_MINI_MODEL": models["mini"]["model"],
            "LITELLM_NANO_MODEL": overrides.get("LITELLM_NANO_MODEL", ""),
            "LITELLM_STANDARD_API_BASE": _provider_value(
                models,
                standard_source_alias,
                "api_base",
                "LITELLM_STANDARD_API_BASE",
                overrides,
            ),
            "LITELLM_STANDARD_API_KEY": _provider_value(
                models,
                standard_source_alias,
                "api_key",
                "LITELLM_STANDARD_API_KEY",
                overrides,
            ),
            "LITELLM_STANDARD_API_VERSION": _provider_value(
                models,
                standard_source_alias,
                "api_version",
                "LITELLM_STANDARD_API_VERSION",
                overrides,
            ),
            "LITELLM_MINI_API_BASE": _provider_value(
                models, "mini", "api_base", "LITELLM_MINI_API_BASE", overrides
            ),
            "LITELLM_MINI_API_KEY": _provider_value(
                models, "mini", "api_key", "LITELLM_MINI_API_KEY", overrides
            ),
            "LITELLM_MINI_API_VERSION": _provider_value(
                models,
                "mini",
                "api_version",
                "LITELLM_MINI_API_VERSION",
                overrides,
            ),
            "LITELLM_NANO_API_BASE": _provider_value(
                models, None, "api_base", "LITELLM_NANO_API_BASE", overrides
            ),
            "LITELLM_NANO_API_KEY": _provider_value(
                models, None, "api_key", "LITELLM_NANO_API_KEY", overrides
            ),
            "LITELLM_NANO_API_VERSION": _provider_value(
                models, None, "api_version", "LITELLM_NANO_API_VERSION", overrides
            ),
            "LITELLM_EMBEDDING_MODEL": models["embedding"]["model"],
            "LITELLM_EMBEDDING_API_BASE": models["embedding"]["api_base"],
            "LITELLM_EMBEDDING_API_KEY": models["embedding"]["api_key"],
            "LITELLM_EMBEDDING_API_VERSION": models["embedding"].get("api_version", ""),
            "SEIIA_CERT_DNS": "",
            "SEARXNG_SECRET_KEY": "",
        }
    )
    values.update(overrides)

    missing_names = sorted(contract - set(values))
    extra_names = sorted(set(values) - contract)
    if missing_names or extra_names:
        details: list[str] = []
        if missing_names:
            details.append("ausentes: " + ", ".join(missing_names))
        if extra_names:
            details.append("extras: " + ", ".join(extra_names))
        raise MigrationError("contrato 1.3 incompleto (" + "; ".join(details) + ")")

    empty_required = sorted(
        name
        for name, value in values.items()
        if not value and name not in OPTIONAL_EMPTY
    )
    if empty_required:
        raise MigrationError(
            "variáveis 1.3 obrigatórias sem valor: " + ", ".join(empty_required)
        )
    return {name: values[name] for name in contract_names}


def _run_openssl(arguments: list[str], *, input_bytes: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            ["openssl", *arguments],
            input=input_bytes,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise MigrationError("openssl não está instalado") from error
    if result.returncode != 0:
        raise MigrationError("par TLS 1.2 inválido")
    return result.stdout


def validate_certificate_pair(
    cert_file: Path, key_file: Path, gateway_host: str
) -> str:
    if not cert_file.is_file() or not key_file.is_file():
        raise MigrationError("par TLS 1.2 incompleto")
    _run_openssl(["x509", "-in", str(cert_file), "-checkend", "0", "-noout"])
    certificate_public_key = _run_openssl(
        ["x509", "-in", str(cert_file), "-pubkey", "-noout"]
    )
    certificate_der = _run_openssl(
        ["pkey", "-pubin", "-outform", "DER"], input_bytes=certificate_public_key
    )
    key_der = _run_openssl(["pkey", "-in", str(key_file), "-pubout", "-outform", "DER"])
    if certificate_der != key_der:
        raise MigrationError("certificado e chave TLS 1.2 não correspondem")

    san = _run_openssl(
        ["x509", "-in", str(cert_file), "-noout", "-ext", "subjectAltName"]
    ).decode(errors="replace")
    dns_names = set(re.findall(r"DNS:([^,\s]+)", san))
    if gateway_host not in dns_names:
        raise MigrationError(
            f"certificado 1.2 não contém SEIIA_GATEWAY_HOST no SAN: {gateway_host}"
        )
    certificate_der = _run_openssl(["x509", "-in", str(cert_file), "-outform", "DER"])
    return ":".join(f"{byte:02X}" for byte in hashlib.sha256(certificate_der).digest())


def _require_private(path: Path) -> None:
    if not path.is_file():
        raise MigrationError(f"arquivo obrigatório ausente: {path}")
    if path.stat().st_mode & 0o077:
        raise MigrationError(f"arquivo privado deve usar modo 0600: {path}")


def _require_private_key(path: Path) -> None:
    if not path.is_file():
        raise MigrationError(f"arquivo obrigatório ausente: {path}")
    if path.stat().st_mode & 0o037:
        raise MigrationError(
            "chave TLS não pode permitir escrita/execução ao grupo nem acesso a "
            f"outros usuários: {path}"
        )


def _contract_names(template: Path) -> list[str]:
    names = list(read_env_file(template).keys())
    if not names:
        raise MigrationError("security_example.env 1.3 não contém variáveis")
    return names


def _target_status(files: tuple[PlannedFile, ...]) -> str:
    any_missing_or_mode_drift = False
    for planned in files:
        if not planned.path.exists():
            any_missing_or_mode_drift = True
            continue
        if not planned.path.is_file():
            raise MigrationError(f"conflito no destino: {planned.path}")
        if planned.path.read_bytes() != planned.content:
            if planned.allow_existing_update:
                any_missing_or_mode_drift = True
                continue
            raise MigrationError(f"arquivo de destino divergente: {planned.path}")
        if planned.path.stat().st_mode & 0o777 != planned.mode:
            any_missing_or_mode_drift = True
    return "ready" if any_missing_or_mode_drift else "already-migrated"


def build_plan(
    source_dir: Path,
    deploy_dir: Path,
    overrides_path: Path,
    old_certs_dir: Path,
) -> MigrationPlan:
    required_target_files = (
        deploy_dir / "default.env",
        deploy_dir / "security_example.env",
        deploy_dir / "litellm_config.template.yaml",
    )
    for path in required_target_files:
        if not path.is_file():
            raise MigrationError(f"destino não é um deploy 1.3 válido; ausente: {path}")

    old_default = read_env_file(source_dir / "env_files/default.env")
    source_version = old_default.get("TAG_ESCAPED", "")
    if not SOURCE_VERSION.match(source_version):
        raise MigrationError(
            "origem não identificada como Servidor SEI IA 1.2.x "
            "(TAG_ESCAPED ausente ou incompatível)"
        )
    old_environment = read_env_file(source_dir / "env_files/prod.env")
    rendered_default = render_target_default(
        deploy_dir / "default.env", old_default, old_environment
    )

    old_security_path = source_dir / "env_files/security.env"
    old_litellm_path = source_dir / "llm_config/litellm_config.yaml"
    _require_private(old_security_path)
    _require_private(old_litellm_path)
    _require_private(overrides_path)
    _require_private_key(old_certs_dir / "seiia.cert.key")

    old_security = read_env_file(old_security_path)
    overrides = read_env_file(overrides_path)
    models = parse_litellm_models(old_litellm_path)
    security_template = deploy_dir / "security_example.env"
    contract_names = _contract_names(security_template)
    values = build_target_values(contract_names, old_security, models, overrides)

    cert_file = old_certs_dir / "seiia.cert.pem"
    key_file = old_certs_dir / "seiia.cert.key"
    fingerprint = validate_certificate_pair(
        cert_file, key_file, values["SEIIA_GATEWAY_HOST"]
    )
    files = (
        PlannedFile(
            deploy_dir / "default.env",
            rendered_default,
            0o644,
            allow_existing_update=True,
        ),
        PlannedFile(
            deploy_dir / "security.env",
            render_security_template(security_template, values),
            0o600,
        ),
        PlannedFile(
            deploy_dir / "litellm_config.yaml",
            (deploy_dir / "litellm_config.template.yaml").read_bytes(),
            0o600,
        ),
        PlannedFile(
            deploy_dir / ".runtime/certs/seiia.cert.pem",
            cert_file.read_bytes(),
            0o644,
        ),
        PlannedFile(
            deploy_dir / ".runtime/certs/seiia.cert.key",
            key_file.read_bytes(),
            0o600,
        ),
    )
    return MigrationPlan(files, fingerprint, _target_status(files))


def _write_atomic(planned: PlannedFile) -> None:
    planned.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=planned.path.parent, prefix=f".{planned.path.name}.migration-"
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(planned.content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(planned.mode)
        os.replace(temporary_path, planned.path)
    finally:
        temporary_path.unlink(missing_ok=True)


def apply_plan(plan: MigrationPlan) -> None:
    for planned in plan.files:
        if (
            planned.path.is_file()
            and planned.path.read_bytes() == planned.content
            and planned.path.stat().st_mode & 0o777 == planned.mode
        ):
            continue
        _write_atomic(planned)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migra configuração e TLS do Servidor SEI IA 1.2.x para 1.3.x."
    )
    parser.add_argument(
        "--source-dir", required=True, type=Path, help="Raiz preservada do deploy 1.2."
    )
    parser.add_argument(
        "--deploy-dir", default=Path.cwd(), type=Path, help="Raiz limpa do deploy 1.3."
    )
    parser.add_argument(
        "--overrides",
        required=True,
        type=Path,
        help="Arquivo 0600 com valores 1.3 sem equivalente inequívoco na 1.2.",
    )
    parser.add_argument(
        "--old-certs-dir",
        required=True,
        type=Path,
        help="Diretório 1.2 com seiia.cert.pem e seiia.cert.key.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        "--dry-run",
        dest="check_only",
        action="store_true",
        help="Valida tudo sem escrever nem parar serviços.",
    )
    mode.add_argument(
        "--apply", action="store_true", help="Grava somente os artefatos validados."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = build_plan(
            args.source_dir.resolve(),
            args.deploy_dir.resolve(),
            args.overrides.resolve(),
            args.old_certs_dir.resolve(),
        )
        print("SOURCE_VERSION=1.2.x")
        print("TARGET_VERSION=1.3.x")
        print(f"CERTIFICATE_SHA256={plan.certificate_fingerprint}")
        if args.apply and plan.status != "already-migrated":
            apply_plan(plan)
            print("MIGRATION_STATUS=applied")
        else:
            print(f"MIGRATION_STATUS={plan.status}")
        return 0
    except MigrationError as error:
        print(f"ERRO: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
