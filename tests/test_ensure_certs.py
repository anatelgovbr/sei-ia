"""Testes do gerador de certificado TLS no host (ops/scripts/ensure_certs.sh).

Cobrem o que importa para a integração com o SEI: o hostname do gateway e os
nomes adicionais entram no SAN, a geração gerenciada é idempotente e um par
fornecido pelo operador nunca é sobrescrito silenciosamente.

Pulam quando openssl/bash não estão no runner (o gerador exige ambos).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "ops/scripts/ensure_certs.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("openssl") is None or shutil.which("bash") is None,
    reason="openssl/bash ausentes no runner",
)


def _run(
    root: Path,
    cert_dns: str | None = None,
    gateway_host: str = "seiia",
) -> None:
    env = {"PATH": os.environ["PATH"]}
    env["SEIIA_GATEWAY_HOST"] = gateway_host
    if cert_dns is not None:
        env["SEIIA_CERT_DNS"] = cert_dns
    subprocess.run(
        ["bash", str(SCRIPT), str(root)], env=env, check=True, capture_output=True
    )


def _extra_dns(san: str) -> list[str]:
    return [
        name
        for name in re.findall(r"DNS:([^,\s]+)", san)
        if name not in ("seiia", "localhost")
    ]


def _san(root: Path) -> str:
    out = subprocess.run(
        [
            "openssl",
            "x509",
            "-in",
            str(root / ".runtime/certs/seiia.cert.pem"),
            "-noout",
            "-ext",
            "subjectAltName",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout


def _fingerprint(root: Path) -> str:
    out = subprocess.run(
        [
            "openssl",
            "x509",
            "-in",
            str(root / ".runtime/certs/seiia.cert.pem"),
            "-noout",
            "-fingerprint",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout


def _create_operator_certificate(root: Path, san: str) -> None:
    certs = root / ".runtime/certs"
    certs.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "30",
            "-keyout",
            str(certs / "seiia.cert.key"),
            "-out",
            str(certs / "seiia.cert.pem"),
            "-subj",
            "/CN=gateway.exemplo.gov.br",
            "-addext",
            f"subjectAltName={san}",
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "default.env").write_text('NB_USER="seiia"\n')
    return tmp_path


def test_dns_entra_no_san(repo: Path):
    _run(repo, "seiia.exemplo.gov.br")
    san = _san(repo)
    assert "DNS:seiia.exemplo.gov.br" in san
    assert "DNS:seiia" in san
    assert "IP Address:127.0.0.1" in san


def test_hostname_do_gateway_entra_no_san(repo: Path):
    _run(repo, gateway_host="gateway.exemplo.gov.br")
    assert "DNS:gateway.exemplo.gov.br" in _san(repo)


def test_idempotente_mesmo_dns(repo: Path):
    _run(repo, "seiia.exemplo.gov.br")
    fp1 = _fingerprint(repo)
    _run(repo, "seiia.exemplo.gov.br")
    assert _fingerprint(repo) == fp1, "nao deveria rotacionar com o mesmo nome DNS"


def test_regenera_ao_trocar_dns(repo: Path):
    _run(repo, "seiia.exemplo.gov.br")
    fp1 = _fingerprint(repo)
    _run(repo, "outro.exemplo.gov.br")
    assert _fingerprint(repo) != fp1
    assert "DNS:outro.exemplo.gov.br" in _san(repo)


def test_sem_dns_san_base(repo: Path):
    _run(repo)
    san = _san(repo)
    assert "DNS:seiia" in san
    assert "IP Address:127.0.0.1" in san
    assert _extra_dns(san) == []


def test_dns_invalido_interrompe_geracao(repo: Path):
    with pytest.raises(subprocess.CalledProcessError):
        _run(repo, "nome_invalido")  # underscore nao e valido em nome DNS

    assert not (repo / ".runtime/certs/seiia.cert.pem").exists()


def test_hostname_do_gateway_e_obrigatorio(repo: Path):
    with pytest.raises(subprocess.CalledProcessError):
        _run(repo, gateway_host="")


def test_certificado_do_operador_valido_e_preservado(repo: Path):
    _create_operator_certificate(repo, "DNS:gateway.exemplo.gov.br")
    fp1 = _fingerprint(repo)

    _run(repo, gateway_host="gateway.exemplo.gov.br")

    assert _fingerprint(repo) == fp1
    assert not (repo / ".runtime/certs/.generated-by-sei-ia").exists()


def test_certificado_do_operador_com_san_incorreto_nao_e_sobrescrito(repo: Path):
    _create_operator_certificate(repo, "DNS:outro.exemplo.gov.br")
    fp1 = _fingerprint(repo)

    with pytest.raises(subprocess.CalledProcessError):
        _run(repo, gateway_host="gateway.exemplo.gov.br")

    assert _fingerprint(repo) == fp1


def test_substituir_certificado_gerenciado_por_certificado_do_orgao_e_preservado(
    repo: Path,
):
    _run(repo, gateway_host="gateway.exemplo.gov.br")
    assert (repo / ".runtime/certs/.generated-by-sei-ia").is_file()
    _create_operator_certificate(repo, "DNS:gateway.exemplo.gov.br")
    operator_fingerprint = _fingerprint(repo)

    _run(repo, gateway_host="gateway.exemplo.gov.br")

    assert _fingerprint(repo) == operator_fingerprint


def test_multiplos_dns(repo: Path):
    _run(repo, "a.exemplo.gov.br,b.exemplo.gov.br")
    san = _san(repo)
    assert "DNS:a.exemplo.gov.br" in san
    assert "DNS:b.exemplo.gov.br" in san


def test_permissoes_restringem_chave_privada(repo: Path):
    _run(repo, "seiia.exemplo.gov.br")
    certs = repo / ".runtime/certs"

    assert certs.stat().st_mode & 0o777 == 0o700
    assert (certs / "seiia.cert.pem").stat().st_mode & 0o777 == 0o644
    assert (certs / "seiia.cert.key").stat().st_mode & 0o777 == 0o600
