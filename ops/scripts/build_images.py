#!/usr/bin/env python3
"""Constrói as imagens da stack com Bake e autorização explícita de rede host."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed


def _positive_integer(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("o paralelismo deve ser maior que zero")
    return number


def _read_json(command: list[str], input_text: str | None = None) -> dict:
    # O comando é fornecido pelo Makefile/operador e executado como argv, sem shell.
    result = subprocess.run(  # noqa: S603
        command, input=input_text, capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def _build_definition(config: dict, service_names: list[str]) -> dict:
    services = config["services"]
    if service_names:
        for name in service_names:
            if name not in services or "build" not in services[name]:
                raise ValueError(f"serviço sem build na composição ativa: {name}")
    else:
        service_names = [
            name for name, service in services.items() if "build" in service
        ]

    # O renderer do Compose resolve env files, profiles, paths e overrides. Somente
    # a configuração de build segue para Bake; credenciais de runtime ficam fora.
    definition = {"name": config["name"], "services": {}}
    for name in service_names:
        service = services[name]
        build_service = {
            "build": service["build"],
            "image": service.get("image") or f"{config['name']}-{name}",
        }
        # Bake também resolve argumentos sem valor pelo ambiente do serviço.
        inherited_args = {
            key: service["environment"][key]
            for key, value in service["build"].get("args", {}).items()
            if value is None and key in service.get("environment", {})
        }
        if inherited_args:
            build_service["environment"] = inherited_args
        definition["services"][name] = build_service

    required_secrets = {
        secret["source"]
        for service in definition["services"].values()
        for secret in service["build"].get("secrets", [])
    }
    if required_secrets:
        definition["secrets"] = {
            name: config["secrets"][name] for name in required_secrets
        }
    return definition


def _build_target(command: list[str], definition: str, target: str) -> int:
    print(f"INFO: Construindo imagem do serviço {target}.", flush=True)
    # O alvo vem da composição do operador; nenhum argumento passa por um shell.
    return subprocess.run(  # noqa: S603
        [*command, target], input=definition, text=True, check=False
    ).returncode


def main() -> int:
    """Renderiza a composição e limita a quantidade de builds em execução."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parallel", type=_positive_integer, default=3)
    parser.add_argument("--service", action="append", default=[])
    parser.add_argument("compose", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    compose = args.compose
    if compose and compose[0] == "--":
        compose = compose[1:]
    if "compose" not in compose or compose.index("compose") == 0:
        parser.error("informe o comando Docker Compose depois de --")

    docker = compose[: compose.index("compose")]
    bake = [*docker, "buildx", "bake", "--file", "-"]
    try:
        config = _read_json([*compose, "config", "--format", "json"])
        compose_builds = _build_definition(config, args.service)
        if not compose_builds["services"]:
            print("INFO: Nenhuma imagem para construir na composição ativa.")
            return 0
        # Bake lê Compose diretamente, preservando suas opções de build. O JSON
        # resultante fica somente em memória e é passado aos builds pelo stdin.
        definition = _read_json([*bake, "--print"], json.dumps(compose_builds))
        targets = definition["group"]["default"]["targets"]
        definition_text = json.dumps(definition)
        command = [*bake, "--allow=network.host", "--load"]
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(_build_target, command, definition_text, target): target
                for target in targets
            }
            for future in as_completed(futures):
                returncode = future.result()
                if returncode:
                    for pending in futures:
                        pending.cancel()
                    print(
                        f"ERRO: build de {futures[future]} terminou com código {returncode}.",
                        file=sys.stderr,
                    )
                    return 1
    except subprocess.CalledProcessError as error:
        if error.stderr:
            print(error.stderr, file=sys.stderr, end="")
        print(
            "ERRO: não foi possível preparar o build com Compose/Bake.", file=sys.stderr
        )
        return 1
    except (OSError, ValueError, KeyError) as error:
        print(f"ERRO: não foi possível preparar o build: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
