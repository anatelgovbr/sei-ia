"""Validação fail-closed do launcher Compose isolado."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

_EXP_DIR = Path(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "experimentos",
        "latencia-session-vs-classico",
    )
)
sys.path.insert(0, str(_EXP_DIR / "scripts" / "shared"))

import isolated_compose as launcher  # noqa: E402
from isolated_compose import (  # noqa: E402
    EVIDENCE_SETTING,
    LONG_CONTEXT_WORKLOAD,
    SESSION_WORKLOAD,
    _compose_command,
    _load_environment,
    sanitized_environment,
    validate_rendered_config,
)


def test_contaminated_shell_is_overridden_by_dedicated_stack():
    env = sanitized_environment(
        {
            "ASSISTENTE_PORT": "8088",
            "COMPOSE_NETWORK_NAME": "docker-host-bridge",
            "COMPOSE_PROJECT_NAME": "shared-project",
        }
    )

    assert env["ASSISTENTE_PORT"] == "8188"
    assert env["COMPOSE_NETWORK_NAME"] == "seiia-bench-rerun-net"
    assert env["COMPOSE_PROJECT_NAME"] == "seiia-bench-rerun"


def test_session_environment_scrubs_long_context_evidence_pins():
    env = sanitized_environment(
        {
            "BENCHMARK_EVIDENCE_INDEX": "/stale/long-context-index.json",
            "ASSISTENTE_SESSION_BENCHMARK_EVIDENCE_INDEX": (
                "/stale/effective-index.json"
            ),
        }
    )

    assert "BENCHMARK_EVIDENCE_INDEX" not in env
    assert "ASSISTENTE_SESSION_BENCHMARK_EVIDENCE_INDEX" not in env


def test_compose_overlay_applies_evidence_pin_only_to_long_context():
    args = SimpleNamespace(
        default_env=Path("default.env"),
        isolated_env=Path("isolated.env"),
        security_env=Path("security.env"),
        root=Path("repo"),
        compose_file=Path("isolated.yml"),
        long_context_compose_file=Path("long-context.yml"),
        workload=SESSION_WORKLOAD,
    )

    session_command = _compose_command(args, "config")
    args.workload = LONG_CONTEXT_WORKLOAD
    long_context_command = _compose_command(args, "config")

    assert str(args.long_context_compose_file) not in session_command
    assert str(args.long_context_compose_file) in long_context_command


def test_render_validator_enforces_workload_specific_evidence_pin():
    rendered = {
        "services": {
            "assistente": {"environment": {EVIDENCE_SETTING: "/protected/index"}},
            "assistente-nginx": {},
        }
    }

    session_errors = validate_rendered_config(rendered, workload=SESSION_WORKLOAD)
    long_context_errors = validate_rendered_config(
        rendered, workload=LONG_CONTEXT_WORKLOAD
    )
    rendered["services"]["assistente"]["environment"] = {}
    missing_long_context_errors = validate_rendered_config(
        rendered, workload=LONG_CONTEXT_WORKLOAD
    )

    assert "Session não pode carregar pin de evidence Long Context" in session_errors
    assert "Long Context exige pin de evidence protegido" not in long_context_errors
    assert "Long Context exige pin de evidence protegido" in missing_long_context_errors


def test_render_validator_rejects_shared_port_or_network():
    rendered = {
        "name": "seiia-bench-rerun",
        "services": {
            "assistente-nginx": {
                "ports": [{"published": "8088", "target": 443}],
                "networks": {"docker-host-bridge": None},
            }
        },
        "networks": {"docker-host-bridge": {"external": True}},
        "volumes": {},
    }

    errors = validate_rendered_config(rendered)

    assert any("8188" in error for error in errors)
    assert any("docker-host-bridge" in error for error in errors)


def test_render_validator_requires_nginx_on_dedicated_gateway_network():
    rendered = {
        "name": "seiia-bench-rerun",
        "services": {
            "assistente-nginx": {
                "image": "nginx:test",
                "ports": [{"published": "8188", "target": 443}],
                "networks": {"benchmark_assistente_frontend": None},
            }
        },
        "networks": {
            "seiia": {"name": "seiia-bench-rerun-net", "external": True},
            "benchmark_assistente_frontend": {"internal": True},
        },
        "volumes": {},
    }

    errors = validate_rendered_config(rendered)

    assert any("gateway dedicado" in error for error in errors)


def test_render_validator_rejects_central_gateway_inheritance():
    rendered = {
        "name": "seiia-bench-rerun",
        "services": {
            "gateway-nginx": {"ports": [{"published": "8088", "target": 8088}]},
            "assistente-nginx": {
                "image": "nginx:1.27-alpine3.19-perl",
                "depends_on": {
                    "assistente": {"condition": "service_healthy"},
                    "similaridade": {"condition": "service_healthy"},
                },
                "ports": [{"published": "8188", "target": 443}],
                "networks": {
                    "seiia": None,
                    "benchmark_assistente_frontend": None,
                },
                "volumes": [],
            },
        },
        "networks": {
            "seiia": {"name": "seiia-bench-rerun-net", "external": True},
            "benchmark_assistente_frontend": {"internal": True},
        },
        "volumes": {},
    }

    errors = validate_rendered_config(rendered)

    assert any("gateway central" in error for error in errors)
    assert any("depender somente do assistente" in error for error in errors)


def test_render_validator_requires_official_nginx_config_and_certificate_mounts():
    rendered = {
        "name": "seiia-bench-rerun",
        "services": {
            "assistente-nginx": {
                "image": "seiia-bench-1428/assistente-nginx:local",
                "depends_on": {"assistente": {"condition": "service_healthy"}},
                "ports": [{"published": "8188", "target": 443}],
                "networks": {
                    "seiia": None,
                    "benchmark_assistente_frontend": None,
                },
                "volumes": [],
            }
        },
        "networks": {
            "seiia": {"name": "seiia-bench-rerun-net", "external": True},
            "benchmark_assistente_frontend": {"internal": True},
        },
        "volumes": {},
    }

    errors = validate_rendered_config(rendered)

    assert any("imagem oficial" in error for error in errors)
    assert any("configuração/certificado" in error for error in errors)


def test_searx_secret_is_ephemeral_when_private_file_omits_it(tmp_path):
    default = tmp_path / "default.env"
    isolated = tmp_path / "isolated.env"
    security = tmp_path / "security.env"
    default.write_text("A=1\n")
    isolated.write_text("SEARXNG_SECRET_KEY=benchmark-placeholder-not-a-secret\n")
    security.write_text(
        "LITELLM_STANDARD_API_BASE=https://pd02.example.test\n"
        "LITELLM_STANDARD_API_KEY=private-placeholder\n"
    )
    security.chmod(0o600)

    env = _load_environment(
        default_env=default,
        isolated_env=isolated,
        security_env=security,
    )

    assert env["SEARXNG_SECRET_KEY"] != "benchmark-placeholder-not-a-secret"
    assert len(env["SEARXNG_SECRET_KEY"]) >= 32


def test_proxy_transversal_mapeia_base_standard_aprovada(tmp_path):
    default = tmp_path / "default.env"
    isolated = tmp_path / "isolated.env"
    security = tmp_path / "security.env"
    default.write_text("A=1\n")
    isolated.write_text("SEARXNG_SECRET_KEY=benchmark-placeholder-not-a-secret\n")
    security.write_text(
        "LITELLM_STANDARD_API_BASE=https://pd02.example.test\n"
        "LITELLM_STANDARD_API_KEY=private-placeholder\n"
    )
    security.chmod(0o600)

    env = _load_environment(
        default_env=default,
        isolated_env=isolated,
        security_env=security,
    )

    assert env["LITELLM_PROXY_URL"] == "https://pd02.example.test"
    assert env["LITELLM_PROXY_API_KEY"] == "private-placeholder"


def test_launcher_resolves_all_model_aliases_from_arm(tmp_path):
    arms = tmp_path / "arms.json"
    arms.write_text(
        json.dumps(
            {
                "arms": {
                    "terra-luna": {
                        "standard_model": "seiia-ds-gpt-terra",
                        "mini_model": "seiia-ds-gpt-luna",
                        "nano_model": "seiia-ds-gpt-luna",
                        "reasoning_effort": "low",
                        "rate_card": str(
                            _EXP_DIR / "rate_cards/benchmark-redesign-v2.json"
                        ),
                    }
                },
                "n": 1,
            }
        )
    )

    models = launcher.load_arm_models(arms, "terra-luna")

    assert models == {
        "standard_model": "seiia-ds-gpt-terra",
        "mini_model": "seiia-ds-gpt-luna",
        "nano_model": "seiia-ds-gpt-luna",
    }


def test_launcher_rejects_alias_with_wrong_profile(tmp_path):
    arms = tmp_path / "arms.json"
    arms.write_text(
        json.dumps(
            {
                "n": 1,
                "arms": {
                    "bad": {
                        "standard_model": "seiia-ds-gpt-luna",
                        "mini_model": "seiia-ds-gpt-luna",
                        "nano_model": "seiia-ds-gpt-luna",
                        "reasoning_effort": "low",
                        "rate_card": str(
                            _EXP_DIR / "rate_cards/benchmark-redesign-v2.json"
                        ),
                    }
                },
            }
        )
    )

    try:
        launcher.load_arm_models(arms, "bad")
    except launcher.IsolatedComposeError as exc:
        assert "incompatível" in str(exc)
    else:
        raise AssertionError("arm inválido foi aceito")
