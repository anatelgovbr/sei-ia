"""Entrypoint único do benchmark Session redesenhado."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
EXPERIMENT_ROOT = HERE.parent
APP_ROOT = EXPERIMENT_ROOT.parents[1]
WORKTREE_ROOT = APP_ROOT.parents[1]
SESSION_RUNNER = EXPERIMENT_ROOT / "scripts/session-classico/run_experiment.py"
CONFIG_PATH = HERE / "arms.json"

sys.path.insert(0, str(EXPERIMENT_ROOT / "scripts/shared"))
from model_campaign import load_model_campaign  # noqa: E402

REQUIRED_KEYS = {
    "SEI_ADDRESS",
    "SEI_API_DB_ADDRESS",
    "SEI_API_DB_USER",
    "SEI_API_DB_IDENTIFIER_SERVICE",
    "LITELLM_PROXY_API_KEY",
    "LANGFUSE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
}


class BenchmarkRedesignError(RuntimeError):
    """Contrato do benchmark redesenhado não foi satisfeito."""


def _usage_value(usage: dict[str, Any], path: str) -> int:
    value: Any = usage
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise BenchmarkRedesignError(f"campo de usage não observado: {path}")
        value = value[part]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BenchmarkRedesignError(f"contador de usage inválido: {path}")
    return value


def _normalize_cache_usage(usage: dict[str, Any], *, read_path: str) -> dict[str, Any]:
    """Normaliza o único efeito de cache cobrado e comparado: cache read."""
    return {
        "cache_read": _usage_value(usage, read_path),
        "provenance": {"cache_read": read_path},
    }


def _load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "benchmark-redesign-arms-1":
        raise BenchmarkRedesignError("schema_version de arms.json inválida")
    if config.get("n") != 1:
        raise BenchmarkRedesignError("O benchmark suporta somente N=1")
    if not isinstance(config.get("arms"), dict) or set(config["arms"]) != {
        "gpt54",
        "terra-luna",
    }:
        raise BenchmarkRedesignError("arms.json deve conter exatamente dois braços")
    canary_qids = config.get("canary_qids")
    if (
        not isinstance(canary_qids, list)
        or len(canary_qids) != 3
        or len(set(canary_qids)) != 3
        or config.get("canary_qid") not in canary_qids
    ):
        raise BenchmarkRedesignError("arms.json deve declarar três canários distintos")
    return config


def _load_private_environment() -> dict[str, str]:
    values = {key: value for key, value in os.environ.items() if value}
    for path in (WORKTREE_ROOT / "security.env", APP_ROOT / ".env"):
        if not path.is_file():
            raise BenchmarkRedesignError(f"arquivo privado ausente: {path.name}")
        values.update(
            {key: value for key, value in dotenv_values(path).items() if value}
        )
    proxy_url = values.get("LITELLM_PROXY_URL") or values.get(
        "LITELLM_STANDARD_API_BASE"
    )
    if proxy_url:
        values["LITELLM_PROXY_URL"] = proxy_url
    missing = sorted(key for key in REQUIRED_KEYS if not values.get(key))
    if not values.get("LITELLM_PROXY_URL"):
        missing.append("LITELLM_PROXY_URL|LITELLM_STANDARD_API_BASE")
    if missing:
        raise BenchmarkRedesignError(
            "variáveis obrigatórias ausentes: " + ",".join(missing)
        )
    return values


def _arm(config: dict[str, Any], name: str) -> dict[str, Any]:
    arm = dict(config["arms"][name])
    rate_card = (HERE / arm["rate_card"]).resolve(strict=True)
    try:
        campaign = load_model_campaign(
            standard_model=arm["standard_model"],
            mini_model=arm["mini_model"],
            nano_model=arm["nano_model"],
            reasoning_effort=arm.get("reasoning_effort"),
            n=config["n"],
            rate_card_path=rate_card,
            reuse_historical_baseline=False,
        )
    except (KeyError, OSError, ValueError) as exc:
        raise BenchmarkRedesignError(
            f"arm incompatível com a rate card: {name}"
        ) from exc
    arm["rate_card"] = str(rate_card)
    arm["rate_card_sha256"] = campaign.rate_card_sha256
    arm["rate_card_compatibility_key"] = campaign.rate_card.get(
        "aggregation_compatibility_key"
    )
    arm["provider"] = campaign.mini.provider
    return arm


def _cache_gate(
    path: Path | None, *, arm_name: str, arm: dict[str, Any]
) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"status": "blocked", "reason": "cache_read_proof_missing"}
    proof = json.loads(path.read_text(encoding="utf-8"))
    required = {"provider_raw", "litellm", "langfuse", "normalizer"}
    campaign = {
        "arm": arm_name,
        "aliases": {
            key: arm[key] for key in ("standard_model", "mini_model", "nano_model")
        },
        "rate_card": {
            "sha256": arm["rate_card_sha256"],
            "aggregation_compatibility_key": arm["rate_card_compatibility_key"],
        },
        "provider": arm["provider"],
    }
    reason = None
    if proof.get("status") != "passed" or set(proof.get("boundaries", {})) != required:
        reason = "cache_read_proof_invalid"
    elif any(
        boundary.get("status") != "passed" for boundary in proof["boundaries"].values()
    ):
        reason = "cache_boundary_not_reconciled"
    observed_campaign = proof.get("campaign")
    if reason is None and observed_campaign != campaign:
        reason = "cache_proof_campaign_mismatch"
    if reason is None and proof.get("provider") != campaign["provider"]:
        reason = "cache_proof_provider_missing"
    if reason is None and (
        not isinstance(proof.get("trace_id"), str) or not proof["trace_id"]
    ):
        reason = "cache_proof_trace_missing"
    provenance = proof.get("provenance")
    if reason is None and (
        not isinstance(provenance, dict)
        or any(
            not isinstance(provenance.get(key), str) or not provenance[key]
            for key in (*required, "cache_read")
        )
    ):
        reason = "cache_proof_provenance_missing"
    read = proof.get("read")
    if reason is None and (
        not isinstance(read, dict)
        or not isinstance(read.get("cache_read"), int)
        or read["cache_read"] <= 0
    ):
        reason = "cache_read_not_observed"
    if reason is not None:
        return {"status": "blocked", "reason": reason}
    return {
        "status": "passed",
        "proof": str(path.resolve()),
        "campaign": campaign,
        "provider": proof["provider"],
        "trace_id": proof["trace_id"],
        "provenance": proof["provenance"],
    }


def build_preflight(*, arm_name: str, cache_proof: Path | None) -> dict[str, Any]:
    config = _load_config()
    arm = _arm(config, arm_name)
    _load_private_environment()
    cache = _cache_gate(cache_proof, arm_name=arm_name, arm=arm)
    return {
        "schema_version": "benchmark-redesign-preflight-1",
        "status": "passed" if cache["status"] == "passed" else "blocked",
        "arm": arm_name,
        "n": config["n"],
        "canary_qid": config["canary_qid"],
        "canary_qids": config["canary_qids"],
        "model_configuration": {
            key: arm[key]
            for key in (
                "standard_model",
                "mini_model",
                "nano_model",
                "reasoning_effort",
                "rate_card",
                "rate_card_sha256",
                "rate_card_compatibility_key",
            )
        },
        "credentials": {"status": "present", "values_exposed": False},
        "cache_gate": cache,
        "inference_attempted": False,
    }


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)


def _runner_command(
    *,
    arm_name: str,
    run_name: str,
    artifacts_dir: Path,
    canary_qid: str | None,
) -> tuple[list[str], dict[str, str]]:
    config = _load_config()
    arm = _arm(config, arm_name)
    env = _load_private_environment()
    env.update(
        {
            "EXP_TRANSPORT": "http",
            "EXP_APP_BASE": "https://127.0.0.1:8188",
        }
    )
    command = [
        sys.executable,
        str(SESSION_RUNNER),
        "--decision-suite",
        "--run-name",
        run_name,
        "--artifacts-dir",
        str(artifacts_dir),
        "--endpoints",
        "session",
        "--no-warmup",
        "--standard-model",
        arm["standard_model"],
        "--mini-model",
        arm["mini_model"],
        "--nano-model",
        arm["nano_model"],
        "--reasoning-effort",
        arm["reasoning_effort"],
        "--n",
        "1",
        "--reuse-historical-baseline",
        "--rate-card",
        arm["rate_card"],
    ]
    if canary_qid is not None:
        if canary_qid not in config["canary_qids"]:
            raise BenchmarkRedesignError("QID não pertence aos três canários fixos")
        command[3:3] = ["--only", canary_qid, "--canary"]
    return command, env


def _canary_command(
    *,
    arm_name: str,
    run_name: str,
    artifacts_dir: Path,
    canary_qid: str | None = None,
) -> tuple[list[str], dict[str, str]]:
    config = _load_config()
    return _runner_command(
        arm_name=arm_name,
        run_name=run_name,
        artifacts_dir=artifacts_dir,
        canary_qid=canary_qid or config["canary_qid"],
    )


def _battery_command(
    *, arm_name: str, run_name: str, artifacts_dir: Path
) -> tuple[list[str], dict[str, str]]:
    return _runner_command(
        arm_name=arm_name,
        run_name=run_name,
        artifacts_dir=artifacts_dir,
        canary_qid=None,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "canary", "battery"):
        command = sub.add_parser(name)
        command.add_argument("--arm", choices=("gpt54", "terra-luna"), required=True)
        command.add_argument("--cache-proof", type=Path)
    preflight = sub.choices["preflight"]
    preflight.add_argument("--output", type=Path, required=True)
    canary = sub.choices["canary"]
    canary.add_argument("--run-name", required=True)
    canary.add_argument("--artifacts-dir", type=Path, required=True)
    canary.add_argument("--qid")
    battery = sub.choices["battery"]
    battery.add_argument("--run-name", required=True)
    battery.add_argument("--artifacts-dir", type=Path, required=True)
    args = parser.parse_args()

    proof = build_preflight(arm_name=args.arm, cache_proof=args.cache_proof)
    if args.command == "preflight":
        _write_private_json(args.output, proof)
        print(json.dumps(proof, ensure_ascii=False))
        return 0 if proof["status"] == "passed" else 2
    if proof["status"] != "passed":
        raise BenchmarkRedesignError(
            "canário bloqueado: prova reconciliada de cache read ausente"
        )
    if args.command == "canary":
        command, env = _canary_command(
            arm_name=args.arm,
            run_name=args.run_name,
            artifacts_dir=args.artifacts_dir,
            canary_qid=args.qid,
        )
    else:
        command, env = _battery_command(
            arm_name=args.arm,
            run_name=args.run_name,
            artifacts_dir=args.artifacts_dir,
        )
    subprocess.run(command, check=True, env=env)  # noqa: S603
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
